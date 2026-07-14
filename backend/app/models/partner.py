"""V14 — Green API Partner models.

PartnerInstanceLog: an audit trail of instance create/delete/sync actions.
MethodSupport: the capability registry (PART G) — seeded by the PHASE 0 probe and
updated by every Green API call site so a 403 permanently marks a method unsupported.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, Text, BigInteger
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class PartnerInstanceLog(Base):
    __tablename__ = "partner_instance_log"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_instance: Mapped[int | None] = mapped_column(BigInteger)
    action: Mapped[str | None] = mapped_column(String(30))       # created | deleted | synced
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MethodSupport(Base):
    __tablename__ = "method_support"
    method: Mapped[str] = mapped_column(String(60), primary_key=True)
    supported: Mapped[bool | None] = mapped_column(Boolean)      # null = unknown/not probed
    last_status_code: Mapped[int | None] = mapped_column(Integer)
    last_checked: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    note: Mapped[str | None] = mapped_column(Text)
