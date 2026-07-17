"""TG — Telegram-specific persistence: resolved chatId cache."""
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class TelegramChatIdCache(Base):
    """Cache of CheckAccount results so a phone→chatId resolution runs once per (instance, phone)."""
    __tablename__ = "telegram_chatid_cache"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instance_id: Mapped[str] = mapped_column(String(50), nullable=False)
    phone: Mapped[str] = mapped_column(String(30), nullable=False)
    chat_id: Mapped[str] = mapped_column(String(60), nullable=False)
    exist: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("uq_tg_chatid_cache", "instance_id", "phone", unique=True),
    )
