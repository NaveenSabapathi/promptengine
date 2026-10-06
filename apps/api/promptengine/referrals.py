"""Promotional access is separate from subscription state; all rewards are atomic."""

import re
import secrets
from datetime import timedelta

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy.dialects.postgresql import insert

from .errors import APIError
from .extensions import db
from .models import Coupon, CouponRedemption, Entitlement, Referral, ReferralBalance, User
from .security import code_digest, json_body, now, rate_limit, requires_auth, text_field

bp = Blueprint("referrals", __name__, url_prefix="/api/rewards")


def extend_access(user_id, days):
    entitlement = db.session.scalar(
        db.select(Entitlement)
        .where(Entitlement.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    base = max(now(), entitlement.bonus_expires_at or now(), entitlement.expires_at or now())
    entitlement.bonus_expires_at = base + timedelta(days=days)


def grant(referral, kind):
    db.session.execute(
        insert(ReferralBalance).values(user_id=referral.referrer_id).on_conflict_do_nothing()
    )
    balance = db.session.scalar(
        db.select(ReferralBalance)
        .where(ReferralBalance.user_id == referral.referrer_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    field = "registration_days" if kind == "registration" else "conversion_days"
    cap, reward = (30, 3) if kind == "registration" else (50, 10)
    days = min(reward, cap - getattr(balance, field))
    if days:
        extend_access(referral.referrer_id, days)
        setattr(balance, field, getattr(balance, field) + days)
        setattr(referral, field, days)


def risk_match(referrer, referee, payment=False):
    if (
        not referrer.ip_hash
        or not referee.ip_hash
        or not referrer.device_hash
        or not referee.device_hash
    ):
        return "missing_registration_signals"
    if referrer.ip_hash == referee.ip_hash:
        return "shared_ip"
    if referrer.device_hash == referee.device_hash:
        return "shared_device"
    if payment:
        if not referrer.payment_hash or not referee.payment_hash:
            return "missing_verified_payment_fingerprint"
        if referrer.payment_hash == referee.payment_hash:
            return "shared_payment_method"
    return None


def register_referral(user, data):
    # HMAC hashes use a domain separator; device IDs are risk signals, never identity proof.
    user.ip_hash = code_digest("referral-ip:" + (request.remote_addr or "unknown"))
    device = data.get("device_id")
    if isinstance(device, str) and re.fullmatch(r"[A-Za-z0-9_-]{16,100}", device):
        user.device_hash = code_digest("referral-device:" + device)
    code = data.get("referral_code")
    if not code:
        return
    if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{20,32}", code):
        raise APIError("invalid_referral", "Referral link is invalid")
    referrer = db.session.scalar(db.select(User).where(User.referral_code == code))
    if not referrer or referrer.id == user.id:
        raise APIError("invalid_referral", "Referral link is unavailable")
    reason = risk_match(referrer, user)
    row = Referral(
        referrer_id=referrer.id, referee_id=user.id, status="registered", blocked_reason=reason
    )
    db.session.add(row)
    if not reason:
        grant(row, "registration")


def payment_fingerprint(payment):
    # Accept only verified webhook fields, never values supplied by the browser.
    # A provider card fingerprint or UPI VPA is required; card IDs are not globally
    # stable fingerprints and therefore are deliberately insufficient.
    fingerprint = (
        payment.get("card", {}).get("fingerprint")
        if isinstance(payment.get("card"), dict)
        else None
    )
    method = "card"
    if payment.get("method") == "upi" and isinstance(payment.get("vpa"), str):
        fingerprint, method = payment["vpa"].strip().lower(), "upi"
    if isinstance(fingerprint, str) and 3 <= len(fingerprint) <= 200:
        return code_digest("referral-payment:" + method + ":" + fingerprint)
    return None


def paid_conversion(user_id, payment):
    # Called exclusively after signature, captured amount, subscription binding,
    # chronology and payment deduplication checks inside the webhook transaction.
    referee = db.session.get(User, user_id)
    referee.payment_hash = payment_fingerprint(payment)
    row = db.session.scalar(
        db.select(Referral).where(Referral.referee_id == user_id).with_for_update()
    )
    if not row or row.status == "converted":
        return
    referrer = db.session.get(User, row.referrer_id)
    row.blocked_reason = risk_match(referrer, referee, payment=True)
    if row.blocked_reason:
        return
    grant(row, "conversion")
    row.status = "converted"


@bp.get("")
@requires_auth(web_only=True)
def rewards():
    user = db.session.scalar(db.select(User).where(User.id == g.user.id).with_for_update())
    if not user.referral_code:
        user.referral_code = secrets.token_urlsafe(18)
    balance = db.session.get(ReferralBalance, user.id)
    db.session.commit()
    return jsonify(
        referral_url=current_app.config["WEB_ORIGIN"] + "/signup?ref=" + user.referral_code,
        registration_days=balance.registration_days if balance else 0,
        conversion_days=balance.conversion_days if balance else 0,
    )


@bp.post("/redeem")
@requires_auth(web_only=True)
def redeem():
    rate_limit("coupon_redeem", 10, seconds=300, identity=str(g.user.id))
    code = text_field(json_body(), "code", 16, 16).upper()
    coupon = db.session.scalar(db.select(Coupon).where(Coupon.code == code).with_for_update())
    if not coupon or coupon.expires_at <= now() or coupon.current_uses >= coupon.max_uses:
        raise APIError("coupon_unavailable", "Coupon is expired or unavailable", 409)
    existing = db.session.scalar(
        db.select(CouponRedemption).where(
            CouponRedemption.coupon_id == coupon.id, CouponRedemption.user_id == g.user.id
        )
    )
    if existing:
        raise APIError("coupon_used", "This account has already redeemed the coupon", 409)
    # Monetary coupons reserve a real provider plan for the next checkout. They
    # never grant access before Razorpay confirms the captured payment.
    row = CouponRedemption(coupon_id=coupon.id, user_id=g.user.id)
    db.session.add(row)
    coupon.current_uses += 1
    if coupon.discount_type == "days_extension":
        extend_access(g.user.id, coupon.days_granted)
    db.session.commit()
    return jsonify(
        redemption_id=str(row.id),
        discount_type=coupon.discount_type,
        days_granted=coupon.days_granted,
        message="Access extended"
        if coupon.discount_type == "days_extension"
        else "Discount reserved; choose it at checkout",
    ), 201
