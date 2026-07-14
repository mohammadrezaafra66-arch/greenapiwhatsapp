import uuid, enum
from datetime import datetime, date as date_type
from sqlalchemy import String, Boolean, Integer, DateTime, Date, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
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
    # V8 Feature 37 — parallel multi-account sending
    parallel_accounts: Mapped[bool] = mapped_column(Boolean, default=False)
    max_parallel_accounts: Mapped[int] = mapped_column(Integer, default=1)
    # V8 Feature 42 — show product prices in generated messages
    show_product_prices: Mapped[bool] = mapped_column(Boolean, default=True)
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
    # ── Message customization (opening line / per-group products / opt-out) ──
    opening_mode: Mapped[str] = mapped_column(String(20), default="ai")  # ai|fixed|none|random
    opening_line: Mapped[str | None] = mapped_column(String(500))
    opening_variants: Mapped[list | None] = mapped_column(JSONB)  # for random mode
    product_variation_mode: Mapped[str] = mapped_column(String(20), default="same")  # same|per_group_random|rotate
    products_per_group: Mapped[int] = mapped_column(Integer, default=3)
    product_weights: Mapped[dict | None] = mapped_column(JSONB)  # {name: weight}
    include_opt_out: Mapped[bool] = mapped_column(Boolean, default=True)
    opt_out_text: Mapped[str | None] = mapped_column(String(300))
    # A/B testing (V13.1) — two message variants, 50/50 split
    ab_test_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    variant_b_prompt: Mapped[str | None] = mapped_column(Text)
    variant_b_template: Mapped[str | None] = mapped_column(Text)
    # Rich WhatsApp formatting (V13.5) — instruct AI to use *bold*/_italic_ etc.
    use_rich_formatting: Mapped[bool] = mapped_column(Boolean, default=False)
    # Smart health-weighted account rotation (V13.2)
    smart_rotation: Mapped[bool] = mapped_column(Boolean, default=False)
    # Drip sending (V13.8) — spread over days with a daily quota
    drip_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    drip_per_day: Mapped[int] = mapped_column(Integer, default=50)
    drip_last_run_date: Mapped[date_type | None] = mapped_column(Date)
    # V14 F7 — interactive buttons (opt-in; defaults reproduce today's plain-text send)
    use_interactive_buttons: Mapped[bool] = mapped_column(Boolean, default=False)
    buttons_config: Mapped[list | None] = mapped_column(JSONB)  # [{type,buttonId,buttonText,...}]
    button_header: Mapped[str | None] = mapped_column(Text)
    button_footer: Mapped[str | None] = mapped_column(Text)
    # V15 — product detail level (Item 8) + chosen account when parallel is off (Item 11)
    product_detail_level: Mapped[str] = mapped_column(String(20), default="medium")  # minimal|medium|detailed
    selected_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # V16 PART 3 — append advertising links to the message
    append_links: Mapped[bool] = mapped_column(Boolean, default=False)
    links_count: Mapped[int] = mapped_column(Integer, default=1)
    links_mode: Mapped[str] = mapped_column(String(20), default="weighted")  # fixed|weighted
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
    ab_variant: Mapped[str | None] = mapped_column(String(1))  # V13.1 — 'A' or 'B'
    # ROI tracking (V13.7)
    replied: Mapped[bool] = mapped_column(Boolean, default=False)
    outcome: Mapped[str | None] = mapped_column(String(30))  # interested|purchased|not_interested
    outcome_note: Mapped[str | None] = mapped_column(Text)
    # V14 PART C — message control
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False)   # F9
    edited_at: Mapped[datetime | None] = mapped_column(DateTime)
    recalled: Mapped[bool] = mapped_column(Boolean, default=False)    # F10 campaign recall

class HourRateLimit(Base):
    __tablename__ = "hour_rate_limits"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hour_start: Mapped[int] = mapped_column(Integer)
    hour_end: Mapped[int] = mapped_column(Integer)
    max_per_hour: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
