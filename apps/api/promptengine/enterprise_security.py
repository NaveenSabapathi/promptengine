"""Role checks and replay-resistant MFA. Secrets never appear in logs or JWTs."""

import base64
import io
import re
import secrets
from datetime import timedelta
from functools import wraps

import pyotp
import qrcode
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from cryptography.fernet import Fernet, InvalidToken
from flask import Blueprint, current_app, g, jsonify
from werkzeug.security import check_password_hash

from .errors import APIError
from .extensions import db
from .models import AuditLog, ExtensionToken, User, WebSession
from .security import json_body, now, rate_limit, requires_auth

bp = Blueprint("security", __name__, url_prefix="/api/security")
hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)


def cipher(key="TOTP_ENCRYPTION_KEY"):
    value = current_app.config.get(key)
    if not value:
        raise APIError("encryption_unconfigured", "Security encryption key is unavailable", 503)
    return Fernet(value.encode())


def audit(action, target, details=None, actor=None):
    db.session.add(
        AuditLog(
            actor_id=actor if actor else getattr(g.get("user"), "id", None),
            action=action,
            target=str(target),
            details=details or {},
        )
    )


def verify_factor(user_id, value):
    # Lock serializes both TOTP counters and recovery-code removal across workers.
    user = db.session.scalar(
        db.select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not user.totp_secret or not isinstance(value, str) or len(value) > 80:
        raise APIError("mfa_invalid", "Provide a valid authenticator or recovery code", 403)
    if re.fullmatch(r"\d{6}", value):
        try:
            totp = pyotp.TOTP(cipher().decrypt(user.totp_secret.encode()).decode())
        except InvalidToken as exc:
            raise APIError(
                "mfa_unavailable", "Authenticator configuration needs recovery", 503
            ) from exc
        step = int(now().timestamp()) // 30
        for candidate in (step, step - 1, step + 1):
            if candidate > user.totp_last_step and secrets.compare_digest(
                totp.at(candidate * 30), value
            ):
                user.totp_last_step = candidate
                return user
    elif user.totp_enabled:
        for index, hashed in enumerate(user.recovery_hashes):
            try:
                hasher.verify(hashed, value)
            except VerificationError:
                continue
            user.recovery_hashes = user.recovery_hashes[:index] + user.recovery_hashes[index + 1 :]
            return user
    raise APIError("mfa_invalid", "Code is invalid or already used", 403)


def require_fresh_mfa():
    if (
        g.auth_kind != "web"
        or not g.user.totp_enabled
        or not g.auth_record.mfa_at
        or g.auth_record.mfa_at < now() - timedelta(minutes=5)
    ):
        raise APIError(
            "mfa_required", "Verify an authenticator code in Security before continuing", 403
        )


def require_admin(function):
    @requires_auth(web_only=True)
    @wraps(function)
    def wrapped(*args, **kwargs):
        if not g.user.is_admin:
            raise APIError("admin_required", "Administrator access required", 403)
        require_fresh_mfa()
        return function(*args, **kwargs)

    return wrapped


@bp.get("")
@requires_auth(web_only=True)
def status():
    return jsonify(
        enabled=g.user.totp_enabled,
        recovery_codes_remaining=len(g.user.recovery_hashes),
        dataset_consent=g.user.dataset_consent,
    )


@bp.post("/enroll")
@requires_auth(web_only=True)
def enroll():
    rate_limit("mfa_enroll", 5, identity=str(g.user.id))
    user = db.session.scalar(db.select(User).where(User.id == g.user.id).with_for_update())
    if user.totp_enabled:
        raise APIError("mfa_enabled", "Two-factor authentication is already enabled", 409)
    data = json_body()
    if g.auth_record.created_at < now() - timedelta(minutes=5):
        raise APIError(
            "recent_login_required", "Sign in again before enrolling an authenticator", 403
        )
    if user.password_hash and not check_password_hash(
        user.password_hash, str(data.get("password", ""))[:128]
    ):
        raise APIError("invalid_credentials", "Verify your current password", 403)
    secret = pyotp.random_base32()
    user.totp_secret = cipher().encrypt(secret.encode()).decode()
    user.totp_last_step = -1
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="PromptLogic")
    image = qrcode.make(uri)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    db.session.commit()
    return jsonify(
        provisioning_uri=uri,
        qr_data_url="data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode(),
    )


@bp.post("/confirm")
@requires_auth(web_only=True)
def confirm():
    rate_limit("mfa_confirm", 5, seconds=300, identity=str(g.user.id))
    user = verify_factor(g.user.id, json_body().get("code"))
    if user.totp_enabled:
        raise APIError("mfa_enabled", "Two-factor authentication is already enabled", 409)
    codes = [secrets.token_hex(10) for _ in range(8)]
    user.recovery_hashes = [hasher.hash(code) for code in codes]
    user.totp_enabled = True
    g.auth_record.mfa_at = now()
    audit("mfa.enabled", user.id)
    db.session.commit()
    return jsonify(recovery_codes=codes)


@bp.post("/step-up")
@requires_auth(web_only=True)
def step_up():
    rate_limit("mfa_step", 5, seconds=300, identity=str(g.user.id))
    if not g.user.totp_enabled:
        raise APIError("mfa_disabled", "Enable two-factor authentication first", 403)
    verify_factor(g.user.id, json_body().get("code"))
    g.auth_record.mfa_at = now()
    audit("mfa.verified", g.user.id)
    db.session.commit()
    return jsonify(ok=True)


@bp.post("/disable")
@requires_auth(web_only=True)
def disable():
    rate_limit("mfa_disable", 5, seconds=300, identity=str(g.user.id))
    user = verify_factor(g.user.id, json_body().get("code"))
    if user.is_admin:
        raise APIError(
            "admin_mfa_required", "Remove the administrator role before disabling MFA", 403
        )
    user.totp_enabled = False
    user.totp_secret = None
    user.recovery_hashes = []
    db.session.execute(
        db.update(WebSession)
        .where(WebSession.user_id == user.id, WebSession.id != g.auth_record.id)
        .values(revoked_at=now())
    )
    db.session.execute(
        db.update(ExtensionToken).where(ExtensionToken.user_id == user.id).values(revoked_at=now())
    )
    audit("mfa.disabled", user.id)
    db.session.commit()
    return jsonify(ok=True)
