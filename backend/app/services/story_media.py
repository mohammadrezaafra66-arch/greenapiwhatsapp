"""V40 PART 1 — normalize + persist incoming WhatsApp statuses (stories) and download their media.

Green API's getIncomingStatuses returns polymorphic dicts (different key names across text/image
statuses and across API versions). `normalize_status` collapses that into a stable field set the
rest of V40 relies on. `persist_incoming_statuses` upserts each into `received_statuses` and, for a
media (image) status, downloads the file to LOCAL storage exactly once — so later analysis and the
Stories tab thumbnail read a durable local copy, never the ~24h-expiring WhatsApp/Green API URL.

Guardrails honored: this runs on the existing on-demand fetch (user opens the Stories tab / hits
refresh), so it never enables background polling and never touches webhook wiring.
"""
from __future__ import annotations
import logging
import os
import uuid
from datetime import datetime

logger = logging.getLogger("afrakala.story_media")

# Persisted under /app (the backend bind-mount), so it survives container restarts and is reachable
# by the media-serving endpoint. Overridable for tests / alt deployments.
STORY_MEDIA_DIR = os.environ.get("STORY_MEDIA_DIR", "/app/.media/statuses")

# Green API status "type" values (and typeMessage suffixes) we treat as media (downloadable image).
_MEDIA_TYPES = {"image", "imagestatus", "imagestatusmessage", "picture", "photo"}
_TEXT_TYPES = {"text", "textstatus", "textstatusmessage"}


def _first(d: dict, *keys):
    """First present, non-empty value among keys (Green API varies the key across versions)."""
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return None


def _status_timestamp(raw) -> datetime | None:
    """Green API sends a unix-seconds timestamp; tolerate ms and already-parsed datetimes."""
    if raw in (None, ""):
        return None
    if isinstance(raw, datetime):
        return raw
    try:
        ts = float(raw)
    except (TypeError, ValueError):
        return None
    if ts > 1e12:        # milliseconds
        ts /= 1000.0
    try:
        return datetime.utcfromtimestamp(ts)
    except (OverflowError, OSError, ValueError):
        return None


def normalize_status(s: dict) -> dict:
    """Collapse a raw Green API status dict into V40's stable field set."""
    raw_type = (_first(s, "type", "typeMessage", "statusType") or "").strip()
    tlow = raw_type.lower()
    media_url = _first(s, "urlFile", "downloadUrl", "fileUrl", "url")
    if tlow in _MEDIA_TYPES or (not tlow and media_url):
        status_type = "image"
    elif tlow in _TEXT_TYPES:
        status_type = "text"
    else:
        status_type = tlow or ("image" if media_url else "text")
    chat_id = _first(s, "chatId", "senderId", "sender")
    phone = None
    if chat_id:
        phone = str(chat_id).split("@")[0].strip() or None
    return {
        "status_message_id": str(_first(s, "idMessage", "receiptId", "id") or "").strip(),
        "sender_chat_id": chat_id,
        "sender_phone": phone,
        "sender_name": _first(s, "senderName", "senderContactName"),
        "status_type": status_type,
        "text_content": _first(s, "textStatus", "text", "textMessage", "message"),
        "caption": _first(s, "caption"),
        "original_media_url": media_url,
        "status_timestamp": _status_timestamp(_first(s, "timestamp", "time")),
        "is_media": status_type == "image" and bool(media_url),
    }


async def _default_download(url: str, dest_path: str) -> int:
    """Stream `url` to `dest_path`; returns byte size. Reuses the project's download convention."""
    from app.services.group_voice import default_download
    return await default_download(url, dest_path)


def _media_dest(instance_id: str, message_id: str, url: str | None) -> str:
    ext = ".jpg"
    if url:
        tail = os.path.splitext(url.split("?")[0])[1].lower()
        if tail in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            ext = tail
    safe = uuid.uuid4().hex
    return os.path.join(STORY_MEDIA_DIR, f"{instance_id}_{safe}{ext}")


async def persist_incoming_statuses(db, instance_id: str, statuses: list[dict], *,
                                    downloader=None, now: datetime | None = None) -> dict:
    """Upsert each fetched status into received_statuses; download image media exactly once.

    Idempotent: a status already stored for this instance is skipped entirely (never re-downloaded),
    matching the one-time-work rule. Best-effort per status — one bad row never aborts the batch.
    Returns a summary dict. Does NOT commit (the caller owns the transaction boundary)."""
    from sqlalchemy import select
    from app.models.received_status import ReceivedStatus
    now = now or datetime.utcnow()
    downloader = downloader or _default_download
    persisted = downloaded = skipped = 0
    for raw in statuses or []:
        try:
            f = normalize_status(raw)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("normalize_status failed: %s", e)
            continue
        mid = f["status_message_id"]
        if not mid:
            skipped += 1
            continue
        existing = (await db.execute(
            select(ReceivedStatus).where(
                ReceivedStatus.instance_id == instance_id,
                ReceivedStatus.status_message_id == mid,
            )
        )).scalar_one_or_none()
        if existing is not None:
            skipped += 1
            continue
        row = ReceivedStatus(
            instance_id=instance_id, status_message_id=mid,
            sender_chat_id=f["sender_chat_id"], sender_phone=f["sender_phone"],
            sender_name=f["sender_name"], status_type=f["status_type"],
            text_content=f["text_content"], caption=f["caption"],
            original_media_url=f["original_media_url"],
            status_timestamp=f["status_timestamp"], media_downloaded=False,
            created_at=now, updated_at=now,
        )
        if f["is_media"] and f["original_media_url"]:
            try:
                os.makedirs(STORY_MEDIA_DIR, exist_ok=True)
                dest = _media_dest(instance_id, mid, f["original_media_url"])
                size = await downloader(f["original_media_url"], dest)
                if size and size > 0:
                    row.local_media_path = dest
                    row.media_downloaded = True
                    downloaded += 1
            except Exception as e:
                # Never let a media failure drop the row — the text/metadata is still worth keeping,
                # and a later analysis run can fall back to the original URL while it is still valid.
                logger.warning("story media download failed (%s / %s): %s", instance_id, mid, e)
        db.add(row)
        persisted += 1
    return {"persisted": persisted, "downloaded": downloaded, "skipped": skipped}
