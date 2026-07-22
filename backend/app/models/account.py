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
    suspended = "suspended"  # TG — Telegram spam-restriction state (Green API 2026)
    # V36 — the instance was deleted in the Green API console (upstream 400 «Instance is
    # deleted»). Distinct from `disconnected` (recoverable via re-scan) and `deleted` (our own
    # soft-delete): it means the number can never come back without re-creating the instance, so
    # the UI shows «این اینستنس در Green API دیگر وجود ندارد» + a «حذف از پلتفرم» action.
    green_api_deleted = "green_api_deleted"

class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    instance_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    api_token: Mapped[str] = mapped_column(String(200), nullable=False)
    # TG — platform discriminator: 'whatsapp' (default, existing behavior) | 'telegram'.
    platform: Mapped[str] = mapped_column(String(20), nullable=False, default="whatsapp")
    # TG — Telegram API base host for this instance (Telegram lives on a separate Green API
    # partner project). Null → the default WhatsApp host is used (backward compatible).
    api_host: Mapped[str | None] = mapped_column(String(200))
    # TG — set when the instance reached 'authorized'; drives the 48h non-contact gate.
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime)
    # V38 — anchor for the mandatory 24h post-RECONNECT rest. Stamped (UTC) every time the
    # instance transitions from a non-active state back to 'authorized'/active (a rescan/relink).
    # DISTINCT from authorized_at (first-auth / Telegram gate anchor): this is re-stamped on every
    # reconnect so a just-recovered number rests 24h before ANY Team-Collaboration send, instead of
    # being instantly send-eligible with zero rest. Enforced ONLY in the TC send path (see
    # services/warmup_reconnect_rest.py + _send_from_main) — it never alters the shared V27 gate.
    reconnected_at: Mapped[datetime | None] = mapped_column(DateTime)
    # V39 PART 1 — GENERALIZED connect anchor: the last moment this account became connected to
    # Green API, whether for the VERY FIRST time (a brand-new account's first authorization) OR
    # after a disconnect (a rescan/relink). Supersedes the reconnect-specific `reconnected_at` as
    # the single source of truth for the UNIVERSAL 24h connect-cooldown (send_gate.can_send_now),
    # which now blocks EVERY send path (mesh, campaigns, Team Collaboration) — not just TC.
    # Grandfather clause: NULL means «connected long enough ago / before this mechanism existed»
    # → NEVER blocking. Stamped at the same 4 non-active→active transition sites as reconnected_at.
    connected_at: Mapped[datetime | None] = mapped_column(DateTime)
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
    # V17 PART 3 — manually mark a known-good number as an eligible warm mesh peer
    # (e.g. 989122270261), so it can warm new numbers even before it "GRADUATED".
    is_warm_peer: Mapped[bool] = mapped_column(Boolean, default=False)
    # V26 — dedicated group-monitoring "listener" role. A listener ONLY receives group
    # messages and (optionally) auto-replies; it is mutually exclusive with the
    # campaign-sender / warm-up-peer / warm-up-cold roles (guarded in listener_service).
    is_listener: Mapped[bool] = mapped_column(Boolean, default=False)
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
