"""V27 PART 1/4 — durable cache of each instance's LIVE Green API state.

A single row per instance records the most recent `getStateInstance` result (from the ~60s
poll of PART 4 or a pushed state-change webhook) plus when it was observed. The pre-send
health gate (PART 1) consults this — via the fast in-memory mirror in services/send_gate.py —
so a just-carded instance stops being used within ~a minute instead of sending 19 more
messages like the live incident. Durable table = observability + survives a worker restart.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class InstanceLiveState(Base):
    __tablename__ = "instance_live_state"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instance_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    # Raw Green API state string, lower-cased (authorized/yellowCard/blocked/notAuthorized/...).
    state: Mapped[str] = mapped_column(String(30), nullable=False, default="unknown")
    # How the state was observed: "poll" | "webhook".
    source: Mapped[str | None] = mapped_column(String(20))
    checked_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
