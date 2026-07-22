"""V40 PART 1 — persist incoming stories + download their media at fetch time.

Proves:
  • normalize_status collapses Green API's polymorphic text/image status dicts into V40's stable
    field set (type, sender phone from chatId, media url, unix→datetime timestamp);
  • persist_incoming_statuses downloads an IMAGE story's media exactly once, records the LOCAL path
    (never the expiring URL), and leaves a TEXT story with no media;
  • re-persisting the same status is idempotent — it is skipped and the downloader is NOT called again
    (the one-time-work rule), so later analysis always has a durable local copy.
"""
import uuid
from datetime import datetime

import pytest

from app.services import story_media
from app.services.story_media import normalize_status, persist_incoming_statuses
from app.models.received_status import ReceivedStatus


# ── a fake session that mirrors the real (instance_id, status_message_id) dedup query ──────────
class _Result:
    def __init__(self, obj): self._obj = obj
    def scalar_one_or_none(self): return self._obj


class _DB:
    def __init__(self):
        self.store = {}      # mid -> row (simulates the unique (instance_id, message_id))
        self.added = []
        self.commits = 0
    async def execute(self, q):
        params = q.compile().params
        mid = params.get("status_message_id_1")
        return _Result(self.store.get(mid))
    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        self.added.append(obj)
        self.store[obj.status_message_id] = obj
    async def commit(self): self.commits += 1


class _Downloader:
    def __init__(self, size=2048):
        self.calls = []
        self.size = size
    async def __call__(self, url, dest):
        self.calls.append((url, dest))
        return self.size


IMAGE_STATUS = {
    "idMessage": "IMG1", "chatId": "989121112233@c.us", "senderName": "فروشگاه پارس",
    "type": "image", "urlFile": "https://api.green-api.example/media/IMG1.jpg",
    "caption": "کولر گازی ۱۸۰۰۰ موجود شد", "timestamp": 1758537600,
}
TEXT_STATUS = {
    "idMessage": "TXT1", "chatId": "989350001122@c.us", "senderName": "موبایل امید",
    "typeMessage": "textStatusMessage", "textStatus": "تخفیف ویژه امروز", "timestamp": 1758537700,
}


def test_normalize_image_status():
    f = normalize_status(IMAGE_STATUS)
    assert f["status_message_id"] == "IMG1"
    assert f["status_type"] == "image"
    assert f["is_media"] is True
    assert f["sender_phone"] == "989121112233"      # chatId → phone
    assert f["original_media_url"].endswith("IMG1.jpg")
    assert f["caption"] == "کولر گازی ۱۸۰۰۰ موجود شد"
    assert isinstance(f["status_timestamp"], datetime)


def test_normalize_text_status():
    f = normalize_status(TEXT_STATUS)
    assert f["status_type"] == "text"
    assert f["is_media"] is False
    assert f["original_media_url"] is None
    assert f["text_content"] == "تخفیف ویژه امروز"


def test_normalize_untyped_with_media_is_image():
    f = normalize_status({"idMessage": "X", "downloadUrl": "http://h/x.png"})
    assert f["status_type"] == "image" and f["is_media"] is True


@pytest.mark.asyncio
async def test_persist_downloads_image_once_and_records_local_path(monkeypatch, tmp_path):
    monkeypatch.setattr(story_media, "STORY_MEDIA_DIR", str(tmp_path))
    db, dl = _DB(), _Downloader()
    summary = await persist_incoming_statuses(db, "7105325764", [IMAGE_STATUS, TEXT_STATUS], downloader=dl)

    assert summary == {"persisted": 2, "downloaded": 1, "skipped": 0}
    assert len(dl.calls) == 1                                  # only the image triggered a download
    img = next(r for r in db.added if r.status_message_id == "IMG1")
    txt = next(r for r in db.added if r.status_message_id == "TXT1")
    assert img.media_downloaded is True and img.local_media_path is not None
    assert img.local_media_path.startswith(str(tmp_path))
    assert txt.media_downloaded is False and txt.local_media_path is None


@pytest.mark.asyncio
async def test_persist_is_idempotent_no_second_download(monkeypatch, tmp_path):
    monkeypatch.setattr(story_media, "STORY_MEDIA_DIR", str(tmp_path))
    db, dl = _DB(), _Downloader()
    first = await persist_incoming_statuses(db, "7105325764", [IMAGE_STATUS], downloader=dl)
    second = await persist_incoming_statuses(db, "7105325764", [IMAGE_STATUS], downloader=dl)

    assert first["persisted"] == 1 and first["downloaded"] == 1
    assert second == {"persisted": 0, "downloaded": 0, "skipped": 1}
    assert len(dl.calls) == 1                                  # NOT re-downloaded on the second fetch
    assert len(db.added) == 1


@pytest.mark.asyncio
async def test_persist_skips_status_without_id(monkeypatch, tmp_path):
    monkeypatch.setattr(story_media, "STORY_MEDIA_DIR", str(tmp_path))
    db, dl = _DB(), _Downloader()
    summary = await persist_incoming_statuses(db, "inst", [{"type": "text", "textStatus": "x"}], downloader=dl)
    assert summary["persisted"] == 0 and summary["skipped"] == 1
    assert db.added == []


@pytest.mark.asyncio
async def test_persist_keeps_row_even_if_download_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(story_media, "STORY_MEDIA_DIR", str(tmp_path))
    async def _boom(url, dest):
        raise RuntimeError("network down")
    db = _DB()
    summary = await persist_incoming_statuses(db, "inst", [IMAGE_STATUS], downloader=_boom)
    # The row is still stored (text/metadata worth keeping); it just isn't marked downloaded.
    assert summary["persisted"] == 1 and summary["downloaded"] == 0
    row = db.added[0]
    assert row.media_downloaded is False and row.local_media_path is None
