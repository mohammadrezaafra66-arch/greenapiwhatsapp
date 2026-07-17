"""TG PART 6 — Telegram-specific anti-ban warm-up schedule + circuit breaker.

Designed around TELEGRAM's abuse model, NOT a copy of the WhatsApp mesh numbers:
  • the 48h danger zone (no outbound to non-contacts on a brand-new account),
  • 10–15s pacing PERMANENTLY (a per-message constant, not just a warm-up phase),
  • suspended/blocked as real, Green-API-visible states.

All thresholds are FIXED constants (mirroring the WhatsApp "not user-configurable" philosophy)
but stored DISTINCTLY from WhatsApp's — assert-tested to differ. The state machine names are
reused for dashboard/UX consistency; the numbers are Telegram's own.

Everything here is pure and unit-testable (no DB/network/time side effects).
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta

from app.services.warmup_state import WarmupState
from app.services.platforms import (
    TELEGRAM_NEW_ACCOUNT_GATE_HOURS, TELEGRAM_MIN_DELAY_SECONDS, TELEGRAM_MAX_DELAY_SECONDS,
)

# Reuse V21's distinct-number trip threshold + window for consistency, on Telegram's OWN stream.
TELEGRAM_BREAKER_THRESHOLD = 2
TELEGRAM_BREAKER_WINDOW_HOURS = 48
# Green API states that mean this Telegram number is in trouble.
TELEGRAM_BAD_STATES = ("suspended", "blocked")


@dataclass
class TelegramWarmupConfig:
    """FIXED Telegram warm-up thresholds — DISTINCT from WhatsApp's WarmupConfig."""
    # 0–48h: NO outbound to non-contacts (the hard danger zone).
    no_noncontact_gate_hours: int = TELEGRAM_NEW_ACCOUNT_GATE_HOURS
    # Days 3–7: low-volume outbound to EXISTING contacts / long-standing groups only.
    contacts_only_until_day: int = 7
    contacts_only_daily_cap: int = 5            # conservative handful/day
    # Days 7+: gradual ramp (Telegram's own conservative curve, not WhatsApp's).
    ramp_daily_caps: list = field(default_factory=lambda: [5, 10, 20, 40])  # d7-14, d14-21, d21-30, d30+
    graduate_after_days: int = 30
    # 10–15s BETWEEN EVERY send, permanently (not just during warm-up).
    min_delay_seconds: int = TELEGRAM_MIN_DELAY_SECONDS
    max_delay_seconds: int = TELEGRAM_MAX_DELAY_SECONDS
    timezone: str = "Asia/Tehran"

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_TELEGRAM_WARMUP_CONFIG = TelegramWarmupConfig()


def hours_since(authorized_at: datetime | None, now: datetime | None = None) -> float:
    if authorized_at is None:
        return 0.0
    now = now or datetime.utcnow()
    return max(0.0, (now - authorized_at).total_seconds() / 3600.0)


def warmup_stage(authorized_at: datetime | None, now: datetime | None = None,
                 cfg: TelegramWarmupConfig = DEFAULT_TELEGRAM_WARMUP_CONFIG) -> dict:
    """The Telegram warm-up stage for an instance authorized at `authorized_at`.

    Returns {stage, daily_cap, allow_noncontact_outbound, contacts_only}. Stage names map to
    the shared WarmupState enum for a consistent dashboard, but the thresholds are Telegram's.
    """
    h = hours_since(authorized_at, now)
    days = h / 24.0

    if h < cfg.no_noncontact_gate_hours:
        # 0–48h — only reply within chats that messaged first; NO non-contact outbound.
        return {"stage": WarmupState.COOLDOWN.value, "daily_cap": 0,
                "allow_noncontact_outbound": False, "contacts_only": True}
    if days < cfg.contacts_only_until_day:
        # Days 3–7 — low volume, contacts / long-standing groups only.
        return {"stage": WarmupState.REPLYING.value, "daily_cap": cfg.contacts_only_daily_cap,
                "allow_noncontact_outbound": False, "contacts_only": True}

    caps = cfg.ramp_daily_caps
    if days < 14:
        stage, cap = WarmupState.RAMPING.value, caps[0]
    elif days < 21:
        stage, cap = WarmupState.RAMPING.value, caps[1]
    elif days < cfg.graduate_after_days:
        stage, cap = WarmupState.MATURING.value, caps[2]
    else:
        stage, cap = WarmupState.GRADUATED.value, caps[3]
    return {"stage": stage, "daily_cap": cap,
            "allow_noncontact_outbound": True, "contacts_only": False}


# ── circuit breaker — Telegram-only distinct-instance counter ─────────────────
def distinct_telegram_offenders(events, now: datetime | None = None,
                                window_hours: int = TELEGRAM_BREAKER_WINDOW_HOURS) -> set:
    """DISTINCT Telegram instance ids that entered suspended/blocked within the rolling
    window. Events are dicts/objects with .platform, .instance_id, .state, .created_at.
    WhatsApp events are IGNORED here, so a WhatsApp incident can NEVER trip the TG breaker."""
    now = now or datetime.utcnow()
    cutoff = now - timedelta(hours=window_hours)
    out = set()
    for e in events:
        platform = _attr(e, "platform")
        state = (_attr(e, "state") or "").lower()
        ts = _attr(e, "created_at")
        iid = _attr(e, "instance_id")
        if platform != "telegram" or state not in TELEGRAM_BAD_STATES or not iid:
            continue
        if ts is not None and ts < cutoff:
            continue
        out.add(iid)
    return out


def should_trip_telegram_breaker(distinct_count: int,
                                 threshold: int = TELEGRAM_BREAKER_THRESHOLD) -> bool:
    """Trip only when >= threshold DISTINCT Telegram instances are in trouble."""
    return int(distinct_count) >= int(threshold)


def _attr(obj, name):
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)
