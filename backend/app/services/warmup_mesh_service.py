"""V17 PART 3 — enrollment, pre-flight, and the mutual-contact mesh handshake.

The "one toggle": turning warm-up ON for an account creates a WarmupEnrollment and runs
pre-flight automatically and safely BEFORE any message can flow:

  1. Apply the exact Green API warming instance settings (webhook-only — polling is NEVER
     enabled; the webhook URL is left untouched so the ngrok tunnel wiring is not disturbed).
  2. Clear any stale outgoing send queue (showMessagesQueue → clearMessagesQueue).
  3. Enforce the 24h cooldown (hold in COOLDOWN until 24h after authorization).
  4. Build the mesh: pick 3–6 warm peers and save each pair as MUTUAL contacts on BOTH
     sides. An edge only becomes `active` (messageable) once BOTH contact flags are true —
     a warming number may never message a stranger.

Green API calls go through an injectable `client_factory(instance_id, api_token)` so the
whole flow unit-tests against a mock with no network.
"""
import logging
import random
from datetime import datetime, timedelta
from sqlalchemy import select

from app.models.account import Account, AccountStatus
from app.models.warmup_mesh import WarmupEnrollment, WarmupMeshEdge, WarmupEventLog
from app.services.green_api import GreenAPIClient
from app.services.warmup_state import (
    WarmupState, HandshakeState, transition, load_config, DEFAULT_WARMUP_CONFIG,
)

logger = logging.getLogger("afrakala.warmup.mesh")

INSUFFICIENT_PEERS_NOTICE = (
    "برای گرم‌کردن به اکانت گرم کافی نیاز است — حداقل یک اکانت گرم اضافه کنید."
)


def _default_client_factory(instance_id: str, api_token: str) -> GreenAPIClient:
    return GreenAPIClient(instance_id, api_token)


# ── peer eligibility + selection ─────────────────────────────────────────────
async def eligible_peer_accounts(db, exclude_instance_id: str) -> list[Account]:
    """Accounts eligible to warm a new number: manually-marked warm peers OR numbers whose
    warm-up has GRADUATED. Must be active and not the new number itself. Never invents
    peers — only the user's own connected instances qualify."""
    accounts = (await db.execute(
        select(Account).where(Account.status == AccountStatus.active)
    )).scalars().all()
    graduated = set((await db.execute(
        select(WarmupEnrollment.instance_id).where(
            WarmupEnrollment.state == WarmupState.GRADUATED.value)
    )).scalars().all())
    out = []
    for a in accounts:
        if a.instance_id == exclude_instance_id:
            continue
        if bool(getattr(a, "is_warm_peer", False)) or a.instance_id in graduated:
            out.append(a)
    return out


def select_peers(peers: list, cfg=DEFAULT_WARMUP_CONFIG, rng: random.Random | None = None) -> list:
    """Pick between peers_per_new_number_min and _max peers (capped by availability).
    Randomized so different new numbers get different, overlapping peer sets."""
    r = rng or random
    if not peers:
        return []
    hi = min(len(peers), cfg.peers_per_new_number_max)
    lo = min(len(peers), cfg.peers_per_new_number_min)
    k = r.randint(lo, hi) if hi >= lo else hi
    pool = list(peers)
    r.shuffle(pool)
    return pool[:k]


# ── 24h cooldown ─────────────────────────────────────────────────────────────
def cooldown_remaining_hours(enrollment, cfg=DEFAULT_WARMUP_CONFIG,
                             now: datetime | None = None) -> float:
    """Hours left in the mandatory post-authorization cooldown. 0 when elapsed. When
    authorized_at is unknown, treat as a full cooldown (conservative)."""
    now = now or datetime.utcnow()
    auth = getattr(enrollment, "authorized_at", None)
    if auth is None:
        return float(cfg.cooldown_hours)
    elapsed = (now - auth).total_seconds() / 3600.0
    return max(0.0, float(cfg.cooldown_hours) - elapsed)


def cooldown_elapsed(enrollment, cfg=DEFAULT_WARMUP_CONFIG, now: datetime | None = None) -> bool:
    return cooldown_remaining_hours(enrollment, cfg, now) <= 0.0


# ── mutual-contact handshake ─────────────────────────────────────────────────
async def _handshake_edge(db, new_acc: Account, peer_acc: Account, client_factory) -> WarmupMeshEdge:
    """Create/refresh the edge between new_acc and peer_acc and save each other as
    contacts on BOTH sides. Edge becomes ACTIVE only when both saves succeed."""
    edge = (await db.execute(
        select(WarmupMeshEdge).where(
            WarmupMeshEdge.new_instance_id == new_acc.instance_id,
            WarmupMeshEdge.peer_instance_id == peer_acc.instance_id,
        )
    )).scalar_one_or_none()
    if edge is None:
        edge = WarmupMeshEdge(
            new_instance_id=new_acc.instance_id,
            peer_instance_id=peer_acc.instance_id,
            direction="bidirectional",
            handshake_state=HandshakeState.NONE.value,
        )
        db.add(edge)

    new_client = client_factory(new_acc.instance_id, new_acc.api_token)
    peer_client = client_factory(peer_acc.instance_id, peer_acc.api_token)

    # New number saves the peer.
    if not edge.saved_as_contact_new and peer_acc.phone:
        try:
            ok = await new_client.add_contact(peer_acc.phone, peer_acc.name or "Peer")
            edge.saved_as_contact_new = bool(ok)
        except Exception as e:
            logger.warning("handshake add_contact (new→peer) failed: %s", e)
    # Peer saves the new number.
    if not edge.saved_as_contact_peer and new_acc.phone:
        try:
            ok = await peer_client.add_contact(new_acc.phone, new_acc.name or "New")
            edge.saved_as_contact_peer = bool(ok)
        except Exception as e:
            logger.warning("handshake add_contact (peer→new) failed: %s", e)

    if edge.saved_as_contact_new and edge.saved_as_contact_peer:
        edge.handshake_state = HandshakeState.ACTIVE.value
    elif edge.saved_as_contact_new or edge.saved_as_contact_peer:
        edge.handshake_state = HandshakeState.CONTACT_SAVED.value
    return edge


def edge_is_messageable(edge) -> bool:
    """A mesh edge may carry a warm-up message ONLY when the mutual-contact handshake is
    complete on both sides. The single most important anti-ban guard."""
    return (bool(edge.saved_as_contact_new) and bool(edge.saved_as_contact_peer)
            and edge.handshake_state == HandshakeState.ACTIVE.value)


# ── enrollment + pre-flight ──────────────────────────────────────────────────
async def _log(db, enrollment_id, event_type, **payload):
    import json
    db.add(WarmupEventLog(
        enrollment_id=enrollment_id, event_type=event_type,
        payload_json=json.dumps(payload, ensure_ascii=False) if payload else None,
    ))


async def enroll_and_preflight(db, account: Account, *, client_factory=None,
                               now: datetime | None = None, rng: random.Random | None = None,
                               cfg=None) -> dict:
    """Turn warm-up ON for `account` (the one toggle). Creates/updates the enrollment,
    runs pre-flight, builds the mutual-contact mesh, and holds the number in COOLDOWN.
    Returns a summary dict (state, peers, cooldown_hours, notice, settings_applied,
    queue_cleared)."""
    client_factory = client_factory or _default_client_factory
    cfg = cfg or DEFAULT_WARMUP_CONFIG
    now = now or datetime.utcnow()

    enrollment = (await db.execute(
        select(WarmupEnrollment).where(WarmupEnrollment.instance_id == account.instance_id)
    )).scalar_one_or_none()
    if enrollment is None:
        enrollment = WarmupEnrollment(
            instance_id=account.instance_id, phone=account.phone,
            state=WarmupState.ENROLLED.value, day_index=0,
        )
        db.add(enrollment)
        await db.flush()
    else:
        # Re-enable a previously-paused enrollment without wiping its progress.
        enrollment.phone = account.phone or enrollment.phone
        if enrollment.state in (WarmupState.PAUSED.value,):
            enrollment.state = WarmupState.ENROLLED.value
    enrollment.is_enabled = True
    if not enrollment.started_at:
        enrollment.started_at = now
    if not enrollment.authorized_at:
        # Authorization time unknown → treat as just-authorized (full 24h cooldown).
        enrollment.authorized_at = now
    enrollment.last_activity_at = now

    result = {"instance_id": account.instance_id, "settings_applied": False,
              "queue_cleared": False, "peers": [], "notice": None}

    client = client_factory(account.instance_id, account.api_token)

    # 1) Apply the exact warming settings (webhook-only; webhook URL left untouched).
    try:
        result["settings_applied"] = bool(await client.set_warming_instance_settings())
    except Exception as e:
        logger.warning("pre-flight set_warming_instance_settings failed: %s", e)

    # 2) Clear any stale outgoing queue before binding.
    try:
        queued = await client.show_messages_queue()
        if queued:
            result["queue_cleared"] = bool(await client.clear_messages_queue())
        else:
            result["queue_cleared"] = True  # nothing to clear
    except Exception as e:
        logger.warning("pre-flight queue clear failed: %s", e)

    # 4) Build the mesh (mutual-contact handshake) with eligible warm peers.
    eligible = await eligible_peer_accounts(db, account.instance_id)
    selected = select_peers(eligible, cfg, rng)
    if len(eligible) < cfg.peers_per_new_number_min:
        result["notice"] = INSUFFICIENT_PEERS_NOTICE
    for peer in selected:
        edge = await _handshake_edge(db, account, peer, client_factory)
        result["peers"].append({
            "peer_instance_id": peer.instance_id,
            "handshake_state": edge.handshake_state,
            "messageable": edge_is_messageable(edge),
        })

    # 3) Enforce the 24h cooldown — hold in COOLDOWN regardless of peers.
    if enrollment.state == WarmupState.ENROLLED.value:
        transition(enrollment, WarmupState.COOLDOWN, now=now)
    enrollment.next_action_at = enrollment.authorized_at + timedelta(hours=cfg.cooldown_hours)
    await _log(db, enrollment.id, "state_change", to=enrollment.state,
               peers=len(selected), notice=result["notice"])

    result["state"] = enrollment.state
    result["cooldown_hours"] = round(cooldown_remaining_hours(enrollment, cfg, now), 2)
    await db.commit()
    return result


async def resume_warmup(db, account: Account, now: datetime | None = None) -> dict:
    """Resume a paused number: re-enable and move it back to the stage matching its day."""
    from app.services.warmup_scheduler import day_index, target_state_for_day
    now = now or datetime.utcnow()
    enrollment = (await db.execute(
        select(WarmupEnrollment).where(WarmupEnrollment.instance_id == account.instance_id)
    )).scalar_one_or_none()
    if enrollment is None:
        return {"instance_id": account.instance_id, "state": None, "resumed": False}
    enrollment.is_enabled = True
    if enrollment.state == WarmupState.PAUSED.value:
        day = day_index(enrollment, now)
        target = target_state_for_day(day, WarmupState.COOLDOWN.value, DEFAULT_WARMUP_CONFIG)
        # PAUSED may resume to any live stage; fall back to COOLDOWN if the jump is illegal.
        from app.services.warmup_state import can_transition
        enrollment.state = target if can_transition(WarmupState.PAUSED.value, target) else WarmupState.COOLDOWN.value
    await _log(db, enrollment.id, "state_change", to=enrollment.state, reason="user_resumed")
    await db.commit()
    return {"instance_id": account.instance_id, "state": enrollment.state, "resumed": True}


async def force_restart(db, account: Account, now: datetime | None = None) -> dict:
    """Operator force-restart: wipe progress and begin the full schedule from Day 1."""
    now = now or datetime.utcnow()
    enrollment = (await db.execute(
        select(WarmupEnrollment).where(WarmupEnrollment.instance_id == account.instance_id)
    )).scalar_one_or_none()
    if enrollment is None:
        return {"instance_id": account.instance_id, "state": None, "restarted": False}
    enrollment.is_enabled = True
    enrollment.state = WarmupState.COOLDOWN.value
    enrollment.day_index = 0
    enrollment.started_at = now
    enrollment.authorized_at = now
    enrollment.sent_today = 0
    enrollment.received_today = 0
    enrollment.reply_ratio = 0.0
    enrollment.rest_until = None
    enrollment.next_action_at = now + timedelta(hours=DEFAULT_WARMUP_CONFIG.cooldown_hours)
    await _log(db, enrollment.id, "state_change", to=enrollment.state, reason="force_restart")
    await db.commit()
    return {"instance_id": account.instance_id, "state": enrollment.state, "restarted": True}


async def disable_warmup(db, account: Account, now: datetime | None = None) -> dict:
    """Turn the toggle OFF: pause everything for this number immediately (no more sends)."""
    now = now or datetime.utcnow()
    enrollment = (await db.execute(
        select(WarmupEnrollment).where(WarmupEnrollment.instance_id == account.instance_id)
    )).scalar_one_or_none()
    if enrollment is None:
        return {"instance_id": account.instance_id, "state": None, "disabled": True}
    enrollment.is_enabled = False
    if enrollment.state not in (WarmupState.BLOCKED_RESET.value,):
        try:
            transition(enrollment, WarmupState.PAUSED, now=now)
        except Exception:
            enrollment.state = WarmupState.PAUSED.value
    await _log(db, enrollment.id, "state_change", to=enrollment.state, reason="user_disabled")
    await db.commit()
    return {"instance_id": account.instance_id, "state": enrollment.state, "disabled": True}
