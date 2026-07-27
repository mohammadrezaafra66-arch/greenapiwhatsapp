"""V51 PART 1 — automatic story analysis chained after each scheduled fetch.

Proves:
  • cap_backlog_ids honors the per-run cap (oldest-first), treats None as uncapped (the manual
    button), and never loses the dropped tail (it just isn't selected this run);
  • the scheduled fetch task, once fetch finishes, dispatches the EXISTING analysis job
    (tasks.analyze_story_backlog) as a non-blocking follow-up with the AUTO_ANALYZE_MAX_STORIES cap —
    it does not run analysis inline and does not build a new analysis path;
  • the manual «تحلیل همه استوری‌ها» endpoint still dispatches the SAME task uncapped (unchanged);
  • (real DB) with a seeded backlog larger than the cap and a mix of healthy / rate-limited(dead)
    vision keys: a capped run processes only the oldest `cap`, the untouched remainder stays
    eligible, AND a story whose vision key was rate-limited stays eligible (no false "no product
    found") — the V40 vision-failure guard is preserved end-to-end.
"""
import inspect
import uuid
from datetime import datetime, timedelta

import pytest as _pytest

from app.services.story_backlog import cap_backlog_ids


# ── the pure cap contract ────────────────────────────────────────────────────────────────────────
def test_cap_backlog_ids_caps_oldest_first():
    ids = [f"id{i}" for i in range(10)]
    capped = cap_backlog_ids(ids, 3)
    assert capped == ["id0", "id1", "id2"]           # oldest-first, exactly the cap
    # the dropped tail is simply not selected — the caller's eligibility (no analysis row) is intact
    assert ids[3:] == [f"id{i}" for i in range(3, 10)]


def test_cap_backlog_ids_none_is_uncapped_manual_button():
    ids = [f"id{i}" for i in range(10)]
    assert cap_backlog_ids(ids, None) is ids          # manual button: full backlog, unchanged


def test_cap_backlog_ids_edge_cases():
    assert cap_backlog_ids([], 5) == []
    assert cap_backlog_ids(["a", "b"], 10) == ["a", "b"]   # cap larger than backlog
    assert cap_backlog_ids(["a", "b"], 0) == []            # zero → nothing
    assert cap_backlog_ids(["a", "b"], -3) == []           # negative → clamped to nothing


# ── the chain: fetch finishes → dispatch existing analysis job (capped, non-blocking) ─────────────
def test_scheduled_fetch_chains_capped_analysis(monkeypatch):
    from app.workers import tasks as tasks_mod

    # Make the fetch half a hermetic no-op (no real Green API / DB).
    class _FakeSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
    monkeypatch.setattr("app.database.AsyncSessionLocal", lambda: _FakeSession())

    async def _fake_fetch_all(db, **kw):
        return {"eligible": 3, "fetched": 3, "failed": 0, "skipped": 2, "total_statuses": 9}
    monkeypatch.setattr(
        "app.services.story_fetch.fetch_stories_for_all_eligible_accounts", _fake_fetch_all)

    dispatched = {}
    def _fake_delay(job_id, instance_id, today_only, max_stories):
        dispatched.update(job_id=job_id, instance_id=instance_id,
                          today_only=today_only, max_stories=max_stories)
    monkeypatch.setattr(tasks_mod.task_analyze_story_backlog, "delay", _fake_delay)

    tasks_mod.task_fetch_incoming_stories()

    # Analysis was chained as a follow-up, full-backlog (instance_id=None, today_only=False),
    # capped to the per-cycle limit — NOT run inline.
    assert dispatched["instance_id"] is None
    assert dispatched["today_only"] is False
    assert dispatched["max_stories"] == tasks_mod.AUTO_ANALYZE_MAX_STORIES
    assert dispatched["job_id"]                      # a real job id for the progress key


def test_cap_is_a_sensible_bounded_multiple_of_batch():
    from app.workers import tasks as tasks_mod
    from app.services.story_backlog import BATCH
    cap = tasks_mod.AUTO_ANALYZE_MAX_STORIES
    assert 0 < cap <= 200                            # bounded — never an unbounded vision run
    assert cap % BATCH == 0                           # whole batches, aligns with the resumable loop


def test_manual_button_still_dispatches_uncapped():
    """Regression: the manual endpoint dispatches the SAME task with the default (uncapped) scope —
    the auto cap is additive and must not have changed the manual path."""
    from app.api.v1 import statuses as statuses_api
    src = inspect.getsource(statuses_api.analyze_today_statuses)
    # It calls .delay(job_id, instance_id, today_only) — no max_stories → None → uncapped.
    assert "task_analyze_story_backlog.delay(job_id, instance_id, today_only)" in src


# ── real DB: cap + resumable + vision-failure guard, end-to-end ──────────────────────────────────
CATALOG = [{"id": "cat-1", "name": "کولر گازی گری 18000", "in_assistant": True}]
V51_INSTANCE = "v51p1_backlog_inst"
SELLER_PHONE = "989129990051"


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


def _img(instance_id, when, mid):
    from app.models.received_status import ReceivedStatus
    return ReceivedStatus(
        instance_id=instance_id, status_message_id=mid, sender_phone=SELLER_PHONE,
        sender_name="فروشنده", status_type="image", local_media_path=f"/media/{mid}.jpg",
        original_media_url=f"http://h/{mid}.jpg", text_content=None, caption=None,
        created_at=when)


@_pytest.mark.asyncio
async def test_capped_run_processes_oldest_and_leaves_remainder_and_ratelimited_eligible(monkeypatch):
    """Seed 5 image stories (all need vision). Cap = 3. Vision layer: healthy for the 1st & 3rd
    oldest, RATE-LIMITED (raises 429) for the 2nd. Expect after one capped run:
      • only the oldest 3 were attempted (the newest 2 untouched → still eligible);
      • the rate-limited one has NO analysis row → still eligible (NO false 'no product');
      • the 2 healthy ones are cached with the detected product.
    """
    from app.database import AsyncSessionLocal, engine
    from app.services.story_backlog import eligible_story_ids, process_backlog_batch, cap_backlog_ids
    from app.models.received_status import ReceivedStatus
    from app.models.story_analysis import StoryProductAnalysis
    from sqlalchemy import select

    async def _catalog(*_a, **_k): return CATALOG
    monkeypatch.setattr("app.services.price_service.get_products", _catalog)
    async def _cores(*_a, **_k): return set()
    async def _no_alert(*_a, **_k): return False
    monkeypatch.setattr("app.services.catalog_spot_alert.get_our_phone_cores", _cores)
    monkeypatch.setattr("app.services.catalog_spot_alert.maybe_raise_spot_alert", _no_alert)
    async def _excluded(*_a, **_k): return set()
    monkeypatch.setattr("app.services.own_number_exclusion.get_excluded_cores", _excluded)

    await engine.dispose()
    await _clear_instance(V51_INSTANCE)
    base = datetime.utcnow() - timedelta(hours=5)
    async with AsyncSessionLocal() as db:
        # created oldest → newest so eligible_story_ids (oldest-first) has a deterministic order
        db.add_all([_img(V51_INSTANCE, base + timedelta(minutes=i), f"v51msg{i}") for i in range(5)])
        await db.commit()

    try:
        async with AsyncSessionLocal() as db:
            ids = await eligible_story_ids(db, instance_id=V51_INSTANCE)
        assert len(ids) == 5

        CAP = 3
        batch_ids = cap_backlog_ids(ids, CAP)
        assert batch_ids == ids[:3]                    # oldest 3 selected

        # A vision layer standing in for the real V42 key pool: the 2nd-oldest story
        # (media path .../v51msg1.jpg) hits a rate-limited/dead key (429) → the analyzer must flag
        # vision_failed (uncached), never fabricate an empty "no product" result. Every other story
        # gets a healthy key that genuinely detects the product.
        async def _mixed_vision(path):
            if path.endswith("v51msg1.jpg"):
                raise RuntimeError("429 Too Many Requests")   # dead/rate-limited key for this one
            return {"text": "کولر گازی گری 18000", "provider": "openai"}  # healthy key

        async with AsyncSessionLocal() as db:
            rows = list((await db.execute(
                select(ReceivedStatus).where(ReceivedStatus.id.in_(batch_ids)))).scalars().all())
            res = await process_backlog_batch(db, rows, vision_fn=_mixed_vision)
            await db.commit()

        # 2 healthy analyzed + product found; 1 rate-limited counted as ai_unavailable (NOT analyzed)
        assert res["analyzed"] == 2
        assert res["products_found"] == 2
        assert res["ai_unavailable"] == 1

        async with AsyncSessionLocal() as db:
            remaining = await eligible_story_ids(db, instance_id=V51_INSTANCE)
            # rows that actually got a durable analysis row:
            analyzed_ids = set((await db.execute(
                select(StoryProductAnalysis.story_id))).scalars().all())

        # The untouched newest 2 + the rate-limited 1 are all still eligible (3 total). No story lost.
        assert set(remaining) == {ids[1], ids[3], ids[4]}
        # The rate-limited story has NO analysis row → it is NOT a false 'no product found'.
        assert ids[1] not in analyzed_ids
        # The 2 healthy ones ARE cached.
        assert ids[0] in analyzed_ids and ids[2] in analyzed_ids
    finally:
        await _clear_instance(V51_INSTANCE)
