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
# V20 PART 2 — a warm PEER (sender) is never itself warmed.
WARM_PEER_NOT_WARMED_NOTICE = (
    "این اکانت به‌عنوان «اکانت گرم مرجع / فرستنده» علامت خورده است و خودش گرم‌سازی نمی‌شود."
)
# V21 PART 2 — shown when a number isn't authorized/connected on Green API yet. An unconnected
# number is NEVER enrolled and NEVER given a mesh slot until it authorizes (scan QR first).
NOT_CONNECTED_NOTICE = (
    "این شماره هنوز به واتساپ متصل نشده — ابتدا با اسکن QR وصل کنید تا گرم‌سازی شروع شود."
)


async def instance_is_authorized(client) -> bool:
    """True ONLY when Green API reports this instance as `authorized` (connected). Fail-safe:
    any non-authorized state (pending/notAuthorized/…) or any error → False, so an unconnected
    number can never enter or run in the mesh. get_state is a plain GET — NOT polling."""
    try:
        state = await client.get_state()
    except Exception as e:
        logger.warning("connection state check failed for %s: %s",
                       getattr(client, "instance_id", "?"), e)
        return False
    return str(state or "").strip() == "authorized"
# V21 PART 1 — warm:cold ratio cap. One warm peer warms AT MOST this many cold numbers at a
# time (conservative anti-ban: a peer serving many cold numbers is itself a suspicious pattern).
MAX_COLD_PER_WARM_PEER = 2
# V21 PART 1 — shown on a cold number's card when every eligible warm peer is already at its
# cap, so this number is waiting for capacity (add another warm sender to free a slot).
CAPACITY_FULL_NOTICE = (
    "ظرفیت اکانت‌های گرم پر است — برای گرم‌کردن این شماره، یک اکانت گرم دیگر به‌عنوان فرستنده "
    "اضافه کنید (هر اکانت گرم حداکثر ۲ شماره)."
)
# V21 PART 1 — cold-number enrollment states that FREE a warm peer's capacity slot (no longer
# actively being warmed). Everything else (COOLDOWN/RECEIVING/…/YELLOWCARD) still occupies a slot.
_SLOT_FREEING_STATES = {
    WarmupState.GRADUATED.value, WarmupState.PAUSED.value, WarmupState.BLOCKED_RESET.value,
}


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
    Randomized so different new numbers get different, overlapping peer sets.
    NOTE: superseded by the V21 ratio-capped assignment (select_least_loaded_peer) for the
    live mesh; kept as a pure utility."""
    r = rng or random
    if not peers:
        return []
    hi = min(len(peers), cfg.peers_per_new_number_max)
    lo = min(len(peers), cfg.peers_per_new_number_min)
    k = r.randint(lo, hi) if hi >= lo else hi
    pool = list(peers)
    r.shuffle(pool)
    return pool[:k]


# ── V21 PART 1 — warm:cold ratio cap (1 warm peer : MAX_COLD_PER_WARM_PEER cold) ──────
def compute_peer_load(edges, enr_map: dict) -> dict[str, int]:
    """How many ACTIVE cold numbers are currently assigned to each warm peer.

    `edges` are WarmupMeshEdge-like objects (new_instance_id → peer_instance_id). `enr_map` is
    {instance_id: (state, is_enabled)}. A cold number occupies its peer's slot while it is
    enrolled+enabled and NOT in a slot-freeing state (GRADUATED/PAUSED/BLOCKED_RESET). Pure."""
    load: dict[str, int] = {}
    for e in edges or []:
        st = enr_map.get(getattr(e, "new_instance_id", None))
        if not st:
            continue
        state, enabled = st
        if not enabled or state in _SLOT_FREEING_STATES:
            continue
        load[e.peer_instance_id] = load.get(e.peer_instance_id, 0) + 1
    return load


def select_least_loaded_peer(eligible: list, load: dict, cap: int = MAX_COLD_PER_WARM_PEER,
                             rng: random.Random | None = None):
    """Pick the eligible warm peer with the FEWEST assigned cold numbers that is still below
    `cap` (balance load evenly, never overload one peer). Returns None when every eligible peer
    is already at the cap → the cold number waits for capacity. Pure and deterministic given rng."""
    r = rng or random
    candidates = [p for p in eligible if load.get(p.instance_id, 0) < cap]
    if not candidates:
        return None
    lo = min(load.get(p.instance_id, 0) for p in candidates)
    least = [p for p in candidates if load.get(p.instance_id, 0) == lo]
    return r.choice(least) if len(least) > 1 else least[0]


async def peer_cold_load(db, cfg=None) -> dict[str, int]:
    """DB-backed compute_peer_load: {warm_peer_instance_id: active-cold-count} across the mesh."""
    from app.services.warmup_exclusion import enrollment_states_by_instance
    edges = (await db.execute(select(WarmupMeshEdge))).scalars().all()
    enr_map = await enrollment_states_by_instance(db)
    return compute_peer_load(edges, enr_map)


async def mesh_capacity_snapshot(db, cfg=None) -> dict:
    """V21 — the dashboard's ratio/capacity view. Returns:
      • peer_load: per-warm-peer roster [{instance_id, name, cold_count, cap, full}]
      • capacity_full_instances: cold numbers actively being warmed that have NO eligible peer
        edge AND every eligible warm peer is at the 1:MAX cap (so they are WAITING for capacity)
      • assignments: {cold_instance_id: warm_peer_instance_id} for linked cold numbers.
    Pure DB reads; used by the mesh dashboard endpoint and tested directly."""
    cfg = cfg or DEFAULT_WARMUP_CONFIG
    from app.services.warmup_exclusion import enrollment_states_by_instance, GRADUATED
    accounts = (await db.execute(
        select(Account).where(Account.status == AccountStatus.active)
    )).scalars().all()
    edges = (await db.execute(select(WarmupMeshEdge))).scalars().all()
    enr_map = await enrollment_states_by_instance(db)

    load = compute_peer_load(edges, enr_map)
    graduated_ids = {iid for iid, (s, _e) in enr_map.items() if s == GRADUATED}
    eligible_ids = {a.instance_id for a in accounts if getattr(a, "is_warm_peer", False)} | graduated_ids
    id_to_name = {a.instance_id: a.name for a in accounts}

    peer_load = [{
        "instance_id": pid,
        "name": id_to_name.get(pid, pid),
        "cold_count": load.get(pid, 0),
        "cap": MAX_COLD_PER_WARM_PEER,
        "full": load.get(pid, 0) >= MAX_COLD_PER_WARM_PEER,
    } for pid in sorted(eligible_ids)]

    edges_by_cold: dict[str, set] = {}
    for e in edges:
        edges_by_cold.setdefault(e.new_instance_id, set()).add(e.peer_instance_id)
    assignments = {cold: next(iter(peers & eligible_ids))
                   for cold, peers in edges_by_cold.items() if (peers & eligible_ids)}

    below_cap = any(load.get(pid, 0) < MAX_COLD_PER_WARM_PEER for pid in eligible_ids)
    capacity_full: set = set()
    if eligible_ids and not below_cap:
        for iid, (state, enabled) in enr_map.items():
            if not enabled or state in _SLOT_FREEING_STATES:
                continue
            if not (edges_by_cold.get(iid, set()) & eligible_ids):
                capacity_full.add(iid)

    return {"peer_load": peer_load, "capacity_full_instances": capacity_full,
            "assignments": assignments}


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


# ── phone resolution (getWaSettings fallback) ────────────────────────────────
async def _resolve_account_phone(account: Account, client) -> str | None:
    """Return account.phone, falling back to getWaSettings (wid/phone) when it is null and
    PERSISTING it back onto the account. The partner/QR flow leaves accounts.phone null (the
    number lives only in the account name), which used to make the mutual-contact handshake
    silently no-op. Mirrors the admin-groups reader's getWaSettings fallback so a null phone
    can never again quietly break the mesh."""
    if account.phone:
        return account.phone
    try:
        wa = await client.get_wa_settings()
        phone = str(wa.get("phone") or wa.get("wid") or "").split("@")[0].strip()
        if phone:
            account.phone = phone   # persisted by the caller's commit
            logger.info("filled accounts.phone for %s from getWaSettings: %s",
                        account.instance_id, phone)
            return phone
    except Exception as e:
        logger.warning("getWaSettings phone fallback failed for %s: %s", account.instance_id, e)
    return None


async def backfill_account_phones(db, *, client_factory=None) -> list[dict]:
    """Fill accounts.phone from getWaSettings for every instance whose phone is null. The
    partner/QR flow leaves phone null. Idempotent — accounts that already have a phone (or are
    deleted) are skipped. Returns per-instance results. Run standalone or on demand."""
    client_factory = client_factory or _default_client_factory
    accounts = (await db.execute(select(Account))).scalars().all()
    results: list[dict] = []
    for a in accounts:
        if a.phone:
            results.append({"instance_id": a.instance_id, "phone": a.phone, "action": "kept"})
            continue
        if a.status == AccountStatus.deleted:
            results.append({"instance_id": a.instance_id, "phone": None, "action": "skipped_deleted"})
            continue
        client = client_factory(a.instance_id, a.api_token)
        phone = await _resolve_account_phone(a, client)
        results.append({"instance_id": a.instance_id, "phone": phone,
                        "action": "filled" if phone else "no_phone"})
    await db.commit()
    return results


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

    # Resolve both phones (getWaSettings fallback + persist) so a null accounts.phone from the
    # partner/QR flow can never again silently skip the mutual-contact step.
    new_phone = await _resolve_account_phone(new_acc, new_client)
    peer_phone = await _resolve_account_phone(peer_acc, peer_client)

    # New number saves the peer.
    if not edge.saved_as_contact_new and peer_phone:
        try:
            ok = await new_client.add_contact(peer_phone, peer_acc.name or "Peer")
            edge.saved_as_contact_new = bool(ok)
        except Exception as e:
            logger.warning("handshake add_contact (new→peer) failed: %s", e)
    # Peer saves the new number.
    if not edge.saved_as_contact_peer and new_phone:
        try:
            ok = await peer_client.add_contact(new_phone, new_acc.name or "New")
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

    # V20 PART 2 — a warm PEER is a SENDER only; it must NEVER be enrolled/warmed. Guard
    # against any path (toggle, batch) putting a peer on the "being warmed" side.
    if getattr(account, "is_warm_peer", False):
        return {"instance_id": account.instance_id, "state": None, "is_warm_peer": True,
                "notice": WARM_PEER_NOT_WARMED_NOTICE, "peers": [], "settings_applied": False,
                "queue_cleared": False, "cooldown_hours": None}

    # V21 PART 2 — never enroll an unconnected number. Verify the LIVE Green API state is
    # `authorized` first; a pending/notAuthorized instance creates NO enrollment and NO edges
    # and gets the connect-first notice (scan QR). Once it authorizes, toggling ON proceeds.
    client = client_factory(account.instance_id, account.api_token)
    if not await instance_is_authorized(client):
        return {"instance_id": account.instance_id, "state": None, "not_connected": True,
                "notice": NOT_CONNECTED_NOTICE, "peers": [], "settings_applied": False,
                "queue_cleared": False, "cooldown_hours": None}

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

    # `client` was created above for the connection check — reuse it.

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

    # 4) Build the mesh (mutual-contact handshake). V21 PART 1 — assign the ONE least-loaded
    #    warm peer that is still below the 1:MAX_COLD_PER_WARM_PEER ratio cap (balance load,
    #    never overload a peer). No eligible peer at all → insufficient-peers notice; peers
    #    exist but all at capacity → capacity-full notice (add another warm sender).
    existing_edges = (await db.execute(
        select(WarmupMeshEdge).where(WarmupMeshEdge.new_instance_id == account.instance_id)
    )).scalars().all()
    have = {e.peer_instance_id for e in existing_edges}
    eligible = await eligible_peer_accounts(db, account.instance_id)
    eligible_ids = {p.instance_id for p in eligible}
    if any(pid in eligible_ids for pid in have):
        # Already linked to a still-eligible peer (e.g. re-enroll) — retry the handshake, no new peer.
        for e in existing_edges:
            if e.peer_instance_id in eligible_ids:
                peer = next(p for p in eligible if p.instance_id == e.peer_instance_id)
                edge = await _handshake_edge(db, account, peer, client_factory)
                result["peers"].append({
                    "peer_instance_id": peer.instance_id,
                    "handshake_state": edge.handshake_state,
                    "messageable": edge_is_messageable(edge),
                })
    elif not eligible:
        result["notice"] = INSUFFICIENT_PEERS_NOTICE
    else:
        load = await peer_cold_load(db, cfg)
        peer = select_least_loaded_peer(
            [p for p in eligible if p.instance_id not in have], load, MAX_COLD_PER_WARM_PEER, rng)
        if peer is None:
            result["notice"] = CAPACITY_FULL_NOTICE
        else:
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
               peers=len(result["peers"]), notice=result["notice"])

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
        # V20 PART 1 — even with no enrollment, COMMIT so the endpoint's auto_warmup=False
        # persists. get_db() does not commit on close, so without this the toggle-OFF is
        # rolled back and the checkbox appears stuck ON.
        await db.commit()
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


async def ensure_mesh_edges(db, account: Account, *, client_factory=None,
                            now: datetime | None = None, rng: random.Random | None = None,
                            cfg=None) -> int:
    """V20 PART 2 — self-heal: build mutual-contact mesh edges from an enrolled cold number
    to eligible warm peers (GRADUATED or is_warm_peer) when it has fewer than the target.
    Fixes the "0 edges / no peer" case for numbers enrolled before any peer existed.

    DURABLE FIX — also RETRY incomplete handshakes: any existing edge that is not yet ACTIVE
    (handshake=none/contact_saved) is re-run through _handshake_edge every tick, so a null
    accounts.phone or a transient addContact failure can never leave an edge stuck at `none`
    forever. Once phones are present (getWaSettings fallback fills them), the retry completes
    the mutual-contact save and the edge flips to ACTIVE. Returns how many NEW edges were built.

    V21 PART 1 — RATIO CAP: a cold number is assigned exactly ONE warm peer, chosen as the
    least-loaded eligible peer still below the 1:MAX_COLD_PER_WARM_PEER cap. If the number
    already has an edge to a still-eligible peer, no new peer is added (retries only). If every
    eligible peer is at capacity, nothing is built (the number waits — surfaced on the dashboard).
    This guarantees a peer never exceeds MAX_COLD_PER_WARM_PEER cold numbers under any tick/retry.
    """
    client_factory = client_factory or _default_client_factory
    cfg = cfg or DEFAULT_WARMUP_CONFIG
    now = now or datetime.utcnow()

    existing = (await db.execute(
        select(WarmupMeshEdge).where(WarmupMeshEdge.new_instance_id == account.instance_id)
    )).scalars().all()
    have = {e.peer_instance_id for e in existing}

    # Retry incomplete handshakes on existing edges (the durable no-silent-no-op guarantee).
    retried = 0
    for edge in existing:
        if getattr(edge, "handshake_state", None) == HandshakeState.ACTIVE.value:
            continue
        peer_acc = (await db.execute(
            select(Account).where(Account.instance_id == edge.peer_instance_id)
        )).scalar_one_or_none()
        if peer_acc is None or peer_acc.status != AccountStatus.active:
            continue
        await _handshake_edge(db, account, peer_acc, client_factory)
        retried += 1

    # Assign at most ONE warm peer, respecting the ratio cap and balancing load.
    built = 0
    eligible = await eligible_peer_accounts(db, account.instance_id)
    eligible_ids = {p.instance_id for p in eligible}
    # Already linked to a still-eligible peer? Then it has its peer — do not add another.
    already_linked = any(pid in eligible_ids for pid in have)
    if not already_linked:
        fresh = [p for p in eligible if p.instance_id not in have]
        load = await peer_cold_load(db, cfg)
        peer = select_least_loaded_peer(fresh, load, MAX_COLD_PER_WARM_PEER, rng)
        if peer is not None:
            await _handshake_edge(db, account, peer, client_factory)
            built += 1

    if built or retried:
        await db.commit()
    return built
