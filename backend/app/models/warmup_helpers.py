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
    # V35 PART 3 — relationship category (friend/colleague/employee/family) shown as a dropdown,
    # and an optional free-text referral note (e.g. «شماره شما را آقای X داده») woven into the
    # AI-generated ask-messages. Both NULLABLE; independent of each other; never break legacy rows.
    relationship: Mapped[str | None] = mapped_column(String(20))               # دوست/همکار/کارمند/فامیل
    referral_note: Mapped[str | None] = mapped_column(Text)                    # مثال: شماره شما را آقای X داده
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
    # V33 PART 4 — status lifecycle: pending → asked → reminded → no_response | done | skipped.
    # `reminder_count` bounds reminders at exactly 2 per ask-step; after the 2nd reminder's window
    # elapses with no completion the task goes terminal `no_response` (never a 3rd reminder / re-ask).
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    asked_at: Mapped[datetime | None] = mapped_column(DateTime)
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime)
    reminder_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
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


class WarmupHelperThread(Base):
    """V29 «همکاری تیمی» PART 3 — a running conversation thread between ONE contact (helper) and
    ONE cold account. One row per (helper, cold_instance) pair that has ever had an ask-step.
    Carries the thread's `topic_summary` so follow-up ask-steps CONTINUE the same topic (e.g.
    "پیگیری ارسال تلویزیون") instead of a fresh random topic each time. `step_count` counts the
    ask-steps taken; `status` is active/paused/done (paused = safety-flagged, PART 4)."""
    __tablename__ = "warmup_helper_thread"
    __table_args__ = (UniqueConstraint("helper_id", "cold_instance_id",
                                       name="uq_warmup_helper_thread_pair"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    helper_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    cold_instance_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    topic_summary: Mapped[str | None] = mapped_column(Text)
    step_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    last_step_at: Mapped[datetime | None] = mapped_column(DateTime)
    # V29 PART 5 — a due cold-account auto-reply. When the contact's incoming is detected, the
    # cold reply is SCHEDULED (never instant) for `pending_reply_at`; a tick sends it once the
    # cold account is eligible (can_send_now + its 24h cooldown cleared + the shared pacer).
    awaiting_reply: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pending_reply_at: Mapped[datetime | None] = mapped_column(DateTime)
    # V30 PART 5 — a due, STAGGERED thank-you. When a completion is detected but the sender's
    # per-instance pacer isn't ready (a burst of completions), the thank-you is scheduled here for
    # `pending_thankyou_at` and sent later by run_thankyou_tick — paced + inside 09–19 Tehran — so
    # multiple thank-yous never fire simultaneously.
    awaiting_thankyou: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pending_thankyou_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WarmupThreadAlert(Base):
    """V29 PART 4 — an admin alert raised when a forbidden/sensitive word appears in either
    direction of a thread. Raising it PAUSES only that thread (status='paused'); the rest of
    «همکاری تیمی» keeps running."""
    __tablename__ = "warmup_thread_alert"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    helper_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    cold_instance_id: Mapped[str | None] = mapped_column(String(50))
    keyword: Mapped[str | None] = mapped_column(String(120))
    direction: Mapped[str | None] = mapped_column(String(20))   # outbound_ask | inbound | cold_reply
    message_excerpt: Mapped[str | None] = mapped_column(Text)
    acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WarmupTeamEnrollment(Base):
    """V29 PART 7 — per-cold-account «عضویت در همکاری تیمی» enrollment, DISTINCT from the mesh
    warm-up enrollment. Once enabled AND its existing 24h post-authorization cooldown has cleared,
    its assigned contacts' ask-steps run automatically over a fixed 10-day window."""
    __tablename__ = "warmup_team_enrollment"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cold_instance_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enrolled_at: Mapped[datetime | None] = mapped_column(DateTime)
    day_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WarmupHelperLog(Base):
    """V29 PART 9 — dedicated «همکاری تیمی» event log, parallel to (never mixed with) the regular
    inbox/send-queue. One row per event: ask / reminder / thank-you / cold-reply / incoming /
    safety-flag, with the from/to accounts, the message sent, any message received, and the
    thread. Displayed with Shamsi dates + exact times on its own page."""
    __tablename__ = "warmup_helper_log"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    from_instance_id: Mapped[str | None] = mapped_column(String(50))
    to_phone: Mapped[str | None] = mapped_column(String(20))
    helper_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    sender_instance_id: Mapped[str | None] = mapped_column(String(50), index=True)
    cold_instance_id: Mapped[str | None] = mapped_column(String(50), index=True)
    thread_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    message_sent: Mapped[str | None] = mapped_column(Text)
    message_received: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


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
    # V39 PART 2 — deliberate, LOGGED override of the hard ≥14-day + clean-history sender-eligibility
    # gate. When `eligibility_overridden_at` is set, this sender was consciously approved as a Team
    # Collaboration sender despite being under-eligible; PART 3's send-time gate honors it. The note
    # (why) is mandatory at override time, and `eligibility_overridden_by` records who approved it.
    # An auditable event is ALSO written to warmup_helper_log at the moment of override.
    eligibility_overridden_at: Mapped[datetime | None] = mapped_column(DateTime)
    eligibility_override_note: Mapped[str | None] = mapped_column(Text)
    eligibility_overridden_by: Mapped[str | None] = mapped_column(String(60))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
