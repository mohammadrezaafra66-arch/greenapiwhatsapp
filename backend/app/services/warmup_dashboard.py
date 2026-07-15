"""V17 PART 6 — warm-up dashboard data builder.

Pure functions that turn enrollment + edge objects into the dashboard payload the Persian
RTL UI renders: state/day/progress, sent/received vs the day's target, reply ratio, mesh
peers + per-edge activity, next action, a status badge, and any banner (paused / resting /
blocked / insufficient warm peers / global breaker). Kept pure so it unit-tests directly.
"""
from __future__ import annotations
from datetime import datetime

from app.services.warmup_state import WarmupState, DEFAULT_WARMUP_CONFIG
from app.services.warmup_scheduler import (
    day_index, target_state_for_day, receiving_inbound_target, ramp_daily_target,
)
from app.services.warmup_mesh_service import edge_is_messageable, INSUFFICIENT_PEERS_NOTICE

# Numbers are considered fully graduated (green light) around day 25.
GRADUATE_DAY = 25

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
    day = day_index(enrollment, now)
    state = target_state_for_day(day, getattr(enrollment, "state", ""), cfg)
    if state == WarmupState.RECEIVING.value:
        return receiving_inbound_target(day)
    if state in (WarmupState.REPLYING.value, WarmupState.RAMPING.value):
        return ramp_daily_target(day, cfg)
    if state == WarmupState.MATURING.value:
        return 100                                  # representative midpoint of the 80–120 band
    return 0                                         # COOLDOWN / side states / graduated


def _iso(dt):
    return dt.isoformat() if isinstance(dt, datetime) else None


def build_number_card(enrollment, edges, now: datetime | None = None,
                      cfg=DEFAULT_WARMUP_CONFIG) -> dict:
    """One dashboard card for an enrolled number."""
    now = now or datetime.utcnow()
    state = getattr(enrollment, "state", WarmupState.ENROLLED.value)
    day = day_index(enrollment, now)
    progress = 100 if state == WarmupState.GRADUATED.value else int(min(100, round(day / GRADUATE_DAY * 100)))

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
    if state == WarmupState.PAUSED.value:
        banner = {"type": "paused", "message": "گرم‌سازی این شماره متوقف است."}
    elif state == WarmupState.YELLOWCARD.value:
        banner = {"type": "yellowcard", "message": "زرد‌کارت دریافت شده؛ شماره در حال استراحت است."}
    elif state == WarmupState.BLOCKED_RESET.value:
        banner = {"type": "blocked", "message": "شماره مسدود/خارج شده؛ گرم‌سازی بازنشانی می‌شود."}
    elif state in (WarmupState.RECEIVING.value, WarmupState.REPLYING.value,
                   WarmupState.RAMPING.value, WarmupState.MATURING.value) and messageable_count == 0:
        banner = {"type": "insufficient_peers", "message": INSUFFICIENT_PEERS_NOTICE}

    return {
        "instance_id": getattr(enrollment, "instance_id", None),
        "phone": getattr(enrollment, "phone", None),
        "state": state,
        "badge": STATE_LABELS_FA.get(state, state),
        "day_index": day,
        "graduate_day": GRADUATE_DAY,
        "progress_pct": progress,
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
        "banner": banner,
    }


def build_dashboard(enrollments, edges_by_instance: dict, breaker_tripped: bool = False,
                    now: datetime | None = None, cfg=DEFAULT_WARMUP_CONFIG) -> dict:
    """The full dashboard payload: one card per enrolled number, plus a global banner when
    the chain-ban breaker is tripped."""
    now = now or datetime.utcnow()
    cards = [
        build_number_card(enr, edges_by_instance.get(getattr(enr, "instance_id", None), []), now, cfg)
        for enr in enrollments
    ]
    global_banner = None
    if breaker_tripped:
        global_banner = {
            "type": "breaker",
            "message": "بریکر زنجیره‌بن فعال است: کل شبکهٔ گرم‌سازی متوقف شده. لطفاً وضعیت شماره‌ها را بررسی کنید.",
        }
    return {
        "breaker_tripped": bool(breaker_tripped),
        "global_banner": global_banner,
        "graduate_day": GRADUATE_DAY,
        "numbers": cards,
        "total": len(cards),
    }
