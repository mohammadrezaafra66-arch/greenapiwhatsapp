import uuid
from datetime import datetime, date as date_type
from sqlalchemy import String, Text, Boolean, DateTime, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class EmergencyContact(Base):
    __tablename__ = "emergency_contacts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    purpose: Mapped[str] = mapped_column(String(100), default='alert')
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class ReportSubscriber(Base):
    __tablename__ = "report_subscribers"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class DailySendLog(Base):
    __tablename__ = "daily_send_logs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    date: Mapped[date_type] = mapped_column(Date, default=datetime.utcnow)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"))
    account_name: Mapped[str | None] = mapped_column(String(100))
    campaign_name: Mapped[str | None] = mapped_column(String(200))
    recipient_phone: Mapped[str | None] = mapped_column(String(20))
    recipient_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str | None] = mapped_column(String(50))
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class ProductMentionLog(Base):
    __tablename__ = "product_mention_logs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_name: Mapped[str | None] = mapped_column(String(500))
    product_id: Mapped[str | None] = mapped_column(String(100))
    # V40 PART 5 — where this mention came from: pv | group | status (story). Lets the report show
    # and filter mentions by source. Backfilled for pre-V40 rows from group_chat_id (@g.us → group).
    source: Mapped[str | None] = mapped_column(String(10))
    sender_phone: Mapped[str | None] = mapped_column(String(20))
    sender_name: Mapped[str | None] = mapped_column(String(200))
    group_name: Mapped[str | None] = mapped_column(String(200))
    group_chat_id: Mapped[str | None] = mapped_column(String(200))
    instance_id: Mapped[str | None] = mapped_column(String(50))
    message_text: Mapped[str | None] = mapped_column(Text)
    mentioned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
