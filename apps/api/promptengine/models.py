import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .extensions import db


class User(db.Model):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(db.String(254), unique=True)
    is_admin: Mapped[bool] = mapped_column(db.Boolean, server_default="false")
    totp_secret: Mapped[str | None] = mapped_column(db.Text)
    totp_enabled: Mapped[bool] = mapped_column(db.Boolean, server_default="false")
    totp_last_step: Mapped[int] = mapped_column(db.BigInteger, server_default="-1")
    recovery_hashes: Mapped[list] = mapped_column(JSONB, server_default="[]")
    dataset_consent: Mapped[bool] = mapped_column(db.Boolean, server_default="false")
    consent_version: Mapped[int] = mapped_column(db.Integer, server_default="0")
    referral_code: Mapped[str | None] = mapped_column(db.String(32), unique=True)
    ip_hash: Mapped[str | None] = mapped_column(db.String(64))
    device_hash: Mapped[str | None] = mapped_column(db.String(64))
    payment_hash: Mapped[str | None] = mapped_column(db.String(64))
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
    bonus_expires_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    override_tier: Mapped[str | None] = mapped_column(db.String(16))
    override_limit: Mapped[int | None] = mapped_column(db.Integer)
    override_expires_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    razorpay_customer_id: Mapped[str | None] = mapped_column(db.String(100), unique=True)
    razorpay_subscription_id: Mapped[str | None] = mapped_column(db.String(100), unique=True)
    expires_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("plan_tier IN ('free', 'pro')", name="plan_tier"),
        CheckConstraint("daily_ai_limit > 0", name="positive_limit"),
        CheckConstraint(
            "override_tier IS NULL OR override_tier IN ('free','pro')", name="override_tier"
        ),
        CheckConstraint(
            "override_limit IS NULL OR override_limit BETWEEN 1 AND 10000", name="override_limit"
        ),
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
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), index=True
    )
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
    mfa_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
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
    preset_id: Mapped[str] = mapped_column(db.String(80))
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


class BillingSubscription(db.Model):
    __tablename__ = "billing_subscriptions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    razorpay_id: Mapped[str | None] = mapped_column(db.String(100), unique=True)
    plan_id: Mapped[str] = mapped_column(db.String(100))
    amount_paise: Mapped[int] = mapped_column(db.Integer)
    currency: Mapped[str] = mapped_column(db.String(3), server_default="INR")
    status: Mapped[str] = mapped_column(db.String(20), server_default="creating")
    checkout_url: Mapped[str | None] = mapped_column(db.String(500))
    current_end: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    last_event_at: Mapped[int] = mapped_column(db.BigInteger, server_default="0")
    cancel_at_cycle_end: Mapped[bool] = mapped_column(db.Boolean, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (
        Index("ix_billing_subscriptions_user_created", "user_id", "created_at"),
        Index(
            "uq_billing_subscriptions_open_user",
            "user_id",
            unique=True,
            postgresql_where=db.text(
                "status IN ('creating','uncertain','created','authenticated',"
                "'active','pending','halted')"
            ),
        ),
        CheckConstraint("amount_paise > 0", name="positive_amount"),
        CheckConstraint("currency = 'INR'", name="currency"),
        CheckConstraint(
            "status IN ('creating','uncertain','failed','created','authenticated',"
            "'active','pending','halted','cancelled','completed','expired')",
            name="status",
        ),
    )


class BillingWebhook(db.Model):
    __tablename__ = "billing_webhooks"
    event_id: Mapped[str] = mapped_column(db.String(128), primary_key=True)
    payload_hash: Mapped[str] = mapped_column(db.String(64), unique=True)
    event_type: Mapped[str] = mapped_column(db.String(80))
    subscription_id: Mapped[str | None] = mapped_column(db.String(100))
    outcome: Mapped[str] = mapped_column(db.String(32))
    received_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=func.now()
    )


class BillingPayment(db.Model):
    __tablename__ = "billing_payments"
    payment_id: Mapped[str] = mapped_column(db.String(100), primary_key=True)
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("billing_subscriptions.id", ondelete="CASCADE"), index=True
    )
    amount_paise: Mapped[int] = mapped_column(db.Integer)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=func.now()
    )


class CustomPreset(db.Model):
    __tablename__ = "custom_presets"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(db.String(100))
    role: Mapped[str] = mapped_column(db.String(200))
    required_fields: Mapped[dict] = mapped_column(db.JSON)
    optional_fields: Mapped[dict] = mapped_column(db.JSON)
    output_constraints: Mapped[list] = mapped_column(db.JSON)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=func.now()
    )


class Team(db.Model):
    __tablename__ = "teams"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(db.String(100))
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=func.now()
    )


class TeamMembership(db.Model):
    __tablename__ = "team_memberships"
    team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(db.String(16), server_default="MEMBER")
    __table_args__ = (
        CheckConstraint("role IN ('OWNER','ADMIN','MEMBER')", name="role"),
        Index("uq_team_owner", "team_id", unique=True, postgresql_where=db.text("role='OWNER'")),
        Index("ix_membership_user", "user_id"),
    )


class TeamInvitation(db.Model):
    __tablename__ = "team_invitations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(db.String(254))
    role: Mapped[str] = mapped_column(db.String(16), server_default="MEMBER")
    token_hash: Mapped[str] = mapped_column(db.String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(db.DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    __table_args__ = (CheckConstraint("role IN ('ADMIN','MEMBER')", name="role"),)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(db.String(80))
    target: Mapped[str] = mapped_column(db.String(100))
    details: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=func.now(), index=True
    )


class ApiRequestMetric(db.Model):
    __tablename__ = "api_request_metrics"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    route: Mapped[str] = mapped_column(db.String(120))
    status: Mapped[int] = mapped_column(db.Integer)
    latency_ms: Mapped[int] = mapped_column(db.Integer)
    provider_latency_ms: Mapped[int | None] = mapped_column(db.Integer)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=func.now(), index=True
    )
    __table_args__ = (
        CheckConstraint("status BETWEEN 100 AND 599 AND latency_ms >= 0", name="metric_valid"),
    )


class Referral(db.Model):
    __tablename__ = "referrals"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    referrer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    referee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[str] = mapped_column(db.String(16), server_default="pending")
    blocked_reason: Mapped[str | None] = mapped_column(db.String(80))
    registration_days: Mapped[int] = mapped_column(db.Integer, server_default="0")
    conversion_days: Mapped[int] = mapped_column(db.Integer, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint("referrer_id <> referee_id", name="no_self_referral"),
        CheckConstraint("status IN ('pending','registered','converted')", name="referral_status"),
        CheckConstraint(
            "registration_days BETWEEN 0 AND 3 AND conversion_days BETWEEN 0 AND 10",
            name="referral_days",
        ),
    )


class ReferralBalance(db.Model):
    __tablename__ = "referral_balances"
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    registration_days: Mapped[int] = mapped_column(db.Integer, server_default="0")
    conversion_days: Mapped[int] = mapped_column(db.Integer, server_default="0")
    __table_args__ = (
        CheckConstraint(
            "registration_days BETWEEN 0 AND 30 AND conversion_days BETWEEN 0 AND 50",
            name="reward_caps",
        ),
    )


class Coupon(db.Model):
    __tablename__ = "coupons"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(db.String(16), unique=True)
    discount_type: Mapped[str] = mapped_column(db.String(20))
    discount_value: Mapped[int] = mapped_column(db.Integer, server_default="0")
    max_uses: Mapped[int] = mapped_column(db.Integer)
    current_uses: Mapped[int] = mapped_column(db.Integer, server_default="0")
    days_granted: Mapped[int] = mapped_column(db.Integer, server_default="0")
    razorpay_plan_id: Mapped[str | None] = mapped_column(db.String(100))
    amount_paise: Mapped[int | None] = mapped_column(db.Integer)
    expires_at: Mapped[datetime] = mapped_column(db.DateTime(timezone=True))
    created_by_admin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint(
            "discount_type IN ('days_extension','percentage','fixed_amount')", name="discount_type"
        ),
        CheckConstraint("max_uses > 0 AND current_uses BETWEEN 0 AND max_uses", name="coupon_uses"),
        CheckConstraint("days_granted BETWEEN 0 AND 365", name="coupon_days"),
        CheckConstraint(
            "(discount_type='days_extension' AND days_granted>0 AND discount_value=0) OR "
            "(discount_type='percentage' AND discount_value BETWEEN 1 AND 99 AND "
            "razorpay_plan_id IS NOT NULL AND amount_paise>0) OR "
            "(discount_type='fixed_amount' AND discount_value>0 AND "
            "razorpay_plan_id IS NOT NULL AND amount_paise>0)",
            name="coupon_value",
        ),
    )


class CouponRedemption(db.Model):
    __tablename__ = "coupon_redemptions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    coupon_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("coupons.id", ondelete="RESTRICT"))
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("billing_subscriptions.id", ondelete="RESTRICT"), unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (UniqueConstraint("coupon_id", "user_id"),)


class MailOutbox(db.Model):
    __tablename__ = "mail_outbox"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient: Mapped[str] = mapped_column(db.String(254))
    subject: Mapped[str] = mapped_column(db.String(200))
    body: Mapped[str] = mapped_column(db.Text)
    attempts: Mapped[int] = mapped_column(db.Integer, server_default="0")
    delivered_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=func.now()
    )


class DatasetJob(db.Model):
    __tablename__ = "dataset_jobs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    consent_version: Mapped[int] = mapped_column(db.Integer)
    encrypted_payload: Mapped[str] = mapped_column(db.Text)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=func.now()
    )


class DatasetPromptLog(db.Model):
    __tablename__ = "dataset_prompt_logs"
    log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    preset_key: Mapped[str] = mapped_column(db.String(80))
    raw_input_context: Mapped[dict] = mapped_column(JSONB)
    final_prompt_output: Mapped[str] = mapped_column(db.Text)
    model_response: Mapped[str] = mapped_column(db.Text)
    token_metrics: Mapped[dict] = mapped_column(JSONB)
    quality_rating: Mapped[int | None] = mapped_column(db.Integer)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), server_default=func.now(), index=True
    )
    __table_args__ = (
        CheckConstraint("quality_rating IS NULL OR quality_rating BETWEEN 1 AND 5", name="rating"),
    )
