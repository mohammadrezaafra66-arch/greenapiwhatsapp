"""V17 PART 2 — mesh warm-up data model.

Three tables drive the automatic, mesh-based warm-up:
  • warmup_enrollment — per-number durable state (the state machine lives here).
  • warmup_mesh_edge  — a directed/bidirectional link between two of the user's OWN
    numbers, gated on mutual-contact handshake before any message may flow.
  • warmup_event_log  — durable audit of every warm-up action (send/receive/read/…).

State/handshake values are stored as varchar and validated in services/warmup_state.py.
"""
import uuid
from datetime import datetime, date as date_type
from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, Date, Text, Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class WarmupEnrollment(Base):
    __tablename__ = "warmup_enrollment"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instance_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    # State machine value (see warmup_state.WarmupState). Stored as varchar so new
    # states never require a Postgres enum migration.
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="ENROLLED")
    day_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime)
    sent_today: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    received_today: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reply_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Rest window after a yellowCard (state=YELLOWCARD/PAUSED until this passes).
    rest_until: Mapped[datetime | None] = mapped_column(DateTime)
    # Tehran-local date the daily counters were last reset on.
    counters_date: Mapped[date_type | None] = mapped_column(Date)
    # Optional per-number config overrides (JSON string); None → global defaults.
    config_json: Mapped[str | None] = mapped_column(Text)
    # V41 PART 1 — recovery mode: this enrollment follows Green API's exact 10-day recovery
    # sequence (a re-warm of a churned/carded number) instead of the general onboarding
    # timeline. A scoped, per-number exception; the general schedule is unchanged when False.
    recovery_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WarmupMeshEdge(Base):
    __tablename__ = "warmup_mesh_edge"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    new_instance_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    peer_instance_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(20), nullable=False, default="bidirectional")
    # none → contact_saved → active. An edge is messageable ONLY when active
    # (both mutual-contact flags true). See warmup_state.HandshakeState.
    handshake_state: Mapped[str] = mapped_column(String(20), nullable=False, default="none")
    saved_as_contact_new: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    saved_as_contact_peer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_msg_at: Mapped[datetime | None] = mapped_column(DateTime)
    msg_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WarmupEventLog(Base):
    __tablename__ = "warmup_event_log"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    enrollment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    edge_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # send | receive | read | typing | delivered | state_change | block | kill | group_add
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    delivery_status: Mapped[str | None] = mapped_column(String(30))
    payload_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


# ── V19 — group-based warm-up (ADD to the mesh, don't replace it) ─────────────
class WarmupGroupTarget(Base):
    """An admin-owned group the user selected as a destination for placing cold numbers."""
    __tablename__ = "warmup_group_target"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    warm_instance_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    group_id: Mapped[str] = mapped_column(String(80), nullable=False)     # ...@g.us
    group_subject: Mapped[str | None] = mapped_column(String(300))
    is_selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WarmupGroupMembership(Base):
    """Tracks placing one cold number into one admin group (status/attempts/errors)."""
    __tablename__ = "warmup_group_membership"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cold_instance_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    warm_instance_id: Mapped[str] = mapped_column(String(50), nullable=False)
    group_id: Mapped[str] = mapped_column(String(80), nullable=False)
    # pending | added | failed | skipped
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime)
    added_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WarmupLinkVault(Base):
    """MANUAL vault for public-group invite links. Data only — Green API cannot auto-join,
    so staff join these by hand on the phone."""
    __tablename__ = "warmup_link_vault"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_name: Mapped[str | None] = mapped_column(String(300))
    invite_link: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
