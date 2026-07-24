"""V47 PART 1 (THREAD A) — the historical own-number cleanup selects EXACTLY the own-number rows.

Proves the one-off's matching query (`scripts.v47_cleanup_own_number_rows._matching_rows`) is
identical in effect to the V45 report safety net: it selects a legacy mention row from an own number
for deletion while leaving the same product's row from an outside number untouched. Real DB, same
style as test_v45_part2's report safety-net test — inserts a uniquely-named product, asserts the
selection, and cleans up after itself so it never disturbs real data.
"""
from datetime import datetime

import pytest

from app.services.own_number_exclusion import normalize_own_number

TEST_INSTANCE = "v47p1_test_inst"
OWN_PHONE = "989121110001"        # listed as own → its historical row must be selected for deletion
OUT_PHONE = "989129990002"        # outside number → must be LEFT alone
OWN_CORE = normalize_own_number(OWN_PHONE)


@pytest.mark.asyncio
async def test_cleanup_selects_only_own_number_rows():
    from app.database import AsyncSessionLocal, engine
    from app.models.reporting import ProductMentionLog
    from scripts.v47_cleanup_own_number_rows import _matching_rows
    from sqlalchemy import delete
    await engine.dispose()          # fresh, loop-bound pool → avoid a stale cross-test connection
    prod = "V47TESTPROD ماشین لباسشویی"
    now = datetime.utcnow()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(ProductMentionLog).where(ProductMentionLog.product_name == prod))
        db.add(ProductMentionLog(product_name=prod, source="status", sender_phone=OWN_PHONE,
                                 instance_id=TEST_INSTANCE, mentioned_at=now))
        db.add(ProductMentionLog(product_name=prod, source="status", sender_phone=OUT_PHONE,
                                 instance_id=TEST_INSTANCE, mentioned_at=now))
        await db.commit()
    try:
        async with AsyncSessionLocal() as db:
            matched = await _matching_rows(db, {OWN_CORE})
            mine = [r for r in matched if r.product_name == prod]
            # exactly the own-number row is selected; the outside row is NOT
            assert len(mine) == 1
            assert mine[0].sender_phone == OWN_PHONE

        # empty cores → nothing selected (null-safe, never a blanket delete)
        async with AsyncSessionLocal() as db:
            assert await _matching_rows(db, set()) == []
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(ProductMentionLog).where(ProductMentionLog.product_name == prod))
            await db.commit()
