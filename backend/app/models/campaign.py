import uuid, enum
from datetime import datetime
from sqlalchemy import String, Boolean, Integer, DateTime, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class CampaignStatus(str, enum.Enum):
    draft = "draft"
    running = "running"
    paused = "paused"
    completed = "completed"

class CampaignType(str, enum.Enum):
    text = "text"
    image = "image"
    poll = "poll"
    interactive_buttons = "interactive_buttons"
    status = "status"

class MessageStatus(str, enum.Enum):
    pending = "pending"
    generating = "generating"
    sent = "sent"
    failed = "failed"
    skipped = "skipped"
    no_whatsapp = "no_whatsapp"

class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[CampaignStatus] = mapped_column(SAEnum(CampaignStatus), default=CampaignStatus.draft)
    campaign_type: Mapped[CampaignType] = mapped_column(SAEnum(CampaignType), default=CampaignType.text)
    message_template: Mapped[str | None] = mapped_column(Text)
    use_gpt: Mapped[bool] = mapped_column(Boolean, default=True)
    gpt_prompt: Mapped[str | None] = mapped_column(Text)
    include_products: Mapped[bool] = mapped_column(Boolean, default=False)
    product_count: Mapped[int] = mapped_column(Integer, default=3)
    # Image campaign
    image_url: Mapped[str | None] = mapped_column(Text)
    # Poll campaign
    poll_question: Mapped[str | None] = mapped_column(String(500))
    poll_options: Mapped[str | None] = mapped_column(Text)  # JSON array
    # Interactive buttons
    button1_text: Mapped[str | None] = mapped_column(String(50))
    button2_text: Mapped[str | None] = mapped_column(String(50))
    button3_text: Mapped[str | None] = mapped_column(String(50))
    footer_text: Mapped[str | None] = mapped_column(String(200))
    schedule_start: Mapped[datetime | None] = mapped_column(DateTime)
    schedule_end: Mapped[datetime | None] = mapped_column(DateTime)
    total_contacts: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    delivered_count: Mapped[int] = mapped_column(Integer, default=0)
    read_count: Mapped[int] = mapped_column(Integer, default=0)
    reply_count: Mapped[int] = mapped_column(Integer, default=0)
    campaign_scope: Mapped[str] = mapped_column(String(20), default="pv")  # pv | group
    group_ids: Mapped[str | None] = mapped_column(Text)  # JSON list of group chatIds
    pause_reason: Mapped[str | None] = mapped_column(Text)  # why auto-paused (shown in progress panel)
    # V5 extensions
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    append_date: Mapped[bool] = mapped_column(Boolean, default=False)
    append_seller_name: Mapped[bool] = mapped_column(Boolean, default=False)
    seller_name: Mapped[str | None] = mapped_column(String(200))
    append_seller_phone: Mapped[bool] = mapped_column(Boolean, default=False)
    seller_phone: Mapped[str | None] = mapped_column(String(20))
    seller_phone2: Mapped[str | None] = mapped_column(String(20))
    emoji_level: Mapped[str] = mapped_column(String(20), default="medium")
    contact_group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    wa_collection_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    product_label_filter: Mapped[str | None] = mapped_column(String(200))
    is_always_on: Mapped[bool] = mapped_column(Boolean, default=False)
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
    green_api_message_id: Mapped[str | None] = mapped_column(String(200))
    delivery_status: Mapped[str | None] = mapped_column(String(50))  # sent/delivered/read/failed
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

class HourRateLimit(Base):
    __tablename__ = "hour_rate_limits"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hour_start: Mapped[int] = mapped_column(Integer)
    hour_end: Mapped[int] = mapped_column(Integer)
    max_per_hour: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
