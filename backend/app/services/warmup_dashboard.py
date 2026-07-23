"""V17 PART 6 — warm-up dashboard data builder.

Pure functions that turn enrollment + edge objects into the dashboard payload the Persian
RTL UI renders: state/day/progress, sent/received vs the day's target, reply ratio, mesh
peers + per-edge activity, next action, a status badge, and any banner (paused / resting /
blocked / insufficient warm peers / global breaker). Kept pure so it unit-tests directly.
"""
from __future__ import annotations
from datetime import datetime

from app.services.warmup_state import WarmupState, DEFAULT_WARMUP_CONFIG, RECOVERY_WARMUP_CONFIG
from app.services.warmup_scheduler import (
    day_index, target_state_for_day, receiving_inbound_target, ramp_daily_target,
    recovery_enabled, RECOVERY_GRADUATE_DAY,
)
from app.services.warmup_mesh_service import (
    edge_is_messageable, INSUFFICIENT_PEERS_NOTICE, CAPACITY_FULL_NOTICE, MAX_COLD_PER_WARM_PEER,
    NOT_CONNECTED_NOTICE,
)

# Numbers are considered fully graduated (green light) around day 25.
GRADUATE_DAY = 25

# V20 PART 3 — shown when an enrolled cold number has NO eligible warm sender at all.
NO_PEER_NOTICE = "هیچ اکانت گرم مرجعی انتخاب نشده — یک اکانت گرم را به‌عنوان فرستنده علامت بزنید."

# V41 PART 5 — distinct labels for a number going through the mesh RECOVERY re-warm (Green API's
# 10-day sequence), so its card is visibly a recovery, not a generic onboarding.
RECOVERY_BADGE_FA = "در حال بازیابی گرم‌سازی"
RECOVERY_RESET_LABEL_FA = "دفعات بازنشانی به‌دلیل اختلال"

# Persian labels for the account ROLE in the warm-up system.
ROLE_LABELS_FA = {
    "being_warmed": "در حال گرم‌سازی",
    "peer_sender": "اکانت گرم مرجع / فرستنده",
    "graduated_peer": "فارغ‌التحصیل (فرستنده)",
    "none": "بدون نقش",
}

# Persian labels for each state badge.
STATE_LABELS_FA = {
    "ENROLLED": "ثبت‌شده",
    "COOLDOWN": "دورهٔ آماده‌سازی (۲۴ساعت)",
    "RECEIVING": "دریافت پیام",
    "REPLYING": "شروع پاسخ‌دهی",
    "RAMPING": "افزایش تدریجی",
    "MATURING": "تثبیت",
    "GRADUATED": "آماده (فارغ‌التحصیل)",
    "PAUSED": "متوقف",
    "YELLOWCARD": "زرد‌کارت (استراحت)",
    "BLOCKED_RESET": "مسدود / بازنشانی",
}


def display_daily_target(enrollment, now: datetime, cfg=DEFAULT_WARMUP_CONFIG) -> int:
    """A stable (RNG-free) representation of the day's target for the dashboard."""
    recovery = recovery_enabled(enrollment)      # V41 PART 1 — recovery-mode timeline when set
    if recovery:
        cfg = RECOVERY_WARMUP_CONFIG
    day = day_index(enrollment, now)
    state = target_state_for_day(day, getattr(enrollment, "state", ""), cfg, recovery=recovery)
    if state == WarmupState.RECEIVING.value:
        return receiving_inbound_target(day)
    if state in (WarmupState.REPLYING.value, WarmupState.RAMPING.value):
        return ramp_daily_target(day, cfg)
    if state == WarmupState.MATURING.value:
        return 100                                  # representative midpoint of the 80–120 band
    return 0                                         # COOLDOWN / side states / graduated


def _iso(dt):
    return dt.isoformat() if isinstance(dt, datetime) else None


def _build_group_warmup(enrollment, memberships, now, cfg) -> dict:
    """V19 — group-placement summary for a cold number's dashboard card."""
    from datetime import timedelta
    from app.services.warmup_group_scheduler import (
        last_action_at, GROUP_MIN_SPACING_HOURS, GROUP_MATURING_MIN_DAYS,
    )
    from app.services.warmup_scheduler import day_index
    memberships = memberships or []
    placements = [{
        "group_id": getattr(m, "group_id", None),
        "warm_instance_id": getattr(m, "warm_instance_id", None),
        "status": getattr(m, "status", None),
        "added_at": _iso(getattr(m, "added_at", None)),
        "last_attempt_at": _iso(getattr(m, "last_attempt_at", None)),
        "error_reason": getattr(m, "error_reason", None),
    } for m in memberships]
    counts = {"added": 0, "pending": 0, "failed": 0}
    for m in memberships:
        st = getattr(m, "status", None)
        if st in counts:
            counts[st] += 1
    last = last_action_at(memberships)
    next_at = None
    if last is not None:
        day = day_index(enrollment, now)
        gap = timedelta(days=GROUP_MATURING_MIN_DAYS) if day > 10 else timedelta(hours=GROUP_MIN_SPACING_HOURS)
        next_at = last + gap
    return {
        "placements": placements,
        "counts": counts,
        "last_action_at": _iso(last),
        "next_action_at": _iso(next_at),
    }


def build_number_card(enrollment, edges, now: datetime | None = None,
                      cfg=DEFAULT_WARMUP_CONFIG, group_memberships=None,
                      has_eligible_peer: bool = True, capacity_full: bool = False,
                      assigned_peer: str | None = None, not_connected: bool = False) -> dict:
    """One dashboard card for an enrolled number (mesh info + V19 group placements).
    V21 — `capacity_full` marks a cold number waiting because every warm peer is at its 1:2
    cap; `assigned_peer` is the warm peer instance this cold number is warmed by (or None);
    `not_connected` marks a number that isn't authorized on Green API yet (enrolled while
    pending) — the mesh skips it until it connects."""
    now = now or datetime.utcnow()
    state = getattr(enrollment, "state", WarmupState.ENROLLED.value)
    day = day_index(enrollment, now)
    # V41 PART 5 — a recovery-mode number follows Green API's ~10-day sequence, so its progress bar
    # must fill against the recovery graduate day, not the general 25-day onboarding horizon.
    recovery = recovery_enabled(enrollment)
    grad_day = RECOVERY_GRADUATE_DAY if recovery else GRADUATE_DAY
    progress = 100 if state == WarmupState.GRADUATED.value else int(min(100, round(day / grad_day * 100)))

    peers = []
    messageable_count = 0
    for e in edges or []:
        m = edge_is_messageable(e)
        messageable_count += 1 if m else 0
        peers.append({
            "peer_instance_id": e.peer_instance_id,
            "handshake_state": e.handshake_state,
            "messageable": m,
            "msg_count": int(getattr(e, "msg_count", 0) or 0),
            "last_msg_at": _iso(getattr(e, "last_msg_at", None)),
        })

    target = display_daily_target(enrollment, now, cfg)
    sent = int(getattr(enrollment, "sent_today", 0) or 0)
    received = int(getattr(enrollment, "received_today", 0) or 0)

    banner = None
    if not_connected:
        # V21 PART 2 — connection is the prerequisite; show it above every other banner.
        banner = {"type": "not_connected", "message": NOT_CONNECTED_NOTICE}
    elif state == WarmupState.PAUSED.value:
        banner = {"type": "paused", "message": "گرم‌سازی این شماره متوقف است."}
    elif state == WarmupState.YELLOWCARD.value:
        # V21 PART 3 — a single carded number is quarantined on its own; the rest keeps running.
        banner = {"type": "yellowcard",
                  "message": "این شماره به‌دلیل کارت زرد قرنطینه شد — بقیهٔ شبکه فعال است."}
    elif state == WarmupState.BLOCKED_RESET.value:
        banner = {"type": "blocked", "message": "شماره مسدود/خارج شده؛ گرم‌سازی بازنشانی می‌شود."}
    elif capacity_full and messageable_count == 0 and len(peers) == 0:
        # V21 PART 1 — every warm peer is at its 1:2 cap → this number waits for capacity.
        # Shown across stages (incl. COOLDOWN) so a waiting number is never silently peerless.
        banner = {"type": "capacity_full", "message": CAPACITY_FULL_NOTICE}
    elif state in (WarmupState.RECEIVING.value, WarmupState.REPLYING.value,
                   WarmupState.RAMPING.value, WarmupState.MATURING.value) and messageable_count == 0:
        # V20 PART 3 — distinguish "no warm sender marked at all" from "peers exist, edges
        # still building", so the 0-peer situation is visible instead of silent.
        if not has_eligible_peer:
            banner = {"type": "no_peer", "message": NO_PEER_NOTICE}
        else:
            banner = {"type": "insufficient_peers", "message": INSUFFICIENT_PEERS_NOTICE}

    # V20 PART 3 — role: a GRADUATED enrollment is now a sender/peer, not being warmed.
    role = "graduated_peer" if state == WarmupState.GRADUATED.value else "being_warmed"

    return {
        "instance_id": getattr(enrollment, "instance_id", None),
        "phone": getattr(enrollment, "phone", None),
        "state": state,
        "role": role,
        "badge": STATE_LABELS_FA.get(state, state),
        "day_index": day,
        "graduate_day": grad_day,
        "progress_pct": progress,
        # V41 PART 5 — recovery re-warm visibility: whether this number is in recovery mode, and the
        # restart-on-disruption counter (how many times PART 2's guard reset it to Day 1, with the
        # last reason/time). Flat, always-present fields — 0/false/None for every normal card.
        "recovery_mode": recovery,
        "recovery_badge": RECOVERY_BADGE_FA if recovery else None,
        "recovery_reset_count": int(getattr(enrollment, "recovery_reset_count", 0) or 0),
        "recovery_reset_label": RECOVERY_RESET_LABEL_FA,
        "recovery_last_reset_at": _iso(getattr(enrollment, "recovery_last_reset_at", None)),
        "recovery_last_reset_reason": getattr(enrollment, "recovery_last_reset_reason", None),
        "sent_today": sent,
        "received_today": received,
        "day_target": target,
        "reply_ratio": round(float(getattr(enrollment, "reply_ratio", 0.0) or 0.0), 3),
        "reply_ratio_ok": float(getattr(enrollment, "reply_ratio", 0.0) or 0.0) >= cfg.min_reply_ratio,
        "next_action_at": _iso(getattr(enrollment, "next_action_at", None)),
        "is_enabled": bool(getattr(enrollment, "is_enabled", False)),
        "rest_until": _iso(getattr(enrollment, "rest_until", None)),
        "peers": peers,
        "peer_count": len(peers),
        "messageable_peer_count": messageable_count,
        # V21 — which warm peer warms this cold number (first messageable/assigned edge), and
        # whether it is currently waiting because every warm peer is at the 1:2 cap.
        "assigned_peer": assigned_peer or (peers[0]["peer_instance_id"] if peers else None),
        "capacity_full": bool(capacity_full and len(peers) == 0),
        "not_connected": bool(not_connected),
        "banner": banner,
        # V19 — group-based warm-up placements (additive track under the same enrollment)
        "group_warmup": _build_group_warmup(enrollment, group_memberships, now, cfg),
    }


def build_dashboard(enrollments, edges_by_instance: dict, breaker_tripped: bool = False,
                    now: datetime | None = None, cfg=DEFAULT_WARMUP_CONFIG,
                    memberships_by_instance: dict | None = None,
                    has_eligible_peer: bool = True, roles: list | None = None,
                    capacity_full_instances: set | None = None,
                    peer_load: list | None = None,
                    not_connected_instances: set | None = None,
                    breaker_offenders: list | None = None) -> dict:
    """The full dashboard payload: one card per enrolled number (mesh + group placements),
    an account ROLE overview (being-warmed vs peer/sender vs none), a no-peer notice when no
    warm sender is marked, plus a global banner when the chain-ban breaker is tripped.
    V21 — `capacity_full_instances` marks cold numbers waiting on the 1:2 ratio cap;
    `peer_load` is the per-warm-peer capacity roster (n/cap) shown on the dashboard."""
    now = now or datetime.utcnow()
    memberships_by_instance = memberships_by_instance or {}
    capacity_full_instances = capacity_full_instances or set()
    not_connected_instances = not_connected_instances or set()
    cards = [
        build_number_card(
            enr, edges_by_instance.get(getattr(enr, "instance_id", None), []), now, cfg,
            group_memberships=memberships_by_instance.get(getattr(enr, "instance_id", None), []),
            has_eligible_peer=has_eligible_peer,
            capacity_full=getattr(enr, "instance_id", None) in capacity_full_instances,
            not_connected=getattr(enr, "instance_id", None) in not_connected_instances,
        )
        for enr in enrollments
    ]
    global_banner = None
    if breaker_tripped:
        offenders = breaker_offenders or []
        names = "، ".join(o.get("instance_id", "?") for o in offenders)
        msg = "بریکر زنجیره‌بن فعال است: کل شبکهٔ گرم‌سازی متوقف شده. لطفاً وضعیت شماره‌ها را بررسی کنید."
        if names:
            # V21 PART 3 — show WHICH distinct numbers tripped it.
            msg += f" شماره‌های عامل: {names}."
        global_banner = {"type": "breaker", "message": msg, "offenders": offenders}
    roles = roles or []
    for r in roles:
        r.setdefault("role_label", ROLE_LABELS_FA.get(r.get("role"), r.get("role")))
    warm_peer_count = sum(1 for r in roles if r.get("role") in ("peer_sender", "graduated_peer"))
    return {
        "breaker_tripped": bool(breaker_tripped),
        "global_banner": global_banner,
        "graduate_day": GRADUATE_DAY,
        "numbers": cards,
        "total": len(cards),
        # V20 PART 3 — role overview + peer availability
        "roles": roles,
        "warm_peer_count": warm_peer_count,
        "has_eligible_peer": bool(has_eligible_peer),
        "no_peer_notice": (None if has_eligible_peer else NO_PEER_NOTICE),
        # V21 — per-warm-peer capacity roster (n/cap) + the 1:2 cap value.
        "peer_load": peer_load or [],
        "max_cold_per_warm_peer": MAX_COLD_PER_WARM_PEER,
    }
