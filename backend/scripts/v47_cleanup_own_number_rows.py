"""V47 PART 1 (THREAD A) — clean up historical product_mention_logs rows that belong to one of
our own numbers.

These are legacy rows recorded BEFORE the V45 detection-time own-number guards existed. The V45
report safety net (`exclude_own_condition`) already hides them from the top-products report, but
they still sit physically in the table. This one-off deletes exactly those rows — nothing else.

The matching logic is IDENTICAL to the V45 report-side safety net: a row belongs to an own number
when its stored `sender_phone` contains one of the currently-listed own-number national cores (in
any format — 09…, 98…, …@c.us all embed the same 10-digit core). Rows with a NULL/blank
sender_phone are never matched (they cannot be attributed to an own number).

Usage (inside the backend container):
    python -m scripts.v47_cleanup_own_number_rows            # dry-run: list matching rows only
    python -m scripts.v47_cleanup_own_number_rows --apply    # delete the matching rows (committed)
"""
import asyncio
import sys

from sqlalchemy import select, or_

from app.database import AsyncSessionLocal
from app.models.reporting import ProductMentionLog
from app.services.own_number_exclusion import get_excluded_cores


async def _matching_rows(db, cores):
    """Every product_mention_logs row whose sender_phone contains one of the own-number cores.
    Mirrors exclude_own_condition's LIKE match exactly, but as a POSITIVE selection (the rows the
    report hides) so we can enumerate and delete precisely those rows."""
    cores = [c for c in (cores or set()) if c]
    if not cores:
        return []
    q = (select(ProductMentionLog)
         .where(ProductMentionLog.sender_phone.isnot(None))
         .where(or_(*[ProductMentionLog.sender_phone.like(f"%{core}%") for core in cores]))
         .order_by(ProductMentionLog.mentioned_at))
    return list((await db.execute(q)).scalars().all())


async def main(apply: bool) -> int:
    async with AsyncSessionLocal() as db:
        cores = await get_excluded_cores(db)
        print(f"currently-listed own-number cores: {len(cores)}", flush=True)
        rows = await _matching_rows(db, cores)
        print(f"matching product_mention_logs rows (own-number sender): {len(rows)}", flush=True)
        for r in rows:
            print(f"  id={r.id} product={r.product_name!r} phone={r.sender_phone!r} "
                  f"source={r.source!r} at={r.mentioned_at}", flush=True)
        if not apply:
            print("DRY RUN — pass --apply to delete these rows.", flush=True)
            return 0
        if not rows:
            print("nothing to delete.", flush=True)
            return 0
        deleted_ids = [r.id for r in rows]
        for r in rows:
            await db.delete(r)
        await db.commit()
        print(f"DELETED {len(deleted_ids)} row(s): {[str(i) for i in deleted_ids]}", flush=True)

    # Verify: re-query in a fresh session and confirm zero remain.
    async with AsyncSessionLocal() as db:
        cores = await get_excluded_cores(db)
        remaining = await _matching_rows(db, cores)
        print(f"post-delete verification — matching rows remaining: {len(remaining)}", flush=True)
        return 0 if not remaining else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main("--apply" in sys.argv)))
