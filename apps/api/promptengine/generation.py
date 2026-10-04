from datetime import timedelta
from time import monotonic

from flask import Blueprint, current_app, g, jsonify, request

from .ai_provider import refine_with_openai, require_provider
from .compiler import count_tokens, local_compile, token_metrics, validate_input
from .entitlements import requires_entitlement
from .errors import APIError
from .extensions import db
from .models import GenerationMetric
from .presets import MODES, PRESET_VERSION, PRESETS, TONES
from .security import json_body, now, rate_limit, requires_auth

bp = Blueprint("generation", __name__, url_prefix="/api")


def checked_request():
    value = validate_input(json_body())
    model = current_app.config["OPENAI_MODEL"]
    # Check the token budget before quota reservation or calling a paid provider.
    total = count_tokens(value.raw_input, model) + sum(
        count_tokens(text, model) for text in value.fields.values()
    )
    if total > current_app.config["MAX_TASK_TOKENS"]:
        raise APIError("input_too_large", "Task and field values exceed the token limit", 413)
    return value


def successful_response(value, output, engine, user_id, start, provider=None):
    metrics = token_metrics(value.raw_input, output["prompt"], current_app.config["OPENAI_MODEL"])
    record = GenerationMetric(
        user_id=user_id,
        preset_id=value.preset,
        preset_version=PRESET_VERSION,
        engine=engine,
        mode=value.mode,
        tone=value.tone,
        model=provider.model if provider else current_app.config["OPENAI_MODEL"],
        tokenizer=metrics["tokenizer"],
        raw_tokens=metrics["raw_tokens"],
        generated_tokens=metrics["generated_tokens"],
        provider_input_tokens=provider.input_tokens if provider else None,
        provider_output_tokens=provider.output_tokens if provider else None,
        latency_ms=max(0, round((monotonic() - start) * 1000)),
    )
    db.session.add(record)
    db.session.commit()
    return jsonify(
        **output,
        generation_id=str(record.id),
        engine=engine,
        metrics=metrics,
        provider_usage={
            "input_tokens": record.provider_input_tokens,
            "output_tokens": record.provider_output_tokens,
            "model": provider.model if provider else None,
        },
        quota_reservation=g.get("ai_usage") if engine == "ai" else None,
    )


@bp.get("/presets")
def list_presets():
    return jsonify(
        version=PRESET_VERSION,
        presets=[preset.public() for preset in PRESETS.values()],
        tones=list(TONES),
        modes=list(MODES),
    )


@requires_entitlement
def execute_ai(value, user_id):
    start = monotonic()
    # The reservation is committed; no database lock is held during this network call.
    result = refine_with_openai(value)
    return successful_response(value, result.output, "ai", user_id, start, result)


@bp.post("/refine")
@requires_auth("refine")
def refine():
    value = checked_request()
    require_provider()  # Unconfigured service must not reserve quota.
    user_id = g.user.id
    rate_limit("refine", 20, identity=str(user_id))
    return execute_ai(value, user_id)


@bp.post("/compile")
@requires_auth("refine")
def compile_local():
    value = checked_request()
    user_id = g.user.id
    rate_limit("compile_local", 30, identity=str(user_id))
    start = monotonic()
    return successful_response(value, local_compile(value), "local", user_id, start)


@bp.get("/generation-metrics")
@requires_auth("usage:read")
def generation_metrics():
    try:
        days = int(request.args.get("days", "30"))
    except ValueError as exc:
        raise APIError("invalid_period", "days must be an integer from 1 to 365") from exc
    if not 1 <= days <= 365:
        raise APIError("invalid_period", "days must be an integer from 1 to 365")
    start = now() - timedelta(days=days)
    groups = (
        db.session.execute(
            db.select(
                GenerationMetric.engine,
                db.func.count().label("generations"),
                db.func.sum(GenerationMetric.raw_tokens).label("raw_tokens"),
                db.func.sum(GenerationMetric.generated_tokens).label("generated_tokens"),
                db.func.sum(GenerationMetric.token_difference).label("token_difference"),
                db.func.sum(GenerationMetric.provider_input_tokens).label("provider_input_tokens"),
                db.func.sum(GenerationMetric.provider_output_tokens).label(
                    "provider_output_tokens"
                ),
            )
            .where(GenerationMetric.user_id == g.user.id, GenerationMetric.created_at >= start)
            .group_by(GenerationMetric.engine)
            .order_by(GenerationMetric.engine)
        )
        .mappings()
        .all()
    )
    return jsonify(days=days, scope="plain_text_only", groups=[dict(group) for group in groups])
