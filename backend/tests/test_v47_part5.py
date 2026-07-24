"""V47 PART 5 — integrated end-to-end across all three threads in one real-DB scenario.

  THREAD A: a legacy own-number product_mention_logs row is selected by the cleanup (and only it),
            while an outside row from the same product is left untouched.
  THREAD B: a genuine MULTI-DAY backlog (stories from more than one day, including a video and an
            empty-text story, plus an own-number story) is fully cleared by the default full-backlog
            action — the own-number story is never eligible, the video/empty-text stories reach a
            terminal skipped state, and the eligible count reaches zero.

THREAD C (navigation) is verified by the frontend node tests (src/nav/*.test.js) and the
nav-inventory --diff CLI; it has no backend surface.
"""
import uuid
from datetime import datetime, timedelta

import pytest

from app.services.own_number_exclusion import normalize_own_number

INSTANCE = "v47p5_e2e_inst"
OWN_PHONE = "989121110055"
OUT_PHONE = "989129990055"
OWN_CORE = normalize_own_number(OWN_PHONE)
PROD = "V47P5PROD ماشین ظرفشویی"


async def _clear():
    from app.database import AsyncSessionLocal
    from app.models.received_status import ReceivedStatus
    from app.models.story_analysis import StoryProductAnalysis
    from app.models.reporting import ProductMentionLog
    from app.models.own_number import OwnNumberExclusion
    from sqlalchemy import select, delete
    async with AsyncSessionLocal() as db:
        ids = list((await db.execute(
            select(ReceivedStatus.id).where(ReceivedStatus.instance_id == INSTANCE))).scalars().all())
        if ids:
            await db.execute(delete(StoryProductAnalysis).where(StoryProductAnalysis.story_id.in_(ids)))
        await db.execute(delete(ReceivedStatus).where(ReceivedStatus.instance_id == INSTANCE))
        await db.execute(delete(ProductMentionLog).where(ProductMentionLog.product_name == PROD))
        await db.execute(delete(OwnNumberExclusion).where(OwnNumberExclusion.phone_core == OWN_CORE))
        await db.commit()


def _rs(**kw):
    from app.models.received_status import ReceivedStatus
    base = dict(instance_id=INSTANCE, status_message_id=uuid.uuid4().hex, sender_phone=OUT_PHONE,
                sender_name="فروشنده", status_type="text", text_content="محصول",
                created_at=datetime.utcnow())
    base.update(kw)
    return ReceivedStatus(**base)


@pytest.mark.asyncio
async def test_all_three_threads_end_to_end(monkeypatch):
    from app.database import AsyncSessionLocal, engine
    from app.models.reporting import ProductMentionLog
    from app.services.own_number_exclusion import add_exclusion
    from app.services.story_backlog import eligible_story_ids, process_backlog_batch
    from app.models.received_status import ReceivedStatus
    from scripts.v47_cleanup_own_number_rows import _matching_rows
    from sqlalchemy import select

    async def _catalog(*_a, **_k):
        return [{"name": PROD, "id": "cat-p5"}]
    monkeypatch.setattr("app.services.price_service.get_products", _catalog)
    async def _cores(*_a, **_k): return set()
    async def _raise(*_a, **_k): return False
    monkeypatch.setattr("app.services.catalog_spot_alert.get_our_phone_cores", _cores)
    monkeypatch.setattr("app.services.catalog_spot_alert.maybe_raise_spot_alert", _raise)

    await engine.dispose()
    await _clear()

    now = datetime.utcnow()
    day1 = now - timedelta(days=2)
    day2 = now - timedelta(days=1)
    async with AsyncSessionLocal() as db:
        # THREAD A — one legacy own-number mention + an outside mention for the SAME product.
        db.add(ProductMentionLog(product_name=PROD, source="status", sender_phone=OWN_PHONE,
                                 instance_id=INSTANCE, mentioned_at=now))
        db.add(ProductMentionLog(product_name=PROD, source="status", sender_phone=OUT_PHONE,
                                 instance_id=INSTANCE, mentioned_at=now))
        # THREAD B — a multi-day backlog: day-1 real text, day-2 video + empty-text, plus own story.
        db.add_all([
            _rs(text_content=f"{PROD} موجود شد", created_at=day1),                 # analyzable text
            _rs(status_type="video", text_content=None, created_at=day2),          # skip (no frame)
            _rs(status_type="text", text_content="   ", created_at=day2),          # skip (empty)
            _rs(sender_phone=OWN_PHONE, text_content="own advert", created_at=day2),  # own → excluded
        ])
        await add_exclusion(db, OWN_PHONE, source="manual")
        await db.commit()

    try:
        # ── THREAD B: full backlog excludes the own story, spans BOTH days ──────────────────────
        async with AsyncSessionLocal() as db:
            ids = await eligible_story_ids(db, instance_id=INSTANCE)
        assert len(ids) == 3, "own-number story must not be eligible; the 3 outside (multi-day) are"

        async with AsyncSessionLocal() as db:
            rows = list((await db.execute(
                select(ReceivedStatus).where(ReceivedStatus.id.in_(ids)))).scalars().all())
            # confirm the backlog genuinely spans more than one day
            assert len({r.created_at.date() for r in rows}) >= 2
            out = await process_backlog_batch(db, rows)
            await db.commit()
        assert out["analyzed"] == 1 and out["products_found"] == 1
        assert out["skipped_no_content"] == 2       # the video + the empty-text story

        # every outside story now has a terminal state → eligible reaches zero
        async with AsyncSessionLocal() as db:
            assert await eligible_story_ids(db, instance_id=INSTANCE) == []

        # ── THREAD A: cleanup selects ONLY the own-number mention row ────────────────────────────
        async with AsyncSessionLocal() as db:
            matched = [r for r in await _matching_rows(db, {OWN_CORE}) if r.product_name == PROD]
            assert len(matched) == 1 and matched[0].sender_phone == OWN_PHONE
    finally:
        await _clear()
