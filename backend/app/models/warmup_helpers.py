"""V25 PART 1 / V28 — outreach-assistant data model (generalizes the V25 "human helpers").

V25 shipped a SMALL, hard-capped (≤25) list of known people that ONLY the main account could
ask. V28 generalizes this into a flexible, multi-sender outreach assistant:
  • ANY of the user's own accounts can be an outreach SENDER (warmup_helper.sender_instance_id),
    each with its OWN contact list (lists never mix between senders).
  • NO hard contact-count cap (the user chose this). A configurable soft-warning THRESHOLD
    (warmup_helper_config.soft_warning_threshold, default 30) only shows a non-blocking banner.
    The REAL, non-configurable safety rail is PACING (slow, jittered, waking-hours-only, plus
    V27's live health gate) — a big list simply takes longer to work through.
  • A short one-line BRIEF per outreach batch (outreach_brief) seeds AI-personalized messages.

Contact `name` stays MANDATORY (nullable=False here + enforced in the service).

Tables:
  • warmup_helper        — a sender's own known contacts (name + phone + sender_instance_id).
  • warmup_helper_task   — one ask pairing a contact with a cold number + its lifecycle.
  • warmup_helper_config — global toggle (default OFF) + send-rate gate + soft_warning_threshold.
  • outreach_brief       — the user's one-line instruction seeding a batch's AI generation.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class WarmupHelper(Base):
    """A known contact (name + phone) that ONE of the user's own sending accounts
    (`sender_instance_id`) may be asked to greet cold numbers through. Never auto-imported.
    V28 — no hard count cap; `name` is mandatory; each contact belongs to exactly one sender.
    V29 «همکاری تیمی» — enriched with the personnel profile the AI uses to explain to each
    contact why helping is personally relevant (job/experience/benefit) + an optional work
    number («شماره کاری») so ONE contact can talk to the SAME cold account from two numbers."""
    __tablename__ = "warmup_helper"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # V28 — the user's OWN account this contact belongs to (the outreach sender). Nullable for
    # backward-compat with V25 rows (backfilled to the main account); required for new rows.
    sender_instance_id: Mapped[str | None] = mapped_column(String(50), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # V29 «همکاری تیمی» — rich personnel profile (all NULLABLE; never breaks legacy rows).
    job_title: Mapped[str | None] = mapped_column(String(200))                 # سمت در آفراکالا
    years_experience: Mapped[int | None] = mapped_column(Integer)              # سابقهٔ تخصصی (سال)
    personal_benefit_note: Mapped[str | None] = mapped_column(Text)            # این سیستم چه سودی برای او دارد
    phone_secondary: Mapped[str | None] = mapped_column(String(20))            # شماره کاری (اختیاری)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WarmupHelperTask(Base):
    """One "please greet this new number" ask, pairing a helper with a cold number.

    status lifecycle: pending → asked → (reminded) → done | skipped.
      • pending  — created, not yet asked (waiting for a slow send slot).
      • asked    — the main account sent the helper the request (asked_at set).
      • reminded — one (and only one) reminder was sent after 1h with no success.
      • done     — the cold number received an incoming message from the helper (webhook).
      • skipped  — abandoned (e.g. helper deactivated) — never messaged again.
    """
    __tablename__ = "warmup_helper_task"
    # V29 — the (contact × cold-account) pairing is now a REAL DB-level unique constraint, not
    # merely app-enforced. A contact may be assigned to AT MOST 2 cold accounts (ceiling enforced
    # in the service), and never the same cold account twice.
    __table_args__ = (UniqueConstraint("helper_id", "cold_instance_id",
                                       name="uq_warmup_helper_task_pair"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    helper_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    cold_instance_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    asked_at: Mapped[datetime | None] = mapped_column(DateTime)
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime)
    done_at: Mapped[datetime | None] = mapped_column(DateTime)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WarmupHelperConfig(Base):
    """Single-row global config for the helper-assist flow.

    is_enabled — the one toggle «کمک‌گیری از افراد واقعی برای گرم‌سازی» (default OFF).
    next_ask_at — the earliest UTC time the main account may send the NEXT helper-ask; the
    engine sets it to now + jittered gap after every send, so asks stay slow and human."""
    __tablename__ = "warmup_helper_config"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    next_ask_at: Mapped[datetime | None] = mapped_column(DateTime)
    # V28 — soft-warning threshold (per-sender contact count over this shows a non-blocking
    # Persian banner; NEVER a hard block). Default 30. The pacing floor is the real safety rail.
    soft_warning_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OutreachBrief(Base):
    """V28 — a short one-line instruction (e.g. «به شماره‌های جدید ما سلام بده») tied to a
    sender, seeding AI-personalized per-contact outreach messages for a batch. Append-only
    history: a new brief per edit. V29 adds `is_current` so the ACTIVE brief per sender is
    known WITHOUT relying on created_at ordering (exactly one current row per sender)."""
    __tablename__ = "outreach_brief"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sender_instance_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    brief_text: Mapped[str] = mapped_column(Text, nullable=False)
    # V29 — exactly one row per sender flagged current/active (app-enforced: setting one current
    # clears the others for that sender). The engine's thread generation seeds from the current.
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WarmupSenderConfig(Base):
    """V29 «همکاری تیمی» — per-SENDER enable flag. The V25/V28 toggle
    (WarmupHelperConfig.is_enabled) stays GLOBAL and still gates the whole helper-assist flow;
    this adds a finer, per-sender switch (V29 is the first place a per-sender toggle is needed),
    so one sender's «همکاری تیمی» can be paused without touching the others. Default ON — a
    sender with contacts participates unless explicitly disabled; the global toggle is the master."""
    __tablename__ = "warmup_sender_config"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sender_instance_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
