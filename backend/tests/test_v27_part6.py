"""V27 PART 6 — media-fingerprint reuse tracking.

Proves:
  • the same media hash to many distinct recipients within the window triggers the warning;
  • different media, or the same file to few recipients, does NOT;
  • recipients outside the window don't count;
  • the SHA-256 fingerprint is stable and content-dependent.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest

from app.services import media_fingerprint as mf
from app.services.media_fingerprint import (
    media_hash, over_threshold, record_and_check,
    MEDIA_REUSE_THRESHOLD, MEDIA_REUSE_WINDOW_SECONDS, MEDIA_REUSE_WARNING_FA,
)

NOW = datetime(2026, 7, 18, 12, 0, 0)


# ── pure fingerprint ─────────────────────────────────────────────────────────
def test_media_hash_stable_and_content_dependent():
    assert media_hash("http://x/a.jpg") == media_hash("http://x/a.jpg")
    assert media_hash("http://x/a.jpg") != media_hash("http://x/b.jpg")
    assert media_hash(b"abc") == media_hash("abc")     # bytes vs str same content
    assert media_hash(None) == ""
    assert len(media_hash("x")) == 64                  # sha-256 hex


def test_over_threshold():
    assert over_threshold(MEDIA_REUSE_THRESHOLD) is True
    assert over_threshold(MEDIA_REUSE_THRESHOLD - 1) is False


# ── record_and_check against an in-memory fake store ─────────────────────────
class _FakeDB:
    """Stores CampaignMediaSend rows in a list; supports the two aggregate queries the
    service issues by re-implementing them over the list via monkeypatched helpers."""
    def __init__(self): self.rows = []
    def add(self, obj): self.rows.append(obj)


@pytest.fixture
def db_patch(monkeypatch):
    db = _FakeDB()

    async def _distinct(db_, instance_id, mhash, now, window_seconds=MEDIA_REUSE_WINDOW_SECONDS):
        cutoff = now - timedelta(seconds=window_seconds)
        seen = {r.recipient_phone for r in db_.rows
                if r.instance_id == str(instance_id) and r.media_hash == mhash and r.sent_at >= cutoff}
        return len(seen)

    monkeypatch.setattr(mf, "_distinct_recipient_count", _distinct)
    return db


@pytest.mark.asyncio
async def test_same_media_many_recipients_triggers_warning(db_patch):
    db = db_patch
    res = None
    for i in range(MEDIA_REUSE_THRESHOLD):
        res = await record_and_check(db, "INST", media_hash("img.jpg"), f"9890000{i:04d}", NOW)
    assert res["distinct_recipients"] == MEDIA_REUSE_THRESHOLD
    assert res["over_threshold"] is True
    assert res["warning"] == MEDIA_REUSE_WARNING_FA


@pytest.mark.asyncio
async def test_few_recipients_no_warning(db_patch):
    db = db_patch
    res = None
    for i in range(3):
        res = await record_and_check(db, "INST", media_hash("img.jpg"), f"phone{i}", NOW)
    assert res["over_threshold"] is False and res["warning"] is None


@pytest.mark.asyncio
async def test_different_media_counted_separately(db_patch):
    db = db_patch
    for i in range(MEDIA_REUSE_THRESHOLD):
        await record_and_check(db, "INST", media_hash("A.jpg"), f"p{i}", NOW)
    # a different file to one recipient is nowhere near the threshold
    res = await record_and_check(db, "INST", media_hash("B.jpg"), "p0", NOW)
    assert res["distinct_recipients"] == 1 and res["over_threshold"] is False


@pytest.mark.asyncio
async def test_old_sends_outside_window_do_not_count(db_patch):
    db = db_patch
    old = NOW - timedelta(seconds=MEDIA_REUSE_WINDOW_SECONDS + 60)
    for i in range(MEDIA_REUSE_THRESHOLD):
        await record_and_check(db, "INST", media_hash("img.jpg"), f"p{i}", old)
    res = await record_and_check(db, "INST", media_hash("img.jpg"), "pnew", NOW)
    assert res["distinct_recipients"] == 1        # only the in-window send counts
    assert res["over_threshold"] is False


@pytest.mark.asyncio
async def test_same_recipient_repeated_counts_once(db_patch):
    db = db_patch
    res = None
    for _ in range(MEDIA_REUSE_THRESHOLD + 5):
        res = await record_and_check(db, "INST", media_hash("img.jpg"), "SAME", NOW)
    assert res["distinct_recipients"] == 1        # distinct recipients, not raw sends
