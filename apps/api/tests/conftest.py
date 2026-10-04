import os

import pytest
from flask import jsonify
from flask_migrate import upgrade

from promptengine import create_app
from promptengine.entitlements import requires_entitlement
from promptengine.errors import APIError
from promptengine.extensions import db
from promptengine.security import requires_auth

ORIGIN = "http://localhost:5173"
PASSWORD = "a-correct-long-test-password"


@pytest.fixture(scope="session")
def app():
    database = os.environ.get("TEST_DATABASE_URL")
    if not database or "test" not in database.rsplit("/", 1)[-1]:
        pytest.fail(
            "Set TEST_DATABASE_URL to a dedicated PostgreSQL database whose name contains 'test'"
        )
    os.environ.update(
        APP_ENV="test",
        SECRET_KEY="session-tests-only-secret-with-at-least-32-chars",
        JWT_SECRET_KEY="jwt-tests-only-distinct-secret-with-at-least-32-chars",
        DATABASE_URL=database,
        WEB_ORIGIN=ORIGIN,
        API_ORIGIN="http://localhost:5000",
    )
    application = create_app({"TESTING": True})

    @application.post("/api/test/ai")
    @requires_auth("refine")
    @requires_entitlement
    def test_execution():
        return jsonify(ok=True)

    @application.post("/api/test/ai-fail")
    @requires_auth("refine")
    @requires_entitlement
    def test_failed_execution():
        raise APIError("provider_unavailable", "Provider timed out", 503)

    with application.app_context():
        upgrade(directory="migrations")
    yield application
    with application.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture(autouse=True)
def clean_database(app):
    with app.app_context():
        tables = ", ".join(f'"{table.name}"' for table in db.metadata.sorted_tables)
        db.session.execute(db.text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
        db.session.commit()
    yield


@pytest.fixture
def client(app):
    return app.test_client()


def signup(client, email="owner@example.com"):
    return client.post(
        "/api/auth/signup", json={"email": email, "password": PASSWORD}, headers={"Origin": ORIGIN}
    )


def web_headers(client):
    cookie = client.get_cookie("csrf_access_token")
    return {"Origin": ORIGIN, "X-CSRF-TOKEN": cookie.value if cookie else ""}
