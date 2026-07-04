import uuid
from datetime import datetime
from sqlalchemy import Integer, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class AccountHourSchedule(Base):
    __tablename__ = "account_hour_schedules"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    hour_start: Mapped[int] = mapped_column(Integer, nullable=False)
    hour_end: Mapped[int] = mapped_column(Integer, nullable=False)
    max_per_hour: Mapped[int] = mapped_column(Integer, default=0)
    gpt_prompt: Mapped[str | None] = mapped_column(Text)
    message_template: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    include_products: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
