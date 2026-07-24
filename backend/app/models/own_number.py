"""V45 PART 1 — "our own numbers" exclusion list.

A small allow-list of phone numbers that belong to THIS business (our own Green API instances plus
any extra personal/business lines the operator adds). Content from these numbers must NEVER be
counted as a product mention in the «پرتکرار محصولات» report, must NEVER consume AI/vision tokens
for analysis, and must NEVER be harvested into the active-contacts lead list — because it is our own
promotional content, not real market signal.

Match key: `phone_core` — the national 10-digit core (9xxxxxxxxx) produced by the project's existing
normalizer (services/product_reports.phone_core), so a number matches regardless of the stored form
(09…, 98…, +98…, …@c.us). It is UNIQUE, so one number can never be listed twice.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class OwnNumberExclusion(Base):
    __tablename__ = "own_number_exclusions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # The national 10-digit core (phone_core) — the format-agnostic match key. UNIQUE = never twice.
    phone_core: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    # The number exactly as it was entered / the account phone, kept only for display.
    phone_raw: Mapped[str | None] = mapped_column(String(30))
    label: Mapped[str | None] = mapped_column(String(200))
    # 'account' = auto-seeded from one of our Green API instances; 'manual' = added by the operator.
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    added_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
