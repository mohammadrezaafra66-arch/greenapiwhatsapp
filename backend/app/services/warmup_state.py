"""V17 PART 2 — warm-up state machine, handshake states, and configurable defaults.

Pure and dependency-light so it unit-tests without a DB. The scheduler (PART 4) and the
kill-switch (PART 5) drive transitions through `transition()`, which rejects any move not
in ALLOWED_TRANSITIONS.
"""
from __future__ import annotations
import enum
from dataclasses import dataclass, field, asdict
from datetime import datetime, date as date_type
import pytz

TEHRAN_TZ = "Asia/Tehran"


class WarmupState(str, enum.Enum):
    """Main warm-up flow plus side states.

    Flow:  ENROLLED → COOLDOWN → RECEIVING → REPLYING → RAMPING → MATURING → GRADUATED
    Side:  PAUSED (user/kill-switch), YELLOWCARD (rest+resume), BLOCKED_RESET (restart d1).
    """
    ENROLLED = "ENROLLED"
    COOLDOWN = "COOLDOWN"
    RECEIVING = "RECEIVING"
    REPLYING = "REPLYING"
    RAMPING = "RAMPING"
    MATURING = "MATURING"
    GRADUATED = "GRADUATED"
    PAUSED = "PAUSED"
    YELLOWCARD = "YELLOWCARD"
    BLOCKED_RESET = "BLOCKED_RESET"


class HandshakeState(str, enum.Enum):
    """Mesh-edge handshake. An edge is messageable ONLY in `active`."""
    NONE = "none"
    CONTACT_SAVED = "contact_saved"
    ACTIVE = "active"


# The linear "happy path" order (used to resume a paused number to the right stage).
FLOW_ORDER = [
    WarmupState.ENROLLED, WarmupState.COOLDOWN, WarmupState.RECEIVING,
    WarmupState.REPLYING, WarmupState.RAMPING, WarmupState.MATURING, WarmupState.GRADUATED,
]

# States a live number can be interrupted from into a side state.
_INTERRUPTIBLE = {
    WarmupState.ENROLLED, WarmupState.COOLDOWN, WarmupState.RECEIVING,
    WarmupState.REPLYING, WarmupState.RAMPING, WarmupState.MATURING, WarmupState.GRADUATED,
}
_SIDE = {WarmupState.PAUSED, WarmupState.YELLOWCARD, WarmupState.BLOCKED_RESET}


def _build_allowed() -> dict[WarmupState, set[WarmupState]]:
    allowed: dict[WarmupState, set[WarmupState]] = {s: set() for s in WarmupState}
    # Forward along the flow (each stage → the next one).
    for a, b in zip(FLOW_ORDER, FLOW_ORDER[1:]):
        allowed[a].add(b)
    # Any interruptible live state → any side state.
    for s in _INTERRUPTIBLE:
        allowed[s] |= _SIDE
    # PAUSED resumes back to any live flow stage (engine picks by day_index).
    allowed[WarmupState.PAUSED] |= set(FLOW_ORDER) | {WarmupState.BLOCKED_RESET}
    # YELLOWCARD → rest (PAUSED) or resume at reduced volume, or escalate to reset.
    allowed[WarmupState.YELLOWCARD] |= {
        WarmupState.PAUSED, WarmupState.RECEIVING, WarmupState.REPLYING,
        WarmupState.RAMPING, WarmupState.MATURING, WarmupState.BLOCKED_RESET,
    }
    # BLOCKED_RESET → restart from the very beginning on re-auth.
    allowed[WarmupState.BLOCKED_RESET] |= {WarmupState.ENROLLED, WarmupState.COOLDOWN}
    return allowed


ALLOWED_TRANSITIONS = _build_allowed()


def can_transition(src: WarmupState | str, dst: WarmupState | str) -> bool:
    src = WarmupState(src)
    dst = WarmupState(dst)
    if src == dst:
        return True  # idempotent no-op is always fine
    return dst in ALLOWED_TRANSITIONS[src]


class IllegalTransition(ValueError):
    pass


def transition(enrollment, dst: WarmupState | str, now: datetime | None = None):
    """Move `enrollment.state` to `dst`, rejecting illegal moves. `enrollment` needs a
    mutable `state` attribute (a real model or a SimpleNamespace)."""
    src = WarmupState(enrollment.state)
    dst = WarmupState(dst)
    if not can_transition(src, dst):
        raise IllegalTransition(f"illegal warm-up transition {src.value} → {dst.value}")
    enrollment.state = dst.value
    if hasattr(enrollment, "updated_at"):
        enrollment.updated_at = now or datetime.utcnow()
    return enrollment


# ── Configurable defaults (2.3) — SHIP THESE EXACT VALUES; admin-editable ────
@dataclass
class WarmupConfig:
    cooldown_hours: int = 24
    receiving_days: list = field(default_factory=lambda: [2, 3, 4])
    reply_start_day: int = 4
    ramp_curve: list = field(default_factory=lambda: [12, 20, 32, 48, 66, 84, 100])
    daily_campaign_cap: int = 200
    new_contacts_per_day_cap: int = 20
    min_reply_ratio: float = 0.50
    peers_per_new_number_min: int = 3
    peers_per_new_number_max: int = 6
    keepwarm_max_idle_days: int = 10
    max_msgs_per_minute: int = 2
    max_active_hours_per_day: int = 6
    active_hours_start: str = "09:00"
    active_hours_end: str = "21:00"
    timezone: str = "Asia/Tehran"
    queue_delay_ms: int = 15000
    auto_typing: int = 2

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_WARMUP_CONFIG = WarmupConfig()

# ── V41 PART 1 — recovery-mode config (Green API's exact 10-day recovery sequence) ──
# Green API support's re-warm guidance for a number whose linked devices churned:
#   • Day 1: no link/authorize at all.
#   • Day 2: authorize, send NOTHING.
#   • Days 3–5 (3 days): OTHER real accounts message it ~every 2h (receiving-only).
#   • Then the number starts replying ~every 2h to existing contacts.
#   • Over the following 7 days: ramp message flow from ~12 up to 100 messages/day.
#   • After ~10 days total the number is much more ban-resistant.
# The general onboarding config differs (2 receiving days, reply on day 4, a long MATURING
# band, graduation only at day 25), so recovery mode uses THIS config: 3 receiving days
# (day_index 2–4) and replying beginning day_index 5. The ramp curve (12→100, 7 steps) and
# the ~2h base cadence (BASE_MU_MIN=120) already match Green API exactly, so they are reused
# unchanged. Day boundaries are anchored on day_index (1-based days since authorization);
# see warmup_scheduler for the day-by-day state mapping and the graduation boundary.
RECOVERY_WARMUP_CONFIG = WarmupConfig(receiving_days=[2, 3, 4], reply_start_day=5)


def load_config(overrides: dict | None = None) -> WarmupConfig:
    """Global defaults merged with an optional per-number override dict (admin-editable)."""
    if not overrides:
        return WarmupConfig()
    base = DEFAULT_WARMUP_CONFIG.to_dict()
    base.update({k: v for k, v in overrides.items() if k in base})
    return WarmupConfig(**base)


# ── daily counters + reply ratio ─────────────────────────────────────────────
def _tehran_today(now: datetime | None = None, tz: str = TEHRAN_TZ) -> date_type:
    zone = pytz.timezone(tz)
    if now is None:
        now = datetime.now(zone)
    elif now.tzinfo is None:
        now = zone.localize(now)
    return now.astimezone(zone).date()


def reset_daily_counters_if_new_day(enrollment, now: datetime | None = None,
                                    tz: str = TEHRAN_TZ) -> bool:
    """Zero sent_today/received_today when the Tehran-local date rolls over. Returns True
    if a reset happened. Idempotent within the same local day."""
    today = _tehran_today(now, tz)
    if getattr(enrollment, "counters_date", None) != today:
        enrollment.sent_today = 0
        enrollment.received_today = 0
        enrollment.counters_date = today
        return True
    return False


def compute_reply_ratio(sent: int, received: int) -> float:
    """Replies received per message sent. 0.0 when nothing has been sent yet.
    (Spec: ~50 replies per 100 sent → ratio ≥ 0.50 is the health floor.)"""
    sent = int(sent or 0)
    received = int(received or 0)
    if sent <= 0:
        return 0.0
    return received / sent
