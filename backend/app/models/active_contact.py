"""V45 PART 3 — harvested "active WhatsApp contacts" lead list.

Every DISTINCT phone number observed being active on WhatsApp — posting a Status/story, or writing
in a group/channel/forum/broadcast-list message — is recorded here EXACTLY ONCE (UNIQUE phone_core)
for lead generation. Our own numbers (PART 1 exclusion list) are never harvested. Private (@c.us)
direct messages are not a harvest source — only public/broadcast surfaces and stories are.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class ActiveWhatsappContact(Base):
    __tablename__ = "active_whatsapp_contacts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # The national 10-digit core (reuses phone_core) — the dedup key. UNIQUE = never stored twice.
    phone_core: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    # A human-friendly display form (09…) of the number.
    phone_display: Mapped[str | None] = mapped_column(String(30))
    # Best available push/display name at first sight (kept; later sightings only backfill if empty).
    display_name: Mapped[str | None] = mapped_column(String(200))
    # Which surface this number was FIRST observed through: status | group | channel | broadcast.
    first_seen_source: Mapped[str | None] = mapped_column(String(20))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    # How many times we have observed this number active (incremented on each later sighting).
    sighting_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
