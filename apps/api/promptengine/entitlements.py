from functools import wraps

from flask import current_app, g
from sqlalchemy.dialects.postgresql import insert

from .errors import APIError
from .extensions import db
from .models import Entitlement, UsageLedger
from .security import now


def effective_entitlement(entitlement):
    if entitlement is None:
        raise APIError("entitlement_missing", "Account entitlement is unavailable", 503)
    if (
        entitlement.override_tier
        and entitlement.override_limit
        and entitlement.override_expires_at
        and entitlement.override_expires_at > now()
    ):
        return entitlement.override_tier, entitlement.override_limit
    if entitlement.bonus_expires_at and entitlement.bonus_expires_at > now():
        return "pro", current_app.config["PRO_DAILY_AI_LIMIT"]
    if (
        entitlement.plan_tier == "pro"
        and entitlement.expires_at is not None
        and entitlement.expires_at <= now()
    ):
        return "free", current_app.config["FREE_DAILY_AI_LIMIT"]
    return entitlement.plan_tier, entitlement.daily_ai_limit


def reserve_ai_request(user_id):
    # Serializes quota reservations and entitlement updates for this user, across all workers.
    entitlement = db.session.scalar(
        db.select(Entitlement)
        .where(
            Entitlement.user_id == user_id,
        )
        .with_for_update()
    )
    _, limit = effective_entitlement(entitlement)
    day = now().date()  # The documented billing/quota boundary is UTC midnight.
    statement = insert(UsageLedger).values(user_id=user_id, date=day, ai_requests_count=1)
    statement = statement.on_conflict_do_update(
        index_elements=[UsageLedger.user_id, UsageLedger.date],
        set_={"ai_requests_count": UsageLedger.ai_requests_count + 1},
        where=UsageLedger.ai_requests_count < limit,
    ).returning(UsageLedger.ai_requests_count)
    count = db.session.execute(statement).scalar_one_or_none()
    if count is None:
        db.session.rollback()
        raise APIError("quota_exceeded", "Daily AI request limit reached; resets at 00:00 UTC", 429)
    # Reserve before external execution; never hold a lock during the AI call.
    db.session.commit()
    return day, count, limit


def release_ai_request(user_id, day):
    db.session.rollback()
    db.session.execute(
        db.update(UsageLedger)
        .where(
            UsageLedger.user_id == user_id,
            UsageLedger.date == day,
            UsageLedger.ai_requests_count > 0,
        )
        .values(ai_requests_count=UsageLedger.ai_requests_count - 1)
    )
    db.session.commit()


def requires_entitlement(function):
    """Apply inside @requires_auth('refine'); validation must precede this decorator.

    Phase 2 will call this only after payload validation. Failed executions release
    their reservation. Process termination can conservatively consume a slot.
    """

    @wraps(function)
    def wrapped(*args, **kwargs):
        user_id = g.user.id
        day, count, limit = reserve_ai_request(user_id)
        g.ai_usage = {"date": day.isoformat(), "used": count, "limit": limit}
        try:
            response = current_app.make_response(function(*args, **kwargs))
            if response.status_code >= 400:
                release_ai_request(user_id, day)
            return response
        except Exception:
            release_ai_request(user_id, day)
            raise

    return wrapped
