"""V14 PART F — safety (yellowCard incidents) and call logs."""
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Text, DateTime, BigInteger, Integer
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class AccountIncident(Base):
    """FEATURE 23 — an automatic safety incident (yellowCard, block spike, low reply rate…)."""
    __tablename__ = "account_incidents"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    id_instance: Mapped[int | None] = mapped_column(BigInteger)
    incident_type: Mapped[str | None] = mapped_column(String(30))   # yellowCard | blocked | notAuthorized | quotaExceeded | sleepMode | lowReplyRate | blockSpike
    detected_via: Mapped[str | None] = mapped_column(String(20))    # webhook | poll | messageStatus
    severity: Mapped[str | None] = mapped_column(String(10))        # critical | warning
    auto_actions: Mapped[dict | None] = mapped_column(JSONB)
    campaigns_paused: Mapped[list | None] = mapped_column(JSONB)
    queue_snapshot: Mapped[list | None] = mapped_column(JSONB)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolved_by: Mapped[str | None] = mapped_column(String(20))     # auto | manual
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CallLog(Base):
    """FEATURE 24 — a WhatsApp call (missed incoming = hot lead)."""
    __tablename__ = "call_logs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    direction: Mapped[str | None] = mapped_column(String(10))       # incoming | outgoing
    from_phone: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str | None] = mapped_column(String(20))          # offer | pickUp | hangUp | missed | declined
    contact_name: Mapped[str | None] = mapped_column(Text)
    called_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
