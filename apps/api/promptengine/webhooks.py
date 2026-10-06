import hashlib
import json
import re
from uuid import UUID

import razorpay
from flask import Blueprint, current_app, jsonify, request
from razorpay.errors import SignatureVerificationError
from sqlalchemy.dialects.postgresql import insert

from .billing import downgrade, lock_entitlement, timestamp
from .errors import APIError
from .extensions import db
from .models import BillingPayment, BillingSubscription, BillingWebhook
from .security import now

bp = Blueprint("webhooks", __name__, url_prefix="/api/webhooks")
EVENTS = {
    "subscription.charged",
    "subscription.cancelled",
    "subscription.halted",
    "subscription.completed",
    "subscription.expired",
}


def signed_payload():
    secret = current_app.config["RAZORPAY_WEBHOOK_SECRET"]
    if not secret:
        raise APIError("webhook_not_configured", "Webhook processing is unavailable", 503)
    raw = request.get_data(cache=True)
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", signature):
        raise APIError("invalid_signature", "Invalid webhook signature", 401)
    try:
        body = raw.decode("utf-8")
        razorpay.Client().utility.verify_webhook_signature(body, signature.lower(), secret)
    except (SignatureVerificationError, UnicodeDecodeError) as exc:
        raise APIError("invalid_signature", "Invalid webhook signature", 401) from exc
    try:
        data = json.loads(body)
    except ValueError as exc:
        raise APIError("invalid_webhook", "Webhook must contain valid JSON") from exc
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("event"), str)
        or len(data["event"]) > 80
    ):
        raise APIError("invalid_webhook", "Invalid webhook event")
    payload_hash = hashlib.sha256(raw).hexdigest()
    event_id = request.headers.get("X-Razorpay-Event-Id") or "body_" + payload_hash
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", event_id):
        raise APIError("invalid_webhook", "Invalid webhook identifier")
    return data, payload_hash, event_id


def subscription_entity(data):
    payload = data.get("payload")
    if not isinstance(payload, dict):
        raise APIError("invalid_webhook", "Subscription payload is required")
    nested = payload.get("subscription")
    entity = nested.get("entity") if isinstance(nested, dict) else None
    if not isinstance(entity, dict):
        raise APIError("invalid_webhook", "Subscription entity is required")
    remote_id = entity.get("id")
    if not isinstance(remote_id, str) or not remote_id.startswith("sub_") or len(remote_id) > 100:
        raise APIError("invalid_webhook", "Invalid subscription identifier")
    return entity


def bind_subscription(entity):
    record = db.session.scalar(
        db.select(BillingSubscription).where(
            BillingSubscription.razorpay_id == entity["id"],
        )
    )
    if not record:
        notes = entity.get("notes", {})
        try:
            attempt_id = UUID(notes.get("promptengine_checkout_id", ""))
        except (ValueError, TypeError, AttributeError) as exc:
            # An early signed webhook may precede checkout persistence. Retry, don't lose it.
            raise APIError(
                "subscription_unknown", "Subscription needs reconciliation", 503
            ) from exc
        record = db.session.get(BillingSubscription, attempt_id)
    if not record:
        raise APIError("subscription_unknown", "Subscription needs reconciliation", 503)
    user_id = record.user_id
    entitlement = lock_entitlement(user_id)
    record = db.session.scalar(
        db.select(BillingSubscription)
        .where(
            BillingSubscription.id == record.id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if entity.get("plan_id") != record.plan_id or (
        record.razorpay_id is not None and record.razorpay_id != entity["id"]
    ):
        raise APIError("subscription_mismatch", "Subscription does not match configured checkout")
    if record.razorpay_id is None:
        if record.status not in {"creating", "uncertain"}:
            raise APIError("subscription_mismatch", "Checkout cannot be bound to this subscription")
        record.razorpay_id = entity["id"]
        entitlement.razorpay_subscription_id = entity["id"]
    return record, entitlement


def apply_event(data, receipt):
    entity = subscription_entity(data)
    event_at = data.get("created_at")
    timestamp(event_at)
    record, entitlement = bind_subscription(entity)
    receipt.subscription_id = entity["id"]
    if entitlement.razorpay_subscription_id != entity["id"]:
        return "superseded"
    if event_at < record.last_event_at:
        return "stale"
    event = data["event"]
    if event == "subscription.charged":
        if record.status in {"cancelled", "completed", "expired", "failed"}:
            return "terminal"
        # A downgrade wins over a charge at the same timestamp (event ordering is not guaranteed).
        if event_at == record.last_event_at and record.status == "halted":
            return "stale"
        end = timestamp(entity.get("current_end"))
        if end <= now() or (record.current_end is not None and end < record.current_end):
            return "expired_period"
        payment_part = data.get("payload", {}).get("payment", {})
        payment = payment_part.get("entity") if isinstance(payment_part, dict) else None
        if (
            not isinstance(payment, dict)
            or payment.get("status") != "captured"
            or entity.get("status") != "active"
            or payment.get("currency") != record.currency
            or not isinstance(payment.get("amount"), int)
            or isinstance(payment["amount"], bool)
            or payment["amount"] < record.amount_paise
        ):
            raise APIError("invalid_payment", "A captured plan payment is required")
        payment_id = payment.get("id")
        if (
            not isinstance(payment_id, str)
            or not payment_id.startswith("pay_")
            or len(payment_id) > 100
        ):
            raise APIError("invalid_payment", "Invalid payment identifier")
        previous = db.session.get(BillingPayment, payment_id)
        if previous:
            if previous.subscription_id != record.id:
                raise APIError("payment_mismatch", "Payment belongs to another subscription")
            return "payment_duplicate"
        db.session.add(
            BillingPayment(
                payment_id=payment_id, subscription_id=record.id, amount_paise=payment["amount"]
            )
        )
        customer_id = entity.get("customer_id")
        if customer_id is not None:
            if (
                not isinstance(customer_id, str)
                or not customer_id.startswith("cust_")
                or len(customer_id) > 100
            ):
                raise APIError("invalid_webhook", "Invalid customer identifier")
            entitlement.razorpay_customer_id = customer_id
        record.status, record.current_end = "active", end
        entitlement.plan_tier = "pro"
        entitlement.daily_ai_limit = current_app.config["PRO_DAILY_AI_LIMIT"]
        entitlement.expires_at = end
        from .referrals import paid_conversion

        paid_conversion(record.user_id, payment)
        # Preserve actual daily usage; an upgrade changes the limit rather than erasing the ledger.
    else:
        new_status = event.split(".", 1)[1]
        if record.status in {"cancelled", "completed", "expired"} and new_status == "halted":
            return "terminal"
        record.status = new_status
        downgrade(entitlement)
    record.last_event_at = event_at
    return "applied"


@bp.post("/razorpay")
def razorpay_webhook():
    data, payload_hash, event_id = signed_payload()
    # Both event ID and body digest are deduplicated in the same transaction as entitlement updates.
    inserted = db.session.execute(
        insert(BillingWebhook)
        .values(
            event_id=event_id,
            payload_hash=payload_hash,
            event_type=data["event"],
            outcome="processing",
        )
        .on_conflict_do_nothing()
        .returning(BillingWebhook.event_id)
    ).scalar_one_or_none()
    if not inserted:
        existing = db.session.get(BillingWebhook, event_id)
        if existing and existing.payload_hash != payload_hash:
            raise APIError(
                "event_id_conflict", "Webhook identifier conflicts with an existing event", 409
            )
        db.session.rollback()
        return jsonify(ok=True, duplicate=True)
    receipt = db.session.get(BillingWebhook, event_id)
    receipt.outcome = apply_event(data, receipt) if data["event"] in EVENTS else "ignored"
    db.session.commit()
    return jsonify(ok=True, outcome=receipt.outcome)
