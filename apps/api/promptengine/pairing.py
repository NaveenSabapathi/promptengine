import hmac
import secrets
from datetime import timedelta

from flask import Blueprint, current_app, g, jsonify
from sqlalchemy.exc import IntegrityError

from .errors import APIError
from .extensions import db
from .models import ExtensionToken, PairingRequest
from .security import (
    EXTENSION_SCOPES,
    code_digest,
    digest,
    json_body,
    new_extension_token,
    now,
    rate_limit,
    requires_auth,
    text_field,
    uuid_field,
)

bp = Blueprint("extension", __name__, url_prefix="/api/extension")


def checked_code(data):
    code = data.get("code")
    if not isinstance(code, str) or len(code) != 6 or not code.isascii() or not code.isdigit():
        raise APIError("invalid_code", "Provide the six-digit pairing code")
    return code


@bp.post("/pairing")
def create_pairing():
    rate_limit("pairing_create", 5)
    data = json_body()
    name = text_field(data, "device_name", 80)
    for _ in range(5):
        code = f"{secrets.randbelow(1000000):06d}"
        secret = secrets.token_urlsafe(48)
        record = PairingRequest(
            code_hash=code_digest(code),
            device_secret_hash=digest(secret),
            device_name=name,
            expires_at=now() + timedelta(minutes=5),
        )
        try:
            # Remove expired codes in case a six-digit value is reused.
            db.session.execute(
                db.delete(PairingRequest).where(
                    PairingRequest.code_hash == record.code_hash,
                    PairingRequest.expires_at <= now(),
                )
            )
            db.session.add(record)
            db.session.commit()
            return jsonify(
                pairing_id=str(record.id),
                code=code,
                device_secret=secret,
                expires_at=record.expires_at.isoformat(),
                scopes=EXTENSION_SCOPES,
                approval_url=current_app.config["WEB_ORIGIN"] + "/settings/extensions",
            ), 201
        except IntegrityError:
            db.session.rollback()
    raise APIError("pairing_unavailable", "Unable to create a pairing code. Try again", 503)


def lookup_pairing(code):
    record = db.session.scalar(
        db.select(PairingRequest)
        .where(
            PairingRequest.code_hash == code_digest(code),
        )
        .with_for_update()
    )
    if record is None or record.expires_at <= now() or record.consumed_at:
        raise APIError(
            "pairing_invalid", "Pairing request is invalid, expired or already used", 400
        )
    return record


@bp.post("/pairing/inspect")
@requires_auth(web_only=True)
def inspect_pairing():
    rate_limit("pairing_inspect", 5, identity=str(g.user.id))
    record = lookup_pairing(checked_code(json_body()))
    return jsonify(
        device_name=record.device_name,
        scopes=EXTENSION_SCOPES,
        expires_at=record.expires_at.isoformat(),
        approved=bool(record.approved_at),
    )


@bp.post("/pairing/approve")
@requires_auth(web_only=True)
def approve_pairing():
    rate_limit("pairing_approve", 5, identity=str(g.user.id))
    record = lookup_pairing(checked_code(json_body()))
    if record.approved_at:
        raise APIError("already_approved", "Pairing request has already been approved", 409)
    record.user_id, record.approved_at = g.user.id, now()
    db.session.commit()
    return jsonify(ok=True)


@bp.post("/pairing/exchange")
def exchange_pairing():
    rate_limit("pairing_exchange", 30)
    data = json_body()
    pairing_id = uuid_field(data.get("pairing_id"))
    secret = text_field(data, "device_secret", 128)
    record = lookup_pairing(checked_code(data))
    if record.id != pairing_id or not hmac.compare_digest(
        record.device_secret_hash, digest(secret)
    ):
        raise APIError("pairing_invalid", "Invalid pairing credentials", 400)
    if not record.approved_at:
        raise APIError("approval_pending", "Approve this device in the web application first", 409)
    token, access = new_extension_token(record.user_id, record.device_name)
    record.consumed_at = now()
    db.session.commit()
    return jsonify(
        access_token=token,
        token_type="Bearer",
        token_id=str(access.id),
        expires_at=access.expires_at.isoformat(),
        scopes=access.scopes,
    )


@bp.get("/tokens")
@requires_auth(web_only=True)
def list_tokens():
    records = db.session.scalars(
        db.select(ExtensionToken)
        .where(
            ExtensionToken.user_id == g.user.id,
        )
        .order_by(ExtensionToken.created_at.desc())
    ).all()
    return jsonify(
        tokens=[
            {
                "id": str(record.id),
                "device_name": record.device_name,
                "scopes": record.scopes,
                "expires_at": record.expires_at.isoformat(),
                "revoked": record.revoked_at is not None,
            }
            for record in records
        ]
    )


@bp.delete("/tokens/<uuid:token_id>")
@requires_auth(web_only=True)
def revoke_token(token_id):
    record = db.session.scalar(
        db.select(ExtensionToken).where(
            ExtensionToken.id == token_id,
            ExtensionToken.user_id == g.user.id,
        )
    )
    if record is None:
        raise APIError("not_found", "Device token not found", 404)
    record.revoked_at = now()
    db.session.commit()
    return jsonify(ok=True)
