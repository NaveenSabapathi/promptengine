from datetime import UTC, datetime, timedelta

import click
from flask import Blueprint, current_app, g, jsonify
from razorpay.errors import BadRequestError, GatewayError, ServerError
from requests.exceptions import RequestException

from .entitlements import effective_entitlement
from .errors import APIError
from .extensions import db
from .models import BillingSubscription, Coupon, CouponRedemption, Entitlement
from .razorpay_provider import checkout_url, provider_client, require_checkout, verified_plan
from .security import json_body, now, rate_limit, requires_auth

bp = Blueprint("billing", __name__, url_prefix="/api/billing")
TERMINAL = {"failed", "cancelled", "completed", "expired"}


def subscription_payload(record):
    if not record:
        return None
    return {
        "id": str(record.id),
        "razorpay_subscription_id": record.razorpay_id,
        "status": record.status,
        "checkout_url": record.checkout_url,
        "current_end": record.current_end.isoformat() if record.current_end else None,
        "cancel_at_cycle_end": record.cancel_at_cycle_end,
        "amount_paise": record.amount_paise,
        "currency": record.currency,
    }


def lock_entitlement(user_id):
    record = db.session.scalar(
        db.select(Entitlement)
        .where(
            Entitlement.user_id == user_id,
        )
        .with_for_update()
    )
    if not record:
        raise APIError("entitlement_missing", "Account entitlement is unavailable", 503)
    return record


def downgrade(entitlement):
    entitlement.plan_tier = "free"
    entitlement.daily_ai_limit = current_app.config["FREE_DAILY_AI_LIMIT"]
    entitlement.expires_at = None


@bp.get("/plans")
def plans():
    return jsonify(
        billing_enabled=current_app.config["BILLING_ENABLED"],
        plans=[
            {
                "tier": "free",
                "amount_paise": 0,
                "currency": "INR",
                "daily_ai_limit": current_app.config["FREE_DAILY_AI_LIMIT"],
                "local_compiling": True,
                "custom_presets": not current_app.config["BILLING_ENABLED"],
            },
            {
                "tier": "pro",
                "amount_paise": current_app.config["PRO_PRICE_PAISE"],
                "currency": "INR",
                "period": "monthly",
                "daily_ai_limit": current_app.config["PRO_DAILY_AI_LIMIT"],
                "local_compiling": True,
                "custom_presets": True,
            },
        ],
    )


@bp.get("/status")
@requires_auth(web_only=True)
def status():
    entitlement = db.session.get(Entitlement, g.user.id)
    tier, limit = effective_entitlement(entitlement)
    record = db.session.scalar(
        db.select(BillingSubscription)
        .where(
            BillingSubscription.user_id == g.user.id,
        )
        .order_by(BillingSubscription.created_at.desc())
        .limit(1)
    )
    return jsonify(
        plan_tier=tier,
        daily_ai_limit=limit,
        billing_enabled=current_app.config["BILLING_ENABLED"],
        subscription=subscription_payload(record),
    )


@bp.post("/subscribe")
@requires_auth(web_only=True)
def subscribe():
    require_checkout()
    data = json_body()
    if data.get("plan_tier") != "pro" or set(data) - {"plan_tier", "redemption_id"}:
        raise APIError(
            "invalid_plan", "Send plan_tier: pro and an optional redeemed discount identifier"
        )
    user_id = g.user.id
    rate_limit("subscribe", 5, identity=str(user_id))
    with provider_client() as client:
        verified_plan(client)  # No paid plan or price comes from client input.
        # Re-verify a discounted provider plan before obtaining business locks.
        if data.get("redemption_id"):
            from .security import uuid_field

            probe = db.session.get(CouponRedemption, uuid_field(data["redemption_id"]))
            if not probe or probe.user_id != user_id or probe.subscription_id:
                raise APIError("coupon_unavailable", "Discount is unavailable", 409)
            discount_probe = db.session.get(Coupon, probe.coupon_id)
            if not discount_probe.razorpay_plan_id or discount_probe.expires_at <= now():
                raise APIError("coupon_unavailable", "Discount is unavailable", 409)
            try:
                discounted = client.plan.fetch(discount_probe.razorpay_plan_id)
            except (RequestException, BadRequestError, GatewayError, ServerError) as exc:
                raise APIError(
                    "billing_unavailable", "Unable to verify discount price", 503
                ) from exc
            item = discounted.get("item", {})
            if (
                discounted.get("id") != discount_probe.razorpay_plan_id
                or discounted.get("period") != "monthly"
                or discounted.get("interval") != 1
                or item.get("amount") != discount_probe.amount_paise
                or item.get("currency") != "INR"
            ):
                raise APIError("discount_plan_mismatch", "Discount plan needs review", 503)
        entitlement = lock_entitlement(user_id)
        existing = db.session.scalar(
            db.select(BillingSubscription).where(
                BillingSubscription.user_id == user_id,
                BillingSubscription.status.not_in(TERMINAL),
            )
        )
        if existing:
            if existing.status in {"created", "authenticated"} and existing.checkout_url:
                return jsonify(subscription=subscription_payload(existing)), 200
            raise APIError(
                "subscription_exists", "A subscription is active or needs reconciliation", 409
            )
        plan_id, amount = (
            current_app.config["RAZORPAY_PRO_PLAN_ID"],
            current_app.config["PRO_PRICE_PAISE"],
        )
        redemption = None
        if data.get("redemption_id"):
            from .security import uuid_field

            redemption = db.session.scalar(
                db.select(CouponRedemption)
                .where(
                    CouponRedemption.id == uuid_field(data["redemption_id"]),
                    CouponRedemption.user_id == user_id,
                )
                .with_for_update()
            )
            if not redemption or redemption.subscription_id:
                raise APIError("coupon_unavailable", "Discount is unavailable", 409)
            discount = db.session.get(Coupon, redemption.coupon_id)
            if discount.discount_type == "days_extension" or discount.expires_at <= now():
                raise APIError("coupon_unavailable", "Discount is unavailable", 409)
            plan_id, amount = discount.razorpay_plan_id, discount.amount_paise
        record = BillingSubscription(user_id=user_id, plan_id=plan_id, amount_paise=amount)
        db.session.add(record)
        db.session.flush()
        if redemption:
            redemption.subscription_id = record.id
        attempt_id, plan_id = record.id, record.plan_id
        previous_remote_id = entitlement.razorpay_subscription_id
        db.session.commit()  # Durable attempt; no DB transaction during provider creation.
        try:
            result = client.subscription.create(
                {
                    "plan_id": plan_id,
                    "quantity": 1,
                    "total_count": current_app.config["RAZORPAY_TOTAL_COUNT"],
                    "customer_notify": False,
                    "expire_by": int((now() + timedelta(days=1)).timestamp()),
                    "notes": {"promptengine_checkout_id": str(attempt_id)},
                }
            )
            remote_id = result.get("id")
            if (
                not isinstance(remote_id, str)
                or not remote_id.startswith("sub_")
                or len(remote_id) > 100
                or result.get("plan_id") != plan_id
            ):
                raise APIError(
                    "billing_invalid_response",
                    "Billing provider returned an invalid subscription",
                    502,
                )
            link = checkout_url(result.get("short_url"))
        except BadRequestError as exc:
            db.session.rollback()
            lock_entitlement(user_id)
            record = db.session.get(BillingSubscription, attempt_id, populate_existing=True)
            if record.status == "creating":
                record.status = "failed"
            db.session.commit()
            raise APIError(
                "billing_rejected", "Billing provider rejected checkout; contact support", 503
            ) from exc
        except (RequestException, GatewayError, ServerError, APIError) as exc:
            db.session.rollback()
            lock_entitlement(user_id)
            record = db.session.get(BillingSubscription, attempt_id, populate_existing=True)
            if record.status == "creating":
                record.status = "uncertain"
                db.session.commit()
            raise APIError(
                "billing_uncertain", "Checkout needs reconciliation; do not retry payment", 503
            ) from exc
        # A webhook can arrive before this response; keep any state it already applied.
        entitlement = lock_entitlement(user_id)
        record = db.session.get(BillingSubscription, attempt_id, populate_existing=True)
        if record.razorpay_id and record.razorpay_id != remote_id:
            raise APIError("billing_conflict", "Subscription needs reconciliation", 503)
        record.razorpay_id, record.checkout_url = remote_id, link
        if record.status == "creating":
            record.status = "created"
        if entitlement.razorpay_subscription_id in {previous_remote_id, remote_id}:
            entitlement.razorpay_subscription_id = remote_id
        db.session.commit()
        return jsonify(subscription=subscription_payload(record)), 201


@bp.post("/cancel")
@requires_auth(web_only=True)
def cancel():
    # Existing subscribers can cancel even when new sales have been disabled.
    if not current_app.config["RAZORPAY_KEY_ID"] or not current_app.config["RAZORPAY_KEY_SECRET"]:
        raise APIError("billing_not_configured", "Billing is unavailable; contact support", 503)
    data = json_body()
    if set(data) - {"at_cycle_end"} or not isinstance(data.get("at_cycle_end", True), bool):
        raise APIError("invalid_cancellation", "at_cycle_end must be a boolean")
    at_cycle_end = data.get("at_cycle_end", True)
    user_id = g.user.id
    rate_limit("cancel_subscription", 5, identity=str(user_id))
    entitlement = db.session.get(Entitlement, user_id)
    record = db.session.scalar(
        db.select(BillingSubscription).where(
            BillingSubscription.user_id == user_id,
            BillingSubscription.razorpay_id == entitlement.razorpay_subscription_id,
        )
    )
    if not record or not record.razorpay_id:
        raise APIError("subscription_not_found", "No subscription to cancel", 404)
    if record.status in TERMINAL:
        return jsonify(subscription=subscription_payload(record))
    local_id, remote_id = record.id, record.razorpay_id
    db.session.rollback()
    try:
        with provider_client() as client:
            result = client.subscription.cancel(
                remote_id, {"cancel_at_cycle_end": int(at_cycle_end)}
            )
    except (RequestException, BadRequestError, GatewayError, ServerError) as exc:
        raise APIError(
            "billing_unavailable", "Cancellation could not be confirmed. Try again later", 503
        ) from exc
    if result.get("id") != remote_id or result.get("status") not in {"active", "cancelled"}:
        raise APIError("billing_invalid_response", "Cancellation needs reconciliation", 503)
    entitlement = lock_entitlement(user_id)
    record = db.session.get(BillingSubscription, local_id, populate_existing=True)
    record.cancel_at_cycle_end = at_cycle_end
    if result["status"] == "cancelled":
        record.status = "cancelled"
        record.last_event_at = max(record.last_event_at, int(now().timestamp()))
        if entitlement.razorpay_subscription_id == remote_id:
            downgrade(entitlement)
    db.session.commit()
    return jsonify(subscription=subscription_payload(record))


def timestamp(value):
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 4102444800:
        raise APIError("invalid_webhook", "Invalid subscription timestamp")
    return datetime.fromtimestamp(value, UTC)


def register_commands(app):
    @app.cli.command("reconcile-checkout")
    @click.argument("checkout_id", type=click.UUID)
    @click.argument("subscription_id")
    def reconcile_checkout(checkout_id, subscription_id):
        """Recover an uncertain checkout using its provider ID, without granting paid access."""
        if not subscription_id.startswith("sub_") or len(subscription_id) > 100:
            raise click.ClickException("Invalid provider subscription ID")
        record = db.session.get(BillingSubscription, checkout_id)
        if not record or record.status not in {"creating", "uncertain"}:
            raise click.ClickException("Only a creating/uncertain checkout can be reconciled")
        user_id, plan_id = record.user_id, record.plan_id
        db.session.rollback()
        try:
            with provider_client() as client:
                remote = client.subscription.fetch(subscription_id)
            if (
                remote.get("id") != subscription_id
                or remote.get("plan_id") != plan_id
                or remote.get("notes", {}).get("promptengine_checkout_id") != str(checkout_id)
                or remote.get("status")
                not in {
                    "created",
                    "authenticated",
                    "active",
                    "pending",
                    "halted",
                    "cancelled",
                    "completed",
                    "expired",
                }
            ):
                raise click.ClickException("Provider subscription does not match this checkout")
            link = checkout_url(remote["short_url"]) if remote.get("short_url") else None
            entitlement = lock_entitlement(user_id)
            record = db.session.get(BillingSubscription, checkout_id, populate_existing=True)
            if record.status not in {"creating", "uncertain"}:
                raise click.ClickException("Checkout was already resolved; no change made")
            record.razorpay_id, record.status = subscription_id, remote["status"]
            record.checkout_url = link
            entitlement.razorpay_subscription_id = subscription_id
            if record.status in TERMINAL or record.status == "halted":
                downgrade(entitlement)
                record.last_event_at = int(now().timestamp())
            db.session.commit()
            click.echo("Checkout reconciled. Pro access requires a verified charged webhook.")
        except (RequestException, BadRequestError, GatewayError, ServerError, APIError) as exc:
            db.session.rollback()
            raise click.ClickException("Provider reconciliation failed; no change made") from exc
