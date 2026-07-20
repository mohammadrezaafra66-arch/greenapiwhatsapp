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
import pytz
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


# ── V28 — send FROM the contact's OWN sender (fallback to the main sender for legacy rows) ──
def resolve_task_sender(accounts: list, helper, enr_map: dict):
    """The account that should send this contact's outreach ask: the contact's own
    `sender_instance_id` account when set (V28 multi-sender), else the V25 main sender
    (legacy rows with no sender). Any account may be a sender — NOT restricted to warm peers."""
    sid = getattr(helper, "sender_instance_id", None)
    if sid:
        for a in accounts:
            if a.instance_id == sid:
                return a
    return pick_main_sender(accounts, enr_map)


def _to_utc_naive(tehran_naive: datetime) -> datetime:
    """Convert the tick's Tehran-local naive time to a naive-UTC instant so the SHARED
    per-instance pacer (peer_pacer, keyed in naive UTC like the mesh) compares apples to
    apples — an outreach send and a mesh send from one instance stay >= the 10–15s floor apart."""
    try:
        return TEHRAN.localize(tehran_naive).astimezone(pytz.utc).replace(tzinfo=None)
    except Exception:
        return tehran_naive


# ── pure: choose the ONE action this tick (reminder wins over a fresh ask) ────
def _reminder_ref_time(task):
    """The last-outreach time a reminder is measured from: reminded_at once reminded, else asked_at."""
    return task.reminded_at if task.status == hs.STATUS_REMINDED else task.asked_at


def reminder_due_for(task, cutoff) -> bool:
    """PURE. Is a reminder due for this awaiting task, under the exactly-2-reminder cap (V33 PART 4)?
      • status 'asked'    → reminder #1 due when asked_at <= cutoff (never reminded yet);
      • status 'reminded' → reminder #2 due when reminder_count < MAX_REMINDERS and reminded_at <= cutoff.
    A task that has already had MAX_REMINDERS reminders is NEVER due (it goes terminal `no_response`
    via expire_exhausted_reminders instead — never a 3rd reminder)."""
    rc = int(getattr(task, "reminder_count", 0) or 0)
    if task.status == hs.STATUS_ASKED:
        return task.asked_at is not None and task.asked_at <= cutoff
    if task.status == hs.STATUS_REMINDED:
        return rc < hs.MAX_REMINDERS and task.reminded_at is not None and task.reminded_at <= cutoff
    return False


def select_action(pending_tasks: list, awaiting_tasks: list, now: datetime,
                  reminder_after_minutes: int = hs.REMINDER_AFTER_MINUTES):
    """Decide the single action to perform this tick. Returns ("remind", task) |
    ("ask", task) | None.

    `awaiting_tasks` are the non-terminal already-asked tasks (status 'asked' OR 'reminded'). A
    reminder is due for an 'asked' task (reminder #1) or a 'reminded' task still under the 2-reminder
    cap (reminder #2), whose last outreach is older than the 45–60 min window. Reminders take priority
    (finish what we started), then a fresh 'pending' ask. Exactly one task is returned, so the sender
    never bursts. Terminal `no_response` tasks are excluded upstream and closed by the expiry sweep."""
    cutoff = now - timedelta(minutes=reminder_after_minutes)
    due_reminders = [t for t in awaiting_tasks if reminder_due_for(t, cutoff)]
    if due_reminders:
        due_reminders.sort(key=lambda t: _reminder_ref_time(t) or now)
        return ("remind", due_reminders[0])
    if pending_tasks:
        pending_tasks.sort(key=lambda t: t.created_at or now)
        return ("ask", pending_tasks[0])
    return None


async def expire_exhausted_reminders(db, now: datetime,
                                     reminder_after_minutes: int = hs.REMINDER_AFTER_MINUTES) -> int:
    """V33 PART 4 — after the 2nd reminder's window elapses with STILL no completion, close the task:
    mark it terminal `no_response` and set ITS (contact, cold) thread `done` so neither the reminder
    path nor the 10-day scheduler ever asks/reminds that pairing again (never a 3rd reminder/re-ask).
    Only that pairing closes — the contact stays eligible for other cold accounts. A LATER completion
    is still honored (handle_helper_incoming accepts a no_response task). Not a send → safe every tick.
    Returns how many tasks were expired."""
    cutoff = now - timedelta(minutes=reminder_after_minutes)
    tasks = (await db.execute(
        select(WarmupHelperTask).where(
            WarmupHelperTask.status == hs.STATUS_REMINDED,
            WarmupHelperTask.reminder_count >= hs.MAX_REMINDERS,
            WarmupHelperTask.reminded_at.isnot(None),
            WarmupHelperTask.reminded_at <= cutoff,
        )
    )).scalars().all()
    from app.services import warmup_helper_thread as wt
    expired = 0
    for t in tasks:
        t.status = hs.STATUS_NO_RESPONSE
        thread = await wt.get_thread(db, t.helper_id, t.cold_instance_id)
        if thread is not None and thread.status == wt.STATUS_ACTIVE:
            thread.status = wt.STATUS_DONE   # stop the 10-day scheduler from re-stepping this pairing
        expired += 1
    return expired


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
    """Create a `pending` task pairing active helpers with cold numbers being warmed, WITHOUT ever
    pushing a contact past the per-contact cold ceiling. Idempotent — never duplicates. Returns how
    many new pending tasks were created.

    V33 PART 1 — the confirmed root cause of the pending-stall was this fan-out: it used to create a
    task for EVERY (active helper × EVERY warmed cold), pinning every contact to all warmed colds at
    once (31 contacts × 3 colds = 93 tasks). That (a) violated the intended ≤2-cold-per-contact
    ceiling and (b) inflated the queue far past what the deliberately-slow, single-sender anti-ban
    pacing (≤1 ask / 20 min) can ever drain — and it REGENERATED the excess every tick, so `pending`
    was structurally undrainable and looked permanently stuck. The fan-out now honors the same
    ceiling `assign_cold_account` enforces (PART 2): a contact is auto-paired only up to
    `MAX_COLD_ACCOUNTS_PER_CONTACT` DISTINCT colds; existing pairings count toward that budget.
    Rows are cheap; the SENDS (not the rows) are what the slow rate gate throttles."""
    if not cold_instance_ids or not active_helpers:
        return 0
    existing = (await db.execute(
        select(WarmupHelperTask.helper_id, WarmupHelperTask.cold_instance_id)
    )).all()
    have = {(str(hid), cid) for hid, cid in existing}
    # Per-contact DISTINCT-cold budget: seed from what each contact is already paired to so the
    # auto-fan-out tops up toward the ceiling but never past it (and never re-creates the stall).
    colds_by_helper: dict[str, set[str]] = {}
    for hid, cid in have:
        colds_by_helper.setdefault(hid, set()).add(cid)
    created = 0
    for helper in active_helpers:
        hid = str(helper.id)
        colds = colds_by_helper.setdefault(hid, set())
        for cold in cold_instance_ids:
            if (hid, cold) in have:
                continue
            if len(colds) >= hs.MAX_COLD_ACCOUNTS_PER_CONTACT:
                break   # contact already at the ceiling — auto-pairing stops here (no stall inflation)
            db.add(WarmupHelperTask(helper_id=helper.id, cold_instance_id=cold,
                                    status=hs.STATUS_PENDING))
            have.add((hid, cold))
            colds.add(cold)
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
    # V27 PART 1 — live pre-send health gate: never ask a helper through an unhealthy main
    # account (cooldown/throttle/live yellowCard-blocked).
    from app.services.send_gate import gate_check
    allowed, gate_reason = gate_check(sender)
    if not allowed:
        logger.info("helper-ask skipped via %s: gate=%s", sender.instance_id, gate_reason)
        return None
    client = client_factory(sender.instance_id, sender.api_token)
    try:
        await show_typing_for_send(client, to_phone, text, enabled=True)
        return await client.send_message(to_phone, text)
    except Exception as e:
        logger.warning("helper-ask send failed (%s → %s): %s", sender.instance_id, to_phone, e)
        return None


async def _unified_ask_text(db, helper, task_sender, cold_acc, cold_instance_id, phone_digits,
                            ai_fn=None) -> str:
    """V31 — generate a mesh-warming ask through the SAME AI thread-aware generator the Team
    Collaboration tick uses: varied, personalized (job/experience/benefit), emoji, and anti-repeat
    seeded from the sender's recent ask bodies in the SHARED warmup_helper_log (so no two recent
    asks — from EITHER path — are near-duplicates). Falls back to the static builder ONLY if
    generation is impossible (e.g. an identifier-like/empty contact name) so the tick never breaks.
    The wa.me link + copy/paste suggestion are still appended, exactly as before."""
    from app.services.outreach_message import generate_thread_ask_message, build_thread_ai_fn
    from app.services import warmup_helper_thread as wt
    from app.services import warmup_helper_log as tclog
    try:
        brief = await hs.get_current_brief(db, helper.sender_instance_id) if helper.sender_instance_id else None
        brief_text = brief.brief_text if brief else None
        existing = await wt.get_thread(db, helper.id, cold_instance_id)
        step_count = int(getattr(existing, "step_count", 0) or 0)
        topic = wt.derive_topic(brief=brief_text, product=None,
                                existing_topic=getattr(existing, "topic_summary", None),
                                step_count=step_count)
        recent = await tclog.recent_ask_bodies(db, task_sender.instance_id)
        forbidden = tuple(v for v in (cold_instance_id, getattr(cold_acc, "name", None),
                                      helper.sender_instance_id, getattr(task_sender, "name", None)) if v)
        text, _src = await generate_thread_ask_message(
            brief=brief_text,
            contact={"name": helper.name, "job_title": getattr(helper, "job_title", None),
                     "years_experience": getattr(helper, "years_experience", None),
                     "personal_benefit_note": getattr(helper, "personal_benefit_note", None)},
            topic=topic, step_count=step_count, cold_phone_digits=[phone_digits],
            recent=recent, ai_fn=ai_fn if ai_fn is not None else build_thread_ai_fn(),
            forbidden=forbidden)
        return text
    except Exception as e:
        logger.info("V31 unified ask generation fell back to static builder: %s", e)
        return hs.build_ask_message(helper.name, hs.wa_me_link(phone_digits))


async def run_helper_tick(db, now: datetime | None = None, *, client_factory=None,
                          rng: random.Random | None = None, cfg=DEFAULT_WARMUP_CONFIG,
                          ai_fn=None) -> dict:
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

    # V33 PART 4 — close out any task whose 2 reminders elapsed with no completion (→ terminal
    # `no_response`). A pure state transition (no send), so it runs regardless of the send gates below.
    expired = await expire_exhausted_reminders(db, now)

    enr_map = await _enrollment_states(db)
    cold_ids = await cold_instances_being_warmed(db, enr_map)
    active_helpers = [h for h in await hs.list_helpers(db) if h.is_active]
    created = await ensure_helper_tasks(db, cold_ids, active_helpers)

    # Slow-send gate: the jittered rate + waking hours, AND (V30 PART 3) the narrower «همکاری
    # تیمی»-specific window (09:00–19:00 Tehran) that gates ask AND reminder alike. Outside any of
    # these we keep the freshly created pending rows but send nothing (never a burst).
    from app.services.warmup_team_hours import in_team_hours
    if not in_team_hours(now) or not hs.can_ask_now(now, conf.next_ask_at, cfg):
        await db.commit()
        return {"enabled": True, "acted": 0, "created": created, "throttled": True,
                "in_hours": in_active_hours(now, cfg), "in_team_hours": in_team_hours(now)}

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
    # V33 PART 4 — reminded tasks (awaiting their 2nd reminder) are candidates too, so include them.
    all_tasks = (await db.execute(
        select(WarmupHelperTask).where(
            WarmupHelperTask.status.in_((hs.STATUS_PENDING, hs.STATUS_ASKED, hs.STATUS_REMINDED))
        )
    )).scalars().all()
    tasks = [t for t in all_tasks
             if t.cold_instance_id in active_cold and str(t.helper_id) in active_helper_ids]
    pending = [t for t in tasks if t.status == hs.STATUS_PENDING]
    awaiting = [t for t in tasks if t.status in (hs.STATUS_ASKED, hs.STATUS_REMINDED)]

    action = select_action(pending, awaiting, now)
    if action is None:
        await db.commit()
        return {"enabled": True, "acted": 0, "created": created, "nothing_due": True}

    kind, task = action
    helper = helper_by_id.get(str(task.helper_id))
    if helper is None:
        await db.commit()
        return {"enabled": True, "acted": 0, "created": created}

    # V28 — send FROM this contact's OWN sender (legacy senderless rows fall back to the main).
    task_sender = resolve_task_sender(accounts, helper, enr_map)
    if task_sender is None:
        await db.commit()
        return {"enabled": True, "acted": 0, "created": created, "no_sender": True}

    # V30 PART 2 — per-sender 20-min ask spacing (asks ONLY; the single reminder is exempt and
    # governed by its own rule). Additional to, never a replacement for, the pacer below.
    if kind == "ask":
        from app.services import warmup_ask_spacing as spacing
        last_ask = await spacing.last_ask_at_for_sender(db, task_sender.instance_id)
        if not spacing.ask_spacing_ok(last_ask, now):
            await db.commit()
            return {"enabled": True, "acted": 0, "created": created, "ask_spacing": True,
                    "sender_instance_id": task_sender.instance_id}

    # V28 PART 4 — HARD safety rail (non-configurable): the shared per-INSTANCE pacer (V27
    # PART 2). Because a large contact list has NO count cap, this fixed floor is what keeps a
    # sender slow — its outreach asks and its mesh sends share ONE pacer, so they can never
    # interleave faster than the 10–15s floor. A big list simply spreads over many hours/days.
    from app.services import peer_pacer
    pacer_now = _to_utc_naive(now)
    if not peer_pacer.peer_ready(task_sender.instance_id, pacer_now):
        await db.commit()
        return {"enabled": True, "acted": 0, "created": created, "paced": True,
                "sender_instance_id": task_sender.instance_id}

    phone_digits, _cold_acc = await _resolve_cold_phone(db, task.cold_instance_id, client_factory)
    link = hs.wa_me_link(phone_digits)

    if kind == "remind":
        text = hs.build_reminder_message(helper.name, link)
    else:
        # V31 — route the ASK through the unified AI thread-aware generator (was static template).
        text = await _unified_ask_text(db, helper, task_sender, _cold_acc, task.cold_instance_id,
                                       phone_digits, ai_fn)

    # _send_from_main already applies V27 PART 1's live health gate on the sender.
    mid = await _send_from_main(task_sender, helper.phone, text, client_factory)

    if kind == "remind":
        task.status = hs.STATUS_REMINDED
        task.reminded_at = now
        task.reminder_count = int(task.reminder_count or 0) + 1   # V33 PART 4 — cap enforced at 2
    else:
        task.status = hs.STATUS_ASKED
        task.asked_at = now
        task.reminder_count = 0                                    # fresh ask-step → fresh 2-reminder budget
    task.attempts = int(task.attempts or 0) + 1

    # V29 PART 9 — record the ask/reminder in the dedicated «همکاری تیمی» log.
    from app.services import warmup_helper_log as tclog
    tclog.record(db, event_type=(tclog.EVENT_REMINDER if kind == "remind" else tclog.EVENT_ASK),
                 from_instance_id=task_sender.instance_id, to_phone=helper.phone,
                 helper_id=helper.id, sender_instance_id=task_sender.instance_id,
                 cold_instance_id=task.cold_instance_id, message_sent=text)

    # Re-arm BOTH gates: the slow jittered ask-gate AND the shared per-instance pacer.
    conf.next_ask_at = hs.next_ask_at(now, r)
    if mid:
        peer_pacer.record_peer_send(task_sender.instance_id, pacer_now, r)
    await db.commit()
    return {"enabled": True, "acted": 1, "created": created, "kind": kind,
            "helper": helper.name, "cold_instance_id": task.cold_instance_id,
            "sender_instance_id": task_sender.instance_id,
            "sent": bool(mid), "next_ask_at": conf.next_ask_at.isoformat()}


async def handle_helper_incoming(db, cold_instance_id: str, sender_phone: str,
                                 now: datetime | None = None, *, message_text: str | None = None,
                                 client_factory=None) -> dict | None:
    """Webhook detection: a cold number received an INCOMING message from a contact's phone →
    mark that contact's task `done`, update the (contact × cold) THREAD, run the thread safety
    scan on the incoming text, and auto-send the contact a Persian thank-you FROM their assigned
    sender. No-op (returns None) when the sender isn't a known contact or no open ask exists.

    V29 «همکاری تیمی»:
      • matches on the contact's PRIMARY *or* «شماره کاری» secondary phone;
      • records the incoming on the thread (stamps last_step_at) and marks the current step done;
      • a forbidden/sensitive word in the incoming text PAUSES only that thread + alerts admin
        (thank-you is skipped for a paused thread — the whole feature keeps running).

    Best-effort and self-contained: does NOT commit (the webhook's outer session commits), but
    sends the thank-you immediately. Guarded by the caller so it can never disrupt the webhook."""
    client_factory = client_factory or _default_client_factory
    now = now or datetime.utcnow()
    digits = hs.wa_me_digits(sender_phone)
    if not digits:
        return None

    # V29 — match the incoming phone against the contact's primary OR secondary («شماره کاری») number.
    helper = (await db.execute(
        select(WarmupHelper).where(
            (WarmupHelper.phone == digits) | (WarmupHelper.phone_secondary == digits)
        ).limit(1)
    )).scalar_one_or_none()
    if helper is None:
        return None

    # V33 PART 4 — a LATE completion after the task went terminal `no_response` is still honored
    # (better to thank a late responder than miss it), so no_response is completion-eligible too.
    task = (await db.execute(
        select(WarmupHelperTask).where(
            WarmupHelperTask.helper_id == helper.id,
            WarmupHelperTask.cold_instance_id == cold_instance_id,
            WarmupHelperTask.status.in_((hs.STATUS_ASKED, hs.STATUS_REMINDED, hs.STATUS_NO_RESPONSE)),
        ).limit(1)
    )).scalar_one_or_none()
    if task is None:
        return None

    task.status = hs.STATUS_DONE
    task.done_at = now

    # V30 PART 4 — completion-based escalation: when a team-enrolled cold account's task completes,
    # assign up to 2 NEW enrolled cold accounts to this contact as their next round (does nothing
    # when the roster is exhausted). Only queues pending tasks; the gated team tick sends them later
    # under the 20-min/09–19/pacer rails. Non-completion is unaffected (still one reminder).
    from app.services import warmup_team_schedule as _ts
    _te = await _ts.get_team_enrollment(db, cold_instance_id)
    if _te is not None and _te.is_enabled:
        await hs.escalate_after_completion(db, helper.id)

    # V29 PART 3/4 — update the conversation thread: record activity (the contact acted) and run
    # the safety scan on the incoming text. A forbidden word pauses THIS thread + raises an alert.
    from app.services import warmup_helper_thread as wt
    from app.services import warmup_thread_safety as safety
    thread = await wt.get_or_create_thread(db, helper.id, cold_instance_id)
    thread.last_step_at = now
    from app.services import warmup_helper_log as tclog
    tclog.record(db, event_type=tclog.EVENT_INCOMING, from_instance_id=None, to_phone=helper.phone,
                 helper_id=helper.id, sender_instance_id=helper.sender_instance_id,
                 cold_instance_id=cold_instance_id, thread_id=thread.id,
                 message_received=message_text)
    flagged = False
    if message_text:
        alert = await safety.scan_and_flag(db, thread, message_text, safety.DIR_INBOUND)
        flagged = alert is not None
        if flagged:
            tclog.record(db, event_type=tclog.EVENT_SAFETY, helper_id=helper.id,
                         sender_instance_id=helper.sender_instance_id,
                         cold_instance_id=cold_instance_id, thread_id=thread.id,
                         message_received=message_text)

    # V29 PART 5 — schedule the cold account's contextual auto-reply for a natural (never instant)
    # delay. The reply is actually generated + sent by run_cold_reply_tick once the cold account is
    # eligible (gated). A safety-paused thread gets NO scheduled reply.
    if not flagged:
        from app.services import warmup_cold_reply as ccr
        thread.awaiting_reply = True
        thread.pending_reply_at = ccr.cold_reply_due_at(now)

    # V28 — thank the contact FROM the same sender that asked them (their own
    # sender_instance_id), falling back to the main account for legacy rows. Generalized to the
    # (sender, contact, cold number) triple instead of one global helper pool. Skipped for a
    # safety-paused thread.
    enr_map = await _enrollment_states(db)
    accounts = (await db.execute(
        select(Account).where(Account.status == AccountStatus.active)
    )).scalars().all()
    sender = resolve_task_sender(accounts, helper, enr_map)
    sent = False
    scheduled = False
    if sender is not None and not flagged:
        # V30 PART 5 — AI-generated, varied, emoji, leak-safe thank-you (was a static line). The
        # FIRST completion sends inline immediately; a BURST of completions (sender pacer not ready)
        # STAGGERS the overflow — schedule it for run_thankyou_tick so thank-yous never fire at once.
        from app.services import peer_pacer
        from app.services.warmup_thankyou import (
            generate_thank_you, build_thankyou_ai_fn, thankyou_due_at,
        )
        forbidden = tuple(v for v in (cold_instance_id, getattr(sender, "name", None),
                                      helper.sender_instance_id) if v)
        # Gate on the THANK-YOU-only pacer (a recent ask/reminder must not defer this courtesy
        # reply; a recent THANK-YOU should). First completion → inline; burst overflow → scheduled.
        if peer_pacer.thankyou_ready(sender.instance_id, now):
            ty_text, _src = await generate_thank_you(
                contact_name=helper.name, ai_fn=build_thankyou_ai_fn(), forbidden=forbidden)
            mid = await _send_from_main(sender, helper.phone, ty_text, client_factory)
            sent = bool(mid)
            if mid:
                peer_pacer.record_thankyou(sender.instance_id, now)
            tclog.record(db, event_type=tclog.EVENT_THANK_YOU, from_instance_id=sender.instance_id,
                         to_phone=helper.phone, helper_id=helper.id,
                         sender_instance_id=getattr(sender, "instance_id", None),
                         cold_instance_id=cold_instance_id, thread_id=thread.id, message_sent=ty_text)
        else:
            thread.awaiting_thankyou = True
            thread.pending_thankyou_at = thankyou_due_at(now)
            scheduled = True
    return {"helper": helper.name, "cold_instance_id": cold_instance_id,
            "sender_instance_id": getattr(sender, "instance_id", None), "thanked": sent,
            "thankyou_scheduled": scheduled, "thread_paused": flagged}
