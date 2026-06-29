import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class StatusSend(Base):
    """Record of a WhatsApp Status (story) posted from one account."""
    __tablename__ = "status_sends"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"))
    instance_id: Mapped[str] = mapped_column(String(50), index=True)
    status_type: Mapped[str] = mapped_column(String(20), default="text")  # text / image
    content: Mapped[str | None] = mapped_column(Text)
    media_url: Mapped[str | None] = mapped_column(Text)
    green_api_message_id: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
