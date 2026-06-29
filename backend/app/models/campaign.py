import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Integer, DateTime, Text, ForeignKey, Float, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
import enum

class CampaignStatus(str, enum.Enum):
    draft = "draft"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"

class MessageStatus(str, enum.Enum):
    pending = "pending"
    generating = "generating"
    queued = "queued"
    sent = "sent"
    failed = "failed"
    skipped = "skipped"
    no_whatsapp = "no_whatsapp"

class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[CampaignStatus] = mapped_column(SAEnum(CampaignStatus), default=CampaignStatus.draft)
    message_template: Mapped[str | None] = mapped_column(Text)
    use_gpt: Mapped[bool] = mapped_column(Boolean, default=True)
    gpt_prompt: Mapped[str | None] = mapped_column(Text)
    include_products: Mapped[bool] = mapped_column(Boolean, default=False)
    product_count: Mapped[int] = mapped_column(Integer, default=3)
    send_image: Mapped[bool] = mapped_column(Boolean, default=False)
    image_url: Mapped[str | None] = mapped_column(Text)
    schedule_start: Mapped[datetime | None] = mapped_column(DateTime)
    schedule_end: Mapped[datetime | None] = mapped_column(DateTime)
    total_contacts: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

class CampaignContact(Base):
    __tablename__ = "campaign_contacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.id"), index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contacts.id"), index=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"))
    status: Mapped[MessageStatus] = mapped_column(SAEnum(MessageStatus), default=MessageStatus.pending, index=True)
    generated_message: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    green_api_message_id: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime)

class HourRateLimit(Base):
    __tablename__ = "hour_rate_limits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hour_start: Mapped[int] = mapped_column(Integer)
    hour_end: Mapped[int] = mapped_column(Integer)
    max_per_hour: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
