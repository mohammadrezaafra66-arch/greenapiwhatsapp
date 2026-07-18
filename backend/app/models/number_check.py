"""V27 PART 5 — cached WhatsApp-existence results per phone number.

Green API's own blog warns that calling CheckWhatsapp too often WITHOUT then messaging the
number is itself a block risk, and that messaging non-existent numbers is a spam trigger. So
each number is checked AT MOST once per NUMBER_CHECK_TTL_DAYS and the result is cached here;
numbers already messaged rely on delivery-status feedback instead of re-querying.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class WhatsappNumberCheck(Base):
    __tablename__ = "whatsapp_number_check"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone: Mapped[str] = mapped_column(String(30), nullable=False, unique=True, index=True)
    exists: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reason: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
