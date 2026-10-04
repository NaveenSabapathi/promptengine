from datetime import timedelta
from uuid import UUID

from conftest import ORIGIN, PASSWORD, signup, web_headers
from flask_jwt_extended import decode_token

from promptengine.extensions import db
from promptengine.models import Entitlement, WebSession
from promptengine.security import now


def test_signup_login_csrf_logout_and_revocation(app, client):
    response = signup(client, "Owner@EXAMPLE.com")
    assert response.status_code == 201
    assert response.json["user"]["email"] == "owner@example.com"
    token = client.get_cookie("access_token_cookie", path="/api").value
    assert "HttpOnly" in response.headers.getlist("Set-Cookie")[0]
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/logout", headers={"Origin": ORIGIN}).status_code == 401
    assert client.post("/api/auth/logout", headers=web_headers(client)).status_code == 200
    stolen = app.test_client()
    stolen.set_cookie("access_token_cookie", token, path="/api")
    assert stolen.get("/api/auth/me").status_code == 401
    login = client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": PASSWORD},
        headers={"Origin": ORIGIN},
    )
    assert login.status_code == 200
    with app.app_context():
        user_id = UUID(login.json["user"]["id"])
        assert db.session.get(Entitlement, user_id).daily_ai_limit == 10


def test_invalid_credentials_and_duplicate_signup(client):
    assert signup(client).status_code == 201
    assert signup(client).status_code == 409
    for email in ["owner@example.com", "missing@example.com"]:
        response = client.post(
            "/api/auth/login",
            json={"email": email, "password": "wrong"},
            headers={"Origin": ORIGIN},
        )
        assert response.status_code == 401
        assert response.json["error"]["code"] == "invalid_credentials"


def test_input_validation_origin_and_login_throttle(client):
    assert signup(client).status_code == 201
    assert client.post("/api/auth/login", json={}).status_code == 403
    assert (
        client.post(
            "/api/auth/login", json={}, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert (
        client.post("/api/auth/login", data="oops", headers={"Origin": ORIGIN}).status_code == 415
    )
    assert client.post("/api/auth/login", json=[], headers={"Origin": ORIGIN}).status_code == 400
    assert (
        client.post(
            "/api/auth/signup",
            json={"email": "bad", "password": PASSWORD},
            headers={"Origin": ORIGIN},
        ).status_code
        == 400
    )
    for _ in range(10):
        assert (
            client.post(
                "/api/auth/login",
                json={"email": "x@example.com", "password": "wrong"},
                headers={"Origin": ORIGIN},
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/auth/login",
            json={"email": "x@example.com", "password": "wrong"},
            headers={"Origin": ORIGIN},
        ).status_code
        == 429
    )


def test_expired_server_session_is_rejected(app, client):
    signup(client)
    with app.app_context():
        claims = decode_token(client.get_cookie("access_token_cookie", path="/api").value)
        record = db.session.get(WebSession, UUID(claims["sid"]))
        record.expires_at = now() - timedelta(seconds=1)
        db.session.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_production_cookies_secure_and_untrusted_origin_no_cors(app, client):
    original = app.config["JWT_COOKIE_SECURE"]
    app.config["JWT_COOKIE_SECURE"] = True
    try:
        response = signup(client)
        assert response.status_code == 201
        assert "Secure" in response.headers.getlist("Set-Cookie")[0]
    finally:
        app.config["JWT_COOKIE_SECURE"] = original
    response = client.get("/api/health/live", headers={"Origin": "https://evil.example"})
    assert "Access-Control-Allow-Origin" not in response.headers


def test_configuration_rejects_insecure_production(monkeypatch):
    import pytest

    from promptengine.config import configuration

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("WEB_ORIGIN", "http://example.com")
    monkeypatch.setenv("API_ORIGIN", "http://example.com")
    with pytest.raises(RuntimeError, match="HTTPS"):
        configuration()
    monkeypatch.setenv("WEB_ORIGIN", "https://example.com")
    monkeypatch.setenv("API_ORIGIN", "https://example.com")
    assert configuration()["JWT_COOKIE_SECURE"] is True
    monkeypatch.setenv("DATABASE_URL", "sqlite:///app.db")
    with pytest.raises(RuntimeError, match="PostgreSQL|postgresql"):
        configuration()
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user@localhost/test")
    monkeypatch.setenv("JWT_SECRET_KEY", "short")
    with pytest.raises(RuntimeError, match="secret|SECRET"):
        configuration()
