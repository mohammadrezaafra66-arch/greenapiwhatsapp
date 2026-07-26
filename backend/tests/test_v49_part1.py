"""V49 PART 1 — product-mention retention is now 90 days (was a 2-day production purge).

Two guarantees:
  1. The purge job's configured window is 90 days — not 2 (or the interim 7). A cheap constant/unit
     assertion so a regression to a shorter window is caught without a DB.
  2. Boundary behavior against a REAL DB (same style as test_v47_part1): rows just INSIDE the 90-day
     window survive; rows just OUTSIDE it are deleted. Seeds uniquely-named rows and cleans up after
     itself so it never disturbs real data.
"""
from datetime import datetime, timedelta

import pytest

from app.workers.tasks import PRODUCT_MENTION_RETENTION_DAYS, purge_old_product_mentions

TEST_INSTANCE = "v49p1_test_inst"
PROD = "V49TESTPROD کولر گازی تست نگهداری"


def test_retention_window_is_90_days():
    # The deliberate ceiling chosen in V49 — guards against a silent regression to 2/7 days.
    assert PRODUCT_MENTION_RETENTION_DAYS == 90


@pytest.mark.asyncio
async def test_only_rows_older_than_90_days_are_purged():
    from app.database import AsyncSessionLocal, engine
    from app.models.reporting import ProductMentionLog
    from sqlalchemy import delete, select, func
    await engine.dispose()          # fresh, loop-bound pool → avoid a stale cross-test connection
    now = datetime(2026, 7, 26, 12, 0, 0)
    # Four ages straddling the 90-day boundary relative to `now`.
    ages = {
        "today":       now - timedelta(days=0),
        "just_inside": now - timedelta(days=89, hours=23),   # < 90d → KEEP
        "just_outside": now - timedelta(days=90, hours=1),   # > 90d → PURGE
        "very_old":    now - timedelta(days=200),            # > 90d → PURGE
    }
    async with AsyncSessionLocal() as db:
        await db.execute(delete(ProductMentionLog).where(ProductMentionLog.instance_id == TEST_INSTANCE))
        for label, ts in ages.items():
            db.add(ProductMentionLog(product_name=f"{PROD} {label}", source="group",
                                     sender_phone="989129990009", instance_id=TEST_INSTANCE,
                                     mentioned_at=ts))
        await db.commit()
    try:
        async with AsyncSessionLocal() as db:
            deleted = await purge_old_product_mentions(db, now=now)
            assert deleted == 2                              # exactly the two >90-day rows

        async with AsyncSessionLocal() as db:
            survivors = (await db.execute(
                select(ProductMentionLog.product_name)
                .where(ProductMentionLog.instance_id == TEST_INSTANCE)
            )).scalars().all()
            survivors = {s.rsplit(" ", 1)[-1] for s in survivors}
            # only the today + just-inside-90-days rows remain
            assert survivors == {"today", "just_inside"}
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(ProductMentionLog).where(ProductMentionLog.instance_id == TEST_INSTANCE))
            await db.commit()
