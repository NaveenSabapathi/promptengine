from contextlib import contextmanager
from urllib.parse import urlparse

import razorpay
import requests
from flask import current_app
from razorpay.errors import BadRequestError, GatewayError, ServerError

from .errors import APIError


class TimedSession(requests.Session):
    def request(self, *args, **kwargs):
        kwargs.setdefault("timeout", (5, 15))
        return super().request(*args, **kwargs)


@contextmanager
def provider_client():
    with TimedSession() as session:
        yield razorpay.Client(
            session=session,
            auth=(current_app.config["RAZORPAY_KEY_ID"], current_app.config["RAZORPAY_KEY_SECRET"]),
            max_retries=0,
        )


def require_checkout():
    if not current_app.config["BILLING_ENABLED"]:
        raise APIError(
            "billing_disabled", "Paid checkout is not enabled during the free launch", 403
        )
    if not all(
        current_app.config[key]
        for key in (
            "RAZORPAY_KEY_ID",
            "RAZORPAY_KEY_SECRET",
            "RAZORPAY_PRO_PLAN_ID",
            "RAZORPAY_WEBHOOK_SECRET",
        )
    ):
        raise APIError("billing_not_configured", "Billing is unavailable; contact support", 503)


def verified_plan(client):
    try:
        plan = client.plan.fetch(current_app.config["RAZORPAY_PRO_PLAN_ID"])
    except (requests.RequestException, BadRequestError, GatewayError, ServerError) as exc:
        raise APIError(
            "billing_unavailable", "Billing provider is unavailable. Try again later", 503
        ) from exc
    item = plan.get("item", {})
    if (
        plan.get("id") != current_app.config["RAZORPAY_PRO_PLAN_ID"]
        or plan.get("period") != "monthly"
        or plan.get("interval") != 1
        or item.get("amount") != current_app.config["PRO_PRICE_PAISE"]
        or item.get("currency") != "INR"
    ):
        raise APIError(
            "billing_plan_mismatch", "Configured billing plan needs review; contact support", 503
        )
    return plan


def checkout_url(value):
    if not isinstance(value, str) or len(value) > 500:
        raise APIError("billing_invalid_response", "Billing provider returned an invalid link", 502)
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "rzp.io"
        or parsed.username
        or parsed.password
    ):
        raise APIError("billing_invalid_response", "Billing provider returned an invalid link", 502)
    return value
