"""V30 PART 2 — per-SENDER minimum 20-minute spacing between «همکاری تیمی» ASK-requests.

An ADDITIONAL, extra-conservative constraint layered ON TOP of the existing rails (the V27
per-instance `peer_pacer` 10–15s floor, the V27 health gate, waking hours). It applies ONLY to
ask-requests (not reminders / thank-yous / cold-replies, which have their own rules): a given
SENDER instance may emit at most one ask every 20 minutes.

Design (consistent with V27's peer-level philosophy): the constraint is keyed on the SENDER
instance, so different senders are never rate-limited against each other by THIS rule — only the
existing global anti-ban rails apply across senders.

The "last ask" time is derived from `warmup_helper_task.asked_at` (set to the tick's Tehran-naive
`now` on every ask in BOTH ask paths), so the gate compares apples to apples with the `now` the
ticks pass in — no UTC/Tehran skew. Pure `ask_spacing_ok` is `now`-injectable for unit tests.
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import select

from app.models.warmup_helpers import WarmupHelperTask, WarmupHelper

# The minimum gap between two ask-requests FROM THE SAME SENDER.
ASK_MIN_SPACING_MINUTES = 20


def ask_spacing_ok(last_ask_at: datetime | None, now: datetime,
                   min_minutes: int = ASK_MIN_SPACING_MINUTES) -> bool:
    """PURE. True when a sender may send its NEXT ask: no prior ask, or the prior ask is at least
    `min_minutes` old. Both datetimes must share the same clock (the ticks use Tehran-naive)."""
    if last_ask_at is None:
        return True
    return (now - last_ask_at).total_seconds() >= min_minutes * 60


async def last_ask_at_for_sender(db, sender_instance_id: str | None) -> datetime | None:
    """The most recent time THIS sender sent any ask (max asked_at over its contacts' tasks).
    None when the sender has never asked. A missing sender id → None (no constraint).

    Selects full task rows and reduces in Python (rather than a SQL func.max) so the reduction
    is portable across the pure-mock test harnesses too — every one supports `.scalars().all()`."""
    if not sender_instance_id:
        return None
    rows = (await db.execute(
        select(WarmupHelperTask)
        .join(WarmupHelper, WarmupHelper.id == WarmupHelperTask.helper_id)
        .where(WarmupHelper.sender_instance_id == sender_instance_id,
               WarmupHelperTask.asked_at.isnot(None))
    )).scalars().all()
    times = [t.asked_at for t in rows if getattr(t, "asked_at", None) is not None]
    return max(times) if times else None
