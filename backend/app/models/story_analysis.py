"""V40 PART 2 — the archive of story product-analysis results (analyze once, cache forever).

Each received story is analyzed AT MOST ONCE. The result (which product, whether it is in the
Afrakala assistant catalog, the AI's confidence/note) is stored here keyed uniquely by story_id, so
re-analyzing a story — via the per-story button OR the daily bulk run — returns this cached row and
NEVER re-calls the AI/OCR path. This is a hard cost-control rule: AI vision calls are the expensive
part of the feature, and a story's content never changes after it is posted.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Text, Boolean, DateTime, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class StoryProductAnalysis(Base):
    __tablename__ = "story_product_analysis"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # One analysis per story — the unique constraint is what makes re-analysis a cached no-op.
    story_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("received_statuses.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    analysis_type: Mapped[str | None] = mapped_column(String(10))          # text | image
    detected_product_name: Mapped[str | None] = mapped_column(String(500))
    matched_product_id: Mapped[str | None] = mapped_column(String(100))    # catalog id when matched
    in_assistant: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ai_confidence: Mapped[float | None] = mapped_column(Float)
    raw_ai_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
