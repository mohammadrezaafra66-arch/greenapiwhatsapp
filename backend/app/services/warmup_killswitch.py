"""V17 PART 5 — kill-switch, chain-ban circuit breaker, and reset/erosion detection.

Webhook-driven safety for the mesh warm-up:

  • yellowCard / block-spike on a number → PAUSE it immediately (YELLOWCARD), stop all its
    outbound, rest >= 48h, then resume at ~5% of prior volume and ramp +10%/week.
  • blocked / notAuthorized / logout → BLOCKED_RESET; on re-auth, restart from Day 1
    (Green API: a block resets warm-up).
  • delivery ratio < ~60% → soft-ban signal → throttle + alert.
  • >= 2 numbers carded/blocked within a rolling 48h window → trip the mesh-wide circuit
    breaker: pause the WHOLE mesh, quarantine the most-connected node first, alert.
  • 14-day idle → erosion; 30-day idle → auto-logout. Either → restart + alert.

Pure helpers are unit-testable; the async actions take an injected DB session so they run
against the repo's FakeSession with simulated webhook payloads.
"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timedelta
from sqlalchemy import select, func

from app.models.warmup_mesh import WarmupEnrollment, WarmupMeshEdge, WarmupEventLog
from app.services.warmup_state import WarmupState, transition, can_transition

logger = logging.getLogger("afrakala.warmup.killswitch")

REST_HOURS = 48
DELIVERY_SOFT_BAN_THRESHOLD = 0.60
BREAKER_INCIDENT_THRESHOLD = 2
BREAKER_WINDOW_HOURS = 48
EROSION_IDLE_DAYS = 14
AUTOLOGOUT_IDLE_DAYS = 30

# Green API states that reset warm-up (vs. yellowCard which only rests it).
RESET_STATES = {"blocked", "notAuthorized", "notauthorized", "logout"}


# ── pure helpers ─────────────────────────────────────────────────────────────
def rest_until(now: datetime, hours: int = REST_HOURS) -> datetime:
    return now + timedelta(hours=hours)


def is_resting(enrollment, now: datetime) -> bool:
    ru = getattr(enrollment, "rest_until", None)
    return ru is not None and now < ru


def delivery_ratio(delivered: int, sent: int) -> float:
    sent = int(sent or 0)
    if sent <= 0:
        return 1.0                     # nothing sent yet → not a soft-ban signal
    return int(delivered or 0) / sent


def is_soft_ban(ratio: float, threshold: float = DELIVERY_SOFT_BAN_THRESHOLD) -> bool:
    return ratio < threshold


def post_rest_volume_fraction(weeks_since_resume: float) -> float:
    """Resume at ~5% of prior volume, ramping +10%/week (compounding), capped at 100%."""
    weeks = max(0.0, float(weeks_since_resume))
    return min(1.0, 0.05 * (1.10 ** weeks))


def reduced_target(base_target: int, weeks_since_resume: float) -> int:
    """A post-yellowCard day's target: base scaled by the resume fraction (>=1 so it can run)."""
    return max(1, int(round(base_target * post_rest_volume_fraction(weeks_since_resume))))


def should_trip_breaker(incident_count: int, threshold: int = BREAKER_INCIDENT_THRESHOLD) -> bool:
    return int(incident_count) >= int(threshold)


def idle_reset_reason(idle_days: float) -> str | None:
    """Reset reason from inactivity: >=30d auto-logout, >=14d erosion, else None."""
    if idle_days >= AUTOLOGOUT_IDLE_DAYS:
        return "auto_logout"
    if idle_days >= EROSION_IDLE_DAYS:
        return "erosion"
    return None


def state_reset_reason(green_state: str) -> str | None:
    """Map a Green API state webhook to a reset reason, or None if it isn't a reset."""
    s = (green_state or "").strip()
    if s in RESET_STATES:
        return s
    return None


# ── alerts + event log ───────────────────────────────────────────────────────
async def _alert(db, message_fa: str, *, scope: str, instance_id: str | None = None,
                 enrollment_id=None):
    """Raise a clear in-app alert (Persian) as a durable warm-up event the dashboard shows."""
    db.add(WarmupEventLog(
        enrollment_id=enrollment_id, event_type="alert",
        payload_json=json.dumps({"scope": scope, "instance_id": instance_id,
                                 "message": message_fa}, ensure_ascii=False),
    ))
    logger.warning("[warmup alert] %s (%s/%s)", message_fa, scope, instance_id)


# ── per-number kill-switch actions ───────────────────────────────────────────
async def on_yellow_card(db, enrollment, now: datetime | None = None) -> dict:
    """Pause a carded number immediately and start its >=48h rest window."""
    now = now or datetime.utcnow()
    prev = enrollment.state
    if can_transition(enrollment.state, WarmupState.YELLOWCARD.value):
        transition(enrollment, WarmupState.YELLOWCARD.value, now=now)
    else:
        enrollment.state = WarmupState.YELLOWCARD.value
    enrollment.rest_until = rest_until(now)
    db.add(WarmupEventLog(enrollment_id=enrollment.id, event_type="kill",
                          payload_json=json.dumps({"from": prev, "reason": "yellowCard",
                                                   "rest_until": enrollment.rest_until.isoformat()})))
    await _alert(db, "زرد‌کارت دریافت شد؛ گرم‌سازی این شماره موقتاً متوقف و ۴۸ ساعت استراحت داده شد.",
                 scope="number", instance_id=enrollment.instance_id, enrollment_id=enrollment.id)
    return {"state": enrollment.state, "rest_until": enrollment.rest_until}


async def on_block_or_logout(db, enrollment, reason: str, now: datetime | None = None) -> dict:
    """A block/logout resets warm-up: move to BLOCKED_RESET (restart from Day 1 on re-auth)."""
    now = now or datetime.utcnow()
    prev = enrollment.state
    if can_transition(enrollment.state, WarmupState.BLOCKED_RESET.value):
        transition(enrollment, WarmupState.BLOCKED_RESET.value, now=now)
    else:
        enrollment.state = WarmupState.BLOCKED_RESET.value
    db.add(WarmupEventLog(enrollment_id=enrollment.id, event_type="kill",
                          payload_json=json.dumps({"from": prev, "reason": reason})))
    await _alert(db, "شماره مسدود/خارج‌شده است؛ گرم‌سازی از روز اول بازنشانی می‌شود.",
                 scope="number", instance_id=enrollment.instance_id, enrollment_id=enrollment.id)
    return {"state": enrollment.state}


async def on_reauthorized(db, enrollment, now: datetime | None = None) -> dict:
    """After a re-auth, restart the FULL schedule from Day 1 (only from BLOCKED_RESET)."""
    now = now or datetime.utcnow()
    if enrollment.state != WarmupState.BLOCKED_RESET.value:
        return {"state": enrollment.state, "restarted": False}
    enrollment.state = WarmupState.COOLDOWN.value      # ENROLLED→COOLDOWN, day 1
    enrollment.day_index = 0
    enrollment.started_at = now
    enrollment.authorized_at = now
    enrollment.sent_today = 0
    enrollment.received_today = 0
    enrollment.reply_ratio = 0.0
    enrollment.rest_until = None
    enrollment.next_action_at = now + timedelta(hours=24)
    db.add(WarmupEventLog(enrollment_id=enrollment.id, event_type="state_change",
                          payload_json=json.dumps({"to": "COOLDOWN", "reason": "reauth_restart"})))
    await _alert(db, "شماره دوباره متصل شد؛ گرم‌سازی از روز اول آغاز شد.",
                 scope="number", instance_id=enrollment.instance_id, enrollment_id=enrollment.id)
    return {"state": enrollment.state, "restarted": True}


async def evaluate_delivery(db, enrollment, delivered: int, sent: int,
                            now: datetime | None = None) -> dict:
    """Delivery ratio < ~60% → soft-ban: throttle (rest window) + alert. Returns the ratio."""
    ratio = delivery_ratio(delivered, sent)
    soft = is_soft_ban(ratio)
    if soft:
        enrollment.rest_until = rest_until(now or datetime.utcnow(), hours=24)
        await _alert(db, f"نرخ تحویل پایین ({int(ratio*100)}٪) — احتمال سافت‌بن؛ ارسال کاهش یافت.",
                     scope="number", instance_id=enrollment.instance_id, enrollment_id=enrollment.id)
    return {"ratio": ratio, "soft_ban": soft}


async def maybe_resume_after_rest(db, enrollment, now: datetime | None = None) -> bool:
    """When a rested (YELLOWCARD) number's rest window has elapsed, resume it at reduced
    volume (REPLYING). The 5%→+10%/week ramp is applied by the scheduler via reduced_target."""
    now = now or datetime.utcnow()
    if enrollment.state != WarmupState.YELLOWCARD.value:
        return False
    if is_resting(enrollment, now):
        return False
    transition(enrollment, WarmupState.REPLYING.value, now=now)
    enrollment.rest_until = now          # resume anchor for the volume ramp
    db.add(WarmupEventLog(enrollment_id=enrollment.id, event_type="state_change",
                          payload_json=json.dumps({"to": "REPLYING", "reason": "rest_elapsed"})))
    return True


# ── chain-ban circuit breaker (mesh-wide) ────────────────────────────────────
async def record_incident(db, instance_id: str, kind: str, now: datetime | None = None):
    """Log a mesh incident (yellowCard/block) used by the breaker's rolling-window count."""
    db.add(WarmupEventLog(
        enrollment_id=None, event_type="incident",
        payload_json=json.dumps({"instance_id": instance_id, "kind": kind}),
    ))


async def count_recent_incidents(db, now: datetime | None = None,
                                 window_hours: int = BREAKER_WINDOW_HOURS) -> int:
    now = now or datetime.utcnow()
    cutoff = now - timedelta(hours=window_hours)
    return (await db.execute(
        select(func.count()).select_from(WarmupEventLog).where(
            WarmupEventLog.event_type == "incident",
            WarmupEventLog.created_at >= cutoff,
        )
    )).scalar() or 0


async def most_connected_instance(db) -> str | None:
    """The mesh node with the most edges — quarantined first when the breaker trips."""
    edges = (await db.execute(select(WarmupMeshEdge))).scalars().all()
    deg: dict[str, int] = {}
    for e in edges:
        deg[e.new_instance_id] = deg.get(e.new_instance_id, 0) + 1
        deg[e.peer_instance_id] = deg.get(e.peer_instance_id, 0) + 1
    if not deg:
        return None
    return max(deg.items(), key=lambda kv: kv[1])[0]


async def trip_global_breaker(db, reason: str, now: datetime | None = None,
                              quarantine_instance: str | None = None) -> dict:
    """Halt the ENTIRE mesh: pause every enabled enrollment, quarantine the most-connected
    node first, alert the operator. An emergency override — sets state directly to PAUSED."""
    now = now or datetime.utcnow()
    enrollments = (await db.execute(
        select(WarmupEnrollment).where(WarmupEnrollment.is_enabled.is_(True))
    )).scalars().all()
    quarantine = quarantine_instance or await most_connected_instance(db)
    paused = 0
    for enr in enrollments:
        if enr.state not in (WarmupState.PAUSED.value, WarmupState.BLOCKED_RESET.value):
            enr.state = WarmupState.PAUSED.value
            paused += 1
    db.add(WarmupEventLog(enrollment_id=None, event_type="kill",
                          payload_json=json.dumps({"scope": "mesh_breaker", "active": True,
                                                   "reason": reason, "quarantine": quarantine})))
    await _alert(db, "بریکر زنجیره‌بن فعال شد: کل شبکهٔ گرم‌سازی موقتاً متوقف شد. لطفاً بررسی کنید.",
                 scope="mesh", instance_id=quarantine)
    return {"tripped": True, "paused": paused, "quarantine": quarantine}


async def check_and_maybe_trip_breaker(db, now: datetime | None = None) -> dict:
    """If >= threshold incidents happened in the rolling window, trip the breaker."""
    n = await count_recent_incidents(db, now)
    if should_trip_breaker(n):
        return await trip_global_breaker(db, reason=f"{n} incidents in {BREAKER_WINDOW_HOURS}h", now=now)
    return {"tripped": False, "incidents": n}


async def is_breaker_tripped(db, now: datetime | None = None,
                             window_hours: int = BREAKER_WINDOW_HOURS) -> bool:
    """True if the mesh breaker was tripped (and not reset) within the window."""
    now = now or datetime.utcnow()
    cutoff = now - timedelta(hours=window_hours)
    rows = (await db.execute(
        select(WarmupEventLog).where(
            WarmupEventLog.event_type == "kill",
            WarmupEventLog.created_at >= cutoff,
        ).order_by(WarmupEventLog.created_at.desc())
    )).scalars().all()
    for r in rows:
        try:
            p = json.loads(r.payload_json or "{}")
        except Exception:
            continue
        if p.get("scope") == "mesh_breaker":
            return bool(p.get("active"))
    return False


async def reset_breaker(db, now: datetime | None = None) -> dict:
    """Operator action: clear the mesh breaker (numbers stay PAUSED until resumed)."""
    db.add(WarmupEventLog(enrollment_id=None, event_type="kill",
                          payload_json=json.dumps({"scope": "mesh_breaker", "active": False,
                                                   "reason": "operator_reset"})))
    return {"reset": True}


# ── entry point used by the webhook layer ────────────────────────────────────
async def handle_warmup_state_signal(db, instance_id: str, green_state: str,
                                     now: datetime | None = None) -> dict | None:
    """Route a Green API state webhook to the right warm-up kill-switch action. No-op (None)
    when the instance isn't enrolled. Records an incident + checks the breaker for
    yellowCard/block signals."""
    now = now or datetime.utcnow()
    enr = (await db.execute(
        select(WarmupEnrollment).where(WarmupEnrollment.instance_id == instance_id)
    )).scalar_one_or_none()
    if not enr:
        return None
    state = (green_state or "").strip()
    if state == "yellowCard":
        res = await on_yellow_card(db, enr, now)
        await record_incident(db, instance_id, "yellowCard", now)
        breaker = await check_and_maybe_trip_breaker(db, now)
        return {"action": "yellowCard", **res, "breaker": breaker}
    reset_reason = state_reset_reason(state)
    if reset_reason:
        res = await on_block_or_logout(db, enr, reset_reason, now)
        await record_incident(db, instance_id, reset_reason, now)
        breaker = await check_and_maybe_trip_breaker(db, now)
        return {"action": "reset", **res, "breaker": breaker}
    if state == "authorized":
        return {"action": "reauth", **(await on_reauthorized(db, enr, now))}
    return None
