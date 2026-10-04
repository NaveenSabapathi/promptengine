from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID

from conftest import signup, web_headers

from promptengine.extensions import db
from promptengine.models import ExtensionToken, PairingRequest
from promptengine.security import now


def pair(client, app):
    extension = app.test_client()
    result = extension.post("/api/extension/pairing", json={"device_name": "Chrome on laptop"})
    assert result.status_code == 201
    credentials = {key: result.json[key] for key in ["pairing_id", "code", "device_secret"]}
    signup(client)
    return extension, credentials


def test_full_pairing_and_scopes_revocation(app, client):
    extension, credentials = pair(client, app)
    assert extension.post("/api/extension/pairing/exchange", json=credentials).status_code == 409
    inspect = client.post(
        "/api/extension/pairing/inspect",
        json={"code": credentials["code"]},
        headers=web_headers(client),
    )
    assert inspect.json["device_name"] == "Chrome on laptop"
    assert (
        client.post(
            "/api/extension/pairing/approve",
            json={"code": credentials["code"]},
            headers=web_headers(client),
        ).status_code
        == 200
    )
    wrong = {**credentials, "device_secret": "wrong-secret"}
    assert extension.post("/api/extension/pairing/exchange", json=wrong).status_code == 400
    exchanged = extension.post("/api/extension/pairing/exchange", json=credentials)
    assert exchanged.status_code == 200
    access = exchanged.json
    headers = {"Authorization": "Bearer " + access["access_token"]}
    assert extension.get("/api/usage", headers=headers).status_code == 200
    assert extension.get("/api/auth/me", headers=headers).status_code == 403
    assert (
        extension.post(
            "/api/extension/pairing/approve", json={"code": credentials["code"]}, headers=headers
        ).status_code
        == 403
    )
    assert extension.post("/api/extension/pairing/exchange", json=credentials).status_code == 400
    with app.app_context():
        record = db.session.get(ExtensionToken, UUID(access["token_id"]))
        assert record.token_hash != access["access_token"]
        record.scopes = ["usage:read"]
        db.session.commit()
    assert extension.get("/api/prompts", headers=headers).status_code == 403
    assert (
        client.delete(
            "/api/extension/tokens/" + access["token_id"], headers=web_headers(client)
        ).status_code
        == 200
    )
    assert extension.get("/api/usage", headers=headers).status_code == 401


def test_pairing_expiry_and_csrf(app, client):
    extension, credentials = pair(client, app)
    assert (
        client.post(
            "/api/extension/pairing/approve", json={"code": credentials["code"]}
        ).status_code
        == 401
    )
    with app.app_context():
        record = db.session.get(PairingRequest, UUID(credentials["pairing_id"]))
        record.expires_at = now() - timedelta(seconds=1)
        db.session.commit()
    assert (
        client.post(
            "/api/extension/pairing/approve",
            json={"code": credentials["code"]},
            headers=web_headers(client),
        ).status_code
        == 400
    )
    assert extension.post("/api/extension/pairing/exchange", json=credentials).status_code == 400


def test_concurrent_exchange_only_issues_one_token(app, client):
    _extension, credentials = pair(client, app)
    assert (
        client.post(
            "/api/extension/pairing/approve",
            json={"code": credentials["code"]},
            headers=web_headers(client),
        ).status_code
        == 200
    )

    def exchange(_):
        with app.test_client() as separate_client:
            return separate_client.post(
                "/api/extension/pairing/exchange", json=credentials
            ).status_code

    with ThreadPoolExecutor(max_workers=5) as workers:
        results = list(workers.map(exchange, range(5)))
    assert results.count(200) == 1
    assert results.count(400) == 4
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(ExtensionToken)) == 1
