"""Load explicitly configured file secrets without exposing their contents."""

import os
from pathlib import Path
from urllib.parse import quote

SECRET_NAMES = (
    "SECRET_KEY",
    "JWT_SECRET_KEY",
    "TOTP_ENCRYPTION_KEY",
    "DATASET_ENCRYPTION_KEY",
    "MAIL_HOOK_SECRET",
    "DATABASE_URL",
    "OPENAI_API_KEY",
    "GOOGLE_CLIENT_SECRET",
    "MICROSOFT_CLIENT_SECRET",
    "RAZORPAY_KEY_SECRET",
    "RAZORPAY_WEBHOOK_SECRET",
)


def load_file_secrets():
    for name in SECRET_NAMES:
        filename = os.getenv(name + "_FILE")
        if not filename:
            continue
        if os.getenv(name):
            raise RuntimeError(f"Configure only {name} or {name}_FILE")
        try:
            value = Path(filename).read_text().strip()
        except (OSError, UnicodeError):
            raise RuntimeError(f"Cannot read {name}_FILE") from None
        if "\x00" in value or "\n" in value or "\r" in value:
            raise RuntimeError(f"{name}_FILE must contain a single line")
        os.environ[name] = value

    # Official PostgreSQL image and API share this password file. Encode it before
    # constructing a SQLAlchemy URL; punctuation cannot change URL semantics.
    filename = os.getenv("POSTGRES_PASSWORD_FILE")
    if filename:
        if os.getenv("DATABASE_URL"):
            raise RuntimeError("Configure DATABASE_URL or POSTGRES_PASSWORD_FILE, not both")
        try:
            password = Path(filename).read_text().strip()
        except (OSError, UnicodeError):
            raise RuntimeError("Cannot read POSTGRES_PASSWORD_FILE") from None
        if not password or any(c in password for c in "\x00\n\r"):
            raise RuntimeError("POSTGRES_PASSWORD_FILE must contain one nonempty line")
        os.environ["DATABASE_URL"] = (
            "postgresql+psycopg://promptengine:"
            + quote(password, safe="")
            + "@db:5432/promptengine"
        )
