import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Text
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
    segment: Mapped[str | None] = mapped_column(String(50))
    has_whatsapp: Mapped[bool | None] = mapped_column(Boolean)
    whatsapp_checked_at: Mapped[datetime | None] = mapped_column(DateTime)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    blacklisted: Mapped[bool] = mapped_column(Boolean, default=False)
    blacklist_reason: Mapped[str | None] = mapped_column(Text)
    last_replied_at: Mapped[datetime | None] = mapped_column(DateTime)
    first_messaged_at: Mapped[datetime | None] = mapped_column(DateTime)  # V14 F23.6 — warm-up new-contact cap
    source: Mapped[str | None] = mapped_column(String(200))
    group_source: Mapped[str | None] = mapped_column(String(500))  # V9: originating group name
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @property
    def full_name(self) -> str:
        parts = [p for p in [self.first_name, self.last_name] if p]
        return " ".join(parts) if parts else self.phone

    @staticmethod
    def normalize_phone(phone: str) -> str | None:
        import re
        phone = re.sub(r"\D", "", str(phone).strip())
        if phone.startswith("0") and len(phone) == 11:
            phone = "98" + phone[1:]
        elif len(phone) == 10 and phone.startswith("9"):
            phone = "98" + phone
        if not re.match(r"^989[0-9]{9}$", phone):
            return None
        return phone

    @property
    def chat_id(self) -> str:
        return f"{self.phone}@c.us"
