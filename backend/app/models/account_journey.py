"""V67 Phase 3 — account_journeys ORM."""
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class AccountJourney(Base):
    __tablename__ = "account_journeys"
    __table_args__ = (
        Index("ix_account_journeys_account_id", "account_id"),
        Index("ix_account_journeys_status", "status"),
        Index("ix_account_journeys_current_state", "current_state"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    fleet_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fleet_accounts.id", ondelete="CASCADE"), nullable=False)
    journey_type: Mapped[str] = mapped_column(String(40), nullable=False)
    profile_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fleet_policies.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="SIMULATING")
    current_state: Mapped[str] = mapped_column(String(40), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    state_changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    policy_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    evidence_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    simulation_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    shadow_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow,
                                                onupdate=datetime.utcnow)
