import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .extensions import db


class User(db.Model):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(db.String(254), unique=True)
    # NULL only for OAuth-only accounts; never accept a password for them implicitly.
    password_hash: Mapped[str | None] = mapped_column(db.Text)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (CheckConstraint("email = lower(email)", name="email_lowercase"),)


class Entitlement(db.Model):
    __tablename__ = "entitlements"
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    plan_tier: Mapped[str] = mapped_column(db.String(16), server_default="free")
    daily_ai_limit: Mapped[int] = mapped_column(db.Integer, server_default="10")
    razorpay_customer_id: Mapped[str | None] = mapped_column(db.String(100), unique=True)
    razorpay_subscription_id: Mapped[str | None] = mapped_column(db.String(100), unique=True)
    expires_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("plan_tier IN ('free', 'pro')", name="plan_tier"),
        CheckConstraint("daily_ai_limit > 0", name="positive_limit"),
    )


class UsageLedger(db.Model):
    __tablename__ = "usage_ledger"
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    date: Mapped[date] = mapped_column(db.Date, primary_key=True)
    ai_requests_count: Mapped[int] = mapped_column(db.Integer, server_default="0")
    __table_args__ = (CheckConstraint("ai_requests_count >= 0", name="nonnegative_count"),)


class SavedPrompt(db.Model):
    __tablename__ = "saved_prompts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(db.String(200))
    content: Mapped[str] = mapped_column(db.Text)
    tags: Mapped[list[str]] = mapped_column(ARRAY(db.String(50)), server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (
        Index("ix_saved_prompts_user_created", "user_id", "created_at"),
        Index("ix_saved_prompts_tags", "tags", postgresql_using="gin"),
        CheckConstraint("char_length(content) BETWEEN 1 AND 50000", name="content_length"),
        CheckConstraint("char_length(title) BETWEEN 1 AND 200", name="title_length"),
    )


class OAuthIdentity(db.Model):
    __tablename__ = "oauth_identities"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(db.String(16))
    issuer: Mapped[str] = mapped_column(db.String(255))
    subject: Mapped[str] = mapped_column(db.String(255))
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("provider", "issuer", "subject"),
        UniqueConstraint("user_id", "provider"),
        CheckConstraint("provider IN ('google', 'microsoft')", name="provider"),
    )


class WebSession(db.Model):
    __tablename__ = "web_sessions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(db.DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=func.now()
    )


class PairingRequest(db.Model):
    __tablename__ = "pairing_requests"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code_hash: Mapped[str] = mapped_column(db.String(64), unique=True)
    device_secret_hash: Mapped[str] = mapped_column(db.String(64))
    device_name: Mapped[str] = mapped_column(db.String(80))
    expires_at: Mapped[datetime] = mapped_column(db.DateTime(timezone=True), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    approved_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=func.now()
    )


class ExtensionToken(db.Model):
    __tablename__ = "extension_tokens"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(db.String(64), unique=True)
    device_name: Mapped[str] = mapped_column(db.String(80))
    scopes: Mapped[list[str]] = mapped_column(ARRAY(db.String(40)))
    expires_at: Mapped[datetime] = mapped_column(db.DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=func.now()
    )


class RateLimitBucket(db.Model):
    __tablename__ = "rate_limit_buckets"
    key: Mapped[str] = mapped_column(db.String(64), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(db.DateTime(timezone=True), primary_key=True)
    count: Mapped[int] = mapped_column(db.Integer)
    expires_at: Mapped[datetime] = mapped_column(db.DateTime(timezone=True), index=True)
    __table_args__ = (CheckConstraint("count > 0", name="positive_count"),)


class GenerationMetric(db.Model):
    """Successful generation measurements only: never store task or prompt content."""

    __tablename__ = "generation_metrics"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    preset_id: Mapped[str] = mapped_column(db.String(40))
    preset_version: Mapped[str] = mapped_column(db.String(40))
    engine: Mapped[str] = mapped_column(db.String(16))
    mode: Mapped[str] = mapped_column(db.String(16))
    tone: Mapped[str] = mapped_column(db.String(16))
    model: Mapped[str] = mapped_column(db.String(128))
    tokenizer: Mapped[str] = mapped_column(db.String(40))
    raw_tokens: Mapped[int] = mapped_column(db.Integer)
    generated_tokens: Mapped[int] = mapped_column(db.Integer)
    token_difference: Mapped[int] = mapped_column(
        db.Integer, db.Computed("raw_tokens - generated_tokens", persisted=True)
    )
    provider_input_tokens: Mapped[int | None] = mapped_column(db.Integer)
    provider_output_tokens: Mapped[int | None] = mapped_column(db.Integer)
    latency_ms: Mapped[int] = mapped_column(db.Integer)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (
        Index("ix_generation_metrics_user_created", "user_id", "created_at"),
        CheckConstraint("engine IN ('ai', 'local')", name="engine"),
        CheckConstraint("mode IN ('Build', 'Compact')", name="mode"),
        CheckConstraint("raw_tokens > 0 AND generated_tokens > 0", name="positive_tokens"),
        CheckConstraint(
            "provider_input_tokens IS NULL OR provider_input_tokens >= 0", name="input_tokens"
        ),
        CheckConstraint(
            "provider_output_tokens IS NULL OR provider_output_tokens >= 0", name="output_tokens"
        ),
        CheckConstraint("latency_ms >= 0", name="latency"),
    )
