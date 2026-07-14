"""V16 PART 3 — advertising-link selection + formatting.

Pure functions (unit-testable) plus one DB helper used by the campaign runners to
append promotional links to a message. Selection is purely additive — when a campaign
has append_links off, links_for_campaign() returns "" so the message is byte-identical.
"""
import random

VALID_TYPES = {"telegram", "whatsapp", "instagram", "website", "other"}


def select_links(links: list, count: int, mode: str = "weighted") -> list:
    """Choose up to `count` distinct active links.

    mode='fixed'    → the top-weighted links (deterministic: weight desc, then title).
    mode='weighted' → weighted-random by `weight` (1..10), no duplicates.
    Only is_active links are eligible; count is capped at the number of active links.
    """
    active = [l for l in (links or []) if l.get("is_active", True)]
    if not active or (count or 0) <= 0:
        return []
    count = min(int(count), len(active))

    if mode == "fixed":
        return sorted(active, key=lambda l: (-int(l.get("weight", 5) or 5), str(l.get("title", ""))))[:count]

    # weighted-random without replacement
    pool = list(active)
    chosen = []
    for _ in range(count):
        weights = [max(1, int(l.get("weight", 5) or 5)) for l in pool]
        pick = random.choices(pool, weights=weights, k=1)[0]
        chosen.append(pick)
        pool.remove(pick)
    return chosen


def format_links_block(links: list) -> str:
    """Each link on its own line («🔗 title: url»), prefixed by a blank line.
    Empty list → '' (so nothing is appended)."""
    if not links:
        return ""
    lines = [f"🔗 {l.get('title', '')}: {l.get('url', '')}" for l in links]
    return "\n\n" + "\n".join(lines)


async def links_for_campaign(campaign, db) -> str:
    """Return the formatted links block to append for this campaign, or '' when the
    feature is off / there are no active links. Never raises (links are additive)."""
    if not getattr(campaign, "append_links", False):
        return ""
    try:
        from sqlalchemy import select
        from app.models.advertising import AdvertisingLink
        rows = (await db.execute(
            select(AdvertisingLink).where(AdvertisingLink.is_active.is_(True))
        )).scalars().all()
        links = [{"id": str(r.id), "url": r.url, "title": r.title,
                  "weight": r.weight, "is_active": r.is_active} for r in rows]
        chosen = select_links(links, getattr(campaign, "links_count", 1) or 1,
                              getattr(campaign, "links_mode", "weighted") or "weighted")
        return format_links_block(chosen)
    except Exception:
        return ""
