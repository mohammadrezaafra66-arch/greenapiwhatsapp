"""V40 PART 1 — persisted incoming WhatsApp statuses (stories) RECEIVED from contacts.

WhatsApp statuses expire ~24h after posting, and this project fetches contacts' incoming
statuses on demand via Green API's getIncomingStatuses (a user-triggered pull — NOT background
polling; the webhook-only guardrail is untouched). Because the media URL Green API returns points
at a soon-to-expire status, any later analysis (the per-story or daily bulk analyze in V40 PART 3)
would fail once the story is gone. So on every fetch we persist each status here AND download its
image to local storage, recording the local path — later analysis reads the LOCAL copy, never the
expiring WhatsApp/Green API URL.

Dedup: (instance_id, status_message_id) is unique. Re-fetching the same status is a no-op that
never re-downloads — the same one-time-work rule the analysis archive (PART 2) enforces for the AI.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Text, Boolean, DateTime, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class ReceivedStatus(Base):
    __tablename__ = "received_statuses"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # The account whose Green API instance fetched this status.
    instance_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # Green API's own status id (idMessage / receiptId) — the dedup key within an instance.
    status_message_id: Mapped[str] = mapped_column(String(200), nullable=False)
    # Who posted the status.
    sender_chat_id: Mapped[str | None] = mapped_column(String(100))
    sender_phone: Mapped[str | None] = mapped_column(String(30), index=True)
    sender_name: Mapped[str | None] = mapped_column(String(200))
    # text | image | video | ... (normalized from Green API's polymorphic type fields).
    status_type: Mapped[str | None] = mapped_column(String(30))
    text_content: Mapped[str | None] = mapped_column(Text)
    caption: Mapped[str | None] = mapped_column(Text)
    # The possibly-expiring original media URL (kept only for provenance/debugging).
    original_media_url: Mapped[str | None] = mapped_column(Text)
    # The persisted LOCAL copy — what all later analysis / thumbnails must use.
    local_media_path: Mapped[str | None] = mapped_column(Text)
    media_downloaded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # The status's own posting time (from Green API), distinct from when we first stored it.
    status_timestamp: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow,
                                                onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("instance_id", "status_message_id", name="uq_received_status_instance_msg"),
        Index("ix_received_status_instance_time", "instance_id", "created_at"),
    )
