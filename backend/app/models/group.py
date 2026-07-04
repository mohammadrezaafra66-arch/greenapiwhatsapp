import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class WhatsAppGroup(Base):
    __tablename__ = "whatsapp_groups"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    green_group_id: Mapped[str | None] = mapped_column(String(100))  # groupId@g.us
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    chat_type: Mapped[str] = mapped_column(String(20), default="group")  # group | broadcast | community
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    # V8 Feature 41 — admin status of this account in the group
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    participant_count: Mapped[int] = mapped_column(Integer, default=0)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
