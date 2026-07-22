"""V40 FIX — an AI outage must cost a retry, never a permanently wrong cached answer.

THE TRAP THIS CLOSES: `story_analyzer` sets analysis_type="image" BEFORE calling vision, and
swallows any vision error. So when the AI pool was exhausted, a story cached as
(analysis_type='image', detected_product_name=NULL) — byte-identical to "vision ran and genuinely
found nothing". Two rules then combine to make it permanent:
  • analyze_story_once never re-analyzes a story that has a cached row;
  • story_reanalysis.is_stale only re-selects rows with analysis_type='text'.
The story would be locked out of re-analysis forever, with no way back short of manual SQL.

This was found for real: every vision-capable key (openai ×6, gemini) was rate-limited, while the
only healthy key (deepseek) is text-only. Running the 399-story bulk at that moment would have
burned the quota AND destroyed the eligibility of every one of them.
"""
import uuid
from types import SimpleNamespace

import pytest

from app.services.story_analyzer import build_story_analyzer
from app.services.story_analysis import analyze_story_once
from app.services.story_reanalysis import is_stale

CATALOG = [{"id": "cat-1", "name": "کولر گازی گری 18000", "in_assistant": True}]


def _story(**kw):
    base = dict(id=uuid.uuid4(), status_type="image", local_media_path="/x/i.jpg",
                text_content=None, caption=None, original_media_url="http://h/i.jpg",
                sender_phone="989120000000", sender_name="tester", instance_id="7105325764")
    base.update(kw)
    return SimpleNamespace(**base)


class _Result:
    def __init__(self, obj): self._obj = obj
    def scalar_one_or_none(self): return self._obj
    # `_analyze_story_rows` also loads our own account phones (catalog_spot_alert); an empty list
    # is fine — these tests are about caching, not the spot alert.
    def scalars(self): return self
    def all(self): return []
    def first(self): return None      # spot-alert dedup lookup: no prior alert today


class _DB:
    def __init__(self):
        self.store = {}
        self.added = []
    async def execute(self, q):
        return _Result(self.store.get(q.compile().params.get("story_id_1")))
    def add(self, obj):
        obj.id = obj.id or uuid.uuid4()
        self.added.append(obj)
        if hasattr(obj, "story_id"):      # StoryProductAnalysis, not the ProductMentionLog
            self.store[obj.story_id] = obj


# ── the two vision outcomes that must NOT be conflated ─────────────────────────────────────────
async def _vision_unavailable(path):
    """The real outage: no working key / every attempt failed."""
    return None


async def _vision_saw_nothing(path):
    """A SUCCESSFUL call whose model simply saw no product (story_vision returns text=None)."""
    return {"text": None, "provider": "gemini"}


async def _vision_raises(path):
    raise RuntimeError("429 Too Many Requests")


@pytest.mark.asyncio
async def test_unavailable_vision_flags_failure():
    analyzer = build_story_analyzer(CATALOG, vision_fn=_vision_unavailable)
    r = await analyzer(_story())
    assert r["vision_failed"] is True
    assert r["detected_product_name"] is None


@pytest.mark.asyncio
async def test_raising_vision_flags_failure():
    analyzer = build_story_analyzer(CATALOG, vision_fn=_vision_raises)
    assert (await analyzer(_story()))["vision_failed"] is True


@pytest.mark.asyncio
async def test_successful_vision_that_saw_nothing_is_not_a_failure():
    """The distinction the whole fix rests on: a real empty answer IS cacheable."""
    analyzer = build_story_analyzer(CATALOG, vision_fn=_vision_saw_nothing)
    r = await analyzer(_story())
    assert r["vision_failed"] is False
    assert r["detected_product_name"] is None


@pytest.mark.asyncio
async def test_text_story_never_flags_vision_failure():
    analyzer = build_story_analyzer(CATALOG, vision_fn=_vision_unavailable)
    r = await analyzer(_story(status_type="text", local_media_path=None,
                              text_content="سلام خوبی؟"))
    assert r["vision_failed"] is False and r["analysis_type"] == "text"


# ── the guard itself: nothing reaches the archive on an outage ─────────────────────────────────
@pytest.mark.asyncio
async def test_failed_vision_is_not_persisted():
    db, story = _DB(), _story()
    analyzer = build_story_analyzer(CATALOG, vision_fn=_vision_unavailable)
    row, from_cache = await analyze_story_once(db, story, analyzer=analyzer)

    assert from_cache is False
    assert db.added == [], "an AI outage must leave NOTHING in the archive"
    assert row is not None, "the caller still gets a result to render"


@pytest.mark.asyncio
async def test_story_is_retried_after_an_outage_and_then_cached():
    """The whole point: the next run re-analyzes and, once vision works, stores the real answer."""
    db, story = _DB(), _story()

    outage = build_story_analyzer(CATALOG, vision_fn=_vision_unavailable)
    await analyze_story_once(db, story, analyzer=outage)
    assert db.added == []

    calls = {"n": 0}
    async def _recovered(path):
        calls["n"] += 1
        return {"text": "کولر گازی گری 18000", "provider": "openai"}

    healthy = build_story_analyzer(CATALOG, vision_fn=_recovered)
    row, from_cache = await analyze_story_once(db, story, analyzer=healthy)

    assert calls["n"] == 1, "the story must be retried, not served from a poisoned cache"
    assert from_cache is False
    assert row.detected_product_name == "کولر گازی گری 18000"
    assert row.matched_product_id == "cat-1" and row.in_assistant is True
    assert len(db.added) == 1

    # …and only NOW is it cached — a third run must not call vision again.
    _, cached = await analyze_story_once(db, story, analyzer=healthy)
    assert cached is True and calls["n"] == 1


@pytest.mark.asyncio
async def test_successful_empty_result_is_persisted_and_locks_out_reanalysis():
    """Contrast case: a genuine empty answer IS cached, and correctly stops being stale."""
    db, story = _DB(), _story()
    analyzer = build_story_analyzer(CATALOG, vision_fn=_vision_saw_nothing)
    row, _ = await analyze_story_once(db, story, analyzer=analyzer)

    assert len(db.added) == 1
    assert row.analysis_type == "image" and row.detected_product_name is None
    assert is_stale(row, story) is False, "a real vision result is not stale — no retry loop"


@pytest.mark.asyncio
async def test_outage_leaves_story_selectable_by_the_invalidation_predicate():
    """Belt and braces: since nothing is cached, the story simply has no row to be locked by."""
    db, story = _DB(), _story()
    analyzer = build_story_analyzer(CATALOG, vision_fn=_vision_unavailable)
    row, _ = await analyze_story_once(db, story, analyzer=analyzer)

    assert story.id not in db.store, "no archive row exists, so nothing blocks re-analysis"
    # Had it been persisted, this is the predicate that would have refused to re-select it:
    assert is_stale(row, story) is False and row.analysis_type == "image"


# ── the one-time repair for rows poisoned BEFORE the guard existed ─────────────────────────────
from datetime import datetime, timedelta                       # noqa: E402

from app.services.story_reanalysis import (                    # noqa: E402
    is_failed_vision_row, purge_failed_vision_analyses,
)

CUTOFF = datetime(2026, 7, 22, 20, 0, 0)


def _cached(*, atype="image", product=None, at=CUTOFF - timedelta(minutes=6)):
    return SimpleNamespace(id=uuid.uuid4(), analysis_type=atype,
                           detected_product_name=product, analyzed_at=at)


def test_pre_cutoff_empty_image_row_is_selected():
    assert is_failed_vision_row(_cached(), CUTOFF) is True


def test_post_cutoff_row_is_protected():
    """The safety bound: a real post-guard empty result must never be purged."""
    assert is_failed_vision_row(_cached(at=CUTOFF + timedelta(minutes=1)), CUTOFF) is False


def test_row_with_a_product_is_never_purged():
    assert is_failed_vision_row(_cached(product="کولر گازی گری 18000"), CUTOFF) is False


def test_text_row_is_never_purged():
    assert is_failed_vision_row(_cached(atype="text"), CUTOFF) is False


class _PurgeDB:
    def __init__(self, rows):
        self.rows = rows
        self.deletes = []
    async def execute(self, q):
        if str(q).strip().upper().startswith("DELETE"):
            self.deletes.append(q)
            return None
        class _R:
            def scalars(s): return s
            def all(s): return self.rows
        return _R()


@pytest.mark.asyncio
async def test_purge_dry_run_changes_nothing():
    db = _PurgeDB([_cached(), _cached()])
    stats = await purge_failed_vision_analyses(db, cutoff=CUTOFF, dry_run=True)
    assert stats["selected"] == 2 and stats["deleted"] == 0
    assert db.deletes == []


@pytest.mark.asyncio
async def test_purge_removes_only_the_poisoned_rows():
    poisoned = [_cached(), _cached()]
    keep = [_cached(product="یخچال"), _cached(atype="text"),
            _cached(at=CUTOFF + timedelta(seconds=1))]
    db = _PurgeDB(poisoned + keep)

    stats = await purge_failed_vision_analyses(db, cutoff=CUTOFF, dry_run=False)
    assert stats["deleted"] == 2

    targeted = set()
    for v in db.deletes[0].compile().params.values():
        targeted.update(v if isinstance(v, (list, tuple)) else [v])
    assert targeted == {p.id for p in poisoned}
    for k in keep:
        assert k.id not in targeted


# ── the bulk summary must not claim to have analyzed what it skipped ───────────────────────────
@pytest.mark.asyncio
async def test_bulk_summary_reports_ai_unavailable_separately(monkeypatch):
    """A bulk run during an outage must store nothing AND say so, not report a false success."""
    from app.api.v1 import statuses

    async def _catalog(*_a, **_k):
        return CATALOG
    monkeypatch.setattr("app.services.price_service.get_products", _catalog)

    class _BulkDB(_DB):
        async def get(self, model, pk): return None

    rows = [_story(), _story(), _story()]
    db = _BulkDB()
    results = await statuses._analyze_story_rows(db, rows, vision_fn=_vision_unavailable)

    skipped = sum(1 for a, _ in results if getattr(a, "vision_failed", False))
    assert skipped == 3, "all three hit the outage"
    assert db.added == [], "and none of them were cached"
    assert len(results) - skipped == 0, "the summary's `analyzed` count must be zero"


@pytest.mark.asyncio
async def test_bulk_summary_counts_a_real_analysis_normally(monkeypatch):
    from app.api.v1 import statuses

    async def _catalog(*_a, **_k):
        return CATALOG
    monkeypatch.setattr("app.services.price_service.get_products", _catalog)

    async def _ok(path):
        return {"text": "کولر گازی گری 18000", "provider": "openai"}

    class _BulkDB(_DB):
        async def get(self, model, pk): return None

    db = _BulkDB()
    results = await statuses._analyze_story_rows(db, [_story()], vision_fn=_ok)
    assert sum(1 for a, _ in results if getattr(a, "vision_failed", False)) == 0
    assert len([o for o in db.added if hasattr(o, "story_id")]) == 1
