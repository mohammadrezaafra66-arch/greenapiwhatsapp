"""V45 PART 1/2 — the "our own numbers" exclusion service.

Single source of truth for: normalizing a number to its match key, listing the currently-excluded
cores, testing whether a phone is excluded, adding/removing entries, and pre-seeding from our own
Green API instances. Reused by every detection/harvest entry point (webhook message path + story
analysis) so the exclusion decision is made in ONE place and BEFORE any AI/vision call.

The match key is the national 10-digit core from the project's existing normalizer
(product_reports.phone_core) — the SAME key the V40 spot-alert path uses for "our own accounts", so
exclusion matching is consistent with the rest of the codebase and format-agnostic.
"""
from __future__ import annotations
import logging
from datetime import datetime

from sqlalchemy import select

from app.models.own_number import OwnNumberExclusion
from app.services.product_reports import phone_core

logger = logging.getLogger("afrakala.own_number_exclusion")


def normalize_own_number(phone: str | None) -> str:
    """The canonical match key for a number: its national 10-digit core (reuses phone_core)."""
    return phone_core(phone or "")


async def get_excluded_cores(db) -> set[str]:
    """Every currently-excluded phone core. Small table → cheap to read per detection pass."""
    rows = (await db.execute(select(OwnNumberExclusion.phone_core))).scalars().all()
    return {c for c in rows if c}


async def is_excluded(db, phone: str | None, *, cores: set[str] | None = None) -> bool:
    """True if `phone` belongs to one of our own numbers. Pass a pre-fetched `cores` set to avoid a
    per-call query when checking many numbers in a loop."""
    core = normalize_own_number(phone)
    if not core:
        return False
    if cores is None:
        cores = await get_excluded_cores(db)
    return core in cores


async def add_exclusion(db, phone: str | None, *, label: str | None = None,
                        source: str = "manual", now: datetime | None = None
                        ) -> tuple[OwnNumberExclusion | None, bool]:
    """Add one number. Returns (row, created). Idempotent on the phone core: a number already listed
    is returned unchanged with created=False (and never duplicated). Does NOT commit."""
    core = normalize_own_number(phone)
    if not core:
        return None, False
    existing = (await db.execute(
        select(OwnNumberExclusion).where(OwnNumberExclusion.phone_core == core)
    )).scalar_one_or_none()
    if existing is not None:
        # Backfill a label if the row had none and one is now supplied (e.g. manual note over a seed).
        if label and not existing.label:
            existing.label = label[:200]
        return existing, False
    row = OwnNumberExclusion(
        phone_core=core, phone_raw=(phone or None), label=(label[:200] if label else None),
        source=source, added_at=now or datetime.utcnow(),
    )
    db.add(row)
    return row, True


async def remove_exclusion(db, exclusion_id) -> bool:
    """Remove one entry by id. Returns True if a row was deleted. Does NOT commit."""
    row = await db.get(OwnNumberExclusion, exclusion_id)
    if row is None:
        return False
    await db.delete(row)
    return True


async def seed_from_accounts(db, now: datetime | None = None) -> int:
    """Pre-seed the list from our own Green API instances. Every account that has a phone number is
    one of our own numbers, so its core is added with source='account'. Idempotent and additive: a
    core already present (in ANY form — seeded or manual) is skipped, so re-running never duplicates
    and never disturbs manual entries. Returns the number of NEW rows added. Does NOT commit.

    Note: seeds from every account carrying a phone regardless of live connection state — an own
    number that is briefly disconnected is still our own number and must stay excluded.
    """
    from app.models.account import Account
    now = now or datetime.utcnow()
    present = await get_excluded_cores(db)
    rows = (await db.execute(
        select(Account.phone, Account.name).where(Account.phone.isnot(None))
    )).all()
    added = 0
    for phone, name in rows:
        core = normalize_own_number(phone)
        if not core or core in present:
            continue
        label = (f"اینستنس: {name}" if name else None)
        db.add(OwnNumberExclusion(
            phone_core=core, phone_raw=phone, label=(label[:200] if label else None),
            source="account", added_at=now,
        ))
        present.add(core)
        added += 1
    if added:
        logger.info("own-number exclusion: pre-seeded %d account number(s)", added)
    return added
