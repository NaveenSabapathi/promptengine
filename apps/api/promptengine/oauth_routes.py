import secrets
from uuid import UUID

from authlib.integrations.base_client.errors import OAuthError
from flask import Blueprint, current_app, g, jsonify, redirect, request, session
from joserfc.errors import JoseError
from requests.exceptions import RequestException
from sqlalchemy.exc import IntegrityError

from .auth import create_user, normalized_email
from .errors import APIError
from .extensions import db, oauth
from .models import OAuthIdentity, User, WebSession
from .security import login_response, now, rate_limit, requires_auth

bp = Blueprint("oauth", __name__, url_prefix="/api/auth")


def valid_microsoft_issuer(claims, value):
    try:
        tenant = str(UUID(claims.get("tid", "")))
    except (ValueError, TypeError, AttributeError):
        return False
    configured = current_app.config["MICROSOFT_TENANT"]
    consumer = "9188040d-6c67-4c5b-b112-36a304b66dad"
    if configured == "consumers" and tenant != consumer:
        return False
    if configured == "organizations" and tenant == consumer:
        return False
    if configured not in {"common", "organizations", "consumers"} and tenant != configured:
        return False
    return value == f"https://login.microsoftonline.com/{tenant}/v2.0"


def oidc_claims_options(provider, client_id):
    # Always create fresh options: Authlib extracts (and mutates) custom validator hooks.
    issuer = (
        {"essential": True, "validate": valid_microsoft_issuer}
        if provider == "microsoft"
        else {"essential": True, "values": ["https://accounts.google.com"]}
    )
    return {"iss": issuer, "aud": {"essential": True, "value": client_id}}


def register_oauth(app):
    for provider, metadata in {
        "google": "https://accounts.google.com/.well-known/openid-configuration",
        "microsoft": (
            "https://login.microsoftonline.com/"
            f"{app.config['MICROSOFT_TENANT']}/v2.0/.well-known/openid-configuration"
        ),
    }.items():
        prefix = provider.upper()
        if app.config[f"{prefix}_CLIENT_ID"] and app.config[f"{prefix}_CLIENT_SECRET"]:
            oauth.register(
                name=provider,
                client_id=app.config[f"{prefix}_CLIENT_ID"],
                client_secret=app.config[f"{prefix}_CLIENT_SECRET"],
                server_metadata_url=metadata,
                client_kwargs={
                    "scope": "openid email profile",
                    "code_challenge_method": "S256",
                    "default_timeout": 10,
                },
            )


def client_for(provider):
    if provider not in {"google", "microsoft"}:
        raise APIError("unknown_provider", "Unsupported login provider", 404)
    # Do not leak OAuth credentials or silently substitute a fake login.
    prefix = provider.upper()
    if not (
        current_app.config[f"{prefix}_CLIENT_ID"] and current_app.config[f"{prefix}_CLIENT_SECRET"]
    ):
        raise APIError(
            "provider_not_configured", f"{provider.title()} login is not configured", 503
        )
    return oauth.create_client(provider)


def start_flow(provider, linking=False):
    client = client_for(provider)
    rate_limit("oauth_start", 20)
    session.clear()
    session.permanent = True
    nonce = secrets.token_urlsafe(32)
    session["oauth_flow"] = {
        "nonce": nonce,
        "provider": provider,
        "started": int(now().timestamp()),
        "link_user_id": str(g.user.id) if linking else None,
        "link_session_id": str(g.auth_record.id) if linking else None,
    }
    try:
        response = client.authorize_redirect(
            current_app.config["API_ORIGIN"] + f"/api/auth/{provider}/callback",
            nonce=nonce,
            prompt="select_account" if provider == "microsoft" else "consent",
        )
        if linking and request.accept_mimetypes.best == "application/json":
            return jsonify(authorization_url=response.location)
        return response
    except RequestException as exc:
        session.clear()
        raise APIError(
            "provider_unavailable", "Login provider is unavailable. Try again later", 503
        ) from exc


@bp.get("/<provider>/login")
def oauth_login(provider):
    return start_flow(provider)


@bp.post("/<provider>/link")
@requires_auth(web_only=True)
def oauth_link(provider):
    return start_flow(provider, linking=True)


def resolve_identity(provider, claims, linked_user_id=None):
    issuer, subject = claims.get("iss"), claims.get("sub")
    if (
        not isinstance(issuer, str)
        or not isinstance(subject, str)
        or not 1 <= len(issuer) <= 255
        or not 1 <= len(subject) <= 255
    ):
        raise APIError("invalid_identity", "Login provider returned an invalid identity", 401)
    identity = db.session.scalar(
        db.select(OAuthIdentity).where(
            OAuthIdentity.provider == provider,
            OAuthIdentity.issuer == issuer,
            OAuthIdentity.subject == subject,
        )
    )
    if identity:
        if linked_user_id and str(identity.user_id) != linked_user_id:
            raise APIError("identity_in_use", "This identity belongs to another account", 409)
        return db.session.get(User, identity.user_id)
    if linked_user_id:
        user = db.session.get(User, UUID(linked_user_id))
        if user is None:
            raise APIError("unauthorized", "Account no longer exists", 401)
    else:
        if provider == "google" and claims.get("email_verified") is not True:
            raise APIError("unverified_email", "Google must verify your email address", 403)
        # Microsoft email is a contact label, never an account-linking or authorization key.
        email = normalized_email(claims.get("email"))
        if db.session.scalar(db.select(User.id).where(User.email == email)):
            raise APIError(
                "account_link_required",
                "Sign in to your existing account and explicitly link this provider",
                409,
            )
        user = create_user(email)
    db.session.add(
        OAuthIdentity(
            user_id=user.id,
            provider=provider,
            issuer=issuer,
            subject=subject,
        )
    )
    db.session.flush()
    return user


@bp.get("/<provider>/callback")
def oauth_callback(provider):
    client = client_for(provider)
    rate_limit("oauth_callback", 30)
    flow = session.pop("oauth_flow", None)
    if not flow or flow["provider"] != provider or now().timestamp() - flow["started"] > 600:
        session.clear()
        raise APIError("invalid_oauth_state", "Login expired. Start again", 401)
    try:
        # Authlib verifies state, PKCE, nonce, signature, audience, expiry and issuer.
        claims_options = oidc_claims_options(provider, client.client_id)
        token = client.authorize_access_token(claims_options=claims_options)
        claims = token.get("userinfo")
        if "id_token" not in token or claims is None:
            raise APIError("invalid_identity", "Provider did not return a verified ID token", 401)
        if claims.get("nonce") != flow["nonce"]:
            raise APIError("invalid_nonce", "Login nonce could not be verified", 401)
        if flow["link_user_id"]:
            link_session = db.session.get(WebSession, UUID(flow["link_session_id"]))
            if (
                not link_session
                or str(link_session.user_id) != flow["link_user_id"]
                or link_session.revoked_at
                or link_session.expires_at <= now()
            ):
                raise APIError("unauthorized", "Sign in again before linking an account", 401)
        user = resolve_identity(provider, claims, flow["link_user_id"])
        response = redirect(current_app.config["WEB_ORIGIN"] + "/workspace")
        return login_response(user, response)
    except (OAuthError, JoseError, ValueError) as exc:
        db.session.rollback()
        raise APIError(
            "oauth_failed", "Provider login could not be verified. Start again", 401
        ) from exc
    except RequestException as exc:
        db.session.rollback()
        raise APIError(
            "provider_unavailable", "Login provider is unavailable. Try again later", 503
        ) from exc
    except IntegrityError as exc:
        db.session.rollback()
        raise APIError(
            "identity_conflict", "Account already exists or provider is already linked", 409
        ) from exc
    finally:
        session.clear()
