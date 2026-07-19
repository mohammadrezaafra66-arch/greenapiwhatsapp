"""V29 «همکاری تیمی» PART 7 — per-cold-account enrollment + the automatic 10-day cycle.

Each cold account gets its OWN «عضویت در همکاری تیمی» toggle (WarmupTeamEnrollment), DISTINCT
from the mesh warm-up enrollment. Once enabled AND its existing 24h post-authorization cooldown
(the SAME clock the mesh uses) has cleared, its assigned contacts' ask-steps run automatically
over a FIXED 10-day window:
  • conservative start (day 0–1: 1 step/day), then up to 2 steps/day through day 9;
  • waking hours only, jittered (one send per tick);
  • never two steps on the SAME thread on the SAME day.

Every send still routes through the EXISTING rails — the thread-aware generator (PART 3), the
V27 pre-send health gate (`gate_check`/`can_send_now`) inside `_send_from_main`, and the shared
per-instance `peer_pacer`. This module only DECIDES which one ask-step (if any) is due; it never
opens a parallel send path. The scheduling decisions are pure + `now`-injectable for unit tests.
"""
from __future__ import annotations
import logging
import random
from datetime import datetime
from sqlalchemy import select

from app.models.account import Account, AccountStatus
from app.models.warmup_helpers import WarmupHelper, WarmupHelperTask, WarmupTeamEnrollment
from app.models.warmup_mesh import WarmupEnrollment
from app.services import warmup_helper_service as hs
from app.services import warmup_helper_thread as wt
from app.services import peer_pacer
from app.services.warmup_scheduler import in_active_hours, to_tehran, TEHRAN
from app.services.warmup_helper_engine import (
    _to_utc_naive, _send_from_main, _resolve_cold_phone, resolve_task_sender,
    _enrollment_states, _default_client_factory,
)
from app.services.warmup_cold_reply import post_auth_cooldown_elapsed

logger = logging.getLogger("afrakala.warmup.teamsched")

TEAM_CYCLE_DAYS = 10          # the fixed 10-day window
STATUS_DONE = "done"


# ── pure schedule math ────────────────────────────────────────────────────────
def team_day_index(enrolled_at: datetime | None, now: datetime) -> int:
    """PURE. Which day of the 10-day cycle we're on (0-based), by Tehran calendar date. An
    unknown enrolled_at → day 0."""
    if enrolled_at is None:
        return 0
    a = to_tehran(enrolled_at).date()
    b = to_tehran(now).date()
    return max(0, (b - a).days)


def daily_step_budget(day_index: int) -> int:
    """PURE. Fixed, non-configurable ramp: day 0–1 → 1 ask-step/day; day 2–9 → 2/day; past the
    10-day window → 0 (cycle complete)."""
    if day_index >= TEAM_CYCLE_DAYS:
        return 0
    return 1 if day_index <= 1 else 2


def _same_tehran_date(a: datetime | None, b: datetime) -> bool:
    if a is None:
        return False
    return to_tehran(a).date() == to_tehran(b).date()


def stepped_today(thread, now: datetime) -> bool:
    """PURE. True if this thread already had an ask-step today (never two/thread/day)."""
    return _same_tehran_date(getattr(thread, "last_step_at", None), now)


def select_thread_for_step(threads: list, now: datetime):
    """PURE. Pick the ONE thread to advance this tick: an ACTIVE thread not already stepped today,
    preferring the least-progressed (lowest step_count) then the longest-idle. None when none due."""
    eligible = [t for t in threads
                if getattr(t, "status", wt.STATUS_ACTIVE) == wt.STATUS_ACTIVE
                and not stepped_today(t, now)]
    if not eligible:
        return None
    eligible.sort(key=lambda t: (int(getattr(t, "step_count", 0) or 0),
                                 getattr(t, "last_step_at", None) or datetime.min))
    return eligible[0]


def steps_done_today(threads: list, now: datetime) -> int:
    """PURE. How many of this cold account's threads already had a step today (daily budget use)."""
    return sum(1 for t in threads if stepped_today(t, now))


# ── enrollment CRUD ───────────────────────────────────────────────────────────
async def get_team_enrollment(db, cold_instance_id: str) -> WarmupTeamEnrollment | None:
    return (await db.execute(
        select(WarmupTeamEnrollment).where(
            WarmupTeamEnrollment.cold_instance_id == cold_instance_id).limit(1)
    )).scalar_one_or_none()


async def set_team_enrolled(db, cold_instance_id: str, enabled: bool,
                            now: datetime | None = None) -> WarmupTeamEnrollment:
    """Enroll/unenroll a cold account in «همکاری تیمی». Enrolling stamps enrolled_at (starting the
    10-day clock) if not already set; unenrolling keeps the row (history) but disables it. Commits."""
    now = now or datetime.utcnow()
    enr = await get_team_enrollment(db, cold_instance_id)
    if enr is None:
        enr = WarmupTeamEnrollment(cold_instance_id=cold_instance_id, is_enabled=bool(enabled),
                                   enrolled_at=now if enabled else None, day_index=0)
        db.add(enr)
    else:
        enr.is_enabled = bool(enabled)
        if enabled and enr.enrolled_at is None:
            enr.enrolled_at = now
            enr.day_index = 0
    await db.commit()
    await db.refresh(enr)
    return enr


# ── the tick: advance ONE due ask-step, fully gated ──────────────────────────
async def run_team_schedule_tick(db, now: datetime | None = None, *, client_factory=None,
                                 ai_fn=None, rng: random.Random | None = None) -> dict:
    """Advance AT MOST one due «همکاری تیمی» ask-step this tick, honoring the 10-day ramp, the
    per-thread/day limit, waking hours, the cold account's 24h cooldown, and the shared pacer +
    health gate on the SENDER. No-op outside waking hours or when nothing is due."""
    client_factory = client_factory or _default_client_factory
    now = now or datetime.now(TEHRAN).replace(tzinfo=None)
    r = rng or random

    # Waking hours only — same window the mesh/helper flows use.
    if not in_active_hours(now):
        return {"acted": 0, "in_hours": False}

    enrolls = (await db.execute(
        select(WarmupTeamEnrollment).where(WarmupTeamEnrollment.is_enabled.is_(True))
    )).scalars().all()
    if not enrolls:
        return {"acted": 0, "enrolled": 0}

    accounts = (await db.execute(
        select(Account).where(Account.status == AccountStatus.active)
    )).scalars().all()
    acc_by_id = {a.instance_id: a for a in accounts}
    enr_map = await _enrollment_states(db)

    for te in enrolls:
        cold = acc_by_id.get(te.cold_instance_id)
        if cold is None:
            continue
        # Gate 1 — the cold account's EXISTING 24h post-authorization cooldown (mesh clock).
        mesh_enr = (await db.execute(
            select(WarmupEnrollment).where(WarmupEnrollment.instance_id == te.cold_instance_id)
        )).scalar_one_or_none()
        if not post_auth_cooldown_elapsed(mesh_enr, now):
            continue

        day_index = team_day_index(te.enrolled_at, now)
        te.day_index = day_index
        budget = daily_step_budget(day_index)
        if budget <= 0:
            te.is_enabled = False if day_index >= TEAM_CYCLE_DAYS else te.is_enabled
            continue

        # Contacts assigned to THIS cold account (via their tasks) → their threads.
        pairs = (await db.execute(
            select(WarmupHelperTask.helper_id).where(
                WarmupHelperTask.cold_instance_id == te.cold_instance_id)
        )).all()
        helper_ids = {hid for (hid,) in pairs}
        if not helper_ids:
            continue
        threads = []
        for hid in helper_ids:
            threads.append(await wt.get_or_create_thread(db, hid, te.cold_instance_id))

        if steps_done_today(threads, now) >= budget:
            continue
        thread = select_thread_for_step(threads, now)
        if thread is None:
            continue

        helper = await db.get(WarmupHelper, thread.helper_id)
        if helper is None or not helper.is_active:
            continue
        # per-sender toggle (V29 PART 1) — a disabled sender is skipped.
        if not await hs.is_sender_enabled(db, helper.sender_instance_id):
            continue

        # Gate 2 — sender health + shared per-instance pacer (the SAME rails as every send).
        sender = resolve_task_sender(accounts, helper, enr_map)
        if sender is None:
            continue
        # Gate 2b (V30 PART 2) — per-sender 20-min ask spacing, layered ON TOP of the pacer.
        # Skip THIS sender's ask if it asked within the window; another sender's enrollment may
        # still proceed this tick (the constraint is per-sender, never across senders).
        from app.services import warmup_ask_spacing as spacing
        last_ask = await spacing.last_ask_at_for_sender(db, sender.instance_id)
        if not spacing.ask_spacing_ok(last_ask, now):
            continue
        pacer_now = _to_utc_naive(now)
        if not peer_pacer.peer_ready(sender.instance_id, pacer_now):
            continue

        # Generate the thread-aware ask (PART 3) and send it FROM the contact's own sender.
        from app.services.outreach_message import generate_thread_ask_message, build_thread_ai_fn
        brief = await hs.get_current_brief(db, helper.sender_instance_id) if helper.sender_instance_id else None
        brief_text = brief.brief_text if brief else None
        phone_digits, cold_acc = await _resolve_cold_phone(db, te.cold_instance_id, client_factory)
        topic = wt.derive_topic(brief=brief_text, product=None,
                                existing_topic=thread.topic_summary,
                                step_count=int(thread.step_count or 0))
        forbidden = tuple(v for v in (te.cold_instance_id, getattr(cold_acc, "name", None),
                                      helper.sender_instance_id, getattr(sender, "name", None)) if v)
        text, source = await generate_thread_ask_message(
            brief=brief_text,
            contact={"name": helper.name, "job_title": helper.job_title,
                     "years_experience": helper.years_experience,
                     "personal_benefit_note": helper.personal_benefit_note},
            topic=topic, step_count=int(thread.step_count or 0),
            cold_phone_digits=[phone_digits],
            ai_fn=ai_fn if ai_fn is not None else build_thread_ai_fn(), forbidden=forbidden)

        mid = await _send_from_main(sender, helper.phone, text, client_factory)

        # Mark the ask-step on both the task lifecycle and the thread.
        task = (await db.execute(
            select(WarmupHelperTask).where(
                WarmupHelperTask.helper_id == helper.id,
                WarmupHelperTask.cold_instance_id == te.cold_instance_id).limit(1)
        )).scalar_one_or_none()
        if task is not None:
            task.status = hs.STATUS_ASKED
            task.asked_at = now
            task.attempts = int(task.attempts or 0) + 1
        wt.advance_thread(thread, topic, now)
        from app.services import warmup_helper_log as tclog
        tclog.record(db, event_type=tclog.EVENT_ASK, from_instance_id=sender.instance_id,
                     to_phone=helper.phone, helper_id=helper.id,
                     sender_instance_id=sender.instance_id, cold_instance_id=te.cold_instance_id,
                     thread_id=thread.id, message_sent=text)
        if mid:
            peer_pacer.record_peer_send(sender.instance_id, pacer_now, r)
        await db.commit()
        return {"acted": 1, "cold_instance_id": te.cold_instance_id, "day_index": day_index,
                "helper": helper.name, "sender_instance_id": sender.instance_id,
                "sent": bool(mid), "source": source, "topic": topic}

    await db.commit()
    return {"acted": 0, "enrolled": len(enrolls)}
