"""V49 PART 4 — end-to-end across all three fixes, on a real DB (v47/v48 integration style).

Threads one previously-missed listing through the WHOLE pipeline:
  1. PART 3 — detect_product_mentions now catches the "<capacity> <brand> … موجود" listing.
  2. It flows into the top-products report (product_reports.top_products_rows) …
  3. … respecting the V45 own-number exclusion (an own-number copy is dropped) and the V44
     normalized merge (a digit-script spelling variant folds into one row).
  4. PART 1 — a 91-day-old copy is purged by purge_old_product_mentions while today's rows survive,
     and the 90-day report window reflects that.

Seeds only its own uniquely-instanced rows and cleans up after itself so it never disturbs real data.
"""
from datetime import datetime, timedelta

import pytest

TEST_INSTANCE = "v49p4_test_inst"
OUT_PHONE = "989121230001"          # outside contact → counted in the report
OWN_PHONE = "989350009999"          # our own number → V45 exclusion must drop it
OWN_CORE = "9350009999"

# A fixed local catalog (no redis/httpx get_products call — keeps this real-DB test hermetic and free
# of cross-event-loop pool issues). The brand lexicon is derived from these names exactly as in prod.
PRODUCTS = [
    {"name": "کولر گازی جنرال گلد 24000 مدل CG-MF24000 اینورتر"},
    {"name": "کولر گازی یونیوا 18000 مدل UN-TS18"},
]


@pytest.mark.asyncio
async def test_v49_detection_report_exclusion_and_retention_end_to_end():
    from app.database import AsyncSessionLocal, engine
    from app.models.reporting import ProductMentionLog
    from app.services.product_match import detect_product_mentions
    from app.services.product_reports import top_products_rows
    from app.workers.tasks import purge_old_product_mentions
    from sqlalchemy import delete
    await engine.dispose()          # fresh, loop-bound pool → avoid a stale cross-test connection

    # 1) PART 3 — the previously-missed brand+capacity listing is now detected end-to-end.
    products = PRODUCTS
    text = "۲۴ هزار جنرال گلد اکو موجود✅"
    hits = detect_product_mentions(text, products)
    assert hits, "brand+capacity listing must now be detected"
    pname = hits[0]["product_name"]
    assert hits[0]["product_id"] is None            # advertised outside the assistant catalog

    # A digit-script spelling variant of the same name → must MERGE into one report row (V44).
    variant = pname.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    if variant == pname:
        variant = pname + " "                       # still normalizes to the same key

    # Anchor to real time: the report's 90-day window and the purge's 90-day cutoff are both relative
    # to utcnow(), so a "today" row is inside both and a "91 days ago" row is outside both.
    now = datetime.utcnow()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(ProductMentionLog).where(ProductMentionLog.instance_id == TEST_INSTANCE))
        # today, outside contact, two spellings → merge to one product, count 2
        db.add(ProductMentionLog(product_name=pname, source="group", sender_phone=OUT_PHONE,
                                 instance_id=TEST_INSTANCE, message_text=text, mentioned_at=now))
        db.add(ProductMentionLog(product_name=variant, source="group", sender_phone=OUT_PHONE,
                                 instance_id=TEST_INSTANCE, message_text=text, mentioned_at=now))
        # today, OWN number → V45 exclusion must drop it from the report
        db.add(ProductMentionLog(product_name=pname, source="group", sender_phone=OWN_PHONE,
                                 instance_id=TEST_INSTANCE, message_text=text, mentioned_at=now))
        # 91 days old (outside contact) → beyond the 90-day retention → must be purged
        db.add(ProductMentionLog(product_name=pname, source="group", sender_phone=OUT_PHONE,
                                 instance_id=TEST_INSTANCE, message_text=text,
                                 mentioned_at=now - timedelta(days=91)))
        await db.commit()

    def _mine(rows):
        from app.services.product_match import product_group_key
        key = product_group_key(pname)
        return [r for r in rows if product_group_key(r["product_name"]) == key]

    async def _raw_count(db):
        from sqlalchemy import select, func
        return (await db.execute(
            select(func.count()).select_from(ProductMentionLog)
            .where(ProductMentionLog.instance_id == TEST_INSTANCE))).scalar()

    try:
        # 2+3) Report over 90 days, own-number excluded: the two today spellings merge into ONE product
        #      row (V44) and the own-number copy is NOT counted (V45). The 91-day row is already out of
        #      the 90-day window, so the detected listing shows a clean count of 2.
        async with AsyncSessionLocal() as db:
            assert await _raw_count(db) == 4         # 2 today outside + 1 today own + 1 old outside
            rows = await top_products_rows(db, days=90, limit=1000, exclude_cores={OWN_CORE})
            mine = _mine(rows)
            assert len(mine) == 1                    # V44 merge → single row
            assert mine[0]["mention_count"] == 2     # two today outside spellings; own excluded

        # 4) PART 1 — the scheduled purge removes ONLY the >90-day row; today's rows survive.
        async with AsyncSessionLocal() as db:
            deleted = await purge_old_product_mentions(db)   # real job, utcnow-based, 90-day window
            assert deleted >= 1                      # at least our 91-day row (no real >90d data today)

        async with AsyncSessionLocal() as db:
            assert await _raw_count(db) == 3         # the 91-day row is gone; the 3 today rows remain
            rows = await top_products_rows(db, days=90, limit=1000, exclude_cores={OWN_CORE})
            mine = _mine(rows)
            assert len(mine) == 1
            assert mine[0]["mention_count"] == 2     # today's two outside spellings still reported
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(ProductMentionLog).where(ProductMentionLog.instance_id == TEST_INSTANCE))
            await db.commit()
