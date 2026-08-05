"""V67 Phase 4 — fleet_evidence_snapshots ORM (immutable historical rows)."""
from __future__ import annotations
import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Index, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class FleetEvidenceSnapshot(Base):
    """Append-only score snapshot. Never update rows in place — insert new."""
    __tablename__ = "fleet_evidence_snapshots"
    __table_args__ = (
        Index("ix_fleet_evidence_account_calc", "account_id", "calculated_at"),
        Index("ix_fleet_evidence_version", "evidence_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    fleet_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fleet_accounts.id", ondelete="SET NULL"))
    trust_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    risk_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    readiness_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    readiness_label: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_version: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    explanation_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    calculated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    simulation_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
