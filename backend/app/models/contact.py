import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    province: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(100))
    has_whatsapp: Mapped[bool | None] = mapped_column(Boolean)
    whatsapp_checked_at: Mapped[datetime | None] = mapped_column(DateTime)
    blacklisted: Mapped[bool] = mapped_column(Boolean, default=False)
    blacklist_reason: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @property
    def full_name(self) -> str:
        parts = [p for p in [self.first_name, self.last_name] if p]
        return " ".join(parts) if parts else self.phone

    @property
    def chat_id(self) -> str:
        """Format for Green API: 989123456789@c.us"""
        phone = self.phone.lstrip("+").lstrip("0")
        if not phone.startswith("98"):
            phone = "98" + phone
        return f"{phone}@c.us"
