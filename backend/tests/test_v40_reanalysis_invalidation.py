"""V40 FIX — the stale-analysis invalidation that unblocks re-analysis after the media-type fix.

Guarantees under test:
  • an analysis that DETECTED a product is never invalidated (real data is preserved);
  • image stories analyzed as text (vision never ran) ARE invalidated — caption-less AND
    caption-only alike, since neither ever reached the image;
  • text-only stories are left alone (their text analysis was genuinely correct);
  • already-re-analyzed rows (analysis_type='image') are excluded → a second run is a no-op;
  • dry-run deletes nothing.
"""
import uuid
from types import SimpleNamespace

import pytest

from app.services.story_reanalysis import (
    is_stale, summarize, invalidate_stale_analyses,
)


def _analysis(*, product=None, atype="text"):
    return SimpleNamespace(id=uuid.uuid4(), detected_product_name=product, analysis_type=atype)


def _story(*, media_url=None, text=None, caption=None):
    return SimpleNamespace(id=uuid.uuid4(), original_media_url=media_url,
                           text_content=text, caption=caption)


# ── the production mix, one row per real-world category ────────────────────────────────────────
def _fixture_pairs():
    return {
        # caption-derived detection — the 12 real products. MUST be preserved.
        "detected": (_analysis(product="کولرگازی جنرال شکار 24000"),
                     _story(media_url="http://h/a.jpg", caption="کولر گازی")),
        # image, no caption, no text — the 377-row majority analyzed against "".
        "empty": (_analysis(), _story(media_url="http://h/b.jpg")),
        # image with a caption that yielded nothing — vision still never ran.
        "cap": (_analysis(), _story(media_url="http://h/c.jpg", caption="یخچال")),
        # text-only story: the text analysis was correct, re-running changes nothing.
        "textonly": (_analysis(), _story(text="سلام")),
        # already re-analyzed through the fixed path.
        "done": (_analysis(atype="image"), _story(media_url="http://h/d.jpg")),
        # no media and no content at all — nothing to re-analyze.
        "nothing": (_analysis(), _story()),
    }


# ── 1. the predicate, category by category ─────────────────────────────────────────────────────
def test_detection_is_never_invalidated():
    a, s = _fixture_pairs()["detected"]
    assert is_stale(a, s) is False


def test_caption_less_image_story_is_stale():
    a, s = _fixture_pairs()["empty"]
    assert is_stale(a, s) is True
    assert is_stale(a, s, only_empty=True) is True


def test_caption_only_image_story_is_stale_but_excluded_by_only_empty():
    a, s = _fixture_pairs()["cap"]
    assert is_stale(a, s) is True
    assert is_stale(a, s, only_empty=True) is False


def test_text_only_story_is_not_stale():
    a, s = _fixture_pairs()["textonly"]
    assert is_stale(a, s) is False


def test_already_reanalyzed_row_is_not_stale():
    """The idempotence hinge: a re-analyzed row is stored as 'image' and must never re-qualify."""
    a, s = _fixture_pairs()["done"]
    assert is_stale(a, s) is False


def test_contentless_non_media_story_is_not_stale():
    a, s = _fixture_pairs()["nothing"]
    assert is_stale(a, s) is False


def test_blank_whitespace_caption_counts_as_no_content():
    a = _analysis()
    s = _story(media_url="http://h/x.jpg", caption="   ", text="")
    assert is_stale(a, s, only_empty=True) is True


# ── 2. the survey the operator reads before applying ───────────────────────────────────────────
def test_summarize_matches_the_production_shape():
    st = summarize(list(_fixture_pairs().values()))
    assert st["analyses_total"] == 6
    assert st["analyses_with_product"] == 1
    assert st["stale_image_no_content"] == 1      # empty
    assert st["stale_image_caption_only"] == 1    # cap
    assert st["stale_total"] == 2


# ── 3. the delete path, against a fake session that records what it was asked to remove ────────
class _Result:
    def __init__(self, rows): self._rows = rows
    def all(self): return self._rows


class _DB:
    def __init__(self, pairs):
        self.pairs = pairs
        self.deletes = []
    async def execute(self, q):
        if str(q).strip().upper().startswith("DELETE"):
            self.deletes.append(q)
            return _Result([])
        return _Result(list(self.pairs))


def _deleted_ids(stmt) -> set:
    """The ids inside DELETE ... WHERE id IN (...). SQLAlchemy compiles the IN list to one param."""
    out = set()
    for v in stmt.compile().params.values():
        out.update(v if isinstance(v, (list, tuple)) else [v])
    return out


@pytest.mark.asyncio
async def test_dry_run_deletes_nothing():
    db = _DB(_fixture_pairs().values())
    stats = await invalidate_stale_analyses(db, dry_run=True)
    assert stats["selected"] == 2 and stats["deleted"] == 0
    assert db.deletes == [], "dry run must not issue a DELETE"


@pytest.mark.asyncio
async def test_apply_deletes_exactly_the_stale_rows():
    pairs = _fixture_pairs()
    db = _DB(pairs.values())
    stats = await invalidate_stale_analyses(db, dry_run=False)

    assert stats["deleted"] == 2
    assert len(db.deletes) == 1
    # the exact ids in the DELETE ... IN (...) are the two stale analyses, and nothing else
    targeted = _deleted_ids(db.deletes[0])
    assert targeted == {pairs["empty"][0].id, pairs["cap"][0].id}
    assert pairs["detected"][0].id not in targeted, "a real detection must never be deleted"


@pytest.mark.asyncio
async def test_only_empty_narrows_the_delete():
    pairs = _fixture_pairs()
    db = _DB(pairs.values())
    stats = await invalidate_stale_analyses(db, only_empty=True, dry_run=False)
    assert stats["deleted"] == 1
    assert _deleted_ids(db.deletes[0]) == {pairs["empty"][0].id}


@pytest.mark.asyncio
async def test_second_run_after_reanalysis_is_a_no_op():
    """Simulates the post-fix state: the two stale rows came back as analysis_type='image'."""
    pairs = _fixture_pairs()
    pairs["empty"] = (_analysis(atype="image"), pairs["empty"][1])
    pairs["cap"] = (_analysis(atype="image"), pairs["cap"][1])
    db = _DB(pairs.values())
    stats = await invalidate_stale_analyses(db, dry_run=False)
    assert stats["selected"] == 0 and stats["deleted"] == 0
    assert db.deletes == [], "no DELETE should be issued when nothing is stale"


# ── 4. the repair step: without it, invalidation is a no-op ────────────────────────────────────
from app.services.story_reanalysis import (            # noqa: E402
    repaired_status_type, needs_media_download, repair_legacy_status_types,
    backfill_missing_media,
)


def _stored(*, stype="incoming", media_url=None, local=None):
    return SimpleNamespace(id=uuid.uuid4(), instance_id="7105325764",
                           status_message_id=uuid.uuid4().hex, status_type=stype,
                           original_media_url=media_url, local_media_path=local,
                           media_downloaded=bool(local), text_content=None, caption=None)


def test_legacy_incoming_with_media_becomes_image():
    assert repaired_status_type(_stored(media_url="http://h/a.jpg")) == "image"


def test_legacy_incoming_without_media_becomes_text():
    assert repaired_status_type(_stored()) == "text"


def test_already_correct_row_is_left_alone():
    assert repaired_status_type(_stored(stype="image", media_url="http://h/a.jpg")) is None
    assert repaired_status_type(_stored(stype="text")) is None


def test_needs_media_download_only_for_undownloaded_images():
    assert needs_media_download(_stored(media_url="http://h/a.jpg")) is True
    assert needs_media_download(_stored(media_url="http://h/a.jpg", local="/m/a.jpg")) is False
    assert needs_media_download(_stored()) is False


class _RowDB:
    """Fake session whose SELECT returns stored ReceivedStatus-like rows."""
    def __init__(self, rows):
        self.rows = rows
    async def execute(self, q):
        class _R:
            def __init__(self, rows): self._rows = rows
            def scalars(self): return self
            def all(self_inner): return self.rows
        return _R(self.rows)


@pytest.mark.asyncio
async def test_repair_dry_run_reports_but_does_not_mutate():
    rows = [_stored(media_url="http://h/a.jpg"), _stored()]
    stats = await repair_legacy_status_types(_RowDB(rows), dry_run=True)
    assert stats == {"rows_total": 2, "to_image": 1, "to_text": 1, "repaired": 0, "dry_run": True}
    assert [r.status_type for r in rows] == ["incoming", "incoming"]


@pytest.mark.asyncio
async def test_repair_apply_reclassifies_rows():
    rows = [_stored(media_url="http://h/a.jpg"), _stored(),
            _stored(stype="image", media_url="http://h/b.jpg")]
    stats = await repair_legacy_status_types(_RowDB(rows), dry_run=False)
    assert stats["repaired"] == 2
    assert rows[0].status_type == "image"
    assert rows[1].status_type == "text"
    assert rows[2].status_type == "image"        # untouched


@pytest.mark.asyncio
async def test_media_backfill_records_local_path_and_survives_failures(monkeypatch, tmp_path):
    from app.services import story_media
    monkeypatch.setattr(story_media, "STORY_MEDIA_DIR", str(tmp_path))
    ok, dead = _stored(media_url="http://h/ok.jpg"), _stored(media_url="http://h/dead.jpg")

    async def _dl(url, dest):
        if "dead" in url:
            raise RuntimeError("410 expired")
        return 1234

    stats = await backfill_missing_media(_RowDB([ok, dead]), downloader=_dl, dry_run=False)
    assert stats["downloaded"] == 1 and stats["failed"] == 1
    assert ok.local_media_path and ok.media_downloaded is True
    assert dead.local_media_path is None, "an expired URL must not fake a local copy"


# ── 5. video/audio must never reach the image-only vision path ─────────────────────────────────
from app.services.story_reanalysis import (            # noqa: E402
    sniff_media_kind, reclassify_from_downloaded_media,
)

_MAGIC = {
    "jpeg":  b"\xff\xd8\xff\xe0" + b"\x00" * 12,
    "png":   b"\x89PNG\r\n\x1a\n" + b"\x00" * 8,
    "webp":  b"RIFF____WEBPVP8 ",
    "gif":   b"GIF89a" + b"\x00" * 10,
    "mp4":   b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 4,
    "ogg":   b"OggS" + b"\x00" * 12,
    "junk":  b"not a media file",
}


def _write(tmp_path, name, blob):
    p = tmp_path / name
    p.write_bytes(blob)
    return str(p)


@pytest.mark.parametrize("magic,expected", [
    ("jpeg", "image"), ("png", "image"), ("webp", "image"), ("gif", "image"),
    ("mp4", "video"), ("ogg", "audio"), ("junk", None),
])
def test_sniff_media_kind(tmp_path, magic, expected):
    assert sniff_media_kind(_write(tmp_path, f"{magic}.bin", _MAGIC[magic])) == expected


def test_sniff_unreadable_file_is_none():
    assert sniff_media_kind("/nonexistent/nope.jpg") is None


@pytest.mark.asyncio
async def test_reclassify_corrects_video_saved_as_image(tmp_path):
    """The exact production case: a .jpg-named MP4 that the URL-only repair typed as 'image'."""
    vid = _stored(stype="image", media_url="http://h/v", local=_write(tmp_path, "v.jpg", _MAGIC["mp4"]))
    img = _stored(stype="image", media_url="http://h/i", local=_write(tmp_path, "i.jpg", _MAGIC["jpeg"]))
    db = _RowDB([vid, img])

    dry = await reclassify_from_downloaded_media(db, dry_run=True)
    assert dry["to_video"] == 1 and dry["corrected"] == 0
    assert vid.status_type == "image", "dry run must not mutate"

    stats = await reclassify_from_downloaded_media(db, dry_run=False)
    assert stats["corrected"] == 1 and stats["to_video"] == 1
    assert vid.status_type == "video", "a video must be excluded from the vision path"
    assert img.status_type == "image", "a real image stays analyzable"


@pytest.mark.asyncio
async def test_reclassified_video_is_not_an_image_story(tmp_path):
    """End of the chain: _is_image_story must reject the corrected video row."""
    from app.services.story_analyzer import _is_image_story
    vid = _stored(stype="image", media_url="http://h/v", local=_write(tmp_path, "v2.jpg", _MAGIC["mp4"]))
    await reclassify_from_downloaded_media(_RowDB([vid]), dry_run=False)
    assert _is_image_story(vid) is False
