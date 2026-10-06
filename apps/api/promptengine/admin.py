import json
import secrets
import string
from datetime import timedelta

import click
import requests
from flask import Blueprint, Response, current_app, g, jsonify, request
from sqlalchemy.orm import Session

from .auth import normalized_email
from .enterprise_security import audit, require_admin
from .errors import APIError
from .extensions import db
from .models import (
    ApiRequestMetric,
    AuditLog,
    Coupon,
    DatasetPromptLog,
    Entitlement,
    ExtensionToken,
    GenerationMetric,
    MailOutbox,
    Referral,
    UsageLedger,
    User,
    WebSession,
)
from .razorpay_provider import provider_client, require_checkout
from .security import json_body, now, text_field

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def integer(data, key, minimum, maximum, default=None):
    value = data.get(key, default)
    if type(value) is not int or not minimum <= value <= maximum:
        raise APIError("invalid_field", f"{key} must be an integer from {minimum} to {maximum}")
    return value


@bp.get("/overview")
@require_admin
def overview():
    since = now() - timedelta(days=1)
    metrics = (
        db.session.execute(
            db.select(
                db.func.count().label("requests"),
                db.func.count().filter(ApiRequestMetric.status >= 500).label("failures"),
                db.func.avg(ApiRequestMetric.provider_latency_ms).label("provider_latency_ms"),
            ).where(ApiRequestMetric.created_at >= since)
        )
        .mappings()
        .one()
    )
    tokens = (
        db.session.execute(
            db.select(
                db.func.coalesce(db.func.sum(GenerationMetric.provider_input_tokens), 0).label(
                    "input_tokens"
                ),
                db.func.coalesce(db.func.sum(GenerationMetric.provider_output_tokens), 0).label(
                    "output_tokens"
                ),
                db.func.coalesce(db.func.sum(GenerationMetric.token_difference), 0).label(
                    "token_delta"
                ),
            ).where(GenerationMetric.created_at >= since)
        )
        .mappings()
        .one()
    )
    accounts = db.session.scalar(db.select(db.func.count(User.id)))
    active = db.session.scalar(
        db.select(db.func.count(db.distinct(WebSession.user_id))).where(
            WebSession.expires_at > now(), WebSession.revoked_at.is_(None)
        )
    )
    used = db.session.scalar(
        db.select(db.func.coalesce(db.func.sum(UsageLedger.ai_requests_count), 0)).where(
            UsageLedger.date == now().date()
        )
    )
    return jsonify(
        accounts=accounts,
        active_accounts=active,
        usage_today=used,
        period_hours=24,
        telemetry={
            **dict(metrics),
            "failure_rate": metrics["failures"] / max(1, metrics["requests"]),
        },
        tokens=dict(tokens),
    )


@bp.get("/users")
@require_admin
def users():
    email = request.args.get("email", "").strip().lower()
    if len(email) > 254:
        raise APIError("invalid_email", "Email is too long")
    query = db.select(User).order_by(User.created_at.desc()).limit(50)
    if email:
        query = query.where(User.email == email)
    rows = db.session.scalars(query).all()
    result = []
    from .entitlements import effective_entitlement

    for user in rows:
        ent = db.session.get(Entitlement, user.id)
        tier, limit = effective_entitlement(ent)
        tokens = db.session.scalars(
            db.select(ExtensionToken).where(
                ExtensionToken.user_id == user.id, ExtensionToken.revoked_at.is_(None)
            )
        ).all()
        result.append(
            {
                "id": str(user.id),
                "email": user.email,
                "is_admin": user.is_admin,
                "plan_tier": tier,
                "daily_ai_limit": limit,
                "devices": [{"id": str(t.id), "name": t.device_name} for t in tokens],
            }
        )
    return jsonify(users=result)


@bp.post("/users/<uuid:user_id>/override")
@require_admin
def override(user_id):
    data = json_body()
    reason = text_field(data, "reason", 500, 5)
    tier = data.get("plan_tier")
    if tier not in {"free", "pro"}:
        raise APIError("invalid_plan", "Select free or pro")
    limit, days = integer(data, "daily_ai_limit", 1, 10000), integer(data, "days", 1, 365)
    ent = db.session.scalar(
        db.select(Entitlement).where(Entitlement.user_id == user_id).with_for_update()
    )
    if not ent:
        raise APIError("not_found", "Account not found", 404)
    ent.override_tier, ent.override_limit, ent.override_expires_at = (
        tier,
        limit,
        now() + timedelta(days=days),
    )
    audit(
        "admin.plan_override",
        user_id,
        {"tier": tier, "limit": limit, "days": days, "reason": reason},
    )
    db.session.commit()
    return jsonify(ok=True)


@bp.post("/users/<uuid:user_id>/revoke")
@require_admin
def revoke(user_id):
    reason = text_field(json_body(), "reason", 500, 5)
    for model in (ExtensionToken, WebSession):
        db.session.execute(
            db.update(model).where(model.user_id == user_id).values(revoked_at=now())
        )
    audit("admin.sessions_revoked", user_id, {"reason": reason})
    db.session.commit()
    return jsonify(ok=True)


@bp.delete("/devices/<uuid:device_id>")
@require_admin
def revoke_device(device_id):
    token = db.session.get(ExtensionToken, device_id)
    if not token:
        raise APIError("not_found", "Device not found", 404)
    token.revoked_at = now()
    audit("admin.device_revoked", device_id)
    db.session.commit()
    return "", 204


@bp.get("/audit")
@require_admin
def logs():
    rows = db.session.scalars(
        db.select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id).limit(200)
    ).all()
    return jsonify(
        logs=[
            {
                "id": str(r.id),
                "actor_id": str(r.actor_id) if r.actor_id else None,
                "action": r.action,
                "target": r.target,
                "details": r.details,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    )


@bp.get("/referrals")
@require_admin
def referrals():
    rows = db.session.scalars(
        db.select(Referral).order_by(Referral.created_at.desc()).limit(200)
    ).all()
    return jsonify(
        referrals=[
            {
                "id": str(r.id),
                "referrer_id": str(r.referrer_id),
                "referee_id": str(r.referee_id),
                "status": r.status,
                "blocked_reason": r.blocked_reason,
                "registration_days": r.registration_days,
                "conversion_days": r.conversion_days,
            }
            for r in rows
        ]
    )


@bp.post("/coupons")
@require_admin
def coupon():
    data = json_body()
    kind = data.get("discount_type")
    if kind not in {"days_extension", "percentage", "fixed_amount"}:
        raise APIError("invalid_discount", "Select a valid discount type")
    fields = dict(
        discount_type=kind,
        max_uses=integer(data, "max_uses", 1, 100000),
        expires_at=now() + timedelta(days=integer(data, "expires_in_days", 1, 365)),
        created_by_admin_id=g.user.id,
    )
    if kind == "days_extension":
        fields["days_granted"] = integer(data, "days_granted", 1, 365)
    else:
        require_checkout()
        value = integer(
            data,
            "discount_value",
            1,
            99 if kind == "percentage" else current_app.config["PRO_PRICE_PAISE"] - 100,
        )
        base = current_app.config["PRO_PRICE_PAISE"]
        amount = base * (100 - value) // 100 if kind == "percentage" else base - value
        plan_id = text_field(data, "razorpay_plan_id", 100)
        with provider_client() as client:
            try:
                plan = client.plan.fetch(plan_id)
            except Exception as exc:
                raise APIError(
                    "billing_unavailable", "Unable to verify discount plan", 503
                ) from exc
        item = plan.get("item", {})
        if (
            plan.get("id") != plan_id
            or plan.get("period") != "monthly"
            or plan.get("interval") != 1
            or item.get("currency") != "INR"
            or item.get("amount") != amount
        ):
            raise APIError(
                "discount_plan_mismatch",
                "Provider plan must match the monthly discounted INR price",
            )
        fields.update(discount_value=value, amount_paise=amount, razorpay_plan_id=plan_id)
    code = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16))
    row = Coupon(code=code, **fields)
    db.session.add(row)
    db.session.flush()
    if data.get("recipient_email"):
        db.session.add(
            MailOutbox(
                recipient=normalized_email(data["recipient_email"]),
                subject="Your PromptLogic coupon",
                body="Redeem at " + current_app.config["WEB_ORIGIN"] + "/rewards\nCoupon: " + code,
            )
        )
    audit("admin.coupon_created", row.id, {"discount_type": kind, "max_uses": row.max_uses})
    db.session.commit()
    return jsonify(id=str(row.id), code=code, expires_at=row.expires_at.isoformat()), 201


@bp.get("/dataset")
@require_admin
def dataset():
    rows = db.session.scalars(
        db.select(DatasetPromptLog).order_by(DatasetPromptLog.created_at.desc()).limit(100)
    ).all()
    return jsonify(
        logs=[
            {
                "id": str(r.log_id),
                "user_id": str(r.user_id),
                "preset_key": r.preset_key,
                "quality_rating": r.quality_rating,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    )


@bp.get("/dataset/<uuid:log_id>")
@require_admin
def dataset_preview(log_id):
    row = db.session.get(DatasetPromptLog, log_id)
    if not row:
        raise APIError("not_found", "Dataset record not found", 404)
    audit("admin.dataset_previewed", log_id)
    db.session.commit()
    return jsonify(
        raw_input_context=row.raw_input_context,
        final_prompt_output=row.final_prompt_output,
        model_response=row.model_response,
    )


@bp.put("/dataset/<uuid:log_id>/rating")
@require_admin
def rating(log_id):
    row = db.session.get(DatasetPromptLog, log_id)
    if not row:
        raise APIError("not_found", "Dataset record not found", 404)
    row.quality_rating = integer(json_body(), "quality_rating", 1, 5)
    audit("admin.dataset_rated", log_id, {"rating": row.quality_rating})
    db.session.commit()
    return jsonify(ok=True)


@bp.post("/dataset/export")
@require_admin
def export():
    data = json_body()
    minimum = integer(data, "minimum_rating", 1, 5, 3)
    reason = text_field(data, "reason", 500, 5)
    rows = db.session.scalars(
        db.select(DatasetPromptLog)
        .join(User)
        .where(
            User.dataset_consent.is_(True),
            DatasetPromptLog.quality_rating >= minimum,
            DatasetPromptLog.created_at > now() - timedelta(days=30),
        )
        .order_by(DatasetPromptLog.log_id)
        .limit(10000)
    ).all()
    # Bound the export, perform all authorization before returning any bytes.
    content = "\n".join(
        json.dumps(
            {
                "messages": [
                    {"role": "system", "content": "Compile a clear, accurate task prompt."},
                    {"role": "user", "content": json.dumps(r.raw_input_context)},
                    {"role": "assistant", "content": r.final_prompt_output},
                ]
            },
            ensure_ascii=False,
        )
        for r in rows
    )
    audit(
        "admin.dataset_exported",
        "dataset",
        {"records": len(rows), "minimum_rating": minimum, "reason": reason},
    )
    db.session.commit()
    return Response(
        content + ("\n" if content else ""),
        mimetype="application/x-ndjson",
        headers={"Content-Disposition": 'attachment; filename="promptlogic-training.ndjson"'},
    )


def register_commands(app):
    @app.cli.command("grant-admin")
    @click.argument("email")
    def grant_admin(email):
        """Operator-only bootstrap; account must already have confirmed MFA."""
        user = db.session.scalar(
            db.select(User).where(User.email == normalized_email(email)).with_for_update()
        )
        if not user or not user.totp_enabled:
            raise click.ClickException(
                "Account must exist and have confirmed two-factor authentication"
            )
        user.is_admin = True
        audit("operator.admin_granted", user.id)
        db.session.commit()
        click.echo("Administrator role granted")

    @app.cli.command("mail-worker")
    def mail_worker():
        """Deliver up to 25 outbox messages to an explicitly configured HTTPS hook."""
        import hashlib
        import hmac
        from urllib.parse import urlparse

        url, secret = app.config["MAIL_HOOK_URL"], app.config["MAIL_HOOK_SECRET"]
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or not secret:
            raise click.ClickException("Configure a trusted HTTPS MAIL_HOOK_URL and secret")
        for _ in range(25):
            with Session(db.engine) as session:
                row = session.scalar(
                    db.select(MailOutbox)
                    .where(MailOutbox.delivered_at.is_(None), MailOutbox.attempts < 5)
                    .order_by(MailOutbox.created_at)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                if not row:
                    break
                payload = json.dumps(
                    {
                        "id": str(row.id),
                        "recipient": row.recipient,
                        "subject": row.subject,
                        "body": row.body,
                    }
                ).encode()
                signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
                row.attempts += 1
                try:
                    response = requests.post(
                        url,
                        data=payload,
                        headers={
                            "Content-Type": "application/json",
                            "X-PromptLogic-Signature": signature,
                            "Idempotency-Key": str(row.id),
                        },
                        timeout=(3, 8),
                        allow_redirects=False,
                    )
                    if 200 <= response.status_code < 300:
                        row.delivered_at = now()
                except requests.RequestException:
                    pass
                session.commit()
        click.echo("Mail outbox batch completed")
