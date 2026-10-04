from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID

from conftest import signup, web_headers

from promptengine.entitlements import reserve_ai_request
from promptengine.errors import APIError
from promptengine.extensions import db
from promptengine.models import Entitlement, UsageLedger
from promptengine.security import now


def test_concurrent_atomic_quota_never_exceeds_limit(app, client):
    user_id = UUID(signup(client).json["user"]["id"])

    def reserve(_):
        with app.app_context():
            try:
                reserve_ai_request(user_id)
                return "accepted"
            except APIError as error:
                return error.code

    with ThreadPoolExecutor(max_workers=12) as workers:
        results = list(workers.map(reserve, range(30)))
    assert results.count("accepted") == 10
    assert results.count("quota_exceeded") == 20
    with app.app_context():
        assert db.session.get(UsageLedger, (user_id, now().date())).ai_requests_count == 10


def test_failed_execution_refunds_quota_and_success_consumes_it(app, client):
    signup(client)
    assert client.post("/api/test/ai-fail", headers=web_headers(client)).status_code == 503
    assert client.get("/api/usage").json["used"] == 0
    assert client.post("/api/test/ai", headers=web_headers(client)).status_code == 200
    assert client.get("/api/usage").json["used"] == 1


def test_expired_pro_falls_back_to_free_and_new_day_resets(app, client):
    user_id = UUID(signup(client).json["user"]["id"])
    with app.app_context():
        entitlement = db.session.get(Entitlement, user_id)
        entitlement.plan_tier = "pro"
        entitlement.daily_ai_limit = 1000
        entitlement.expires_at = now() - timedelta(seconds=1)
        db.session.add(
            UsageLedger(
                user_id=user_id, date=now().date() - timedelta(days=1), ai_requests_count=100
            )
        )
        db.session.commit()
    usage = client.get("/api/usage").json
    assert usage["plan_tier"] == "free"
    assert usage["daily_ai_limit"] == 10
    assert usage["used"] == 0
