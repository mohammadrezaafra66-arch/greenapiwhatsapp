"""V29 «همکاری تیمی» PART 3 — conversation-thread service.

One `warmup_helper_thread` row per (helper, cold_instance) pair that has ever had an ask-step.
It carries the running `topic_summary` so follow-up ask-steps CONTINUE the same topic instead
of a fresh random one, plus `step_count` and a status (active/paused/done).

The pure pieces (topic derivation, status transitions) are `now`-injectable so the thread
progression is unit-tested without a DB or the clock. The async wrappers load/persist rows.
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import select

from app.models.warmup_helpers import WarmupHelperThread

STATUS_ACTIVE = "active"
STATUS_PAUSED = "paused"
STATUS_DONE = "done"


# ── pure: topic derivation ────────────────────────────────────────────────────
def derive_topic(*, brief: str | None, product: str | None,
                 existing_topic: str | None, step_count: int) -> str:
    """PURE. The thread's topic for the NEXT ask-step.

    • step_count > 0 with an existing topic → KEEP it (continue the same conversation).
    • step 0 (or no topic yet) → invent a natural, product-relevant opening topic: prefer a real
      product ("پیگیری سفارش تلویزیون"), else fall back to the brief, else a generic greeting.
    Never restarts an established thread on an unrelated topic."""
    if step_count > 0 and (existing_topic or "").strip():
        return existing_topic.strip()
    prod = (product or "").strip()
    if prod:
        return f"پیگیری سفارش {prod}"
    b = (brief or "").strip()
    if b:
        return b[:120]
    return "احوال‌پرسی و یک درخواست کوچک"


# ── async: get-or-create + advance ────────────────────────────────────────────
async def get_or_create_thread(db, helper_id, cold_instance_id: str) -> WarmupHelperThread:
    """Fetch the (helper, cold) thread, creating a fresh active one (step_count=0) if none exists."""
    th = (await db.execute(
        select(WarmupHelperThread).where(
            WarmupHelperThread.helper_id == helper_id,
            WarmupHelperThread.cold_instance_id == cold_instance_id,
        ).limit(1)
    )).scalar_one_or_none()
    if th is None:
        th = WarmupHelperThread(helper_id=helper_id, cold_instance_id=cold_instance_id,
                                step_count=0, status=STATUS_ACTIVE)
        db.add(th)
        await db.flush()
    return th


async def get_thread(db, helper_id, cold_instance_id: str) -> WarmupHelperThread | None:
    return (await db.execute(
        select(WarmupHelperThread).where(
            WarmupHelperThread.helper_id == helper_id,
            WarmupHelperThread.cold_instance_id == cold_instance_id,
        ).limit(1)
    )).scalar_one_or_none()


def advance_thread(thread: WarmupHelperThread, topic_summary: str,
                   now: datetime | None = None) -> WarmupHelperThread:
    """PURE-ish (mutates the passed row). Record that one more ask-step happened on this thread:
    update the topic, bump step_count, stamp last_step_at. Caller commits."""
    now = now or datetime.utcnow()
    thread.topic_summary = topic_summary
    thread.step_count = int(thread.step_count or 0) + 1
    thread.last_step_at = now
    return thread


def pause_thread(thread: WarmupHelperThread) -> WarmupHelperThread:
    thread.status = STATUS_PAUSED
    return thread


def is_active(thread: WarmupHelperThread | None) -> bool:
    return thread is not None and thread.status == STATUS_ACTIVE
