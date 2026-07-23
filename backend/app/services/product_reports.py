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


def _split_sources(raw: str | None) -> list[str]:
    """Turn the string_agg of distinct sources into a clean, stable list (pv/group/status)."""
    if not raw:
        return []
    return sorted({s.strip() for s in raw.split(",") if s and s.strip()})


async def top_products_rows(db: AsyncSession, *, days: int, limit: int,
                            source: str | None = None) -> list[dict]:
    """The exact top-products aggregation the tab uses: per product_name over the last `days`,
    mention_count (all rows), group_count (distinct group), sender_count (distinct sender), the
    distinct `sources` contributing (pv/group/status), and the last mention time. When `source` is
    given, only mentions from that source are counted (the report's منبع filter). Returns raw rows
    (rank + raw `last_mention` datetime) so each caller formats the timestamp as it needs."""
    # V43 PART 2 — the tab's تعداد picker now goes up to 1000, so the top-products aggregation honors
    # a limit that high (the grouped query stays fast at this size). Other callers of clamp_limit
    # keep their own ceilings; only this shared top-products path is raised.
    limit = clamp_limit(limit, hi=1000)
    q = (
        select(
            ProductMentionLog.product_name,
            func.max(ProductMentionLog.product_id).label("product_id"),
            func.count().label("mention_count"),
            func.count(func.distinct(ProductMentionLog.group_chat_id)).label("group_count"),
            func.count(func.distinct(ProductMentionLog.sender_phone)).label("sender_count"),
            func.string_agg(func.distinct(ProductMentionLog.source), ",").label("sources"),
            func.max(ProductMentionLog.mentioned_at).label("last_mention"),
        )
        .where(ProductMentionLog.mentioned_at >= _cutoff(days))
        .group_by(ProductMentionLog.product_name)
        .order_by(func.count().desc())
        .limit(limit)
    )
    if source:
        q = q.where(ProductMentionLog.source == source)
    rows = (await db.execute(q)).all()
    return [
        {
            "rank": i + 1,
            "product_name": r.product_name,
            "product_id": r.product_id,
            "in_assistant": bool(r.product_id),
            "mention_count": r.mention_count,
            "group_count": r.group_count,
            "sender_count": r.sender_count,
            "sources": _split_sources(getattr(r, "sources", None)),
            "last_mention": r.last_mention,   # raw datetime (may be None)
        }
        for i, r in enumerate(rows)
    ]


def phone_core(phone: str) -> str:
    """The national 10-digit core (9xxxxxxxxx) present in EVERY stored form of an Iranian mobile
    (09…, 98…, …@c.us), so one contact's mentions can be matched across pv/group/status regardless
    of how each row happened to store the number."""
    import re
    from app.services.phone_extract import normalize_sender_phone, normalize_digits
    d = re.sub(r"\D", "", normalize_sender_phone(normalize_digits(phone or "")))
    return d[-10:] if len(d) >= 10 else d


async def contact_trend_rows(db: AsyncSession, *, phone: str, days: int,
                             limit: int = 500) -> dict:
    """V40 PART 6 — one contact's advertising trend over time, unified across pv/group/status.
    Returns {timeline, summary}: `timeline` = every mention (newest first) with source + product +
    in_assistant flag + time; `summary` = per-product repeat counts for this contact (how many times,
    when last, in/out of assistant). Matched by the national 10-digit core so phone-format variants
    across sources all collapse to the same contact."""
    core = phone_core(phone)
    if not core:
        return {"timeline": [], "summary": []}
    rows = (await db.execute(
        select(ProductMentionLog)
        .where(ProductMentionLog.mentioned_at >= _cutoff(days))
        .where(ProductMentionLog.sender_phone.like(f"%{core}%"))
        .order_by(ProductMentionLog.mentioned_at.desc())
        .limit(clamp_limit(limit, hi=2000))
    )).scalars().all()

    timeline = [
        {
            "mentioned_at": m.mentioned_at,                # raw datetime
            "source": m.source or "pv",
            "product_name": m.product_name,
            "in_assistant": bool(m.product_id),
            "group_name": m.group_name or "",
        }
        for m in rows
    ]
    agg: dict[str, dict] = {}
    for m in rows:
        key = m.product_name or "—"
        e = agg.setdefault(key, {"product_name": key, "count": 0, "in_assistant": False,
                                 "last_mention": None, "sources": set()})
        e["count"] += 1
        e["in_assistant"] = e["in_assistant"] or bool(m.product_id)
        if m.source:
            e["sources"].add(m.source)
        if e["last_mention"] is None or (m.mentioned_at and m.mentioned_at > e["last_mention"]):
            e["last_mention"] = m.mentioned_at
    summary = sorted(
        ({**e, "sources": sorted(e["sources"])} for e in agg.values()),
        key=lambda e: e["count"], reverse=True,
    )
    return {"timeline": timeline, "summary": summary}


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
        # A «شماره کاری»-style secondary: the first DISTINCT extra number (not the sender's own,
        # even if they retyped it in the message). None when the seller listed no other number.
        secondary = next((c for c in all_contacts if c != sender_display), None)
        out.append({
            "mentioned_at": m.mentioned_at,               # raw datetime
            "group_name": m.group_name or "",
            "sender_display_name": m.sender_name or "",
            "sender_phone": sender_display,               # the sender's own number (primary)
            "sender_phone_secondary": secondary,
            "all_contacts": all_contacts,                 # every distinct number (superset)
            "message_preview": (m.message_text or "")[:120],
            "product_id": m.product_id,                   # nullable; not the aggregation key
        })
    return out
