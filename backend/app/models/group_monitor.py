"""V26 — group-monitoring (listener) data model.

Four tables ported from the Rubika group-listener implementation to WhatsApp/Green API:

  • monitored_group      — a group a listener instance watches (+ auto-reply config)
  • group_message        — every captured incoming group message (deduped on idMessage)
  • group_keyword        — trigger words (detect/auto-reply) and forbidden words (flag admin)
  • group_predefined_reply — canned replies used when conversation_mode = 'predefined'

Everything is ADDITIVE. The listener role is a separate account role (Account.is_listener)
and is mutually exclusive with the campaign-sender / warm-up-peer / warm-up-cold roles
(guarded in app.services.listener_service). Comments/vars English; UI strings Persian.
"""
import uuid
from datetime import datetime
from sqlalchemy import (
    String, Text, Boolean, Integer, DateTime, ForeignKey, Index, BigInteger,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


# conversation_mode values (stored as plain varchar for forward-compatible migrations).
CONVERSATION_MODE_OFF = "off"
CONVERSATION_MODE_PREDEFINED = "predefined"
CONVERSATION_MODE_AI = "ai"
CONVERSATION_MODES = (CONVERSATION_MODE_OFF, CONVERSATION_MODE_PREDEFINED, CONVERSATION_MODE_AI)

# group_keyword.kind values.
KEYWORD_KIND_TRIGGER = "trigger"
KEYWORD_KIND_FORBIDDEN = "forbidden"
KEYWORD_KINDS = (KEYWORD_KIND_TRIGGER, KEYWORD_KIND_FORBIDDEN)

# transcription_status values.
TRANSCRIPTION_NONE = "none"
TRANSCRIPTION_PENDING = "pending"
TRANSCRIPTION_DONE = "done"
TRANSCRIPTION_FAILED = "failed"


class MonitoredGroup(Base):
    __tablename__ = "monitored_group"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # The listener instance (Green API idInstance as string) that watches this group.
    listener_instance_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    group_id: Mapped[str] = mapped_column(String(80), nullable=False)   # ...@g.us
    group_name: Mapped[str | None] = mapped_column(String(300))
    is_monitored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auto_reply_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # off | predefined | ai  (default off → detect/store only, never send)
    conversation_mode: Mapped[str] = mapped_column(String(20), nullable=False, default=CONVERSATION_MODE_OFF)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("uq_monitored_group_listener_group", "listener_instance_id", "group_id", unique=True),
    )


class GroupMessage(Base):
    __tablename__ = "group_message"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    listener_instance_id: Mapped[str] = mapped_column(String(50), nullable=False)
    group_id: Mapped[str] = mapped_column(String(80), nullable=False)
    group_name: Mapped[str | None] = mapped_column(String(300))
    sender: Mapped[str | None] = mapped_column(String(80))          # ...@c.us (author inside group)
    sender_name: Mapped[str | None] = mapped_column(String(300))
    # Green API idMessage — unique for dedupe.
    id_message: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    type_message: Mapped[str | None] = mapped_column(String(50))    # textMessage/audioMessage/imageMessage/...
    text: Mapped[str | None] = mapped_column(Text)
    is_voice: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    audio_url: Mapped[str | None] = mapped_column(Text)
    audio_local_path: Mapped[str | None] = mapped_column(Text)
    transcription: Mapped[str | None] = mapped_column(Text)
    # none | pending | done | failed
    transcription_status: Mapped[str] = mapped_column(String(20), nullable=False, default=TRANSCRIPTION_NONE)
    transcription_error: Mapped[str | None] = mapped_column(Text)
    matched_keywords: Mapped[str | None] = mapped_column(Text)       # comma-joined matched trigger words
    flagged_forbidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    replied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_group_message_group_created", "group_id", "created_at"),
    )


class GroupKeyword(Base):
    __tablename__ = "group_keyword"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    word: Mapped[str] = mapped_column(String(300), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default=KEYWORD_KIND_TRIGGER)  # trigger | forbidden
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class GroupPredefinedReply(Base):
    __tablename__ = "group_predefined_reply"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # null → default reply used when no keyword-specific reply matches.
    keyword_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("group_keyword.id", ondelete="CASCADE"), nullable=True)
    reply_text: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class GroupForbiddenAlert(Base):
    """Admin-visible alert raised when a forbidden/sensitive word is seen in a group.
    A row here (never an auto-message) is how forbidden words are surfaced to the admin."""
    __tablename__ = "group_forbidden_alert"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    listener_instance_id: Mapped[str | None] = mapped_column(String(50))
    group_id: Mapped[str | None] = mapped_column(String(80))
    group_name: Mapped[str | None] = mapped_column(String(300))
    sender: Mapped[str | None] = mapped_column(String(80))
    sender_name: Mapped[str | None] = mapped_column(String(300))
    word: Mapped[str | None] = mapped_column(String(300))
    message_text: Mapped[str | None] = mapped_column(Text)
    group_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
