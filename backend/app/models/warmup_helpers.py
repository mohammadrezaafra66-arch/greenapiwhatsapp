"""V25 PART 1 — "human helpers" warm-up assist data model.

A SMALL, capped list (≤25) of REAL known people (staff + friends) who already have the
user's number saved. The main warm account slowly asks each helper to send a friendly
WhatsApp message to a NEW cold number, giving it genuine human incoming traffic. This is
NOT bulk messaging — the hard 25-cap and slow jittered sending are enforced in the
service/engine layer (see services/warmup_helper_service.py and warmup_helper_engine.py).

Three tables:
  • warmup_helper        — the capped list of known helper contacts (name + phone).
  • warmup_helper_task   — one ask pairing a helper with a cold number + its lifecycle.
  • warmup_helper_config — a single-row global toggle (default OFF) + the send-rate gate.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class WarmupHelper(Base):
    """A known contact who already has the user's number saved and has agreed to help warm
    new numbers. Hard-capped at 25 ACTIVE rows at the service layer — never auto-imported."""
    __tablename__ = "warmup_helper"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
