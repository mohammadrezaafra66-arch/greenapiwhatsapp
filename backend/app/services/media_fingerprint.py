"""V27 PART 6 — media-fingerprint reuse tracking for campaign images.

Sending the identical image/video to many recipients is a spam signal distinct from text
similarity. We SHA-256 the media, and per sending instance count how many DISTINCT recipients
received that same hash within a rolling window. Above a conservative threshold we surface a
Persian WARNING (product photos are often legitimately reused — this is a report signal, NOT
a hard block). Threshold/window are top-level constants so they are easy to tune.
"""
from __future__ import annotations
import hashlib
import logging
from datetime import datetime, timedelta
from sqlalchemy import select, func

from app.models.media_send import CampaignMediaSend

logger = logging.getLogger("afrakala.media_fingerprint")

# Mirror the documented "10+ contacts within an hour" text-similarity signal.
MEDIA_REUSE_WINDOW_SECONDS = 3600
MEDIA_REUSE_THRESHOLD = 10

MEDIA_REUSE_WARNING_FA = (
    "این تصویر به تعداد زیادی از مخاطبان با فایل کاملاً یکسان ارسال شده — "
    "ریسک تشخیص اسپم را افزایش می‌دهد."
)


def media_hash(content) -> str:
    """SHA-256 hex of media content. Accepts bytes or a str identifier (e.g. the file URL —
    in this system an uploaded file has one stable URL, so URL == file identity)."""
    if content is None:
        return ""
    data = content if isinstance(content, (bytes, bytearray)) else str(content).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def over_threshold(distinct_recipients: int, threshold: int = MEDIA_REUSE_THRESHOLD) -> bool:
    return int(distinct_recipients) >= int(threshold)


async def _distinct_recipient_count(db, instance_id: str, mhash: str, now: datetime,
                                    window_seconds: int = MEDIA_REUSE_WINDOW_SECONDS) -> int:
    cutoff = now - timedelta(seconds=window_seconds)
    return (await db.execute(
        select(func.count(func.distinct(CampaignMediaSend.recipient_phone))).where(
            CampaignMediaSend.instance_id == str(instance_id),
            CampaignMediaSend.media_hash == mhash,
            CampaignMediaSend.sent_at >= cutoff,
        )
    )).scalar() or 0


async def record_and_check(db, instance_id: str, mhash: str, recipient_phone: str,
                           now: datetime | None = None) -> dict:
    """Record one media send and return {"distinct_recipients", "over_threshold", "warning"}.
    `warning` is the Persian string when the reuse count crosses the threshold, else None.
    Best-effort/never blocks — a spam WARNING only."""
    now = now or datetime.utcnow()
    if not mhash:
        return {"distinct_recipients": 0, "over_threshold": False, "warning": None}
    db.add(CampaignMediaSend(instance_id=str(instance_id), media_hash=mhash,
                             recipient_phone=str(recipient_phone), sent_at=now))
    count = await _distinct_recipient_count(db, instance_id, mhash, now)
    flagged = over_threshold(count)
    if flagged:
        logger.warning("media reuse: instance=%s hash=%s distinct_recipients=%d",
                       instance_id, mhash[:12], count)
    return {"distinct_recipients": count, "over_threshold": flagged,
            "warning": MEDIA_REUSE_WARNING_FA if flagged else None}


async def reuse_report(db, now: datetime | None = None,
                       window_seconds: int = MEDIA_REUSE_WINDOW_SECONDS,
                       threshold: int = MEDIA_REUSE_THRESHOLD) -> list[dict]:
    """Report every (instance, media_hash) whose distinct-recipient count in the window is at
    or above the threshold — for the campaign UI/report to display the Persian warning."""
    now = now or datetime.utcnow()
    cutoff = now - timedelta(seconds=window_seconds)
    rows = (await db.execute(
        select(CampaignMediaSend.instance_id, CampaignMediaSend.media_hash,
               func.count(func.distinct(CampaignMediaSend.recipient_phone)).label("n"))
        .where(CampaignMediaSend.sent_at >= cutoff)
        .group_by(CampaignMediaSend.instance_id, CampaignMediaSend.media_hash)
        .having(func.count(func.distinct(CampaignMediaSend.recipient_phone)) >= threshold)
    )).all()
    return [{"instance_id": r[0], "media_hash": r[1], "distinct_recipients": int(r[2]),
             "warning": MEDIA_REUSE_WARNING_FA} for r in rows]
