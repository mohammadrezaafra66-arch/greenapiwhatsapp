import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class MessageTemplate(Base):
    __tablename__ = "message_templates"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100))  # seasonal/product/general
    content: Mapped[str] = mapped_column(Text, nullable=False)
    campaign_type: Mapped[str] = mapped_column(String(50), default="text")
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
