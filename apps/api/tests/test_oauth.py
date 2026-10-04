from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from conftest import signup, web_headers

from promptengine.errors import APIError
from promptengine.extensions import db, oauth
from promptengine.models import OAuthIdentity, User
from promptengine.oauth_routes import register_oauth, resolve_identity, valid_microsoft_issuer
from promptengine.security import now


@pytest.fixture
def google(app):
    previous = {key: app.config[key] for key in ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"]}
    app.config.update(
        GOOGLE_CLIENT_ID="test-google-client", GOOGLE_CLIENT_SECRET="test-google-secret"
    )
    register_oauth(app)
    with app.app_context():
        client = oauth.create_client("google")
        client.server_metadata.update(
            issuer="https://accounts.google.com",
            authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
            token_endpoint="https://oauth2.googleapis.com/token",
            jwks_uri="https://www.googleapis.com/oauth2/v3/certs",
            _loaded_at=now().timestamp(),
        )
    yield client
    app.config.update(previous)


def test_missing_provider_and_invalid_state(client, google):
    assert client.get("/api/auth/microsoft/login").status_code == 503
    assert client.get("/api/auth/unknown/login").status_code == 404
    assert client.get("/api/auth/google/callback?code=bad&state=bad").status_code == 401


def test_oauth_start_uses_pkce_nonce_and_validates_state(client, google):
    response = client.get("/api/auth/google/login")
    assert response.status_code == 302
    query = parse_qs(urlparse(response.location).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["nonce"][0] and query["state"][0] and query["code_challenge"][0]
    assert query["redirect_uri"] == ["http://localhost:5000/api/auth/google/callback"]
    # Actual Authlib validation, with no provider network call for mismatched state.
    response = client.get("/api/auth/google/callback?code=bad&state=bad")
    assert response.status_code == 401
    assert response.json["error"]["code"] == "oauth_failed"


def test_google_identity_never_autolinks_email(app, client):
    account = signup(client).json["user"]
    claims = {
        "iss": "https://accounts.google.com",
        "sub": "new-google-subject",
        "email": "owner@example.com",
        "email_verified": True,
    }
    with app.app_context():
        with pytest.raises(APIError, match="explicitly link") as error:
            resolve_identity("google", claims)
        assert error.value.code == "account_link_required"
        user = resolve_identity("google", claims, account["id"])
        db.session.commit()
        assert str(user.id) == account["id"]
        # Subsequent login resolves immutable identity even if the email has changed.
        assert resolve_identity("google", {**claims, "email": "changed@example.com"}).id == user.id
        other = User(email="other@example.com")
        db.session.add(other)
        db.session.commit()
        with pytest.raises(APIError) as conflict:
            resolve_identity("google", claims, str(other.id))
        assert conflict.value.code == "identity_in_use"


def test_unverified_google_email_and_microsoft_issuer_policies(app):
    tenant = "11111111-2222-3333-4444-555555555555"
    consumer = "9188040d-6c67-4c5b-b112-36a304b66dad"
    original = app.config["MICROSOFT_TENANT"]
    with app.app_context():
        with pytest.raises(APIError) as error:
            resolve_identity(
                "google",
                {
                    "iss": "https://accounts.google.com",
                    "sub": "subject",
                    "email": "x@example.com",
                    "email_verified": False,
                },
            )
        assert error.value.code == "unverified_email"
        assert valid_microsoft_issuer(
            {"tid": tenant}, f"https://login.microsoftonline.com/{tenant}/v2.0"
        )
        assert not valid_microsoft_issuer({"tid": tenant}, "https://attacker.example")
        assert not valid_microsoft_issuer(
            {"tid": "bad"}, "https://login.microsoftonline.com/bad/v2.0"
        )
        try:
            app.config["MICROSOFT_TENANT"] = "organizations"
            assert not valid_microsoft_issuer(
                {"tid": consumer}, f"https://login.microsoftonline.com/{consumer}/v2.0"
            )
            app.config["MICROSOFT_TENANT"] = tenant
            assert not valid_microsoft_issuer(
                {"tid": consumer}, f"https://login.microsoftonline.com/{consumer}/v2.0"
            )
        finally:
            app.config["MICROSOFT_TENANT"] = original


def test_link_requires_csrf_and_expired_flow_is_rejected(app, client, google):
    signup(client)
    assert client.post("/api/auth/google/link").status_code == 401
    assert client.post("/api/auth/google/link", headers=web_headers(client)).status_code == 302
    with client.session_transaction() as state:
        state["oauth_flow"] = {
            **state["oauth_flow"],
            "started": int((now() - timedelta(minutes=11)).timestamp()),
        }
    assert client.get("/api/auth/google/callback?code=bad&state=bad").status_code == 401


def test_new_oauth_account_creates_entitlement(app):
    from promptengine.models import Entitlement

    with app.app_context():
        user = resolve_identity(
            "google",
            {
                "iss": "https://accounts.google.com",
                "sub": "fresh",
                "email": "fresh@example.com",
                "email_verified": True,
            },
        )
        db.session.commit()
        assert db.session.get(Entitlement, user.id).daily_ai_limit == 10
        assert db.session.scalar(db.select(OAuthIdentity).where(OAuthIdentity.user_id == user.id))


@pytest.fixture
def signed_google_token(google):
    import json
    import time

    import jwt as pyjwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(pyjwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    public["kid"] = "test-provider-key"
    google.server_metadata.update(
        jwks={"keys": [public]}, id_token_signing_alg_values_supported=["RS256"]
    )

    def sign(overrides=None, signing_key=None):
        claims = {
            "iss": "https://accounts.google.com",
            "sub": "signed-google-subject",
            "aud": "test-google-client",
            "nonce": "expected-nonce",
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
            "email": "signed@example.com",
            "email_verified": True,
            **(overrides or {}),
        }
        return {
            "id_token": pyjwt.encode(
                claims, signing_key or key, algorithm="RS256", headers={"kid": "test-provider-key"}
            )
        }

    return sign


def test_actual_oidc_signature_audience_nonce_expiry_and_issuer(app, google, signed_google_token):
    import time

    from cryptography.hazmat.primitives.asymmetric import rsa
    from joserfc.errors import JoseError
    from joserfc.errors import JoseError as JOSEVerificationError

    with app.app_context():
        claims = google.parse_id_token(signed_google_token(), nonce="expected-nonce")
        assert claims["sub"] == "signed-google-subject"
        for overrides in [
            {"aud": "attacker-app"},
            {"nonce": "wrong"},
            {"iss": "https://attacker.example"},
            {"exp": int(time.time()) - 300},
        ]:
            with pytest.raises((JoseError, JOSEVerificationError)):
                google.parse_id_token(signed_google_token(overrides), nonce="expected-nonce")
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with pytest.raises((JoseError, JOSEVerificationError)):
            google.parse_id_token(
                signed_google_token(signing_key=other_key), nonce="expected-nonce"
            )


def test_callback_with_real_signed_id_token_and_replay_rejection(
    client, google, signed_google_token, monkeypatch
):
    # Substitute only the external HTTPS response. Actual state + ID-token validation still run.
    response = client.get("/api/auth/google/login")
    query = parse_qs(urlparse(response.location).query)
    nonce, state = query["nonce"][0], query["state"][0]
    monkeypatch.setattr(
        google, "fetch_access_token", lambda **kwargs: signed_google_token({"nonce": nonce})
    )
    callback = f"/api/auth/google/callback?code=fixture-provider-code&state={state}"
    response = client.get(callback)
    assert response.status_code == 302
    assert response.location == "http://localhost:5173/workspace"
    assert client.get("/api/auth/me").json["user"]["email"] == "signed@example.com"
    assert client.get(callback).status_code == 401


def test_actual_microsoft_signed_token_checks_tenant_issuer_and_audience(
    app, google, signed_google_token
):
    from joserfc.errors import JoseError
    from joserfc.errors import JoseError as JOSEVerificationError

    previous = {key: app.config[key] for key in ["MICROSOFT_CLIENT_ID", "MICROSOFT_CLIENT_SECRET"]}
    app.config.update(
        MICROSOFT_CLIENT_ID="test-ms-client", MICROSOFT_CLIENT_SECRET="test-ms-secret"
    )
    register_oauth(app)
    tenant = "11111111-2222-3333-4444-555555555555"
    from promptengine.oauth_routes import oidc_claims_options

    def options():
        return oidc_claims_options("microsoft", "test-ms-client")

    try:
        with app.app_context():
            microsoft = oauth.create_client("microsoft")
            microsoft.server_metadata.update(
                issuer="https://login.microsoftonline.com/{tenantid}/v2.0",
                jwks=google.server_metadata["jwks"],
                id_token_signing_alg_values_supported=["RS256"],
                _loaded_at=now().timestamp(),
            )
            claims = {
                "iss": f"https://login.microsoftonline.com/{tenant}/v2.0",
                "tid": tenant,
                "aud": "test-ms-client",
                "sub": "ms-subject",
            }
            assert (
                microsoft.parse_id_token(
                    signed_google_token(claims),
                    nonce="expected-nonce",
                    claims_options=options(),
                )["sub"]
                == "ms-subject"
            )
            for overrides in [
                {"iss": "https://attacker.example"},
                {"tid": "bad"},
                {"aud": "other-client", "azp": "test-ms-client"},
            ]:
                with pytest.raises((JoseError, JOSEVerificationError)):
                    microsoft.parse_id_token(
                        signed_google_token({**claims, **overrides}),
                        nonce="expected-nonce",
                        claims_options=options(),
                    )
    finally:
        app.config.update(previous)
