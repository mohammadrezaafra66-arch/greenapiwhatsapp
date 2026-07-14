import uuid, enum
from datetime import datetime, date
from sqlalchemy import String, Integer, Float, Boolean, Date, DateTime, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class AccountStatus(str, enum.Enum):
    active = "active"
    banned = "banned"
    disconnected = "disconnected"
    pending = "pending"
    deleted = "deleted"   # V14 F2 — soft-delete after partner deleteInstanceAccount

class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    instance_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    api_token: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[AccountStatus] = mapped_column(SAEnum(AccountStatus), default=AccountStatus.pending)
    daily_limit: Mapped[int] = mapped_column(Integer, default=50)
    sent_today: Mapped[int] = mapped_column(Integer, default=0)
    received_today: Mapped[int] = mapped_column(Integer, default=0)
    received_yesterday: Mapped[int] = mapped_column(Integer, default=0)
    quick_replies_yesterday: Mapped[int] = mapped_column(Integer, default=0)
    days_active: Mapped[int] = mapped_column(Integer, default=0)
    # V8 Feature 39 — Meta-standard per-account send limits
    max_daily_absolute: Mapped[int] = mapped_column(Integer, default=200)
    incoming_ratio_multiplier: Mapped[float] = mapped_column(Float, default=0.5)
    max_sends_per_minute: Mapped[float] = mapped_column(Float, default=2.0)
    last_reset_date: Mapped[date | None] = mapped_column(Date)
    banned_at: Mapped[datetime | None] = mapped_column(DateTime)
    ban_reason: Mapped[str | None] = mapped_column(Text)
    quota_exceeded_at: Mapped[datetime | None] = mapped_column(DateTime)
    proxy_host: Mapped[str | None] = mapped_column(String(200))
    proxy_port: Mapped[int | None] = mapped_column(Integer)
    proxy_login: Mapped[str | None] = mapped_column(String(100))
    proxy_password: Mapped[str | None] = mapped_column(String(200))
    proxy_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    # V15 Item 26 — managed auto warm-up for new accounts
    auto_warmup: Mapped[bool] = mapped_column(Boolean, default=False)
    warmup_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    warmup_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    # V14 PART F — yellowCard safety (throttle + cooldown)
    throttle_factor: Mapped[float] = mapped_column(Float, default=1.0)
    throttle_until: Mapped[datetime | None] = mapped_column(DateTime)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime)
    incident_count_7d: Mapped[int] = mapped_column(Integer, default=0)
    last_incident_at: Mapped[datetime | None] = mapped_column(DateTime)
    # V14 PART A — Partner-managed instances
    created_via_partner: Mapped[bool] = mapped_column(Boolean, default=False)
    partner_created_at: Mapped[datetime | None] = mapped_column(DateTime)
    profile_picture_url: Mapped[str | None] = mapped_column(Text)
    tariff: Mapped[str | None] = mapped_column(String(40))
    is_orphaned: Mapped[bool] = mapped_column(Boolean, default=False)
    warmup_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    polling_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_reply_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_reply_message: Mapped[str | None] = mapped_column(Text)
    auto_reply_outside_hours: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def computed_daily_limit(self) -> int:
        """Daily send limit following Meta best practices (V8 Feature 39)."""
        days = self.days_active or 0
        absolute = self.max_daily_absolute or 200
        # V14 F23.6 — Green API says the first 10 days are the highest-risk period.
        # During warm-up hard-cap at 5 messages/day (overrides formula + configured limit).
        if days < 10:
            return min(5, absolute)
        base = min(days, 10)
        incoming = min(int((self.received_yesterday or 0) * (self.incoming_ratio_multiplier or 0.5)), 20)
        replies = min((self.quick_replies_yesterday or 0) * 5, 50)
        calculated = base + incoming + replies
        # Never exceed the absolute per-account maximum.
        return min(calculated, absolute)
