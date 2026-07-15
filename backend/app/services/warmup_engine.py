"""V17 PART 4 — the automatic mesh warm-up engine.

`plan_number_action` is a PURE decision function (no DB/network) that, given an
enrollment, its mesh edges, and `now`, returns exactly what a number should do this tick
(wait / defer / cooldown / target_reached / no_peers / send). `execute_action` performs a
planned send (typing → send → counters → event log) against injected clients. `run_warmup_
tick` is the Celery-driven orchestration that loads state, advances the state machine, and
runs one action per due number.

Guardrails enforced here: only messageable (mutual-contact) edges are ever chosen; the
2/min and active-hours caps hold; outbound is capped to keep reply_ratio >= 0.50; and the
schedule is per-number jittered so peers never fire on the same minute.
"""
from __future__ import annotations
import json
import logging
import random
from datetime import datetime
from sqlalchemy import select

from app.models.account import Account, AccountStatus
from app.models.warmup_mesh import WarmupEnrollment, WarmupMeshEdge, WarmupEventLog
from app.services.green_api import GreenAPIClient
from app.services.warmup_state import (
    WarmupState, transition, can_transition, reset_daily_counters_if_new_day,
    compute_reply_ratio, DEFAULT_WARMUP_CONFIG,
)
from app.services.warmup_scheduler import (
    day_index, target_state_for_day, daily_target, allowed_outbound,
    in_active_hours, next_active_start, schedule_next_action,
)
from app.services.warmup_mesh_service import edge_is_messageable
from app.services.warmup_content import generate_mesh_message, content_hash
from app.services.typing_sim import show_typing_for_send

logger = logging.getLogger("afrakala.warmup.engine")


def _default_client_factory(instance_id: str, api_token: str) -> GreenAPIClient:
    return GreenAPIClient(instance_id, api_token)


def messageable_edges(edges) -> list:
    """Only edges whose mutual-contact handshake is complete — the anti-stranger gate."""
    return [e for e in edges if edge_is_messageable(e)]


def plan_number_action(enrollment, edges, now: datetime, cfg=DEFAULT_WARMUP_CONFIG,
                       rng: random.Random | None = None) -> dict:
    """Decide this number's next action. Pure: `edges` are objects, no DB/network.

    Returns a dict with an "action":
      cooldown | idle | defer | wait | target_reached | no_peers | send
    A "send" plan carries: direction ("inbound"|"outbound"), edge, next_action_at, state.
    """
    r = rng or random
    day = day_index(enrollment, now)
    state = target_state_for_day(day, getattr(enrollment, "state", ""), cfg)

    # Non-active stages do nothing this tick (COOLDOWN/side-states/graduated-idle).
    if state == WarmupState.COOLDOWN.value:
        return {"action": "cooldown", "state": state, "day": day}
    if state in (WarmupState.PAUSED.value, WarmupState.YELLOWCARD.value,
                 WarmupState.BLOCKED_RESET.value, WarmupState.GRADUATED.value):
        return {"action": "idle", "state": state, "day": day}

    # Active hours only — otherwise defer to the next window with fresh jitter.
    if not in_active_hours(now, cfg):
        return {"action": "defer", "state": state, "day": day,
                "next_action_at": next_active_start(now, cfg, rng=r)}

    # Respect the per-number jittered schedule.
    naa = getattr(enrollment, "next_action_at", None)
    if naa is not None and now < naa:
        return {"action": "wait", "state": state, "day": day}

    # Daily target reached?
    target = daily_target(enrollment, now, cfg, r)
    done = int(getattr(enrollment, "sent_today", 0)) + int(getattr(enrollment, "received_today", 0))
    if target and done >= target:
        return {"action": "target_reached", "state": state, "day": day, "target": target}

    # Only ever act on a fully-handshaked (messageable) edge.
    live = messageable_edges(edges)
    if not live:
        return {"action": "no_peers", "state": state, "day": day}

    # Direction: RECEIVING is inbound-only. From REPLYING on, send outbound only while it
    # keeps reply_ratio >= min_ratio; otherwise take an inbound turn.
    sent = int(getattr(enrollment, "sent_today", 0))
    received = int(getattr(enrollment, "received_today", 0))
    if state == WarmupState.RECEIVING.value:
        direction = "inbound"
    else:
        direction = "outbound" if sent < allowed_outbound(received, cfg.min_reply_ratio) else "inbound"

    edge = r.choice(live)
    return {
        "action": "send", "state": state, "day": day, "direction": direction,
        "edge": edge, "target": target,
        "next_action_at": schedule_next_action(now, target or 12, cfg, rng=r),
    }


async def execute_action(db, action: dict, enrollment, new_account: Account,
                         peer_account: Account, *, client_factory=None,
                         now: datetime | None = None, recent_hashes: set | None = None,
                         history: list | None = None, ai_fn=None,
                         rng: random.Random | None = None) -> dict:
    """Perform a planned "send": generate anti-repeat content, show typing, send from the
    correct side, update counters + reply_ratio + the edge, and write the event log.
    Injected `client_factory`/`ai_fn` keep it fully unit-testable."""
    client_factory = client_factory or _default_client_factory
    now = now or datetime.utcnow()
    recent_hashes = set(recent_hashes or set())
    direction = action["direction"]
    edge = action["edge"]

    msg, source = await generate_mesh_message(
        persona=f"persona:{new_account.instance_id}", history=history or [],
        recent_hashes=recent_hashes, name=(peer_account.name if direction == "outbound" else new_account.name),
        ai_fn=ai_fn, rng=rng,
    )

    if direction == "inbound":
        sender, recipient, event_type = peer_account, new_account, "receive"
    else:
        sender, recipient, event_type = new_account, peer_account, "send"

    client = client_factory(sender.instance_id, sender.api_token)
    mid = None
    try:
        await show_typing_for_send(client, recipient.phone, msg, enabled=True)
        mid = await client.send_message(recipient.phone, msg)
    except Exception as e:
        logger.warning("mesh send failed (%s → %s): %s", sender.instance_id, recipient.instance_id, e)

    # Counters + ratio + edge bookkeeping.
    if direction == "inbound":
        enrollment.received_today = int(getattr(enrollment, "received_today", 0)) + 1
    else:
        enrollment.sent_today = int(getattr(enrollment, "sent_today", 0)) + 1
    enrollment.reply_ratio = compute_reply_ratio(
        getattr(enrollment, "sent_today", 0), getattr(enrollment, "received_today", 0))
    enrollment.last_activity_at = now
    enrollment.next_action_at = action.get("next_action_at")
    edge.msg_count = int(getattr(edge, "msg_count", 0)) + 1
    edge.last_msg_at = now

    db.add(WarmupEventLog(
        enrollment_id=getattr(enrollment, "id", None),
        edge_id=getattr(edge, "id", None),
        event_type=event_type,
        content_hash=content_hash(msg),
        delivery_status="requested" if mid else "failed",
        payload_json=json.dumps({"text": msg, "source": source, "direction": direction,
                                 "peer": peer_account.instance_id}, ensure_ascii=False),
    ))
    return {"message": msg, "source": source, "message_id": mid, "direction": direction}


# ── recent per-edge history for anti-repeat ──────────────────────────────────
async def _recent_edge_history(db, edge_id, limit: int = 20) -> tuple[set, list]:
    if edge_id is None:
        return set(), []
    rows = (await db.execute(
        select(WarmupEventLog).where(WarmupEventLog.edge_id == edge_id)
        .order_by(WarmupEventLog.created_at.desc()).limit(limit)
    )).scalars().all()
    hashes, texts = set(), []
    for row in rows:
        if row.content_hash:
            hashes.add(row.content_hash)
        try:
            t = json.loads(row.payload_json or "{}").get("text")
            if t:
                texts.append(t)
        except Exception:
            pass
    return hashes, texts


async def _advance_state(db, enrollment, now, cfg) -> None:
    """Move the persisted state toward the schedule's target (legal transitions only)."""
    reset_daily_counters_if_new_day(enrollment, now)
    day = day_index(enrollment, now)
    target = target_state_for_day(day, enrollment.state, cfg)
    if target != enrollment.state and can_transition(enrollment.state, target):
        try:
            transition(enrollment, target, now=now)
            db.add(WarmupEventLog(enrollment_id=enrollment.id, event_type="state_change",
                                  payload_json=json.dumps({"to": target, "day": day})))
        except Exception as e:
            logger.debug("state advance skipped: %s", e)


async def run_warmup_tick(db, now: datetime | None = None, *, client_factory=None,
                          ai_fn=None, rng: random.Random | None = None) -> dict:
    """One beat tick: advance every enabled enrollment and run one due action each.
    Peers are the user's OWN accounts; only messageable edges are used."""
    client_factory = client_factory or _default_client_factory
    now = now or datetime.utcnow()
    r = rng or random

    # V17 PART 5 — if the chain-ban breaker is tripped, the whole mesh stays halted.
    from app.services.warmup_killswitch import is_breaker_tripped, maybe_resume_after_rest
    if await is_breaker_tripped(db, now):
        return {"acted": 0, "deferred": 0, "idle": 0, "total": 0, "halted": True}

    enrollments = (await db.execute(
        select(WarmupEnrollment).where(WarmupEnrollment.is_enabled.is_(True))
    )).scalars().all()

    acted = deferred = waited = 0
    for enr in enrollments:
        # Resume a rested (yellowCard) number once its >=48h rest window has elapsed.
        await maybe_resume_after_rest(db, enr, now)
        await _advance_state(db, enr, now, cfg=DEFAULT_WARMUP_CONFIG)
        new_acc = (await db.execute(
            select(Account).where(Account.instance_id == enr.instance_id)
        )).scalar_one_or_none()
        if not new_acc or new_acc.status != AccountStatus.active:
            continue
        # V20 PART 2 — self-heal missing mesh edges to newly-available warm peers (fixes the
        # "enrolled before any peer existed → 0 edges" case). No-op when peers/edges suffice.
        from app.services.warmup_mesh_service import ensure_mesh_edges
        await ensure_mesh_edges(db, new_acc, client_factory=client_factory, now=now, rng=r)
        edges = (await db.execute(
            select(WarmupMeshEdge).where(WarmupMeshEdge.new_instance_id == enr.instance_id)
        )).scalars().all()

        plan = plan_number_action(enr, edges, now, DEFAULT_WARMUP_CONFIG, r)
        if plan["action"] == "defer":
            enr.next_action_at = plan["next_action_at"]
            deferred += 1
            continue
        if plan["action"] != "send":
            waited += 1
            continue

        edge = plan["edge"]
        peer_acc = (await db.execute(
            select(Account).where(Account.instance_id == edge.peer_instance_id)
        )).scalar_one_or_none()
        if not peer_acc:
            continue
        recent_hashes, history = await _recent_edge_history(db, getattr(edge, "id", None))
        await execute_action(db, plan, enr, new_acc, peer_acc, client_factory=client_factory,
                             now=now, recent_hashes=recent_hashes, history=history,
                             ai_fn=ai_fn, rng=r)
        acted += 1

    await db.commit()
    return {"acted": acted, "deferred": deferred, "idle": waited, "total": len(enrollments)}
