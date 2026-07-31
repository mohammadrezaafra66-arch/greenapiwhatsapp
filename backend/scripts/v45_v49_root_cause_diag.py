"""PART 3 — root-cause diagnostic for the V45/V49 failures.

Both tests are known to fail on origin/main (5f7d944) as well as on main today, so the cause is
environmental. This determines WHICH environmental factor, rather than assuming "data rot".

Run: docker-compose exec -T backend python _v45_v49_diag.py
"""
import asyncio
from datetime import datetime, timedelta

from sqlalchemy import text

from app.database import engine


async def main() -> None:
    async with engine.begin() as conn:
        print("=" * 68)
        print("PART 3 — V45/V49 ROOT CAUSE DIAGNOSTIC")
        print("=" * 68)

        rows = (await conn.execute(text(
            "select tablename from pg_tables where schemaname='public' "
            "and (tablename like '%product%' or tablename like '%message%') "
            "order by tablename"))).fetchall()
        print("\n[schema] product/message tables actually present:")
        for (name,) in rows:
            print(f"   - {name}")

        total = (await conn.execute(text(
            "select count(*) from product_mention_logs"))).scalar()
        print(f"\n[volume] product_mention_logs total rows: {total:,}")

        # ── V45's exact window: days=2, limit=1000 ────────────────────────────
        print("\n" + "-" * 68)
        print("V45: top_products_rows(days=2, limit=1000)")
        print("-" * 68)
        distinct_2d = (await conn.execute(text(
            "select count(distinct product_name) from product_mention_logs "
            "where mentioned_at >= now() - interval '2 days'"))).scalar()
        rows_2d = (await conn.execute(text(
            "select count(*) from product_mention_logs "
            "where mentioned_at >= now() - interval '2 days'"))).scalar()
        print(f"  rows in window            : {rows_2d:,}")
        print(f"  DISTINCT product_name     : {distinct_2d:,}")
        print(f"  test limit                : 1000")
        if distinct_2d > 1000:
            print(f"  >>> {distinct_2d - 1000:,} products fall OUTSIDE the limit.")
            print("  >>> A product with mention_count=1 cannot be in the top 1000.")
            print("  >>> ROOT CAUSE for V45: limit truncation, not detection logic.")
        else:
            print("  >>> Window fits inside the limit; truncation is NOT the cause.")

        # ── V49's exact window: days=90 ───────────────────────────────────────
        print("\n" + "-" * 68)
        print("V49: top_products_rows(days=90, limit=1000)")
        print("-" * 68)
        distinct_90d = (await conn.execute(text(
            "select count(distinct product_name) from product_mention_logs "
            "where mentioned_at >= now() - interval '90 days'"))).scalar()
        print(f"  DISTINCT product_name (90d): {distinct_90d:,}")

        pname = "24 هزار جنرال گلد اکو موجود✅"
        like = (await conn.execute(text(
            "select count(*), count(distinct sender_phone) "
            "from product_mention_logs where product_name like :p "
            "and mentioned_at >= now() - interval '90 days'"),
            {"p": f"%{pname[:20]}%"})).fetchone()
        print(f"  leftover rows matching the V49 fixture name: {like[0]} "
              f"(from {like[1]} distinct senders)")
        if like[0]:
            print("  >>> Residue from previous runs is still in the table.")
            print("  >>> The test DELETEs by instance_id only, so rows written under a")
            print("  >>> different instance_id survive and inflate the count.")
            det = (await conn.execute(text(
                "select instance_id, count(*) from product_mention_logs "
                "where product_name like :p and mentioned_at >= now() - interval '90 days' "
                "group by instance_id order by 2 desc limit 5"),
                {"p": f"%{pname[:20]}%"})).fetchall()
            for inst, n in det:
                print(f"        instance_id={inst!r}: {n} row(s)")

        # ── own-number exclusion list ────────────────────────────────────────
        print("\n" + "-" * 68)
        print("Own-number exclusion list")
        print("-" * 68)
        cores = (await conn.execute(text(
            "select phone_core from own_number_exclusions order by phone_core"))).fetchall()
        print(f"  entries: {len(cores)}")
        for (c,) in cores:
            print(f"   - {c}")

        print("\n" + "=" * 68)
        print("Both tests assert exact counts against this live, shared table.")
        print("Neither controls the data it measures. That is the defect.")
        print("=" * 68)


if __name__ == "__main__":
    asyncio.run(main())
