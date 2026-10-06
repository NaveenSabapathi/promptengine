"""Durable asynchronous, opt-in logging; team content is excluded."""

import json
import re
from datetime import timedelta

import click
from flask import Blueprint, current_app, g, jsonify

from .enterprise_security import cipher
from .errors import APIError
from .extensions import db
from .models import ApiRequestMetric, DatasetJob, DatasetPromptLog, User
from .security import json_body, now, requires_auth

bp = Blueprint("datasets", __name__, url_prefix="/api/dataset")
PATTERNS = (
    (r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[EMAIL]"),
    (r"(?<!\w)(?:\+?\d[\d ()-]{7,}\d)(?!\w)", "[PHONE]"),
    (
        r"\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{12,}|AIza[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{16,})\b",
        "[API_KEY]",
    ),
    (
        r"(?i)\b(?:api[_ -]?key|secret|password|authorization|access[_ -]?token)"
        r"\s*[:=]\s*[\"']?[^\s,\"'}]{4,}",
        "[SECRET]",
    ),
    (r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b", "[TOKEN]"),
)


def scrub(value):
    if isinstance(value, str):
        for pattern, replacement in PATTERNS:
            value = re.sub(pattern, replacement, value)
        return value
    if isinstance(value, dict):
        return {scrub(str(k)): scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def enqueue(value, output, metrics):
    if not current_app.config["DATASET_ENABLED"] or g.get("team_id"):
        return
    # Serialize consent updates and enqueue. Revocation purges all existing jobs
    # and logs, and workers re-check the version before persistence.
    user = db.session.scalar(
        db.select(User)
        .where(User.id == g.user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not user.dataset_consent:
        return
    payload = scrub(
        {
            "preset_key": value.preset,
            "raw_input_context": {"raw_input": value.raw_input, "fields": value.fields},
            "final_prompt_output": output["prompt"],
            "model_response": json.dumps(output),
            "token_metrics": metrics,
        }
    )
    db.session.add(
        DatasetJob(
            user_id=user.id,
            consent_version=user.consent_version,
            encrypted_payload=cipher("DATASET_ENCRYPTION_KEY")
            .encrypt(json.dumps(payload).encode())
            .decode(),
        )
    )


@bp.post("/consent")
@requires_auth(web_only=True)
def consent():
    data = json_body()
    if set(data) != {"enabled"} or not isinstance(data["enabled"], bool):
        raise APIError("invalid_consent", "Provide enabled as a boolean")
    if data["enabled"] and not current_app.config["DATASET_ENABLED"]:
        raise APIError("dataset_disabled", "Training-data collection is disabled", 403)
    user = db.session.scalar(db.select(User).where(User.id == g.user.id).with_for_update())
    user.dataset_consent = data["enabled"]
    user.consent_version += 1
    if not user.dataset_consent:
        db.session.execute(db.delete(DatasetJob).where(DatasetJob.user_id == user.id))
        db.session.execute(db.delete(DatasetPromptLog).where(DatasetPromptLog.user_id == user.id))
    db.session.commit()
    return jsonify(enabled=user.dataset_consent)


def process_jobs(limit=100):
    # Discover IDs without locking; every worker locks User before Job, matching
    # consent revocation/enqueue and avoiding job/user lock inversion.
    ids = db.session.execute(
        db.select(DatasetJob.id, DatasetJob.user_id).order_by(DatasetJob.created_at).limit(limit)
    ).all()
    db.session.rollback()
    processed = 0
    for job_id, user_id in ids:
        user = db.session.scalar(
            db.select(User).where(User.id == user_id).with_for_update(skip_locked=True)
        )
        if not user:
            db.session.rollback()
            continue
        job = db.session.scalar(
            db.select(DatasetJob).where(DatasetJob.id == job_id).with_for_update(skip_locked=True)
        )
        if not job:
            db.session.rollback()
            continue
        if (
            user.dataset_consent
            and user.consent_version == job.consent_version
            and job.created_at > now() - timedelta(days=30)
        ):
            payload = json.loads(
                cipher("DATASET_ENCRYPTION_KEY").decrypt(job.encrypted_payload.encode())
            )
            db.session.add(DatasetPromptLog(log_id=job.id, user_id=user.id, **payload))
        db.session.delete(job)
        db.session.commit()
        processed += 1
    return processed


def register_commands(app):
    @app.cli.command("dataset-worker")
    def worker():
        """Drain a bounded batch of durable logging jobs; invoke every minute."""
        click.echo(f"Processed {process_jobs()} jobs")

    @app.cli.command("cleanup-telemetry")
    def cleanup():
        for model in (DatasetJob, DatasetPromptLog, ApiRequestMetric):
            db.session.execute(
                db.delete(model).where(model.created_at < now() - timedelta(days=30))
            )
        db.session.commit()
        click.echo("Expired telemetry removed")
