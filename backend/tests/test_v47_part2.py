"""V47 PART 2 (THREAD B) — async, resumable, full-backlog story analysis with terminal skip states.

Coverage:
  • has_no_analyzable_content: correctly classifies video/empty-text (skip) vs image/captioned (keep).
  • process_backlog_batch (hermetic): video + empty-text stories get a terminal `skipped` analysis row
    (counted separately, NOT as analyzed); an AI-outage image is counted ai_unavailable and left
    uncached (stays eligible); an already-analyzed no-content story is never double-inserted.
  • summary_message keeps "analyzed" and "skipped — no content" as distinct honest categories.
  • (real DB) eligible_story_ids returns the FULL multi-day backlog by default, honors today_only as
    an opt-in, and excludes own numbers; terminal-skipped stories drop out of the eligible set;
    a per-batch commit survives a simulated mid-run interruption (only the remainder stays eligible).
  • (real DB) the endpoint returns a task_id immediately without doing the analysis inline.
"""
import uuid
from types import SimpleNamespace

import pytest

from app.services.story_backlog import (has_no_analyzable_content, process_backlog_batch,
                                         summary_message, SKIPPED_TYPE)


# ── hermetic fakes ────────────────────────────────────────────────────────────────────────────
CATALOG = [{"name": "کولر گازی گری 18000", "id": "cat-1"}]


def _story(**kw):
    base = dict(id=uuid.uuid4(), status_type="text", local_media_path=None,
                text_content=None, caption=None, sender_phone="989120000000",
                sender_name="فروشنده", instance_id="inst-1")
    base.update(kw)
    return SimpleNamespace(**base)


class _Result:
    def __init__(self, obj): self._obj = obj
    def scalar_one_or_none(self): return self._obj
    def scalars(self): return self
    def all(self): return self._obj if isinstance(self._obj, list) else []


class _DB:
    def __init__(self, fetch_rows=None):
        self.store = {}
        self.added = []
        self.commits = 0
        self._fetch_rows = fetch_rows or []
    async def execute(self, q):
        params = q.compile().params
        if "story_id_1" in params:
            return _Result(self.store.get(params["story_id_1"]))
        return _Result(list(self._fetch_rows))
    async def get(self, model, pk): return None
    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        self.added.append(obj)
        if hasattr(obj, "story_id"):
            self.store[obj.story_id] = obj
    async def commit(self): self.commits += 1


@pytest.fixture(autouse=True)
def _no_spot_alert(monkeypatch):
    async def _cores(*_a, **_k): return set()
    async def _raise(*_a, **_k): return False
    monkeypatch.setattr("app.services.catalog_spot_alert.get_our_phone_cores", _cores)
    monkeypatch.setattr("app.services.catalog_spot_alert.maybe_raise_spot_alert", _raise)
    yield


@pytest.fixture
def _catalog(monkeypatch):
    async def _c(*_a, **_k): return CATALOG
    monkeypatch.setattr("app.services.price_service.get_products", _c)


# ── classification ────────────────────────────────────────────────────────────────────────────
def test_has_no_analyzable_content_classification():
    assert has_no_analyzable_content(_story(status_type="video", text_content=None)) is True
    assert has_no_analyzable_content(_story(status_type="text", text_content="   ")) is True
    assert has_no_analyzable_content(_story(status_type="text", text_content=None)) is True
    # anything with real text/caption is analyzable — even a video with a caption
    assert has_no_analyzable_content(_story(status_type="video", caption="کولر گازی")) is False
    assert has_no_analyzable_content(_story(status_type="text", text_content="یخچال")) is False
    # an image story is left to the vision path (never terminal-skipped here)
    assert has_no_analyzable_content(_story(status_type="image", local_media_path="/x.jpg")) is False
    assert has_no_analyzable_content(_story(status_type="image", local_media_path=None)) is False


# ── terminal skip ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_video_and_empty_text_get_terminal_skipped_row(_catalog):
    from app.models.story_analysis import StoryProductAnalysis
    rows = [
        _story(status_type="video", text_content=None),            # no frame → skip
        _story(status_type="text", text_content="   "),            # empty text → skip
        _story(status_type="text", text_content="کولر گازی گری 18000 موجود"),  # real product
    ]
    db = _DB()
    out = await process_backlog_batch(db, rows)
    assert out["skipped_no_content"] == 2
    assert out["analyzed"] == 1
    assert out["products_found"] == 1
    skipped = [o for o in db.added if isinstance(o, StoryProductAnalysis)
               and o.analysis_type == SKIPPED_TYPE]
    assert len(skipped) == 2
    # each terminal row carries a reason and is NOT a product success
    assert all(s.detected_product_name is None and s.raw_ai_note for s in skipped)


@pytest.mark.asyncio
async def test_already_analyzed_no_content_story_not_double_inserted(_catalog):
    from app.models.story_analysis import StoryProductAnalysis
    story = _story(status_type="video", text_content=None)
    db = _DB()
    # pretend this story already has an analysis row (e.g. the per-story button ran meanwhile)
    db.store[story.id] = StoryProductAnalysis(story_id=story.id, analysis_type=SKIPPED_TYPE)
    before = len(db.added)
    out = await process_backlog_batch(db, [story])
    # counted as skipped_no_content, but no NEW row added (race-safe dedup)
    assert out["skipped_no_content"] == 1
    assert len(db.added) == before


@pytest.mark.asyncio
async def test_ai_unavailable_image_counted_and_not_cached(_catalog):
    async def _vision_down(_path):
        return None                       # vision unavailable → vision_failed, must stay eligible
    story = _story(status_type="image", local_media_path="/x/i.jpg")
    db = _DB()
    out = await process_backlog_batch(db, [story], vision_fn=_vision_down)
    assert out["ai_unavailable"] == 1
    assert out["analyzed"] == 0
    from app.models.story_analysis import StoryProductAnalysis
    assert [o for o in db.added if isinstance(o, StoryProductAnalysis)] == []  # nothing cached


def test_summary_message_keeps_skip_and_ai_categories_distinct():
    msg = summary_message({"analyzed": 5, "products_found": 3, "outside_assistant": 1,
                           "skipped_no_content": 4, "ai_unavailable": 2})
    assert "5" in msg and "3" in msg
    assert "بدون محتوای قابل‌تحلیل" in msg      # the distinct skipped category
    assert "تلاش مجدد" in msg                    # ai-unavailable retry note


# ── real-DB: full-backlog scope, today opt-in, own exclusion, resumability, instant task_id ──────
import pytest as _pytest
from datetime import datetime, timedelta

ELIG_INSTANCE = "v47p2_elig_inst"
RES_INSTANCE = "v47p2_resume_inst"
OWN_PHONE = "989121110009"
OUT_PHONE = "989129990009"


async def _clear_instance(instance_id):
    from app.database import AsyncSessionLocal
    from app.models.received_status import ReceivedStatus
    from app.models.story_analysis import StoryProductAnalysis
    from sqlalchemy import select, delete
    async with AsyncSessionLocal() as db:
        ids = list((await db.execute(
            select(ReceivedStatus.id).where(ReceivedStatus.instance_id == instance_id))).scalars().all())
        if ids:
            await db.execute(delete(StoryProductAnalysis).where(StoryProductAnalysis.story_id.in_(ids)))
        await db.execute(delete(ReceivedStatus).where(ReceivedStatus.instance_id == instance_id))
        await db.commit()


def _rs(instance_id, **kw):
    from app.models.received_status import ReceivedStatus
    base = dict(instance_id=instance_id, status_message_id=uuid.uuid4().hex,
                sender_phone=OUT_PHONE, sender_name="فروشنده", status_type="text",
                text_content="یخچال ساید", created_at=datetime.utcnow())
    base.update(kw)
    return ReceivedStatus(**base)


@_pytest.mark.asyncio
async def test_eligible_full_backlog_vs_today_only_and_own_exclusion(monkeypatch):
    from app.database import AsyncSessionLocal, engine
    from app.services.story_backlog import eligible_story_ids
    from app.services.own_number_exclusion import add_exclusion, remove_exclusion, normalize_own_number
    from app.models.own_number import OwnNumberExclusion
    from sqlalchemy import select, delete
    await engine.dispose()
    await _clear_instance(ELIG_INSTANCE)
    today = datetime.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    three_days = today - timedelta(days=3)
    own_core = normalize_own_number(OWN_PHONE)
    async with AsyncSessionLocal() as db:
        db.add_all([
            _rs(ELIG_INSTANCE, text_content="A backlog", created_at=yesterday),          # backlog
            _rs(ELIG_INSTANCE, text_content="B today", created_at=today),                # today
            _rs(ELIG_INSTANCE, text_content="C own", sender_phone=OWN_PHONE, created_at=today),  # own → excluded
            _rs(ELIG_INSTANCE, status_type="video", text_content=None, created_at=three_days),   # multi-day backlog
        ])
        await add_exclusion(db, OWN_PHONE, source="manual")
        await db.commit()
    try:
        async with AsyncSessionLocal() as db:
            full = await eligible_story_ids(db, instance_id=ELIG_INSTANCE)
            today_only = await eligible_story_ids(db, instance_id=ELIG_INSTANCE, today_only=True)
        # full backlog: A (yesterday) + B (today) + video (3 days) = 3, own C excluded
        assert len(full) == 3
        # today-only opt-in: just B (own C still excluded, A/video are prior days)
        assert len(today_only) == 1
    finally:
        await _clear_instance(ELIG_INSTANCE)
        async with AsyncSessionLocal() as db:
            await db.execute(delete(OwnNumberExclusion).where(OwnNumberExclusion.phone_core == own_core))
            await db.commit()


@_pytest.mark.asyncio
async def test_terminal_skip_and_per_batch_commit_survives_interruption(monkeypatch):
    from app.database import AsyncSessionLocal, engine
    from app.services.story_backlog import eligible_story_ids, process_backlog_batch
    from app.models.received_status import ReceivedStatus
    from sqlalchemy import select
    async def _catalog(*_a, **_k): return CATALOG
    monkeypatch.setattr("app.services.price_service.get_products", _catalog)
    async def _cores(*_a, **_k): return set()
    async def _raise(*_a, **_k): return False
    monkeypatch.setattr("app.services.catalog_spot_alert.get_our_phone_cores", _cores)
    monkeypatch.setattr("app.services.catalog_spot_alert.maybe_raise_spot_alert", _raise)
    await engine.dispose()
    await _clear_instance(RES_INSTANCE)
    async with AsyncSessionLocal() as db:
        db.add_all([
            _rs(RES_INSTANCE, status_type="video", text_content=None),        # no-content → skip
            _rs(RES_INSTANCE, status_type="text", text_content="   "),        # empty → skip
            _rs(RES_INSTANCE, status_type="text", text_content="کولر گازی گری 18000"),  # real
        ])
        await db.commit()
    try:
        async with AsyncSessionLocal() as db:
            ids = await eligible_story_ids(db, instance_id=RES_INSTANCE)
        assert len(ids) == 3

        # process ONLY the first batch (one story) and commit — simulates one durable batch.
        async with AsyncSessionLocal() as db:
            rows = list((await db.execute(
                select(ReceivedStatus).where(ReceivedStatus.id == ids[0]))).scalars().all())
            await process_backlog_batch(db, rows)
            await db.commit()

        # SIMULATED CRASH before the rest. The committed batch must have survived: only the
        # remaining 2 stay eligible (never re-doing the first).
        async with AsyncSessionLocal() as db:
            remaining = await eligible_story_ids(db, instance_id=RES_INSTANCE)
        assert set(remaining) == set(ids[1:])

        # finish the remainder → every story now has a terminal state → eligible reaches zero.
        async with AsyncSessionLocal() as db:
            rows = list((await db.execute(
                select(ReceivedStatus).where(ReceivedStatus.id.in_(remaining)))).scalars().all())
            await process_backlog_batch(db, rows)
            await db.commit()
        async with AsyncSessionLocal() as db:
            assert await eligible_story_ids(db, instance_id=RES_INSTANCE) == []
    finally:
        await _clear_instance(RES_INSTANCE)


@_pytest.mark.asyncio
async def test_endpoint_returns_task_id_immediately_without_inline_analysis(monkeypatch):
    from app.database import AsyncSessionLocal, engine
    from app.api.v1 import statuses
    from app.workers import tasks as tasks_mod
    await engine.dispose()

    dispatched = {}
    def _fake_delay(job_id, instance_id, today_only):
        dispatched["job_id"] = job_id
        dispatched["instance_id"] = instance_id
    monkeypatch.setattr(tasks_mod.task_analyze_story_backlog, "delay", _fake_delay)

    class _FakeRedis:
        def __init__(self): self.kv = {}
        async def set(self, k, v, ex=None): self.kv[k] = v
        async def get(self, k): return self.kv.get(k)
    fake = _FakeRedis()
    async def _get_redis(): return fake
    monkeypatch.setattr("app.services.redis_rate_limiter.get_redis", _get_redis)

    async with AsyncSessionLocal() as db:
        res = await statuses.analyze_today_statuses(account_id=None, db=db)
    # returned instantly with a task_id; work was DELEGATED to the task, not run inline
    assert res["started"] is True
    assert res["task_id"] and res["task_id"] == dispatched.get("job_id")
    assert isinstance(res["total"], int)
    # progress key was seeded so the very first poll has an accurate total
    from app.workers.tasks import story_backlog_progress_key
    assert story_backlog_progress_key(res["task_id"]) in fake.kv
