"""V16 PART 3 — advertising links appended to campaign messages."""
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class AdvertisingLink(Base):
    __tablename__ = "advertising_links"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)   # Persian display label
    link_type: Mapped[str] = mapped_column(String(20), default="other")  # telegram|whatsapp|instagram|website|other
    weight: Mapped[int] = mapped_column(Integer, default=5)           # 1..10
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
