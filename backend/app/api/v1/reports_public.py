"""Narrow, READ-ONLY public LAN API for the «جدول محصولات پر تکرار» (top repeated products) tab.

A separate system on the LAN (e.g. http://192.168.170.8:3100) fetches these to render the same
live data a human sees on /reporting → «جدول محصولات پر تکرار» and its «مشاهده فروشندگان اخیر»
drill-down. This is a STABLE, minimal public contract — it does NOT expose the rest of the
reporting internals. Both endpoints format from the SAME shared aggregation the UI uses
(app.services.product_reports), so they can never drift from the tab.

Read-only: no writes, no side effects, no auth (matching the app's other read endpoints). CORS for
these paths is handled by a dedicated, env-configurable allowlist in main.py (scoped to
/api/v1/reports/* only). No PII beyond the phone numbers the «مشاهده فروشندگان اخیر» panel already
shows in-app.
"""
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import product_reports as pr
from app.utils.shamsi import to_shamsi

router = APIRouter(prefix="/reports", tags=["reports-public"])


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


# ── scoped CORS helpers (pure, unit-tested; the middleware in main.py applies these) ──────────
def parse_allowed_origins(raw: str | None) -> list[str]:
    """Parse the REPORTS_ALLOWED_ORIGINS comma-separated env value into a clean list."""
    return [o.strip() for o in (raw or "").split(",") if o.strip()]


def cors_headers_for(origin: str | None, allowed: list[str],
                     request_headers: str | None = None) -> dict:
    """The CORS response headers to add for a /reports request, given the request Origin and the
    configured allowlist. Echoes a SPECIFIC allowed origin (never '*' when an Origin is present, so
    it stays valid alongside allow-credentials); only a credential-less, origin-less caller under a
    '*' allowlist gets '*'. A disallowed origin gets no header from this layer."""
    allow_all = "*" in allowed
    if origin and (allow_all or origin in allowed):
        return {
            "Access-Control-Allow-Origin": origin,
            "Vary": "Origin",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": request_headers or "*",
            "Access-Control-Max-Age": "600",
        }
    if allow_all and not origin:
        return {"Access-Control-Allow-Origin": "*"}
    return {}


@router.get("/top-products")
async def public_top_products(range: int = 30, limit: int = 30, source: str | None = None,
                              db: AsyncSession = Depends(get_db)):
    """Top-N most-mentioned products over the last `range` DAYS — the exact rows the tab shows.

    `range` is a number of days (the tab's بازه picker: 7 / 30 / 90); any positive int is accepted
    so it always matches the tab for the same value. `limit` is the count (the تعداد picker:
    50 / 100 / 150). Each row: rank, product_name, mention_count (all mentions in range),
    group_count (distinct groups), sender_count (distinct senders), last_mentioned_at."""
    days = max(1, int(range))
    # Match the UI tab's own top-products ceiling (raised to 1000 in V43 PART 2). The public and UI
    # endpoints share one aggregation, so their limits must not diverge — otherwise the LAN report
    # silently truncates at 500 while the in-app tab shows up to 1000. (The sibling mentioners
    # endpoint deliberately stays at the default 500, matching its own UI counterpart product_sellers,
    # which is unchanged.)
    limit = pr.clamp_limit(limit, hi=1000)
    from app.services.price_service import get_products
    product_ids = {p.get("name"): p.get("id") for p in await get_products(500) if p.get("name")}
    # V45 PART 2.3 — top_products_rows fetches the own-number exclusion list itself and filters those
    # rows out of the shared aggregation (so the public report matches the in-app tab).
    rows = await pr.top_products_rows(db, days=days, limit=limit, source=source)
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "range_days": days,
        "limit": limit,
        "source": source,
        "count": len(rows),
        "products": [
            {
                **({"product_id": r["product_id"] or product_ids.get(r["product_name"]),
                    "in_assistant": bool(r["product_id"] or product_ids.get(r["product_name"])),
                    "assistant_status": "در دستیار داریم" if (r["product_id"] or product_ids.get(r["product_name"])) else "خارج از دستیار"}),
                "rank": r["rank"],
                "product_name": r["product_name"],
                "mention_count": r["mention_count"],
                "group_count": r["group_count"],
                "sender_count": r["sender_count"],
                "sources": r["sources"],
                "last_mentioned_at": _iso(r["last_mention"]),
                "last_mentioned_shamsi": to_shamsi(r["last_mention"]),
            }
            for r in rows
        ],
    }


@router.get("/top-products/{product_name}/mentioners")
async def public_product_mentioners(product_name: str, range: int = 30, limit: int = 100,
                                    db: AsyncSession = Depends(get_db)):
    """The «مشاهده فروشندگان اخیر» drill-down for one product (by name — the tab's aggregation key;
    URL-encode names with spaces/special chars). Recent mentions over the last `range` DAYS, newest
    first: timestamp, group_name, sender_phone (the sender's own number), sender_phone_secondary
    (first extra number found in the message, if any), sender_display_name — plus all_contacts and
    a message_preview (the same fields the in-app «خروجی اکسل» export uses)."""
    days = max(1, int(range))
    limit = pr.clamp_limit(limit)
    rows = await pr.product_mentioners_rows(db, product_name=product_name, days=days, limit=limit)
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "product_name": product_name,
        "range_days": days,
        "count": len(rows),
        "mentioners": [
            {
                "timestamp": _iso(r["mentioned_at"]),
                "timestamp_shamsi": to_shamsi(r["mentioned_at"]),
                "group_name": r["group_name"],
                "sender_display_name": r["sender_display_name"],
                "sender_phone": r["sender_phone"],
                "sender_phone_secondary": r["sender_phone_secondary"],
                "all_contacts": r["all_contacts"],
                "message_preview": r["message_preview"],
            }
            for r in rows
        ],
    }
