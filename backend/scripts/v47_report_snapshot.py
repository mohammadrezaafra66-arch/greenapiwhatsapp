"""V47 PART 1 self-check helper — snapshot the report state so we can prove the cleanup shifts
totals by exactly the deleted rows' contribution and touches nothing else.

Reports three numbers over a wide window (3650 days, so the historical rows are in range):
  raw_total          = total rows physically in product_mention_logs
  filtered_mentions  = sum of mention_count in the NORMAL report (own-number safety net ON)
  unfiltered_mentions= sum of mention_count with the safety net OFF (exclude_cores=set())

Expected after deleting the 2 own-number rows:
  raw_total          -> down by exactly 2
  filtered_mentions  -> UNCHANGED (safety net already hid them)
  unfiltered_mentions-> down by exactly 2 (their only contribution)

Usage: python -m scripts.v47_report_snapshot
"""
import asyncio

from sqlalchemy import select, func

from app.database import AsyncSessionLocal
from app.models.reporting import ProductMentionLog
from app.services.product_reports import top_products_rows


async def main() -> int:
    async with AsyncSessionLocal() as db:
        raw_total = (await db.execute(
            select(func.count()).select_from(ProductMentionLog))).scalar()
        filtered = await top_products_rows(db, days=3650, limit=1000)
        unfiltered = await top_products_rows(db, days=3650, limit=1000, exclude_cores=set())
        f_sum = sum(r["mention_count"] for r in filtered)
        u_sum = sum(r["mention_count"] for r in unfiltered)
        print(f"raw_total={raw_total}", flush=True)
        print(f"filtered_report_rows={len(filtered)} filtered_mentions={f_sum}", flush=True)
        print(f"unfiltered_report_rows={len(unfiltered)} unfiltered_mentions={u_sum}", flush=True)
    return 0


if __name__ == "__main__":
    asyncio.run(main())
