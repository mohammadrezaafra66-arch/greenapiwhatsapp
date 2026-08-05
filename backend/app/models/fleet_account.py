"""V67 Phase 2 — canonical fleet_accounts row (AFM decision truth for fleet_state)."""
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import (
    String, Integer, Boolean, DateTime, Text, ForeignKey, Index, CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from app.services.fleet_state import FLEET_STATE_VALUES


_STATE_CHECK = ", ".join(f"'{v}'" for v in FLEET_STATE_VALUES)


class FleetAccount(Base):
    """One-to-one projection over accounts. Sensors remain on Account / Warmup / live state."""
    __tablename__ = "fleet_accounts"
    __table_args__ = (
        CheckConstraint(f"fleet_state IN ({_STATE_CHECK})", name="ck_fleet_accounts_fleet_state"),
        Index("ix_fleet_accounts_fleet_state", "fleet_state"),
        Index("ix_fleet_accounts_cutover_state", "cutover", "fleet_state"),
        Index("ix_fleet_accounts_policy_id", "policy_id"),
        Index("ix_fleet_accounts_next_action_at", "next_action_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    fleet_state: Mapped[str] = mapped_column(String(40), nullable=False, default="NEW")
    journey_type: Mapped[str | None] = mapped_column(String(40))
    journey_profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    policy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fleet_policies.id", ondelete="SET NULL"),
    )
    risk_budget: Mapped[str] = mapped_column(String(40), nullable=False, default="NORMAL")
    cutover: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    registered_at: Mapped[datetime | None] = mapped_column(DateTime)
    linked_at: Mapped[datetime | None] = mapped_column(DateTime)
    first_real_inbound_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_real_inbound_at: Mapped[datetime | None] = mapped_column(DateTime)
    first_real_outbound_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_real_outbound_at: Mapped[datetime | None] = mapped_column(DateTime)
    campaign_ready_at: Mapped[datetime | None] = mapped_column(DateTime)
    mature_at: Mapped[datetime | None] = mapped_column(DateTime)
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime)

    paused_reason: Mapped[str | None] = mapped_column(Text)
    state_reason: Mapped[str | None] = mapped_column(Text)
    state_changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow,
                                                onupdate=datetime.utcnow)
