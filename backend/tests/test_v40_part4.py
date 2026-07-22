"""V40 PART 4 — the «تحلیل محصولات استوری‌ها» tab payload.

Proves: the in-assistant / outside badge follows the in_assistant flag; the thumbnail resolves to
the LOCAL persisted-image endpoint (never an external/expiring URL) and only when media was actually
downloaded; the list endpoint shapes joined (analysis, story) rows correctly.
"""
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.api.v1 import statuses as st


def _analysis(**kw):
    base = dict(id=uuid.uuid4(), story_id=uuid.uuid4(), analysis_type="image",
                detected_product_name="کولر گازی گری ۱۸۰۰۰", in_assistant=True,
                ai_confidence=None, analyzed_at=datetime(2026, 7, 22, 9, 0))
    base.update(kw)
    return SimpleNamespace(**base)


def _story(analysis, **kw):
    base = dict(id=analysis.story_id, sender_name="فروشگاه پارس", sender_phone="989121112233",
                text_content="کولر موجود شد", caption=None,
                local_media_path="/app/.media/statuses/x.jpg", media_downloaded=True)
    base.update(kw)
    return SimpleNamespace(**base)


def test_badge_in_assistant():
    a = _analysis(in_assistant=True)
    p = st._analysis_row_payload(a, _story(a))
    assert p["in_assistant"] is True
    assert p["assistant_status"] == "در دستیار داریم"


def test_badge_outside_assistant():
    a = _analysis(in_assistant=False, detected_product_name="یخچال سامسونگ")
    p = st._analysis_row_payload(a, _story(a))
    assert p["in_assistant"] is False
    assert p["assistant_status"] == "خارج از دستیار"


def test_thumbnail_points_at_local_media_endpoint():
    a = _analysis()
    p = st._analysis_row_payload(a, _story(a))
    assert p["thumbnail_url"] == f"/api/v1/statuses/media/{a.story_id}"
    assert "http" not in p["thumbnail_url"]           # never an external/expiring URL


def test_thumbnail_none_without_downloaded_media():
    a = _analysis(analysis_type="text")
    p = st._analysis_row_payload(a, _story(a, local_media_path=None, media_downloaded=False))
    assert p["thumbnail_url"] is None


def test_confidence_passthrough_and_shamsi():
    a = _analysis(ai_confidence=0.9)
    p = st._analysis_row_payload(a, _story(a))
    assert p["ai_confidence"] == 0.9
    assert p["analyzed_shamsi"]                        # a non-empty Shamsi string


# ── the list endpoint shapes joined rows ──────────────────────────────────────────────────────
class _Result:
    def __init__(self, rows): self._rows = rows
    def all(self): return list(self._rows)


class _DB:
    def __init__(self, rows): self._rows = rows
    async def execute(self, q): return _Result(self._rows)
    async def get(self, model, pk): return None


@pytest.mark.asyncio
async def test_story_analysis_list_shapes_rows():
    a1 = _analysis(in_assistant=True)
    a2 = _analysis(in_assistant=False, detected_product_name="یخچال سامسونگ")
    db = _DB([(a1, _story(a1)), (a2, _story(a2))])
    out = await st.story_analysis_list(account_id=None, limit=50, db=db)
    assert out["count"] == 2
    assert out["items"][0]["assistant_status"] == "در دستیار داریم"
    assert out["items"][1]["assistant_status"] == "خارج از دستیار"
    assert out["items"][0]["contact_name"] == "فروشگاه پارس"
