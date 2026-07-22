"""V40 FIX — invalidate cached story analyses that never actually saw the story's content.

Until the `normalize_status` media-type fix, every incoming status was classified as "incoming"
(Green API's DIRECTION value) instead of image/text. `is_media` was therefore always False, so no
story image was ever downloaded, `local_media_path` stayed NULL, and `_is_image_story` never became
true — every image story was analyzed as TEXT against its caption alone, or, for a caption-less
story, against an empty string.

Those cached rows look exactly like a genuine "analyzed, found nothing" result, and PART 2's
analyze-once cache means they would never be retried even after the fix lands. This module finds
precisely those rows and deletes them, so each story becomes eligible for a real vision re-analysis.

Two guarantees this deliberately keeps:
  • An analysis that DETECTED a product is never touched. A caption-derived detection is real data;
    re-running it would risk losing a good result and re-spend AI budget for nothing.
  • Only rows with `analysis_type = 'text'` qualify. Once a story has been re-analyzed through the
    fixed path it is stored as 'image', so a second run selects nothing — the operation is
    idempotent by construction and cannot loop.

`is_stale` is the single decision point: the DB query below only JOINs, it carries no filtering
logic of its own, so the predicate the tests pin is the exact predicate production applies.
"""
from __future__ import annotations
import logging
import os

from sqlalchemy import select, delete

from app.models.story_analysis import StoryProductAnalysis
from app.models.received_status import ReceivedStatus

logger = logging.getLogger("afrakala.story_reanalysis")

# The bad values the pre-fix normalize_status wrote into status_type: Green API's direction, stored
# as if it were a media type. Rows carrying one of these were never correctly classified.
_LEGACY_DIRECTION_TYPES = {"incoming", "outgoing"}


def repaired_status_type(story) -> str | None:
    """The status_type the FIXED classifier would have produced for an already-stored row, or None
    if the row is fine. Uses the media URL, the only discriminator surviving on a persisted row."""
    if (getattr(story, "status_type", None) or "").strip().lower() not in _LEGACY_DIRECTION_TYPES:
        return None
    return "image" if getattr(story, "original_media_url", None) else "text"


def needs_media_download(story) -> bool:
    """An image story whose media was never fetched because the classifier said it wasn't media."""
    return bool(getattr(story, "original_media_url", None)) and not getattr(
        story, "local_media_path", None)


async def repair_legacy_status_types(db, *, dry_run: bool = True) -> dict:
    """Reclassify rows the old code stored as "incoming" into image/text.

    Required BEFORE invalidation is worth anything: `_is_image_story` demands status_type=='image',
    and `persist_incoming_statuses` skips rows that already exist, so a re-fetch would never repair
    them. Without this, re-analysis would simply re-cache the same empty results.
    """
    rows = (await db.execute(select(ReceivedStatus))).scalars().all()
    changes = [(r, t) for r in rows if (t := repaired_status_type(r))]
    stats = {
        "rows_total": len(rows),
        "to_image": sum(1 for _, t in changes if t == "image"),
        "to_text": sum(1 for _, t in changes if t == "text"),
        "repaired": 0,
        "dry_run": dry_run,
    }
    if dry_run:
        return stats
    for row, t in changes:
        row.status_type = t
    stats["repaired"] = len(changes)
    logger.info("repaired %s legacy status_type rows", len(changes))
    return stats


def sniff_media_kind(path: str) -> str | None:
    """The real media kind of a downloaded file, from its magic bytes: image | video | audio.

    A row that was already persisted carries no `typeMessage`, so `repaired_status_type` can only
    tell "has a media URL" — it cannot separate an image status from a video one, and Green API
    media URLs often carry no file extension either. Sniffing the bytes we actually downloaded is
    the only reliable discriminator, and it matters: a video handed to the image-only vision path
    burns an AI call for nothing. Returns None if the file is unreadable.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(16)
    except OSError:
        return None
    if head[:3] == b"\xff\xd8\xff":                                   return "image"   # jpeg
    if head[:8] == b"\x89PNG\r\n\x1a\n":                              return "image"   # png
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":                 return "image"   # webp
    if head[:6] in (b"GIF87a", b"GIF89a"):                            return "image"   # gif
    if head[4:8] == b"ftyp":                                          return "video"   # mp4/3gp
    if head[:4] == b"\x1aE\xdf\xa3":                                  return "video"   # matroska
    if head[:4] == b"OggS" or head[:3] == b"ID3" or head[:2] == b"\xff\xfb":
        return "audio"
    return None


async def reclassify_from_downloaded_media(db, *, dry_run: bool = True) -> dict:
    """Correct status_type using the bytes actually on disk, so videos/audio never reach the
    image-only vision path. Runs AFTER the media backfill."""
    rows = [r for r in (await db.execute(select(ReceivedStatus))).scalars().all()
            if r.local_media_path]
    changes = []
    for row in rows:
        kind = sniff_media_kind(row.local_media_path)
        if kind and kind != row.status_type:
            changes.append((row, kind))
    stats = {"with_local_media": len(rows), "corrected": 0, "dry_run": dry_run,
             "to_video": sum(1 for _, k in changes if k == "video"),
             "to_audio": sum(1 for _, k in changes if k == "audio"),
             "to_image": sum(1 for _, k in changes if k == "image")}
    if dry_run:
        return stats
    for row, kind in changes:
        row.status_type = kind
    stats["corrected"] = len(changes)
    logger.info("reclassified %s stories from downloaded media bytes", len(changes))
    return stats


async def backfill_missing_media(db, *, downloader=None, dry_run: bool = True,
                                 limit: int | None = None) -> dict:
    """Download the still-missing story images to local storage (best-effort, one row at a time).

    These URLs expire roughly 24h after the story was posted, so some will already be dead — a
    failure is recorded, never raised, and the row simply stays un-downloaded.
    """
    from app.services import story_media

    downloader = downloader or story_media._default_download
    rows = [r for r in (await db.execute(select(ReceivedStatus))).scalars().all()
            if needs_media_download(r)]
    if limit is not None:
        rows = rows[:limit]
    stats = {"candidates": len(rows), "downloaded": 0, "failed": 0, "dry_run": dry_run}
    if dry_run or not rows:
        return stats

    os.makedirs(story_media.STORY_MEDIA_DIR, exist_ok=True)
    for row in rows:
        try:
            dest = story_media._media_dest(row.instance_id, row.status_message_id,
                                           row.original_media_url)
            size = await downloader(row.original_media_url, dest)
            if size and size > 0:
                row.local_media_path = dest
                row.media_downloaded = True
                stats["downloaded"] += 1
            else:
                stats["failed"] += 1
        except Exception as e:
            stats["failed"] += 1
            logger.warning("media backfill failed (%s): %s", row.status_message_id, e)
    return stats


def is_stale(analysis, story, *, only_empty: bool = False) -> bool:
    """True when this cached analysis was produced without ever looking at the story's image.

    `only_empty=True` narrows to the worst subset: image stories with NO caption and NO text, whose
    analysis necessarily ran against an empty string and could not have detected anything.
    """
    if getattr(analysis, "detected_product_name", None):
        return False                                   # a real detection — never invalidate
    if getattr(analysis, "analysis_type", None) != "text":
        return False                                   # vision already ran → genuine no-detection
    if not getattr(story, "original_media_url", None):
        return False                                   # no image existed; text analysis was correct
    if only_empty:
        if (getattr(story, "text_content", None) or "").strip():
            return False
        if (getattr(story, "caption", None) or "").strip():
            return False
    return True


def _has_content(story) -> bool:
    return bool((getattr(story, "text_content", None) or "").strip()
                or (getattr(story, "caption", None) or "").strip())


async def _pairs(db) -> list[tuple]:
    """Every (analysis, story) pair. Pure JOIN — all filtering happens in `is_stale`."""
    return list((await db.execute(
        select(StoryProductAnalysis, ReceivedStatus)
        .join(ReceivedStatus, ReceivedStatus.id == StoryProductAnalysis.story_id)
    )).all())


def summarize(pairs) -> dict:
    """Counts describing the cache, so the operator sees exactly what will change."""
    stale = [(a, s) for a, s in pairs if is_stale(a, s)]
    return {
        "analyses_total": len(pairs),
        "analyses_with_product": sum(1 for a, _ in pairs if a.detected_product_name),
        "stale_image_no_content": sum(1 for _, s in stale if not _has_content(s)),
        "stale_image_caption_only": sum(1 for _, s in stale if _has_content(s)),
        "stale_total": len(stale),
    }


def is_failed_vision_row(analysis, cutoff) -> bool:
    """A row cached by the image path with no product, analyzed at/before `cutoff`.

    ONE-TIME REMEDIATION ONLY, for rows written BEFORE the `vision_failed` guard existed. Back then
    an AI outage and a genuine "the model saw no product" produced byte-identical rows, so content
    alone cannot tell them apart — which is why the caller must supply an explicit `cutoff`. After
    the guard, an outage caches nothing at all, so any such row is a REAL empty result and must be
    left alone; that is exactly what the cutoff enforces.
    """
    if getattr(analysis, "analysis_type", None) != "image":
        return False
    if getattr(analysis, "detected_product_name", None):
        return False
    at = getattr(analysis, "analyzed_at", None)
    return bool(at and cutoff and at <= cutoff)


async def purge_failed_vision_analyses(db, *, cutoff, dry_run: bool = True) -> dict:
    """Delete pre-guard image analyses that an AI outage cached as empty, freeing them for retry.

    Deliberately NOT part of `is_stale`: folding this into the normal predicate would make every
    genuine "vision found nothing" row eligible forever, and the re-analysis loop would never
    settle. This is an operator-invoked, cutoff-bounded repair.
    """
    rows = (await db.execute(select(StoryProductAnalysis))).scalars().all()
    ids = [a.id for a in rows if is_failed_vision_row(a, cutoff)]
    stats = {"analyses_total": len(rows), "selected": len(ids), "deleted": 0,
             "cutoff": str(cutoff), "dry_run": dry_run}
    if dry_run or not ids:
        return stats
    await db.execute(delete(StoryProductAnalysis).where(StoryProductAnalysis.id.in_(ids)))
    stats["deleted"] = len(ids)
    logger.info("purged %s failed-vision analyses cached at/before %s", len(ids), cutoff)
    return stats


async def invalidate_stale_analyses(db, *, only_empty: bool = False, dry_run: bool = True) -> dict:
    """Delete the stale cached analyses so their stories become eligible for re-analysis.

    Returns a summary of the cache plus how many rows were (or would be) removed. Does NOT commit —
    the caller owns the transaction boundary, matching the rest of V40.
    """
    pairs = await _pairs(db)
    stats = summarize(pairs)
    ids = [a.id for a, s in pairs if is_stale(a, s, only_empty=only_empty)]
    stats.update({"selected": len(ids), "only_empty": only_empty, "dry_run": dry_run, "deleted": 0})

    if dry_run or not ids:
        return stats

    await db.execute(delete(StoryProductAnalysis).where(StoryProductAnalysis.id.in_(ids)))
    stats["deleted"] = len(ids)
    logger.info("invalidated %s stale story analyses (only_empty=%s)", len(ids), only_empty)
    return stats
