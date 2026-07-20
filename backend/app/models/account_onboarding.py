"""V35 PART 4 — guided onboarding wizard «راه‌اندازی».

A dedicated, time-gated, step-by-step record that walks the user through correctly onboarding a
brand-new phone number — SIM insertion → WhatsApp activation → Green API connection → Team
Collaboration enrollment — encoding the project's established anti-ban discipline (SIM aging via
real phone use, then two enforced 24h waits) as a guided sequence instead of relying on memory.

Two fixed gates (constants, not per-record):
  • Gate A — SIM insertion → WhatsApp activation: 24 hours.
  • Gate B — WhatsApp activation → Green API login: 24 hours.

All timestamps are stored as real (naive UTC) datetimes; the UI enters/shows them in Shamsi.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class AccountOnboarding(Base):
    __tablename__ = "account_onboarding"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone_number: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    phone_make_model: Mapped[str | None] = mapped_column(String(120))     # e.g. "Samsung A14"
    # Step 1 — the user-entered moment the SIM was put in a phone (starts Gate A).
    sim_inserted_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Step 2 — set when the user confirms WhatsApp is up on this number (starts Gate B).
    whatsapp_activated_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Step 4 — when the user was shown the Green-API login prompt / when the number connected.
    green_api_login_prompted_at: Mapped[datetime | None] = mapped_column(DateTime)
    green_api_connected_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Persisted convenience marker of the furthest-reached step (1..4); the AUTHORITATIVE
    # locked/unlocked state is always DERIVED from the timestamps + now (onboarding_service).
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
