"""V40 FIX — regression guard for the Green API media-type classification bug.

THE BUG THIS LOCKS DOWN: `normalize_status` read the media type from Green API's `type` field, but
on getIncomingStatuses `type` is a DIRECTION and is always the literal string "incoming". Every one
of the 565 production stories was therefore stored with status_type="incoming", `is_media` was
permanently False, no image was ever downloaded, and the vision path never ran once.

The pre-existing PART 1 tests missed it because they hand-built payloads with `"type": "image"` and
`"typeMessage": "textStatusMessage"` — values Green API never sends. These tests instead round-trip
the REAL documented getIncomingStatuses payload shape through the real function.

Real shape (green-api.com → GetIncomingStatuses), abridged:
    {"type": "incoming", "typeMessage": "imageMessage", "downloadUrl": "...", "caption": "..."}
    {"type": "incoming", "typeMessage": "extendedTextMessage", "textMessage": "...",
     "extendedTextMessage": {"text": "...", "backgroundColor": "#228B22", "font": "SANS_SERIF"}}
"""
import uuid
from datetime import datetime

import pytest

from app.services import story_media
from app.services.story_media import normalize_status, persist_incoming_statuses


# ── same fake session/downloader shape the PART 1 suite uses (kept local: test modules are not
# importable from one another under this pytest layout) ────────────────────────────────────────
class _Result:
    def __init__(self, obj): self._obj = obj
    def scalar_one_or_none(self): return self._obj


class _DB:
    def __init__(self):
        self.store = {}
        self.added = []
    async def execute(self, q):
        return _Result(self.store.get(q.compile().params.get("status_message_id_1")))
    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        self.added.append(obj)
        self.store[obj.status_message_id] = obj


class _Downloader:
    def __init__(self, size=2048):
        self.calls = []
        self.size = size
    async def __call__(self, url, dest):
        self.calls.append((url, dest))
        return self.size


# ── the REAL payloads, verbatim in shape from Green API's documented response ──────────────────
REAL_IMAGE_STATUS = {
    "type": "incoming",
    "idMessage": "38E322274FDEBA56047000000000000",
    "timestamp": 1710232636,
    "typeMessage": "imageMessage",
    "chatId": "989126771898@c.us",
    "downloadUrl": "https://sw-media.storage.greenapi.net/media/38E322274FDEBA56.jpg",
    "caption": "کولرگازی ۲۴۰۰۰ هایسنس اینورتر",
    "fileName": "dcf81410-bdbc-4aed-bf23-d1845cd74754.jpg",
    "mimeType": "image/jpeg",
    "senderId": "989126771898@c.us",
    "senderName": "Sina",
    "senderContactName": "Sina Soltani",
}

REAL_TEXT_STATUS = {
    "type": "incoming",
    "idMessage": "1E1A12D337F2BFA5FC0000000000000",
    "timestamp": 1710232595,
    "typeMessage": "extendedTextMessage",
    "chatId": "989124454080@c.us",
    "textMessage": "پنکه 4015 مدیا",
    "extendedTextMessage": {"text": "پنکه 4015 مدیا", "backgroundColor": "#228B22",
                            "font": "SANS_SERIF"},
    "senderId": "989124454080@c.us",
    "senderName": "Amir Tajik",
}

# A caption-less image status — the 377-row production majority, whose entire product signal is in
# the image and which the old code analyzed against an empty string.
REAL_IMAGE_NO_CAPTION = {
    "type": "incoming", "idMessage": "NOCAP1", "timestamp": 1710232700,
    "typeMessage": "imageMessage", "chatId": "989122999920@c.us",
    "downloadUrl": "https://sw-media.storage.greenapi.net/media/NOCAP1.jpg",
    "senderName": "Dr.Ghasemi",
}


# ── 1. the exact regression: "incoming" must never be read as a media type ─────────────────────
def test_real_image_status_is_classified_image_not_incoming():
    f = normalize_status(REAL_IMAGE_STATUS)
    assert f["status_type"] == "image", "Green API's type='incoming' was read as the media type"
    assert f["is_media"] is True, "a real image status must be downloadable"
    assert f["original_media_url"].endswith("38E322274FDEBA56.jpg")
    assert f["caption"] == "کولرگازی ۲۴۰۰۰ هایسنس اینورتر"
    assert f["sender_phone"] == "989126771898"
    assert isinstance(f["status_timestamp"], datetime)


def test_real_text_status_is_classified_text():
    f = normalize_status(REAL_TEXT_STATUS)
    assert f["status_type"] == "text"
    assert f["is_media"] is False
    assert f["original_media_url"] is None
    assert f["text_content"] == "پنکه 4015 مدیا"


def test_direction_value_is_never_stored_as_a_status_type():
    """The precise defect: a direction leaking into status_type. Guard every payload variant."""
    for payload in (REAL_IMAGE_STATUS, REAL_TEXT_STATUS, REAL_IMAGE_NO_CAPTION):
        assert normalize_status(payload)["status_type"] not in ("incoming", "outgoing")


def test_direction_only_payload_falls_back_to_media_url():
    """`type` is the ONLY type-ish key and it is a direction → fall back to the media URL."""
    assert normalize_status({"idMessage": "A", "type": "incoming",
                             "downloadUrl": "http://h/a.jpg"})["status_type"] == "image"
    assert normalize_status({"idMessage": "B", "type": "incoming",
                             "textMessage": "hi"})["status_type"] == "text"


def test_nested_extended_text_is_extracted():
    """A text status carrying ONLY the nested form must not be persisted as empty."""
    f = normalize_status({"idMessage": "N", "type": "incoming",
                          "typeMessage": "extendedTextMessage",
                          "extendedTextMessage": {"text": "فروش ویژه"}})
    assert f["status_type"] == "text" and f["text_content"] == "فروش ویژه"


def test_video_status_is_typed_but_not_downloaded():
    """Non-image media is recorded with its true type but stays out of the image-only vision path."""
    f = normalize_status({"idMessage": "V", "type": "incoming", "typeMessage": "videoMessage",
                          "downloadUrl": "http://h/v.mp4"})
    assert f["status_type"] == "video"
    assert f["is_media"] is False


# ── 2. end-to-end: the real payload actually reaches local storage ─────────────────────────────
@pytest.mark.asyncio
async def test_real_payloads_persist_and_download_the_image(monkeypatch, tmp_path):
    monkeypatch.setattr(story_media, "STORY_MEDIA_DIR", str(tmp_path))
    db, dl = _DB(), _Downloader()
    summary = await persist_incoming_statuses(
        db, "7105325764", [REAL_IMAGE_STATUS, REAL_TEXT_STATUS, REAL_IMAGE_NO_CAPTION], downloader=dl)

    assert summary == {"persisted": 3, "downloaded": 2, "skipped": 0}
    assert len(dl.calls) == 2                       # both image statuses, not the text one

    img = next(r for r in db.added if r.status_message_id == REAL_IMAGE_STATUS["idMessage"])
    assert img.status_type == "image"
    assert img.media_downloaded is True
    assert img.local_media_path and img.local_media_path.startswith(str(tmp_path))

    nocap = next(r for r in db.added if r.status_message_id == "NOCAP1")
    assert nocap.media_downloaded is True, "caption-less image stories are exactly what regressed"

    txt = next(r for r in db.added if r.status_message_id == REAL_TEXT_STATUS["idMessage"])
    assert txt.status_type == "text" and txt.local_media_path is None


@pytest.mark.asyncio
async def test_persisted_real_image_reaches_the_vision_path(monkeypatch, tmp_path):
    """The full causal chain the bug broke: real payload → status_type/local path → vision runs."""
    monkeypatch.setattr(story_media, "STORY_MEDIA_DIR", str(tmp_path))
    from app.services.story_analyzer import build_story_analyzer

    db, dl = _DB(), _Downloader()
    await persist_incoming_statuses(db, "7105325764", [REAL_IMAGE_NO_CAPTION], downloader=dl)
    story = db.added[0]

    seen = {}
    async def _vision(path):
        seen["path"] = path
        return {"text": "ماشین لباسشویی اسنوا"}

    analyzer = build_story_analyzer([], vision_fn=_vision)
    result = await analyzer(story)

    assert seen.get("path") == story.local_media_path, "vision must read the LOCAL persisted copy"
    assert result["analysis_type"] == "image"
    assert result["detected_product_name"] == "ماشین لباسشویی اسنوا"
