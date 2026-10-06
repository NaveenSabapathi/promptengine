import os
from datetime import timedelta
from urllib.parse import urlparse
from uuid import UUID


def configuration():
    environment = os.getenv("APP_ENV", "production")
    if environment not in {"production", "development", "test"}:
        raise RuntimeError("APP_ENV must be production, development or test")
    development = environment in {"development", "test"}
    origin = os.getenv("WEB_ORIGIN", "http://localhost:5173" if development else "")
    api_origin = os.getenv("API_ORIGIN", "http://localhost:5000" if development else origin)
    secret = os.getenv("SECRET_KEY", "")
    jwt_secret = os.getenv("JWT_SECRET_KEY", "")
    database = os.getenv("DATABASE_URL", "")
    if len(secret) < 32 or len(jwt_secret) < 32 or secret == jwt_secret:
        raise RuntimeError(
            "Set distinct SECRET_KEY and JWT_SECRET_KEY values of at least 32 characters"
        )
    if not database.startswith("postgresql+psycopg://"):
        raise RuntimeError("DATABASE_URL must use postgresql+psycopg://; SQLite is not supported")
    for value in (origin, api_origin):
        parsed = urlparse(value)
        if (
            not parsed.netloc
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.scheme not in {"http", "https"}
        ):
            raise RuntimeError("WEB_ORIGIN and API_ORIGIN must be plain HTTP(S) origins")
        if not development and parsed.scheme != "https":
            raise RuntimeError("Production requires HTTPS origins")
    if not development and origin.rstrip("/") != api_origin.rstrip("/"):
        raise RuntimeError("Production web and API must share one origin")
    tenant = os.getenv("MICROSOFT_TENANT", "common")
    if tenant not in {"common", "organizations", "consumers"}:
        UUID(tenant)
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    if model not in {"gpt-4o-mini", "gpt-4o-mini-2024-07-18"}:
        raise RuntimeError("OPENAI_MODEL must be gpt-4o-mini or its approved snapshot")
    timeout = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "20"))
    if not 1 <= timeout <= 25:
        raise RuntimeError("OPENAI_TIMEOUT_SECONDS must be between 1 and 25")
    billing_enabled = os.getenv("BILLING_ENABLED", "false").lower()
    if billing_enabled not in {"true", "false"}:
        raise RuntimeError("BILLING_ENABLED must be true or false")
    pro_limit = int(os.getenv("PRO_DAILY_AI_LIMIT", "100"))
    pro_price = int(os.getenv("PRO_PRICE_PAISE", "49900"))
    total_count = int(os.getenv("RAZORPAY_TOTAL_COUNT", "120"))
    if (
        not 10 < pro_limit <= 10000
        or not 100 <= pro_price <= 100000000
        or not 1 <= total_count <= 1200
    ):
        raise RuntimeError("Invalid Pro quota, price or billing-cycle configuration")
    from cryptography.fernet import Fernet

    for name in ("TOTP_ENCRYPTION_KEY", "DATASET_ENCRYPTION_KEY"):
        value = os.getenv(name, "")
        if value:
            try:
                Fernet(value.encode())
            except (ValueError, TypeError) as exc:
                raise RuntimeError(f"{name} must be a valid Fernet key") from exc
    if os.getenv("DATASET_ENABLED", "false").lower() == "true" and not os.getenv(
        "DATASET_ENCRYPTION_KEY"
    ):
        raise RuntimeError("DATASET_ENABLED requires DATASET_ENCRYPTION_KEY")
    return {
        "TOTP_ENCRYPTION_KEY": os.getenv("TOTP_ENCRYPTION_KEY", ""),
        "DATASET_ENCRYPTION_KEY": os.getenv("DATASET_ENCRYPTION_KEY", ""),
        "DATASET_ENABLED": os.getenv("DATASET_ENABLED", "false").lower() == "true",
        "MAIL_HOOK_URL": os.getenv("MAIL_HOOK_URL", ""),
        "MAIL_HOOK_SECRET": os.getenv("MAIL_HOOK_SECRET", ""),
        "APP_ENV": environment,
        "SECRET_KEY": secret,
        "JWT_SECRET_KEY": jwt_secret,
        "SQLALCHEMY_DATABASE_URI": database,
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "SQLALCHEMY_ENGINE_OPTIONS": {"pool_pre_ping": True},
        "MAX_CONTENT_LENGTH": 65536,
        "JWT_TOKEN_LOCATION": ["cookies"],
        "JWT_COOKIE_SECURE": not development,
        "JWT_COOKIE_SAMESITE": "Lax",
        "JWT_COOKIE_CSRF_PROTECT": True,
        "JWT_ACCESS_COOKIE_PATH": "/api",
        "JWT_ACCESS_TOKEN_EXPIRES": timedelta(hours=12),
        "JWT_ENCODE_ISSUER": "promptengine",
        "JWT_DECODE_ISSUER": "promptengine",
        "JWT_ENCODE_AUDIENCE": "promptengine-web",
        "JWT_DECODE_AUDIENCE": "promptengine-web",
        "SESSION_COOKIE_SECURE": not development,
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "PERMANENT_SESSION_LIFETIME": timedelta(minutes=10),
        "WEB_ORIGIN": origin.rstrip("/"),
        "API_ORIGIN": api_origin.rstrip("/"),
        "GOOGLE_CLIENT_ID": os.getenv("GOOGLE_CLIENT_ID", ""),
        "GOOGLE_CLIENT_SECRET": os.getenv("GOOGLE_CLIENT_SECRET", ""),
        "MICROSOFT_CLIENT_ID": os.getenv("MICROSOFT_CLIENT_ID", ""),
        "MICROSOFT_CLIENT_SECRET": os.getenv("MICROSOFT_CLIENT_SECRET", ""),
        "MICROSOFT_TENANT": tenant,
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
        "OPENAI_MODEL": model,
        "OPENAI_TIMEOUT_SECONDS": timeout,
        "OPENAI_MAX_OUTPUT_TOKENS": 4096,
        "MAX_TASK_TOKENS": 12000,
        "BILLING_ENABLED": billing_enabled == "true",
        "RAZORPAY_KEY_ID": os.getenv("RAZORPAY_KEY_ID", ""),
        "RAZORPAY_KEY_SECRET": os.getenv("RAZORPAY_KEY_SECRET", ""),
        "RAZORPAY_PRO_PLAN_ID": os.getenv("RAZORPAY_PRO_PLAN_ID", ""),
        "RAZORPAY_WEBHOOK_SECRET": os.getenv("RAZORPAY_WEBHOOK_SECRET", ""),
        "RAZORPAY_TOTAL_COUNT": total_count,
        "PRO_DAILY_AI_LIMIT": pro_limit,
        "PRO_PRICE_PAISE": pro_price,
        "FREE_DAILY_AI_LIMIT": 10,
        "EXTENSION_TOKEN_DAYS": 30,
        "TRUST_PROXY": os.getenv("TRUST_PROXY", "false").lower() == "true",
    }
