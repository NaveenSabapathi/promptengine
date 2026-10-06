import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from functools import wraps

from flask import current_app, g, request
from flask_jwt_extended import (
    create_access_token,
    get_jwt,
    get_jwt_identity,
    set_access_cookies,
    verify_jwt_in_request,
)
from sqlalchemy.dialects.postgresql import insert

from .errors import APIError
from .extensions import db
from .models import ExtensionToken, RateLimitBucket, User, WebSession

EXTENSION_SCOPES = ["refine", "prompts:read", "prompts:write", "usage:read"]


def now():
    return datetime.now(UTC)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def code_digest(value):
    return hmac.new(
        current_app.config["SECRET_KEY"].encode(), value.encode(), hashlib.sha256
    ).hexdigest()


def json_body():
    if not request.is_json:
        raise APIError("invalid_json", "Send an application/json object", 415)
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise APIError("invalid_json", "Send a valid JSON object")
    return value


def text_field(data, name, maximum, minimum=1):
    value = data.get(name)
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        raise APIError("invalid_field", f"{name} must contain {minimum}–{maximum} characters")
    return value.strip()


def uuid_field(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise APIError("invalid_id", "Invalid identifier") from exc


def require_web_origin():
    # Also protects pre-login endpoints from login CSRF.
    if request.headers.get("Origin") != current_app.config["WEB_ORIGIN"]:
        raise APIError("invalid_origin", "Request must originate from the web application", 403)


def rate_limit(action, limit, seconds=60, identity=None):
    instant = now()
    bucket_start = datetime.fromtimestamp(int(instant.timestamp()) // seconds * seconds, UTC)
    key = code_digest(f"rate:{action}:{identity or request.remote_addr}")
    statement = (
        insert(RateLimitBucket)
        .values(
            key=key,
            window_start=bucket_start,
            count=1,
            expires_at=bucket_start + timedelta(seconds=seconds * 2),
        )
        .on_conflict_do_update(
            index_elements=[RateLimitBucket.key, RateLimitBucket.window_start],
            set_={"count": RateLimitBucket.count + 1},
        )
        .returning(RateLimitBucket.count)
    )
    count = db.session.execute(statement).scalar_one()
    db.session.commit()
    if count > limit:
        raise APIError("rate_limited", "Too many attempts. Please try again later", 429)


def login_response(user, response, mfa_at=None):
    instant = now()
    record = WebSession(user_id=user.id, expires_at=instant + timedelta(hours=12), mfa_at=mfa_at)
    db.session.add(record)
    db.session.flush()
    encoded = create_access_token(identity=str(user.id), additional_claims={"sid": str(record.id)})
    db.session.commit()
    set_access_cookies(response, encoded)
    return response


def requires_auth(scope=None, web_only=False):
    def decorator(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            authorization = request.headers.get("Authorization", "")
            if authorization:
                if web_only:
                    raise APIError("web_session_required", "Use a signed-in web session", 403)
                scheme, _, token = authorization.partition(" ")
                if (
                    scheme.lower() != "bearer"
                    or not token.startswith("pe_ext_")
                    or len(token) > 200
                ):
                    raise APIError("unauthorized", "Invalid access token", 401)
                record = db.session.scalar(
                    db.select(ExtensionToken).where(
                        ExtensionToken.token_hash == digest(token),
                        ExtensionToken.revoked_at.is_(None),
                        ExtensionToken.expires_at > now(),
                    )
                )
                if record is None:
                    raise APIError("unauthorized", "Expired or revoked access token", 401)
                if scope and scope not in record.scopes:
                    raise APIError(
                        "insufficient_scope", "Access token does not permit this action", 403
                    )
                g.auth_kind, g.auth_record = "extension", record
                user_id = record.user_id
            else:
                verify_jwt_in_request(locations=["cookies"])
                claims = get_jwt()
                try:
                    sid = uuid.UUID(claims.get("sid", ""))
                    user_id = uuid.UUID(get_jwt_identity())
                except (ValueError, TypeError) as exc:
                    raise APIError("unauthorized", "Invalid session", 401) from exc
                record = db.session.get(WebSession, sid)
                if (
                    record is None
                    or record.user_id != user_id
                    or record.revoked_at
                    or record.expires_at <= now()
                ):
                    raise APIError("unauthorized", "Expired or revoked session", 401)
                if request.method not in {"GET", "HEAD", "OPTIONS"}:
                    require_web_origin()
                g.auth_kind, g.auth_record = "web", record
            g.user = db.session.get(User, user_id)
            if g.user is None:
                raise APIError("unauthorized", "Account no longer exists", 401)
            from .teams import resolve_team

            resolve_team()
            return function(*args, **kwargs)

        return wrapped

    return decorator


def new_extension_token(user_id, device_name):
    token = "pe_ext_" + secrets.token_urlsafe(48)
    record = ExtensionToken(
        user_id=user_id,
        token_hash=digest(token),
        device_name=device_name,
        scopes=EXTENSION_SCOPES,
        expires_at=now() + timedelta(days=current_app.config["EXTENSION_TOKEN_DAYS"]),
    )
    db.session.add(record)
    db.session.flush()
    return token, record
