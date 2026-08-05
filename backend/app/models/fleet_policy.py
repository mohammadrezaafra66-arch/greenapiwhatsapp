"""V67 Phase 2 — versioned fleet policy storage (no runtime activation)."""
from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, UniqueConstraint, Index, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class FleetPolicy(Base):
    """Configurable AFM policy snapshot. Phase 2 stores only; engines do not execute yet."""
    __tablename__ = "fleet_policies"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_fleet_policies_name_version"),
        Index("ix_fleet_policies_active", "is_active"),
        Index(
            "uq_fleet_policies_one_default",
            "is_default",
            unique=True,
            postgresql_where=text("is_default IS TRUE"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    policy_type: Mapped[str] = mapped_column(String(40), nullable=False, default="CONSERVATIVE")
    settings_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow,
                                                onupdate=datetime.utcnow)
