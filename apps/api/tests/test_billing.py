import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from urllib.parse import urlparse
from uuid import UUID

import pytest
import requests
from conftest import signup, web_headers

from promptengine.extensions import db
from promptengine.models import (
    BillingPayment,
    BillingSubscription,
    BillingWebhook,
    Entitlement,
    UsageLedger,
)
from promptengine.security import new_extension_token, now

SECRET = "fixture-webhook-secret-only"


@pytest.fixture
def billing_provider(app, monkeypatch):
    # Use the real Razorpay SDK and signature verifier; replace only external HTTPS transport.
    values = {
        "BILLING_ENABLED": True,
        "RAZORPAY_KEY_ID": "rzp_test_fixture",
        "RAZORPAY_KEY_SECRET": "fixture-key-secret",
        "RAZORPAY_WEBHOOK_SECRET": SECRET,
        "RAZORPAY_PRO_PLAN_ID": "plan_fixture",
        "PRO_PRICE_PAISE": 49900,
        "PRO_DAILY_AI_LIMIT": 100,
    }
    originals = {key: app.config[key] for key in values}
    app.config.update(values)
    state = {
        "requests": [],
        "creates": 0,
        "timeout_create": False,
        "wrong_price": False,
        "subscriptions": {},
        "cancel_status": "cancelled",
    }

    def send(session, request, **kwargs):
        path = urlparse(request.url).path
        body = json.loads(request.body) if request.body else {}
        state["requests"].append((request.method, path, body, kwargs.get("timeout")))
        if path == "/v1/plans/plan_fixture":
            data = {
                "id": "plan_fixture",
                "period": "monthly",
                "interval": 1,
                "item": {"amount": 10 if state["wrong_price"] else 49900, "currency": "INR"},
            }
        elif path == "/v1/subscriptions":
            state["creates"] += 1
            if state["timeout_create"]:
                raise requests.Timeout("fixture timeout")
            remote = f"sub_fixture{state['creates']}"
            data = {
                "id": remote,
                "plan_id": "plan_fixture",
                "status": "created",
                "short_url": "https://rzp.io/i/fixture",
                "notes": body["notes"],
            }
            state["subscriptions"][remote] = data
        elif request.method == "GET" and path.startswith("/v1/subscriptions/sub_"):
            data = state["subscriptions"][path.split("/")[-1]]
        elif path.endswith("/cancel"):
            remote = path.split("/")[-2]
            data = {**state["subscriptions"][remote], "status": state["cancel_status"]}
        else:
            raise AssertionError(f"Unexpected provider endpoint {path}")
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(data).encode()
        response.headers["Content-Type"] = "application/json"
        response.request = request
        return response

    monkeypatch.setattr(requests.Session, "send", send)
    yield state
    app.config.update(originals)


def checkout(client):
    return client.post(
        "/api/billing/subscribe", json={"plan_tier": "pro"}, headers=web_headers(client)
    )


def event_for(subscription, event="subscription.charged", offset=0, payment_id="pay_fixture"):
    subscription_id = subscription["razorpay_subscription_id"]
    timestamp = int(now().timestamp()) + offset
    entity = {
        "id": subscription_id,
        "plan_id": "plan_fixture",
        "customer_id": "cust_fixture",
        "status": "active" if event.endswith("charged") else event.split(".")[1],
        "current_end": int((now() + timedelta(days=30)).timestamp()),
    }
    return {
        "event": event,
        "created_at": timestamp,
        "payload": {
            "subscription": {"entity": entity},
            "payment": {
                "entity": {
                    "id": payment_id,
                    "status": "captured",
                    "amount": 49900,
                    "currency": "INR",
                }
            },
        },
    }


def send_event(client, event, event_id="evt_fixture", signature=None):
    body = json.dumps(event, ensure_ascii=False).encode()
    signed = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        "/api/webhooks/razorpay",
        data=body,
        content_type="application/json",
        headers={"X-Razorpay-Signature": signature or signed, "X-Razorpay-Event-Id": event_id},
    )


def test_free_launch_blocks_checkout_and_keeps_local_features(app, client):
    signup(client)
    response = checkout(client)
    assert response.status_code == 403
    plans = client.get("/api/billing/plans").json
    assert plans["billing_enabled"] is False
    assert plans["plans"][0]["daily_ai_limit"] == 10
    assert plans["plans"][0]["custom_presets"] is True


def test_checkout_real_sdk_reuses_subscription_and_requires_csrf(app, client, billing_provider):
    signup(client)
    assert client.post("/api/billing/subscribe", json={"plan_tier": "pro"}).status_code == 401
    response = checkout(client)
    assert response.status_code == 201
    assert response.json["subscription"]["checkout_url"].startswith("https://rzp.io/")
    assert client.get("/api/billing/status").json["plan_tier"] == "free"
    assert checkout(client).status_code == 200
    assert billing_provider["creates"] == 1
    method, path, payload, timeout = [
        row for row in billing_provider["requests"] if row[1] == "/v1/subscriptions"
    ][0]
    assert payload["plan_id"] == "plan_fixture"
    assert payload["quantity"] == 1 and payload["total_count"] == 120
    assert payload["customer_notify"] is False
    assert timeout == (5, 15)
    assert payload["notes"]["promptengine_checkout_id"] == response.json["subscription"]["id"]


def test_wrong_plan_price_never_creates_a_subscription(app, client, billing_provider):
    signup(client)
    billing_provider["wrong_price"] = True
    assert checkout(client).status_code == 503
    assert billing_provider["creates"] == 0
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(BillingSubscription)) == 0


def test_creation_timeout_does_not_create_duplicate_checkouts(app, client, billing_provider):
    signup(client)
    billing_provider["timeout_create"] = True
    assert checkout(client).status_code == 503
    assert client.get("/api/billing/status").json["subscription"]["status"] == "uncertain"
    assert checkout(client).status_code == 409
    assert billing_provider["creates"] == 1


def test_signature_required_and_verified_over_exact_body(app, client, billing_provider):
    assert (
        client.post("/api/webhooks/razorpay", json={"event": "subscription.charged"}).status_code
        == 401
    )
    assert (
        send_event(client, {"event": "subscription.charged"}, signature="0" * 64).status_code == 401
    )
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(BillingWebhook)) == 0


def test_charge_upgrades_limits_preserves_daily_usage_and_duplicate_payment_is_safe(
    app, client, billing_provider
):
    user_id = UUID(signup(client).json["user"]["id"])
    subscription = checkout(client).json["subscription"]
    with app.app_context():
        db.session.add(UsageLedger(user_id=user_id, date=now().date(), ai_requests_count=9))
        db.session.commit()
    charged = event_for(subscription)
    assert send_event(client, charged).json["outcome"] == "applied"
    usage = client.get("/api/usage").json
    assert usage["plan_tier"] == "pro" and usage["daily_ai_limit"] == 100 and usage["used"] == 9
    assert send_event(client, charged).json["duplicate"] is True
    assert send_event(client, charged, "changed_header").json["duplicate"] is True
    repeated = {**charged, "created_at": charged["created_at"] + 1}
    assert (
        send_event(client, repeated, "new_event_same_payment").json["outcome"]
        == "payment_duplicate"
    )
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(BillingPayment)) == 1
        assert db.session.get(Entitlement, user_id).razorpay_customer_id == "cust_fixture"


@pytest.mark.parametrize(
    "event",
    [
        "subscription.cancelled",
        "subscription.halted",
        "subscription.completed",
        "subscription.expired",
    ],
)
def test_downgrades_and_stale_charges_do_not_restore_pro(client, billing_provider, event):
    signup(client)
    subscription = checkout(client).json["subscription"]
    assert send_event(client, event_for(subscription), "charge").status_code == 200
    assert (
        send_event(client, event_for(subscription, event, offset=10), "downgrade").status_code
        == 200
    )
    assert client.get("/api/usage").json["plan_tier"] == "free"
    late = event_for(subscription, offset=1, payment_id="pay_late")
    assert send_event(client, late, "late_charge").json["outcome"] == "stale"
    assert client.get("/api/usage").json["daily_ai_limit"] == 10


def test_halted_subscription_can_recover_with_new_captured_charge(client, billing_provider):
    signup(client)
    subscription = checkout(client).json["subscription"]
    send_event(client, event_for(subscription), "charge")
    send_event(client, event_for(subscription, "subscription.halted", offset=1), "halt")
    recovered = event_for(subscription, offset=2, payment_id="pay_recovered")
    assert send_event(client, recovered, "recovery").json["outcome"] == "applied"
    assert client.get("/api/usage").json["plan_tier"] == "pro"


def test_terminal_subscription_never_reactivates_even_with_newer_charge(client, billing_provider):
    signup(client)
    subscription = checkout(client).json["subscription"]
    send_event(client, event_for(subscription, "subscription.cancelled"), "cancel")
    assert (
        send_event(client, event_for(subscription, offset=1), "late").json["outcome"] == "terminal"
    )
    assert client.get("/api/usage").json["plan_tier"] == "free"


def test_unknown_subscription_rolls_back_receipt_for_retry(app, client, billing_provider):
    event = event_for({"razorpay_subscription_id": "sub_unknown"})
    assert send_event(client, event).status_code == 503
    with app.app_context():
        assert db.session.get(BillingWebhook, "evt_fixture") is None


def test_early_webhook_recovers_durable_checkout_binding(app, client, billing_provider):
    user_id = UUID(signup(client).json["user"]["id"])
    with app.app_context():
        record = BillingSubscription(
            user_id=user_id, plan_id="plan_fixture", amount_paise=49900, status="uncertain"
        )
        db.session.add(record)
        db.session.commit()
        local_id = str(record.id)
    event = event_for({"razorpay_subscription_id": "sub_early"})
    event["payload"]["subscription"]["entity"]["notes"] = {"promptengine_checkout_id": local_id}
    assert send_event(client, event).status_code == 200
    assert client.get("/api/usage").json["plan_tier"] == "pro"


def test_concurrent_duplicate_events_apply_only_once(app, client, billing_provider):
    signup(client)
    subscription = checkout(client).json["subscription"]
    event = event_for(subscription)

    def deliver(_):
        with app.test_client() as separate:
            return send_event(separate, event).json

    with ThreadPoolExecutor(max_workers=6) as workers:
        results = list(workers.map(deliver, range(6)))
    assert sum(value.get("outcome") == "applied" for value in results) == 1
    assert sum(value.get("duplicate", False) for value in results) == 5


def test_cancel_at_cycle_end_keeps_access_until_confirmed_cancel(client, billing_provider):
    signup(client)
    subscription = checkout(client).json["subscription"]
    send_event(client, event_for(subscription), "charge")
    billing_provider["cancel_status"] = "active"
    response = client.post(
        "/api/billing/cancel", json={"at_cycle_end": True}, headers=web_headers(client)
    )
    assert response.status_code == 200
    assert client.get("/api/usage").json["plan_tier"] == "pro"
    billing_provider["cancel_status"] = "cancelled"
    response = client.post(
        "/api/billing/cancel", json={"at_cycle_end": False}, headers=web_headers(client)
    )
    assert response.status_code == 200
    assert client.get("/api/usage").json["plan_tier"] == "free"


def test_billing_routes_are_web_only_and_cross_account_data_is_hidden(
    app, client, billing_provider
):
    user_id = UUID(signup(client).json["user"]["id"])
    checkout(client)
    other = app.test_client()
    signup(other, "other@example.com")
    assert other.get("/api/billing/status").json["subscription"] is None
    with app.app_context():
        token, _record = new_extension_token(user_id, "extension")
        db.session.commit()
    assert (
        other.get("/api/billing/status", headers={"Authorization": "Bearer " + token}).status_code
        == 403
    )


@pytest.mark.parametrize("field,value", [("plan_id", "plan_other"), ("status", "authenticated")])
def test_mismatched_subscription_never_grants_pro(client, billing_provider, field, value):
    signup(client)
    subscription = checkout(client).json["subscription"]
    event = event_for(subscription)
    event["payload"]["subscription"]["entity"][field] = value
    assert send_event(client, event).status_code == 400
    assert client.get("/api/usage").json["plan_tier"] == "free"


def test_reconciliation_cli_binds_uncertain_checkout_without_granting_pro(
    app, client, billing_provider
):
    user_id = UUID(signup(client).json["user"]["id"])
    with app.app_context():
        record = BillingSubscription(
            user_id=user_id, plan_id="plan_fixture", amount_paise=49900, status="uncertain"
        )
        db.session.add(record)
        db.session.commit()
        local_id = str(record.id)
    billing_provider["subscriptions"]["sub_recovered"] = {
        "id": "sub_recovered",
        "plan_id": "plan_fixture",
        "status": "active",
        "notes": {"promptengine_checkout_id": local_id},
        "short_url": "https://rzp.io/i/recovered",
    }
    result = app.test_cli_runner().invoke(args=["reconcile-checkout", local_id, "sub_recovered"])
    assert result.exit_code == 0, result.output
    assert client.get("/api/billing/status").json["subscription"]["status"] == "active"
    assert client.get("/api/usage").json["plan_tier"] == "free"
    send_event(client, event_for({"razorpay_subscription_id": "sub_recovered"}), "recover_charge")
    assert client.get("/api/usage").json["plan_tier"] == "pro"


def test_same_event_id_different_body_is_rejected_without_changing_access(client, billing_provider):
    signup(client)
    subscription = checkout(client).json["subscription"]
    assert send_event(client, event_for(subscription), "same_event").status_code == 200
    changed = event_for(subscription, "subscription.halted", offset=1)
    assert send_event(client, changed, "same_event").status_code == 409
    assert client.get("/api/usage").json["plan_tier"] == "pro"


def test_old_subscription_webhook_does_not_downgrade_new_subscription(client, billing_provider):
    signup(client)
    old = checkout(client).json["subscription"]
    send_event(client, event_for(old, "subscription.cancelled"), "cancel_old")
    new = checkout(client).json["subscription"]
    assert new["id"] != old["id"]
    send_event(client, event_for(new, payment_id="pay_new"), "charge_new")
    late = event_for(old, "subscription.cancelled", offset=10)
    assert send_event(client, late, "old_cancel_redelivery").json["outcome"] == "superseded"
    assert client.get("/api/usage").json["plan_tier"] == "pro"


def test_concurrent_checkouts_only_create_one_remote_subscription(app, client, billing_provider):
    signup(client)
    access = client.get_cookie("access_token_cookie", path="/api").value
    csrf = client.get_cookie("csrf_access_token").value

    def start(_):
        with app.test_client() as separate:
            separate.set_cookie("access_token_cookie", access, path="/api")
            separate.set_cookie("csrf_access_token", csrf)
            return checkout(separate).status_code

    with ThreadPoolExecutor(max_workers=3) as workers:
        results = list(workers.map(start, range(3)))
    assert results.count(201) == 1
    assert set(results) <= {200, 201, 409}
    assert billing_provider["creates"] == 1
