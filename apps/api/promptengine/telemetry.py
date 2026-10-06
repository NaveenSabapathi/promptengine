from time import monotonic

from flask import g, request
from sqlalchemy import text
from sqlalchemy.orm import Session

from .extensions import db
from .models import ApiRequestMetric


def register_telemetry(app):
    @app.before_request
    def start():
        g.request_start = monotonic()

    @app.after_request
    def record(response):
        if not request.path.startswith("/api/") or request.path.startswith("/api/health/"):
            return response
        # Independent transaction: never commit a business handler's pending writes.
        # Metrics contain route templates, not URLs, user content, or credentials.
        try:
            with Session(db.engine) as session:
                session.execute(text("SET LOCAL statement_timeout = '1000ms'"))
                session.add(
                    ApiRequestMetric(
                        route=str(request.url_rule or "unmatched")[:120],
                        status=response.status_code,
                        latency_ms=max(0, round((monotonic() - g.request_start) * 1000)),
                        provider_latency_ms=g.get("provider_latency_ms"),
                    )
                )
                session.commit()
        except Exception as exc:
            app.logger.warning("Telemetry persistence unavailable (%s)", type(exc).__name__)
        return response
