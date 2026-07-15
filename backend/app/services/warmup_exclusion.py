"""V18 PART 2 — enrollment-based campaign exclusion (single source of truth).

A number that is being mesh-warmed (V17 `warmup_enrollment`, active and not yet GRADUATED)
must NEVER be pulled into a real campaign — otherwise it can be blasted and banned. Once it
GRADUATES it becomes campaign-eligible again.

This replaces the old `auto_warmup`-flag check as the authority, while still honoring the
legacy flag for any account that has no enrollment yet (smooth migration).

`warmup_campaign_excluded` is pure (takes a precomputed enrollment map) so it unit-tests
without a DB; the async helpers fail SAFE — if enrollments can't be read they fall back to
legacy behavior rather than breaking campaigns.
"""
from __future__ import annotations
import logging
from sqlalchemy import select

from app.services.warmup_state import WarmupState

logger = logging.getLogger("afrakala.warmup.exclusion")

GRADUATED = WarmupState.GRADUATED.value


async def enrollment_states_by_instance(db) -> dict:
    """{instance_id: (state, is_enabled)} for every warm-up enrollment. Fail-safe: returns
    {} if the table is unreadable, so campaigns fall back to legacy exclusion."""
    try:
        from app.models.warmup_mesh import WarmupEnrollment
        rows = (await db.execute(
            select(WarmupEnrollment.instance_id, WarmupEnrollment.state, WarmupEnrollment.is_enabled)
        )).all()
        return {iid: (state, bool(enabled)) for iid, state, enabled in rows}
    except Exception as e:
        logger.warning("enrollment map unreadable (fallback to legacy): %s", e)
        return {}


def warmup_campaign_excluded(account, enr_map: dict) -> bool:
    """True if `account` must be kept OUT of real campaigns because of warm-up.

    Enrollment is authoritative:
      • active (is_enabled) and NOT GRADUATED  → excluded (still warming).
      • GRADUATED                              → eligible (graduation overrides legacy flag).
      • enrollment disabled/paused             → eligible (warm-up not actively running).
      • no enrollment                          → legacy `auto_warmup` behavior.
    """
    st = enr_map.get(getattr(account, "instance_id", None))
    if st is not None:
        state, enabled = st
        if state == GRADUATED:
            return False
        return bool(enabled)
    from app.services.warmup_auto import in_active_warmup
    return in_active_warmup(account)


async def active_warming_instance_ids(db) -> set:
    """Instance ids currently being warmed (active, non-graduated) — never campaign-eligible."""
    m = await enrollment_states_by_instance(db)
    return {iid for iid, (state, enabled) in m.items() if enabled and state != GRADUATED}


async def enrolled_instance_ids(db) -> set:
    """Every instance that has a warm-up enrollment row (V17-managed) — used so the LEGACY
    warm-up engine defers to V17 and never double-warms an enrolled number."""
    m = await enrollment_states_by_instance(db)
    return set(m.keys())


async def reconcile_stale_auto_warmup(db) -> int:
    """V20 PART 1 — one-time/idempotent reconcile: clear the legacy `auto_warmup=true` flag
    on any account that has NO active (is_enabled) warm-up enrollment. Never touches an
    account with a real active enrollment. Returns how many flags were cleared."""
    from app.models.account import Account
    m = await enrollment_states_by_instance(db)
    active = {iid for iid, (state, enabled) in m.items() if enabled}
    accounts = (await db.execute(
        select(Account).where(Account.auto_warmup.is_(True))
    )).scalars().all()
    cleared = 0
    for a in accounts:
        if a.instance_id not in active:
            a.auto_warmup = False
            cleared += 1
    if cleared:
        await db.commit()
    return cleared
