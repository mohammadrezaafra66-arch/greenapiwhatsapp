"""V67 Phase 5 — optional immutable plan snapshot ORM."""
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class FleetPlanSnapshot(Base):
    __tablename__ = "fleet_plan_snapshots"
    __table_args__ = (
        Index("ix_fleet_plan_snapshots_type_created", "plan_type", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_type: Mapped[str] = mapped_column(String(40), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    planner_version: Mapped[str] = mapped_column(String(40), nullable=False)
    simulation_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
