import uuid, enum
from datetime import datetime, date
from sqlalchemy import String, Integer, Boolean, Date, DateTime, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class AccountStatus(str, enum.Enum):
    active = "active"
    banned = "banned"
    disconnected = "disconnected"
    pending = "pending"

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
        base = min(self.days_active, 10)
        incoming = min(self.received_yesterday, 20)
        replies = min(self.quick_replies_yesterday * 5, 50)
        warmup = base + incoming + replies
        # The manually-configured daily_limit column acts as a floor, so an
        # account that isn't warming up (days_active=0) can still send up to its
        # configured limit instead of being stuck at 0.
        limit = max(warmup, self.daily_limit or 0)
        # Anti-ban: during the first week of warm-up, hard-cap at 5 messages/day
        # (overriding the configured floor) to keep a fresh account under the radar.
        if (self.days_active or 0) < 7:
            return min(limit, 5)
        return limit
