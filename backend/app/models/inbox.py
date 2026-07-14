import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class InboxMessage(Base):
    __tablename__ = "inbox_messages"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instance_id: Mapped[str] = mapped_column(String(50), index=True)
    sender_phone: Mapped[str] = mapped_column(String(20), index=True)
    sender_name: Mapped[str | None] = mapped_column(String(200))
    message_type: Mapped[str] = mapped_column(String(50), default="text")
    text_content: Mapped[str | None] = mapped_column(Text)
    media_url: Mapped[str | None] = mapped_column(Text)
    is_group: Mapped[bool] = mapped_column(Boolean, default=False)
    group_name: Mapped[str | None] = mapped_column(String(200))
    is_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    category: Mapped[str | None] = mapped_column(String(50))  # price_inquiry/complaint/order/unsubscribe
    auto_replied: Mapped[bool] = mapped_column(Boolean, default=False)
    call_status: Mapped[str | None] = mapped_column(String(50))
    button_reply_id: Mapped[str | None] = mapped_column(String(200))
    button_reply_title: Mapped[str | None] = mapped_column(Text)
    poll_votes: Mapped[str | None] = mapped_column(Text)  # JSON
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    edited_text: Mapped[str | None] = mapped_column(Text)
    original_message_id: Mapped[str | None] = mapped_column(String(200))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)  # V14 F15
    original_payload: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Blacklist(Base):
    __tablename__ = "blacklist"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChatJournal(Base):
    __tablename__ = "chat_journals"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"))
    instance_id: Mapped[str | None] = mapped_column(String(50))
    chat_id: Mapped[str | None] = mapped_column(String(100))
    direction: Mapped[str | None] = mapped_column(String(10))  # in / out
    message_type: Mapped[str | None] = mapped_column(String(50))
    text_content: Mapped[str | None] = mapped_column(Text)
    file_url: Mapped[str | None] = mapped_column(Text)
    green_message_id: Mapped[str | None] = mapped_column(String(200))
    timestamp: Mapped[datetime | None] = mapped_column(DateTime)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UploadedFile(Base):
    __tablename__ = "uploaded_files"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"))
    original_filename: Mapped[str | None] = mapped_column(String(500))
    green_api_url: Mapped[str | None] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
