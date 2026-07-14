import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class StatusSchedule(Base):
    __tablename__ = "status_schedules"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"))
    name: Mapped[str | None] = mapped_column(String(200))
    status_type: Mapped[str] = mapped_column(String(50), nullable=False)   # intro | special_offer | custom
    content_type: Mapped[str] = mapped_column(String(30), default="text")  # text | image | voice (V14 F19)
    voice_file_url: Mapped[str | None] = mapped_column(Text)                 # V14 F19
    target_participants: Mapped[list | None] = mapped_column(JSONB)          # V14 F19 — null/[] = public
    intro_subtype: Mapped[str | None] = mapped_column(String(50))          # history/services/... (Feature 4)
    custom_text: Mapped[str | None] = mapped_column(Text)
    show_price: Mapped[bool] = mapped_column(Boolean, default=False)
    include_image: Mapped[bool] = mapped_column(Boolean, default=False)
    include_caption: Mapped[bool] = mapped_column(Boolean, default=True)
    image_url: Mapped[str | None] = mapped_column(Text)
    product_selection: Mapped[str] = mapped_column(String(20), default="random")  # manual | random
    product_pool: Mapped[list | None] = mapped_column(JSONB)
    product_pick_count: Mapped[int] = mapped_column(Integer, default=3)
    days_of_week: Mapped[list | None] = mapped_column(JSONB)   # [0..6] (0=Saturday .. 6=Friday)
    specific_dates: Mapped[list | None] = mapped_column(JSONB) # ["1403/05/20", ...] Shamsi
    times: Mapped[list | None] = mapped_column(JSONB)          # ["09:00","20:00"]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
