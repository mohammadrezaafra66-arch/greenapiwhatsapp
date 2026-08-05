"""V67 Phase 7 — fleet_shadow_snapshots ORM (observational only)."""
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import (
    String, Integer, Boolean, DateTime, Float, ForeignKey, Index, CheckConstraint, Text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class FleetShadowSnapshot(Base):
    __tablename__ = "fleet_shadow_snapshots"
    __table_args__ = (
        CheckConstraint(
            "mismatch_class IN ("
            "'MATCH','SAFE_MISMATCH','DANGEROUS_MISMATCH','INSUFFICIENT_EVIDENCE',"
            "'LEGACY_MORE_PERMISSIVE','V67_MORE_PERMISSIVE','POLICY_VERSION_MISMATCH',"
            "'SENSOR_STALE','RUNTIME_UNKNOWN')",
            name="ck_fleet_shadow_mismatch_class",
        ),
        CheckConstraint(
            "severity IN ('INFO','LOW','MEDIUM','HIGH','CRITICAL')",
            name="ck_fleet_shadow_severity",
        ),
        CheckConstraint(
            "dangerous_threshold_status IN ('UNRATIFIED')",
            name="ck_fleet_shadow_threshold_status",
        ),
        CheckConstraint("simulation_only IS TRUE", name="ck_fleet_shadow_simulation_only"),
        CheckConstraint("mutates_runtime IS FALSE", name="ck_fleet_shadow_mutates_runtime"),
        CheckConstraint("executes IS FALSE", name="ck_fleet_shadow_executes"),
        Index("ix_fleet_shadow_account_observed", "account_id", "observed_at"),
        Index("ix_fleet_shadow_mismatch_observed", "mismatch_class", "observed_at"),
        Index("ix_fleet_shadow_severity_observed", "severity", "observed_at"),
        Index("ix_fleet_shadow_run_id", "run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False,
    )
    fleet_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fleet_accounts.id", ondelete="CASCADE"), nullable=False,
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    scheduled_slot: Mapped[datetime | None] = mapped_column(DateTime)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    shadow_version: Mapped[str] = mapped_column(String(40), nullable=False)
    policy_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    policy_version: Mapped[int | None] = mapped_column(Integer)
    legacy_state: Mapped[str | None] = mapped_column(String(80))
    canonical_fleet_state: Mapped[str | None] = mapped_column(String(40))
    adapter_recommended_state: Mapped[str | None] = mapped_column(String(40))
    journey_recommended_state: Mapped[str | None] = mapped_column(String(40))
    trust_score: Mapped[float | None] = mapped_column(Float)
    risk_level: Mapped[str | None] = mapped_column(String(20))
    readiness_label: Mapped[str | None] = mapped_column(String(40))
    daily_capacity: Mapped[int | None] = mapped_column(Integer)
    recommended_usage: Mapped[int | None] = mapped_column(Integer)
    eligibility_decision: Mapped[str | None] = mapped_column(String(60))
    legacy_eligibility: Mapped[str | None] = mapped_column(String(80))
    mismatch_class: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_codes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    missing_evidence: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    sensor_versions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    sensor_freshness: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    legacy_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    v67_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    comparison_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    dangerous_threshold_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="UNRATIFIED",
    )
    simulation_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    mutates_runtime: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    executes: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
