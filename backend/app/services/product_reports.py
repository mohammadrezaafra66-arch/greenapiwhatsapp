"""Shared, read-only computation behind the «جدول محصولات پر تکرار» (top repeated products) tab
and its «مشاهده فروشندگان اخیر» (recent mentioners) drill-down on /reporting.

This is the SINGLE source of truth for both:
  • the existing UI endpoints (api/v1/reporting.py → /top-products, /product-sellers), and
  • the new narrow public LAN contract (api/v1/reports_public.py → /reports/*),
so the public API can NEVER drift from what a human sees in the tab — both format from the exact
same aggregation/query here. Read-only; no writes, no side effects.

The "product" identity used by the tab is the `product_name` string: the top-products aggregation
GROUPs BY product_name (product_mention_logs has a nullable `product_id` that is NOT the grouping
key), and the drill-down filters by product_name. So product_name is the correct drill-down key.
"""
from __future__ import annotations
from datetime import datetime, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reporting import ProductMentionLog
from app.services.phone_extract import contacts_for


def _cutoff(days: int) -> datetime:
    return datetime.utcnow() - timedelta(days=max(1, days))


def clamp_limit(limit: int, hi: int = 500) -> int:
    return max(1, min(int(limit), hi))


async def top_products_rows(db: AsyncSession, *, days: int, limit: int) -> list[dict]:
    """The exact top-products aggregation the tab uses: per product_name over the last `days`,
    mention_count (all rows), group_count (distinct group), sender_count (distinct sender), and the
    last mention time. Returns raw rows (rank + raw `last_mention` datetime) so each caller can
    format the timestamp however it needs (Shamsi for the UI, ISO for the public API)."""
    limit = clamp_limit(limit)
    rows = (await db.execute(
        select(
            ProductMentionLog.product_name,
            func.count().label("mention_count"),
            func.count(func.distinct(ProductMentionLog.group_chat_id)).label("group_count"),
            func.count(func.distinct(ProductMentionLog.sender_phone)).label("sender_count"),
            func.max(ProductMentionLog.mentioned_at).label("last_mention"),
        )
        .where(ProductMentionLog.mentioned_at >= _cutoff(days))
        .group_by(ProductMentionLog.product_name)
        .order_by(func.count().desc())
        .limit(limit)
    )).all()
    return [
        {
            "rank": i + 1,
            "product_name": r.product_name,
            "mention_count": r.mention_count,
            "group_count": r.group_count,
            "sender_count": r.sender_count,
            "last_mention": r.last_mention,   # raw datetime (may be None)
        }
        for i, r in enumerate(rows)
    ]


async def product_mentioners_rows(db: AsyncSession, *, product_name: str, days: int,
                                  limit: int) -> list[dict]:
    """The exact drill-down the «مشاهده فروشندگان اخیر» modal shows: the recent mentions of one
    product (by name) over the last `days`, newest first, each with sender contact info + group +
    time. Contact numbers are derived the SAME way the modal does (`contacts_for`): the sender's own
    number first, then any additional numbers found in the message text. Returns raw rows (raw
    `mentioned_at` datetime) for the caller to format."""
    limit = clamp_limit(limit)
    rows = (await db.execute(
        select(ProductMentionLog)
        .where(ProductMentionLog.product_name == product_name)
        .where(ProductMentionLog.mentioned_at >= _cutoff(days))
        .order_by(ProductMentionLog.mentioned_at.desc())
        .limit(limit)
    )).scalars().all()

    out = []
    for m in rows:
        sender_display, phones_in_msg, all_contacts = contacts_for(
            m.sender_phone or "", m.message_text or "")
        out.append({
            "mentioned_at": m.mentioned_at,               # raw datetime
            "group_name": m.group_name or "",
            "sender_display_name": m.sender_name or "",
            "sender_phone": sender_display,               # the sender's own number (primary)
            # first ADDITIONAL number found in the message text (a «شماره کاری»-style secondary),
            # None when the seller listed no extra number
            "sender_phone_secondary": (phones_in_msg[0] if phones_in_msg else None),
            "all_contacts": all_contacts,                 # every distinct number (superset)
            "message_preview": (m.message_text or "")[:120],
            "product_id": m.product_id,                   # nullable; not the aggregation key
        })
    return out
