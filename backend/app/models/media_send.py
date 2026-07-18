"""V27 PART 6 — per-send record of campaign media fingerprints.

One row per (instance, media hash, recipient) so we can count how many DISTINCT recipients
received the SAME image/video file from one instance inside a rolling window. Sending the
identical file to many people is a separately-tracked spam signal, parallel to text similarity.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class CampaignMediaSend(Base):
    __tablename__ = "campaign_media_send"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instance_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    media_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    recipient_phone: Mapped[str] = mapped_column(String(30), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_media_send_instance_hash_time", "instance_id", "media_hash", "sent_at"),
    )
