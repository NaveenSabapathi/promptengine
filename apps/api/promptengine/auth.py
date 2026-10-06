from email_validator import EmailNotValidError, validate_email
from flask import Blueprint, current_app, g, jsonify
from flask_jwt_extended import unset_jwt_cookies
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from .errors import APIError
from .extensions import db
from .models import Entitlement, OAuthIdentity, User
from .security import (
    json_body,
    login_response,
    now,
    rate_limit,
    require_web_origin,
    requires_auth,
)

bp = Blueprint("auth", __name__, url_prefix="/api/auth")
# Dummy verification evens out the expensive work for unknown accounts.
DUMMY_PASSWORD_HASH = generate_password_hash("unusable-dummy-password")


def normalized_email(value):
    if not isinstance(value, str) or len(value) > 254:
        raise APIError("invalid_email", "Provide a valid email address")
    try:
        return validate_email(value.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        raise APIError("invalid_email", "Provide a valid email address") from exc


def password_value(data, signup=False):
    password = data.get("password")
    minimum = 12 if signup else 1
    if not isinstance(password, str) or not minimum <= len(password) <= 128:
        raise APIError("invalid_password", f"Password must contain {minimum}–128 characters")
    return password


def user_payload(user):
    return {
        "id": str(user.id),
        "email": user.email,
        "created_at": user.created_at.isoformat(),
        "is_admin": user.is_admin,
        "totp_enabled": user.totp_enabled,
        "dataset_consent": user.dataset_consent,
    }


def create_user(email, password_hash=None):
    user = User(email=email, password_hash=password_hash)
    db.session.add(user)
    db.session.flush()
    db.session.add(Entitlement(user_id=user.id))
    db.session.flush()
    return user


@bp.get("/capabilities")
def capabilities():
    return jsonify(
        providers={
            provider: bool(
                current_app.config[f"{provider.upper()}_CLIENT_ID"]
                and current_app.config[f"{provider.upper()}_CLIENT_SECRET"]
            )
            for provider in ("google", "microsoft")
        },
        ai_enabled=bool(current_app.config["OPENAI_API_KEY"]),
    )


@bp.post("/signup")
def signup():
    require_web_origin()
    rate_limit("signup", 5)
    data = json_body()
    if set(data) - {"email", "password", "code", "referral_code", "device_id"}:
        raise APIError("invalid_field", "Unexpected account field")
    email = normalized_email(data.get("email"))
    password = password_value(data, signup=True)
    try:
        user = create_user(email, generate_password_hash(password))
        from .referrals import register_referral

        register_referral(user, data)
        response = login_response(user, jsonify(user=user_payload(user)))
        return response, 201
    except IntegrityError as exc:
        db.session.rollback()
        raise APIError(
            "account_exists", "An account already exists; sign in to continue", 409
        ) from exc


@bp.post("/login")
def login():
    require_web_origin()
    rate_limit("login_ip", 20)
    data = json_body()
    if set(data) - {"email", "password", "code", "referral_code", "device_id"}:
        raise APIError("invalid_field", "Unexpected account field")
    email = normalized_email(data.get("email"))
    password = password_value(data)
    rate_limit("login_account", 10, seconds=900, identity=email)
    user = db.session.scalar(db.select(User).where(User.email == email))
    password_hash = user.password_hash if user and user.password_hash else DUMMY_PASSWORD_HASH
    matches = check_password_hash(password_hash, password)
    if not user or not user.password_hash or not matches:
        raise APIError("invalid_credentials", "Email or password is incorrect", 401)
    mfa_at = None
    if user.totp_enabled:
        if not data.get("code"):
            raise APIError("mfa_required", "Enter your authenticator or recovery code", 403)
        from .enterprise_security import verify_factor

        verify_factor(user.id, data.get("code"))
        mfa_at = now()
    return login_response(user, jsonify(user=user_payload(user)), mfa_at=mfa_at)


@bp.get("/me")
@requires_auth(web_only=True)
def me():
    return jsonify(
        user=user_payload(g.user),
        linked_providers=list(
            db.session.scalars(
                db.select(OAuthIdentity.provider).where(OAuthIdentity.user_id == g.user.id)
            )
        ),
    )


@bp.post("/logout")
@requires_auth(web_only=True)
def logout():
    g.auth_record.revoked_at = now()
    db.session.commit()
    response = jsonify(ok=True)
    unset_jwt_cookies(response)
    return response
