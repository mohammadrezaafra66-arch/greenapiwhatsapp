"""V40 PART 2 — the analyze-once cache around story product analysis.

`analyze_story_once` is the SINGLE entry point for analyzing a story. It first consults the
`story_product_analysis` archive: if this story was already analyzed, it returns that cached row and
NEVER calls the (expensive) analyzer. Only a never-seen story runs the analyzer and persists its
result. Both the per-story button and the daily bulk run (PART 3) go through here, so the one-time-
work / cost-control guarantee holds no matter how analysis is triggered.

The `analyzer` is injected (PART 3 supplies the real text/image implementation); PART 2 only owns
the schema + the cache contract. An analyzer returns a dict with any of:
  analysis_type, detected_product_name, matched_product_id, in_assistant, ai_confidence, raw_ai_note.

One deliberate exception to "always cache the first result": if the analyzer reports
`vision_failed` — the image path was taken but the AI could not run at all — the result is NOT
persisted. A cached empty row is indistinguishable from a genuine "found nothing", so combined with
the analyze-once rule it would permanently lock that story out of re-analysis. An AI outage must
cost a retry, never a permanently wrong answer.
"""
from __future__ import annotations
import logging
from datetime import datetime

from sqlalchemy import select

from app.models.story_analysis import StoryProductAnalysis

logger = logging.getLogger("afrakala.story_analysis")


async def get_cached_analysis(db, story_id) -> StoryProductAnalysis | None:
    """The archived analysis row for this story, or None if it was never analyzed."""
    return (await db.execute(
        select(StoryProductAnalysis).where(StoryProductAnalysis.story_id == story_id)
    )).scalar_one_or_none()


def _build_row(story_id, result: dict, now: datetime) -> StoryProductAnalysis:
    return StoryProductAnalysis(
        story_id=story_id,
        analyzed_at=now,
        analysis_type=result.get("analysis_type"),
        detected_product_name=result.get("detected_product_name"),
        matched_product_id=result.get("matched_product_id"),
        in_assistant=bool(result.get("in_assistant")),
        ai_confidence=result.get("ai_confidence"),
        raw_ai_note=(result.get("raw_ai_note") or None),
        created_at=now,
    )


async def analyze_story_once(db, story, *, analyzer, now: datetime | None = None
                             ) -> tuple[StoryProductAnalysis, bool]:
    """Return (analysis_row, from_cache). If the story was analyzed before, return the cached row
    WITHOUT calling `analyzer`. Otherwise run `analyzer(story)`, persist the result, and return it.

    Does NOT commit — the caller owns the transaction (a bulk run commits once at the end)."""
    now = now or datetime.utcnow()
    cached = await get_cached_analysis(db, story.id)
    if cached is not None:
        return cached, True
    result = await analyzer(story) or {}
    row = _build_row(story.id, result, now)
    if result.get("vision_failed"):
        # The AI was unavailable, not merely unproductive. Caching this would be a one-way door:
        # the stored row is indistinguishable from "analyzed, genuinely found nothing", and the
        # analyze-once rule means the story would never be retried. Return the (unsaved) result so
        # the caller can still render something, but leave NOTHING in the archive.
        logger.warning("vision unavailable for story %s — result NOT cached, story stays eligible",
                       getattr(story, "id", "?"))
        # Transient marker (a plain attribute, not a column) so callers can report honestly that
        # the story was skipped rather than analyzed. Without it a bulk run would claim to have
        # analyzed stories it actually stored nothing for.
        row.vision_failed = True
        return row, False
    db.add(row)
    return row, False
