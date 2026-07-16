"""V25 PART 1 — the automatic "human helpers" warm-up engine.

Driven by a frequent Celery tick. When the single toggle is ON, this:
  1. pairs each cold number being warmed with each ACTIVE helper (creating `pending` tasks),
  2. sends AT MOST ONE helper-ask (or one reminder) per tick, gated by the slow jittered
     rate limiter + waking hours, FROM the user's main warm account (never a cold number),
  3. marks the task `asked`/`reminded` and re-arms the rate gate.

Success detection + auto thank-you happen on the webhook path (handle_helper_incoming),
called when a cold number receives an incoming message from a helper's phone.

The scheduling DECISIONS (which one action to run, who sends) are pure and injectable so the
"slow, not-all-at-once, waking-hours-only, one-reminder-max" guarantees are unit-tested
without the network, a DB, or the clock.
"""
from __future__ import annotations
import logging
import random
from datetime import datetime, timedelta
from sqlalchemy import select

from app.models.account import Account, AccountStatus
from app.models.warmup_mesh import WarmupEnrollment
from app.models.warmup_helpers import WarmupHelper, WarmupHelperTask
from app.services.green_api import GreenAPIClient
from app.services.warmup_state import WarmupState, DEFAULT_WARMUP_CONFIG
from app.services import warmup_helper_service as hs
from app.services.warmup_scheduler import in_active_hours, TEHRAN
from app.services.typing_sim import show_typing_for_send

logger = logging.getLogger("afrakala.warmup.helpers")

# Enrollment states that are NOT actively being warmed → their cold number gets no helper asks.
_INACTIVE_COLD_STATES = {
    WarmupState.GRADUATED.value, WarmupState.PAUSED.value, WarmupState.BLOCKED_RESET.value,
}


def _default_client_factory(instance_id: str, api_token: str) -> GreenAPIClient:
    return GreenAPIClient(instance_id, api_token)


# ── pure: choose the ONE main sending account ────────────────────────────────
def pick_main_sender(accounts: list, enr_map: dict):
    """Pick the user's main warm sending account (never a cold number being warmed).

    Preference: a manually-marked warm peer (is_warm_peer) → a GRADUATED number → any active
    account that is NOT currently being warmed. Returns the Account or None. Pure: `accounts`
    are active Account-like objects, `enr_map` is {instance_id: (state, is_enabled)}."""
    def _being_warmed(a) -> bool:
        st = enr_map.get(a.instance_id)
        return bool(st and st[1] and st[0] not in _INACTIVE_COLD_STATES)

    peers = [a for a in accounts if getattr(a, "is_warm_peer", False)]
    if peers:
        return peers[0]
    graduated = [a for a in accounts
                 if (enr_map.get(a.instance_id) or (None, None))[0] == WarmupState.GRADUATED.value]
    if graduated:
        return graduated[0]
    others = [a for a in accounts if not _being_warmed(a)]
    return others[0] if others else None


# ── pure: choose the ONE action this tick (reminder wins over a fresh ask) ────
def select_action(pending_tasks: list, asked_tasks: list, now: datetime,
                  reminder_after_hours: int = hs.REMINDER_AFTER_HOURS):
    """Decide the single action to perform this tick. Returns ("remind", task) |
    ("ask", task) | None.

    A reminder is due for an `asked` (never-reminded) task whose asked_at is older than
    `reminder_after_hours`. Reminders take priority (finish what we started), then a fresh
    `pending` ask. Exactly one task is returned, so the main account never sends in a burst.
    `asked_tasks` must already exclude tasks that were reminded/done (status == 'asked')."""
    cutoff = now - timedelta(hours=reminder_after_hours)
    due_reminders = [t for t in asked_tasks
                     if t.status == hs.STATUS_ASKED and t.asked_at is not None and t.asked_at <= cutoff]
    if due_reminders:
        due_reminders.sort(key=lambda t: t.asked_at)
        return ("remind", due_reminders[0])
    if pending_tasks:
        pending_tasks.sort(key=lambda t: t.created_at or now)
        return ("ask", pending_tasks[0])
    return None


# ── DB helpers ───────────────────────────────────────────────────────────────
async def _enrollment_states(db) -> dict:
    rows = (await db.execute(
        select(WarmupEnrollment.instance_id, WarmupEnrollment.state, WarmupEnrollment.is_enabled)
    )).all()
    return {iid: (state, bool(enabled)) for iid, state, enabled in rows}


async def cold_instances_being_warmed(db, enr_map: dict) -> list[str]:
    """Cold numbers eligible for helper greetings: enrolled + enabled + actively being warmed."""
    return [iid for iid, (state, enabled) in enr_map.items()
            if enabled and state not in _INACTIVE_COLD_STATES]


async def ensure_helper_tasks(db, cold_instance_ids: list[str],
                              active_helpers: list[WarmupHelper]) -> int:
    """Create a `pending` task for every (active helper × cold number) pair that has none yet.
    Idempotent — never duplicates. Returns how many new pending tasks were created. Rows are
    cheap; the SENDS (not the rows) are what the slow rate gate throttles."""
    if not cold_instance_ids or not active_helpers:
        return 0
    existing = (await db.execute(
        select(WarmupHelperTask.helper_id, WarmupHelperTask.cold_instance_id)
    )).all()
    have = {(str(hid), cid) for hid, cid in existing}
    created = 0
    for helper in active_helpers:
        for cold in cold_instance_ids:
            if (str(helper.id), cold) in have:
                continue
            db.add(WarmupHelperTask(helper_id=helper.id, cold_instance_id=cold,
                                    status=hs.STATUS_PENDING))
            created += 1
    if created:
        await db.flush()
    return created


async def _resolve_cold_phone(db, cold_instance_id: str, client_factory) -> tuple[str | None, Account | None]:
    """Return (phone_digits, account) for the cold number, backfilling accounts.phone from
    getWaSettings when null (reuse of the mesh's phone-backfill logic) so the wa.me link can
    always be built. Persists a filled phone."""
    acc = (await db.execute(
        select(Account).where(Account.instance_id == cold_instance_id)
    )).scalar_one_or_none()
    if acc is None:
        return None, None
    if acc.phone:
        return hs.wa_me_digits(acc.phone), acc
    from app.services.warmup_mesh_service import _resolve_account_phone
    client = client_factory(acc.instance_id, acc.api_token)
    phone = await _resolve_account_phone(acc, client)   # fills + returns, caller commits
    return (hs.wa_me_digits(phone) if phone else None), acc


async def _send_from_main(sender: Account, to_phone: str, text: str, client_factory) -> str | None:
    """Send one message from the main warm account, respecting typing simulation so it looks
    human. Best-effort — a send failure never crashes the tick."""
    client = client_factory(sender.instance_id, sender.api_token)
    try:
        await show_typing_for_send(client, to_phone, text, enabled=True)
        return await client.send_message(to_phone, text)
    except Exception as e:
        logger.warning("helper-ask send failed (%s → %s): %s", sender.instance_id, to_phone, e)
        return None


async def run_helper_tick(db, now: datetime | None = None, *, client_factory=None,
                          rng: random.Random | None = None, cfg=DEFAULT_WARMUP_CONFIG) -> dict:
    """One tick of the helper-assist flow. Default OFF; webhook-only detection elsewhere.

    Sends AT MOST one helper-ask/reminder, gated by waking hours + the jittered rate limiter,
    FROM the main warm account. Returns a summary dict."""
    client_factory = client_factory or _default_client_factory
    # Waking-hours + rate-gate math run in Tehran-local time (in_active_hours treats a naive
    # datetime as Tehran); use naive Tehran-local now so the gate and the hours check agree and
    # the naive `next_ask_at` column never mixes aware/naive values.
    now = now or datetime.now(TEHRAN).replace(tzinfo=None)
    r = rng or random

    conf = await hs.get_config(db)
    if not conf.is_enabled:
        return {"enabled": False, "acted": 0}

    enr_map = await _enrollment_states(db)
    cold_ids = await cold_instances_being_warmed(db, enr_map)
    active_helpers = [h for h in await hs.list_helpers(db) if h.is_active]
    created = await ensure_helper_tasks(db, cold_ids, active_helpers)

    # Slow-send gate: waking hours + jittered rate. Outside a slot we still keep the freshly
    # created pending rows, but send nothing (never a burst).
    if not hs.can_ask_now(now, conf.next_ask_at, cfg):
        await db.commit()
        return {"enabled": True, "acted": 0, "created": created, "throttled": True,
                "in_hours": in_active_hours(now, cfg)}

    # Pick the ONE main sending account (never a cold number).
    accounts = (await db.execute(
        select(Account).where(Account.status == AccountStatus.active)
    )).scalars().all()
    sender = pick_main_sender(accounts, enr_map)
    if sender is None:
        await db.commit()
        return {"enabled": True, "acted": 0, "created": created, "no_sender": True}

    # Candidate tasks limited to cold numbers still being warmed + active helpers.
    active_cold = set(cold_ids)
    active_helper_ids = {str(h.id) for h in active_helpers}
    helper_by_id = {str(h.id): h for h in active_helpers}
    all_tasks = (await db.execute(
        select(WarmupHelperTask).where(
            WarmupHelperTask.status.in_((hs.STATUS_PENDING, hs.STATUS_ASKED))
        )
    )).scalars().all()
    tasks = [t for t in all_tasks
             if t.cold_instance_id in active_cold and str(t.helper_id) in active_helper_ids]
    pending = [t for t in tasks if t.status == hs.STATUS_PENDING]
    asked = [t for t in tasks if t.status == hs.STATUS_ASKED]

    action = select_action(pending, asked, now)
    if action is None:
        await db.commit()
        return {"enabled": True, "acted": 0, "created": created, "nothing_due": True}

    kind, task = action
    helper = helper_by_id.get(str(task.helper_id))
    if helper is None:
        await db.commit()
        return {"enabled": True, "acted": 0, "created": created}

    phone_digits, _cold_acc = await _resolve_cold_phone(db, task.cold_instance_id, client_factory)
    link = hs.wa_me_link(phone_digits)

    if kind == "remind":
        text = hs.build_reminder_message(helper.name, link)
    else:
        text = hs.build_ask_message(helper.name, link)

    mid = await _send_from_main(sender, helper.phone, text, client_factory)

    if kind == "remind":
        task.status = hs.STATUS_REMINDED
        task.reminded_at = now
    else:
        task.status = hs.STATUS_ASKED
        task.asked_at = now
    task.attempts = int(task.attempts or 0) + 1

    # Re-arm the slow-send rate gate with fresh jitter.
    conf.next_ask_at = hs.next_ask_at(now, r)
    await db.commit()
    return {"enabled": True, "acted": 1, "created": created, "kind": kind,
            "helper": helper.name, "cold_instance_id": task.cold_instance_id,
            "sent": bool(mid), "next_ask_at": conf.next_ask_at.isoformat()}


async def handle_helper_incoming(db, cold_instance_id: str, sender_phone: str,
                                 now: datetime | None = None, *, client_factory=None) -> dict | None:
    """Webhook detection: a cold number received an INCOMING message from a helper's phone →
    mark that helper's task `done` and auto-send the helper a Persian thank-you FROM the main
    account. No-op (returns None) when the sender isn't a known helper or no open ask exists.

    Best-effort and self-contained: does NOT commit (the webhook's outer session commits), but
    sends the thank-you immediately. Guarded by the caller so it can never disrupt the webhook."""
    client_factory = client_factory or _default_client_factory
    now = now or datetime.utcnow()
    digits = hs.wa_me_digits(sender_phone)
    if not digits:
        return None

    helper = (await db.execute(
        select(WarmupHelper).where(WarmupHelper.phone == digits).limit(1)
    )).scalar_one_or_none()
    if helper is None:
        return None

    task = (await db.execute(
        select(WarmupHelperTask).where(
            WarmupHelperTask.helper_id == helper.id,
            WarmupHelperTask.cold_instance_id == cold_instance_id,
            WarmupHelperTask.status.in_((hs.STATUS_ASKED, hs.STATUS_REMINDED)),
        ).limit(1)
    )).scalar_one_or_none()
    if task is None:
        return None

    task.status = hs.STATUS_DONE
    task.done_at = now

    # Thank the helper from the main warm account (best-effort).
    enr_map = await _enrollment_states(db)
    accounts = (await db.execute(
        select(Account).where(Account.status == AccountStatus.active)
    )).scalars().all()
    sender = pick_main_sender(accounts, enr_map)
    sent = False
    if sender is not None:
        mid = await _send_from_main(sender, helper.phone, hs.build_thankyou_message(helper.name),
                                    client_factory)
        sent = bool(mid)
    return {"helper": helper.name, "cold_instance_id": cold_instance_id, "thanked": sent}
