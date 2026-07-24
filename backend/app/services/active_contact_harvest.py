"""V45 PART 3 — harvest DISTINCT active WhatsApp numbers into the lead list.

`upsert_active_contact` is the single entry point used by every observation site (story reception +
group/channel/forum/broadcast message ingest). It:
  • normalizes the number to its national core (reuses phone_core);
  • NEVER harvests one of our own numbers (PART 1 exclusion list);
  • inserts a new row the first time a number is seen, or just bumps last_seen_at + sighting_count on
    a later sighting — so a number is stored EXACTLY ONCE (the UNIQUE phone_core also enforces this).

Source classification reuses the codebase's established chat-id distinction (the same @g.us/@c.us
convention product-mention `source` tagging uses) rather than inventing new categories.
"""
from __future__ import annotations
import logging
from datetime import datetime

from sqlalchemy import select

from app.models.active_contact import ActiveWhatsappContact
from app.services.own_number_exclusion import normalize_own_number, is_excluded_core
from app.services.phone_extract import normalize_sender_phone

logger = logging.getLogger("afrakala.active_contact_harvest")


def message_source_for_chat_id(chat_id: str | None) -> str | None:
    """Classify a message's chat surface for harvesting. Returns the source label for a public/
    broadcast surface, or None for a PRIVATE (@c.us) chat — a direct DM to us is not a harvest
    source (requirement: only stories + group/channel/forum/broadcast-list activity is harvested)."""
    s = (chat_id or "").strip().lower()
    if not s:
        return None
    if s.endswith("@c.us"):
        return None                       # private direct chat → not harvested
    if s.endswith("@g.us"):
        return "group"
    if s.endswith("@newsletter"):
        return "channel"
    if s.endswith("@broadcast"):
        return "broadcast"
    return "group"                        # any other non-private surface → treat as group-like


async def upsert_active_contact(db, phone: str | None, *, name: str | None, source: str,
                                excluded_cores: set[str] | None = None,
                                now: datetime | None = None) -> ActiveWhatsappContact | None:
    """Record one sighting of an active number. Inserts on first sight, else bumps last_seen_at +
    sighting_count (never a duplicate row). Skips blank numbers and our OWN numbers. Returns the row
    (or None if skipped). Does NOT commit — the caller owns the transaction.

    Pass a pre-fetched `excluded_cores` set to avoid a per-message exclusion query in a loop."""
    core = normalize_own_number(phone)
    if not core:
        return None
    if excluded_cores is None:
        from app.services.own_number_exclusion import get_excluded_cores
        excluded_cores = await get_excluded_cores(db)
    if is_excluded_core(phone, excluded_cores):
        return None                       # our own number → never harvested
    now = now or datetime.utcnow()
    existing = (await db.execute(
        select(ActiveWhatsappContact).where(ActiveWhatsappContact.phone_core == core)
    )).scalar_one_or_none()
    if existing is not None:
        existing.last_seen_at = now
        existing.sighting_count = (existing.sighting_count or 0) + 1
        if not existing.display_name and name:      # backfill a name we didn't have before
            existing.display_name = name[:200]
        return existing
    row = ActiveWhatsappContact(
        phone_core=core,
        phone_display=normalize_sender_phone(phone or "") or (phone or None),
        display_name=(name[:200] if name else None),
        first_seen_source=source,
        first_seen_at=now, last_seen_at=now, sighting_count=1,
    )
    db.add(row)
    return row


async def harvest_status_senders(db, statuses, *, now: datetime | None = None) -> int:
    """Harvest the posters of a batch of fetched stories as active contacts (source='status').
    Fetches the own-number exclusion set once for the whole batch. Returns how many senders were
    upserted (new or bumped). Does NOT commit — the caller owns the transaction."""
    from app.services.story_media import normalize_status
    from app.services.own_number_exclusion import get_excluded_cores
    cores = await get_excluded_cores(db)
    n = 0
    for s in statuses or []:
        try:
            f = normalize_status(s)
        except Exception:
            continue
        row = await upsert_active_contact(
            db, f.get("sender_phone"), name=f.get("sender_name"), source="status",
            excluded_cores=cores, now=now)
        if row is not None:
            n += 1
    return n
