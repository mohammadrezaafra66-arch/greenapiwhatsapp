"""V40 PART 7 — admin alert when a CATALOG (in-assistant) product is spotted being advertised by an
OUTSIDE contact (not one of our own accounts).

This reuses V26's admin-visible-alert-ROW mechanism (like GroupForbiddenAlert): an alert is a row
here — surfaced/list-able + mark-read — never an auto-message to anyone.

DELIBERATELY PRICE-FREE (deferred): this pass has NO price data (price extraction is out of scope),
so this is a "spotted" alert only — it fires when we SEE a catalog product being advertised outside,
NOT on undercutting. A FUTURE pass, once story/message price extraction exists, should upgrade this
to compare the spotted price against our catalog price and alert ONLY on undercutting, instead of on
every sighting. Do not approximate a price comparison here without real price data.

Dedup: one alert per (contact core phone, product_name, day) — re-seeing the same advertisement the
same day does not spam a second alert.
"""
import uuid
from datetime import datetime, date as date_type
from sqlalchemy import String, Text, Boolean, DateTime, Date, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class CatalogSpotAlert(Base):
    __tablename__ = "catalog_spot_alert"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_phone: Mapped[str] = mapped_column(String(20), nullable=False)   # national core (9xxxxxxxxx)
    contact_name: Mapped[str | None] = mapped_column(String(200))
    product_name: Mapped[str | None] = mapped_column(String(500))
    product_id: Mapped[str | None] = mapped_column(String(100))
    source: Mapped[str | None] = mapped_column(String(10))                   # pv | group | status
    instance_id: Mapped[str | None] = mapped_column(String(50))
    message_text: Mapped[str | None] = mapped_column(Text)
    alert_date: Mapped[date_type] = mapped_column(Date, nullable=False, default=date_type.today)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("contact_phone", "product_name", "alert_date",
                         name="uq_catalog_spot_contact_product_day"),
        Index("ix_catalog_spot_created", "created_at"),
    )
