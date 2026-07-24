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
from app.services.product_match import product_group_key


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
                            source: str | None = None, search: str | None = None) -> list[dict]:
    """The exact top-products aggregation the tab uses: per product_name over the last `days`,
    mention_count (all rows), group_count (distinct group), sender_count (distinct sender), the
    distinct `sources` contributing (pv/group/status), and the last mention time. When `source` is
    given, only mentions from that source are counted (the report's منبع filter). When `search` is
    given (V44), only products whose NORMALIZED name contains the normalized search term are returned
    — the same normalization used for grouping, so a search matches every spelling of a product.
    Returns raw rows (rank + raw `last_mention` datetime) so each caller formats the timestamp."""
    # V43 PART 2 — the tab's تعداد picker now goes up to 1000, so the top-products aggregation honors
    # a limit that high (the grouped query stays fast at this size). Other callers of clamp_limit
    # keep their own ceilings; only this shared top-products path is raised.
    limit = clamp_limit(limit, hi=1000)
    # Aggregate per RAW product_name in SQL (fast, uses the DB's distinct counts). The V44 merge below
    # then folds near-identical spellings together in Python, so the SQL limit is NOT applied here —
    # otherwise a low-ranked spelling variant could fall outside the window and never merge into its
    # real product. The retained data is small (a few days), so fetching all groups is cheap.
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
    )
    if source:
        q = q.where(ProductMentionLog.source == source)
    rows = (await db.execute(q)).all()

    # V44 — merge near-identical product-name spellings into ONE row by a normalized key (reusing the
    # project's existing normalizers via product_match.product_group_key), so the same real product is
    # not fragmented across spacing/digit-script/case/letter variants. mention_count (the ranking
    # metric) and sources/last_mention are exact; group_count/sender_count are summed as an upper
    # bound (the same group or sender using two spellings of one product is rare). The most-frequent
    # spelling is shown, and any catalog match makes the merged row in-assistant.
    merged: dict[str, dict] = {}
    for r in rows:
        key = product_group_key(r.product_name)
        e = merged.get(key)
        if e is None:
            e = {"product_name": r.product_name, "product_id": None, "mention_count": 0,
                 "group_count": 0, "sender_count": 0, "sources": set(),
                 "last_mention": None, "_top": -1}
            merged[key] = e
        mc = int(r.mention_count or 0)
        e["mention_count"] += mc
        e["group_count"] += int(r.group_count or 0)
        e["sender_count"] += int(r.sender_count or 0)
        for s in _split_sources(getattr(r, "sources", None)):
            e["sources"].add(s)
        lm = getattr(r, "last_mention", None)
        if lm is not None and (e["last_mention"] is None or lm > e["last_mention"]):
            e["last_mention"] = lm
        if mc > e["_top"]:                       # display the most-common spelling
            e["_top"] = mc
            e["product_name"] = r.product_name
        if e["product_id"] is None and r.product_id:   # any catalog match → in-assistant
            e["product_id"] = r.product_id

    # V44 — server-side search over the FULL merged set (not just the loaded page), tolerant of the
    # same normalization as the grouping: a search for one spelling («ال جی») matches every merged
    # variant («ال‌جی»). A term that normalizes to empty (only spaces/punctuation) is treated as no
    # filter. Applied BEFORE the limit so it searches all products in the window.
    items = merged.items()
    term = product_group_key(search) if search else ""
    if term:
        items = [(k, e) for k, e in items if term in k]
    ordered = sorted((e for _k, e in items),
                     key=lambda e: e["mention_count"], reverse=True)[:limit]
    return [
        {
            "rank": i + 1,
            "product_name": e["product_name"],
            "product_id": e["product_id"],
            "in_assistant": bool(e["product_id"]),
            "mention_count": e["mention_count"],
            "group_count": e["group_count"],
            "sender_count": e["sender_count"],
            "sources": sorted(e["sources"]),
            "last_mention": e["last_mention"],   # raw datetime (may be None)
        }
        for i, e in enumerate(ordered)
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
