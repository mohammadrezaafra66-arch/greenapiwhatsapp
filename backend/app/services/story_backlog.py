"""V47 PART 2 (THREAD B) — the story-analysis BACKLOG job: full-backlog scope, batched/resumable
processing, and a terminal "skipped" state for stories that have nothing to analyze.

Why this exists (confirmed diagnosis, do not re-derive):
  • The old «تحلیل همه استوری‌های امروز» button ran ONE synchronous request that looped every eligible
    story with real vision calls and committed ONCE at the end, so on a real backlog the browser hit
    its 30s timeout and a mid-run teardown lost the whole run. It also only looked at stories from
    "today" (UTC), so a backlog from a PRIOR day was invisible and never cleared.
  • Video stories (no analyzable frame) and text stories with empty text_content produced no useful
    analysis, so under the old today-only view they sat "eligible" forever and the eligible count
    could never reach a true zero.

This module owns the reusable, testable pieces; the Celery task (tasks.task_analyze_story_backlog)
drives the batching + Redis progress, and the endpoint (api/v1/statuses.py) dispatches it and returns
a task_id immediately. It reuses the EXISTING analysis path (_analyze_story_rows → analyze_story_once
→ vision) unchanged — no second analysis mechanism.
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select

from app.models.received_status import ReceivedStatus
from app.models.story_analysis import StoryProductAnalysis

logger = logging.getLogger("afrakala.story_backlog")

BATCH = 20

# Terminal marker for a story that has nothing any analyzer could read (video with no frame, or a
# text story with empty text). Distinct from "text"/"image" so it is NEVER counted as a product
# analysis and the eligible backlog can genuinely reach zero. Kept <=10 chars for the String(10)
# analysis_type column, so no schema migration is needed.
SKIPPED_TYPE = "skipped"


def has_no_analyzable_content(story) -> bool:
    """True when there is literally nothing for any analyzer to read.

    An IMAGE-type story is never terminal-skipped here: the vision path handles it (and, on an AI
    outage, deliberately leaves it uncached so it is retried later). Everything else (text, video,
    unknown) is analyzable ONLY through its text — with no text_content AND no caption there is
    nothing to analyze, so it earns a terminal skipped state instead of sitting eligible forever."""
    if getattr(story, "status_type", None) == "image":
        return False
    parts = [getattr(story, "text_content", None), getattr(story, "caption", None)]
    text = " ".join(p for p in parts if p and str(p).strip()).strip()
    return not text


def skip_reason(story) -> str:
    """Human-readable (Persian, user-facing) reason a story was terminally skipped."""
    if getattr(story, "status_type", None) == "video":
        return "ویدیو: فریم قابل‌تحلیلی ندارد"       # video: no analyzable frame
    return "بدون متن: محتوایی برای تحلیل ندارد"        # empty text: nothing to analyze


def _skipped_row(story, now: datetime) -> StoryProductAnalysis:
    return StoryProductAnalysis(
        story_id=story.id, analyzed_at=now, analysis_type=SKIPPED_TYPE,
        detected_product_name=None, matched_product_id=None, in_assistant=False,
        ai_confidence=None, raw_ai_note=skip_reason(story), created_at=now)


async def eligible_story_ids(db, *, instance_id: str | None = None,
                             today_only: bool = False) -> list:
    """Every un-analyzed story's id, own-numbers EXCLUDED, oldest first.

    Default scope is the FULL backlog (all un-analyzed stories, any day) — dropping the old
    UTC-midnight "today only" filter that hid prior-day backlogs. `today_only=True` restores the old
    narrow scope as an explicit opt-in. Own numbers are excluded here (not merely inside the analyzer)
    so they never count toward the eligible backlog — they are intentionally never analyzed."""
    from app.services.own_number_exclusion import get_excluded_cores, is_excluded_core
    q = (select(ReceivedStatus.id, ReceivedStatus.sender_phone)
         .outerjoin(StoryProductAnalysis, StoryProductAnalysis.story_id == ReceivedStatus.id)
         .where(StoryProductAnalysis.id.is_(None))
         .order_by(ReceivedStatus.created_at))
    if today_only:
        start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        q = q.where(ReceivedStatus.created_at >= start)
    if instance_id:
        q = q.where(ReceivedStatus.instance_id == instance_id)
    rows = (await db.execute(q)).all()
    cores = await get_excluded_cores(db)
    return [rid for rid, phone in rows if not is_excluded_core(phone, cores)]


async def process_backlog_batch(db, rows, *, vision_fn=None, now: datetime | None = None) -> dict:
    """Process one batch of already-fetched story rows. Does NOT commit — the caller (task) commits
    per batch so a restart loses at most this batch, never the whole run.

    Partitions the batch: no-analyzable-content stories get a terminal `skipped` analysis row
    (deduped via the analyze-once cache, so a race with the per-story button can't double-insert);
    everything else runs through the EXISTING _analyze_story_rows path. Returns honest counts that
    keep "analyzed" and "skipped — no content" as separate categories."""
    from app.api.v1.statuses import _analyze_story_rows
    from app.services.story_analysis import get_cached_analysis
    now = now or datetime.utcnow()

    to_analyze = []
    skipped_no_content = 0
    for story in rows:
        if has_no_analyzable_content(story):
            # Only create the terminal row if this story has no analysis yet (race-safe against the
            # per-story button having analyzed it between task dispatch and now).
            if await get_cached_analysis(db, story.id) is None:
                db.add(_skipped_row(story, now))
            skipped_no_content += 1
        else:
            to_analyze.append(story)

    results = await _analyze_story_rows(db, to_analyze, vision_fn=vision_fn)

    analyzed = products_found = outside = ai_unavailable = 0
    for analysis, _from_cache in results:
        if getattr(analysis, "vision_failed", False):
            ai_unavailable += 1                 # AI outage — NOT cached, story stays eligible for retry
            continue
        analyzed += 1
        if analysis.detected_product_name:
            products_found += 1
            if not analysis.in_assistant:
                outside += 1
    return {
        "analyzed": analyzed,
        "products_found": products_found,
        "outside_assistant": outside,
        "skipped_no_content": skipped_no_content,
        "ai_unavailable": ai_unavailable,
    }


def summary_message(totals: dict) -> str:
    """The user-facing (Persian) one-line summary built from cumulative totals."""
    msg = (f"{totals.get('analyzed', 0)} استوری تحلیل شد، "
           f"{totals.get('products_found', 0)} محصول شناسایی شد "
           f"({totals.get('outside_assistant', 0)} خارج از دستیار).")
    if totals.get("skipped_no_content"):
        msg += f" {totals['skipped_no_content']} استوری بدون محتوای قابل‌تحلیل رد شد."
    if totals.get("ai_unavailable"):
        msg += (f" ⚠️ {totals['ai_unavailable']} استوری به دلیل در دسترس نبودن هوش مصنوعی "
                f"تحلیل نشد و برای تلاش مجدد باقی ماند.")
    return msg
