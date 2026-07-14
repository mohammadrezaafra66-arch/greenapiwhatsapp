"""V14 PART B — interactive & rich messaging models."""
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Text, DateTime, Float
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class ButtonReply(Base):
    """FEATURE 8 — a recipient pressed an interactive button."""
    __tablename__ = "button_replies"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    contact_phone: Mapped[str | None] = mapped_column(String(20))
    chat_id: Mapped[str | None] = mapped_column(String(60))
    button_id: Mapped[str | None] = mapped_column(String(20))
    button_text: Mapped[str | None] = mapped_column(Text)
    message_id: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ButtonAutoReply(Base):
    """FEATURE 8 — auto-reply rule: when a button is pressed, reply with reply_text."""
    __tablename__ = "button_auto_replies"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    button_id: Mapped[str | None] = mapped_column(String(20))
    button_text: Mapped[str | None] = mapped_column(Text)
    reply_text: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MessageReaction(Base):
    """FEATURE 11 (receive) — an incoming emoji reaction on one of our messages."""
    __tablename__ = "message_reactions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chat_id: Mapped[str | None] = mapped_column(String(60))
    sender_phone: Mapped[str | None] = mapped_column(String(20))
    sender_name: Mapped[str | None] = mapped_column(Text)
    emoji: Mapped[str | None] = mapped_column(Text)
    reacted_message_id: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SavedContactCard(Base):
    """FEATURE 12 — reusable contact card preset."""
    __tablename__ = "saved_contact_cards"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    phone_contact: Mapped[str] = mapped_column(String(20), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    company: Mapped[str | None] = mapped_column(String(100), default="افراکالا")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SavedLocation(Base):
    """FEATURE 13 — reusable location preset."""
    __tablename__ = "saved_locations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
