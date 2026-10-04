import click
from flask import Flask, g, jsonify, request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import configuration
from .errors import APIError, error_response
from .extensions import db, jwt, migrate, oauth


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(configuration())
    if test_config:
        app.config.update(test_config)
    if app.config["TRUST_PROXY"]:
        # Enable only behind a single trusted reverse proxy; no public direct API access.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=0)
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    oauth.init_app(app)

    from . import auth, generation, oauth_routes, pairing, prompts
    from .entitlements import effective_entitlement
    from .models import ExtensionToken, PairingRequest, RateLimitBucket, UsageLedger, WebSession
    from .security import now, requires_auth

    oauth_routes.register_oauth(app)
    for blueprint in (auth.bp, oauth_routes.bp, pairing.bp, prompts.bp, generation.bp):
        app.register_blueprint(blueprint)

    @app.errorhandler(APIError)
    def api_error(error):
        db.session.rollback()
        return error_response(error.code, error.message, error.status)

    @app.errorhandler(HTTPException)
    def http_error(error):
        db.session.rollback()
        return error_response(error.name.lower().replace(" ", "_"), error.description, error.code)

    @app.errorhandler(SQLAlchemyError)
    def database_error(error):
        db.session.rollback()
        app.logger.error("Database operation failed (%s)", type(error).__name__)
        return error_response("database_unavailable", "Service temporarily unavailable", 503)

    @app.errorhandler(Exception)
    def unexpected_error(error):
        db.session.rollback()
        # Do not log exception messages containing SQL parameters, credentials or prompt content.
        app.logger.error("Unhandled API error (%s)", type(error).__name__)
        return error_response("internal_error", "An unexpected error occurred", 500)

    @jwt.unauthorized_loader
    def missing_jwt(_reason):
        return error_response("unauthorized", "Sign in to continue", 401)

    @jwt.invalid_token_loader
    def invalid_jwt(_reason):
        return error_response("unauthorized", "Invalid session", 401)

    @jwt.expired_token_loader
    def expired_jwt(_header, _payload):
        return error_response("session_expired", "Session expired; sign in again", 401)

    @app.after_request
    def secure_response(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        if app.config["APP_ENV"] == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # Production is same-origin. Only the explicitly configured development UI receives CORS.
        origin = request.headers.get("Origin")
        if origin == app.config["WEB_ORIGIN"]:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-CSRF-TOKEN"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response.vary.add("Origin")
        return response

    @app.get("/api/health/live")
    def liveness():
        return jsonify(status="ok")

    @app.get("/api/health/ready")
    def readiness():
        # Verify the schema, not only the TCP connection. Migrations run separately.
        db.session.execute(text("SELECT 1 FROM entitlements LIMIT 1"))
        return jsonify(status="ok")

    @app.get("/api/usage")
    @requires_auth("usage:read")
    def usage():
        from .models import Entitlement

        day = now().date()
        entitlement = db.session.get(Entitlement, g.user.id)
        tier, limit = effective_entitlement(entitlement)
        record = db.session.get(UsageLedger, (g.user.id, day))
        used = record.ai_requests_count if record else 0
        return jsonify(
            date=day.isoformat(),
            timezone="UTC",
            plan_tier=tier,
            daily_ai_limit=limit,
            used=used,
            remaining=max(0, limit - used),
        )

    @app.cli.command("warm-tokenizer")
    def warm_tokenizer():
        """Cache the model vocabulary before serving requests; no task data is sent."""
        from .compiler import tokenizer

        click.echo(tokenizer(app.config["OPENAI_MODEL"]).name)

    @app.cli.command("cleanup-auth")
    def cleanup_auth():
        """Run daily to remove expired authentication and rate-limit records."""
        instant = now()
        for model in (PairingRequest, ExtensionToken, WebSession, RateLimitBucket):
            db.session.execute(db.delete(model).where(model.expires_at <= instant))
        db.session.commit()
        click.echo("Expired authentication records removed")

    return app
