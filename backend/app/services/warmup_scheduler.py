"""V17 PART 4 — pure scheduling / decision logic for the automatic mesh warm-up.

Everything here is pure and injectable (RNG + `now` passed in) so the whole day-by-day
engine unit-tests deterministically without Celery, a DB, time, or the network. The async
orchestration in warmup_engine.py composes these functions.

Design rules straight from the spec:
  • Every gap is randomized (never fixed) and clamped to sane bounds.
  • Each number runs its OWN jittered schedule — peers never fire on synchronized minutes.
  • Never exceed 2 messages/minute or `max_active_hours_per_day` active hours/day.
  • All activity only within active hours (Asia/Tehran); jobs outside defer to the next
    window with fresh jitter.
  • Daily volume follows the ramp curve; outbound is capped so reply_ratio stays >= 0.50.
"""
from __future__ import annotations
import random
from datetime import datetime, timedelta, time as dtime
import pytz

from app.services.warmup_state import (
    WarmupState, DEFAULT_WARMUP_CONFIG, RECOVERY_WARMUP_CONFIG,
)

TEHRAN = pytz.timezone("Asia/Tehran")

# ── V41 PART 1 — recovery-mode timeline boundaries (Green API's exact sequence) ──
# Keyed on day_index (1-based days since authorization; day_index 0 = enrolled, pre-auth).
# Mapping to Green API's calendar (GA Day N ≈ day_index N-1, since GA Day 1 is the no-link
# pre-auth day and GA Day 2 is the authorize-only day):
#   day_index 0–1  → COOLDOWN   (GA Day 1 no-link + GA Day 2 authorize, send nothing)
#   day_index 2–4  → RECEIVING  (GA Days 3–5, peers message it ~every 2h, receiving-only)
#   day_index 5    → REPLYING   (GA Day 6, the number begins replying ~every 2h)
#   day_index 6–11 → RAMPING    (GA Days 7–12, ramp 12→100 over the 7-step ramp_curve)
#   day_index ≥ 12 → GRADUATED
# Reconciliation of Green API's own numbers: it states both a "7-day ramp 12→100" and
# "much more ban-resistant after ~10 days". Those overlap rather than sum; we honor the full
# 7-step ramp and only declare GRADUATED after it completes (day_index 12), which is strictly
# MORE conservative than graduating at day 10 — never less safe. By GA's day-10 milestone the
# number is already deep in the ramp (~66/day) and fully interactive.
RECOVERY_RECEIVING_DAYS = (2, 3, 4)
RECOVERY_REPLY_START_DAY = RECOVERY_WARMUP_CONFIG.reply_start_day          # 5
RECOVERY_RAMP_LEN = len(RECOVERY_WARMUP_CONFIG.ramp_curve)                 # 7 steps (12→100)
RECOVERY_GRADUATE_DAY = RECOVERY_REPLY_START_DAY + RECOVERY_RAMP_LEN       # day_index 12


def recovery_enabled(enrollment) -> bool:
    """True when this enrollment follows the V41 recovery-mode timeline."""
    return bool(getattr(enrollment, "recovery_mode", False))


def effective_config(enrollment, cfg=DEFAULT_WARMUP_CONFIG):
    """The config an enrollment's schedule should use: the recovery config for a recovery-mode
    enrollment (fixed 3-day receive / day-5 reply / graduate-at-12 sequence), else `cfg`."""
    return RECOVERY_WARMUP_CONFIG if recovery_enabled(enrollment) else cfg

# Hard floor between two sends from ONE number: 2 msgs/min → >= 30s apart.
HARD_MIN_GAP_SECONDS = 30
# Base cadence spec: ~120min mean, 35min sd, clamped 45–210min during RECEIVING/REPLYING.
BASE_MU_MIN = 120
BASE_SIGMA_MIN = 35
GAP_MIN_FLOOR_MIN = 8       # hard minimum gap once volume ramps (spec ~8–10 min)
GAP_MIN_MIN = 45            # base-cadence clamp low
GAP_MAX_MIN = 210           # base-cadence clamp high


# ── active hours ─────────────────────────────────────────────────────────────
def _parse_hhmm(s: str) -> dtime:
    h, m = str(s).split(":")
    return dtime(int(h), int(m))


def to_tehran(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return TEHRAN.localize(dt)
    return dt.astimezone(TEHRAN)


def in_active_hours(dt: datetime, cfg=DEFAULT_WARMUP_CONFIG) -> bool:
    """True if `dt` (any tz; naive treated as Tehran) is within [start, end) Tehran-local."""
    local = to_tehran(dt)
    start = _parse_hhmm(cfg.active_hours_start)
    end = _parse_hhmm(cfg.active_hours_end)
    return start <= local.time() < end


def next_active_start(dt: datetime, cfg=DEFAULT_WARMUP_CONFIG,
                      rng: random.Random | None = None) -> datetime:
    """The next moment activity may resume: the start of the current window if we are
    before it today, else tomorrow's window start — plus fresh 0–40min jitter so numbers
    don't all resume on the exact minute. Returns a Tehran-aware datetime."""
    r = rng or random
    local = to_tehran(dt)
    start = _parse_hhmm(cfg.active_hours_start)
    end = _parse_hhmm(cfg.active_hours_end)
    jitter = timedelta(minutes=r.uniform(0, 40))
    if local.time() < start:
        base = local.replace(hour=start.hour, minute=start.minute, second=0, microsecond=0)
    elif local.time() >= end:
        nxt = (local + timedelta(days=1)).replace(hour=start.hour, minute=start.minute,
                                                  second=0, microsecond=0)
        base = nxt
    else:
        return local  # already inside the window
    return base + jitter


# ── circadian + weekend multipliers ──────────────────────────────────────────
def circadian_multiplier(hour: int) -> float:
    """Slower mornings/late nights, slightly faster midday. Returns a volume multiplier."""
    if hour < 9 or hour >= 21:
        return 0.3
    if 9 <= hour < 11:
        return 0.7
    if 11 <= hour < 16:
        return 1.15      # midday peak
    if 16 <= hour < 19:
        return 1.0
    return 0.7           # 19–21 wind-down


def weekend_multiplier(dt: datetime) -> float:
    """Iran weekend is lighter. Friday (weekday 4) ~0.5, Thursday (3) ~0.7, else 1.0."""
    wd = to_tehran(dt).weekday()  # Mon=0 … Sun=6
    if wd == 4:      # Friday
        return 0.5
    if wd == 3:      # Thursday
        return 0.7
    return 1.0


# ── gap (interval) computation — always randomized ───────────────────────────
def next_gap_minutes(mu: float = BASE_MU_MIN, sigma: float = BASE_SIGMA_MIN,
                     lo: float = GAP_MIN_MIN, hi: float = GAP_MAX_MIN,
                     rng: random.Random | None = None) -> float:
    """A single jittered gap in minutes: clamp(Normal(mu, sigma), lo, hi). Never constant."""
    r = rng or random
    return max(lo, min(hi, r.gauss(mu, sigma)))


def mu_for_target(daily_target: int, cfg=DEFAULT_WARMUP_CONFIG) -> float:
    """Shrink the mean gap so `daily_target` messages fit into the active-hours window.
    Larger targets → smaller mean gap, floored at GAP_MIN_FLOOR_MIN."""
    start = _parse_hhmm(cfg.active_hours_start)
    end = _parse_hhmm(cfg.active_hours_end)
    window_min = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
    window_min = min(window_min, cfg.max_active_hours_per_day * 60)
    if daily_target <= 0:
        return float(GAP_MAX_MIN)
    return max(float(GAP_MIN_FLOOR_MIN), window_min / daily_target)


def schedule_next_action(now: datetime, daily_target: int, cfg=DEFAULT_WARMUP_CONFIG,
                         rng: random.Random | None = None) -> datetime:
    """Compute the next action time from `now`: a jittered gap scaled to the day's target,
    circadian/weekend-adjusted, hard-floored at the 2/min gap, and deferred out of any
    inactive window. Returns a Tehran-aware datetime, always strictly after `now`."""
    r = rng or random
    local = to_tehran(now)
    mu = mu_for_target(daily_target, cfg)
    # Circadian/weekend stretch the mean gap when volume should be lower.
    mult = circadian_multiplier(local.hour) * weekend_multiplier(local)
    mult = max(0.2, mult)
    eff_mu = mu / mult
    gap = next_gap_minutes(mu=eff_mu, sigma=max(5.0, eff_mu * 0.3),
                           lo=GAP_MIN_FLOOR_MIN, hi=GAP_MAX_MIN, rng=r)
    nxt = local + timedelta(minutes=gap)
    # Enforce the 2/min hard floor.
    if (nxt - local).total_seconds() < HARD_MIN_GAP_SECONDS:
        nxt = local + timedelta(seconds=HARD_MIN_GAP_SECONDS)
    # Defer out of inactive windows with fresh jitter.
    if not in_active_hours(nxt, cfg):
        nxt = next_active_start(nxt, cfg, rng=r)
    return nxt


# ── day index + state advancement ────────────────────────────────────────────
def _naive(dt: datetime | None) -> datetime | None:
    """Drop tzinfo so aware/naive datetimes can be compared for a coarse day count."""
    return dt.replace(tzinfo=None) if (dt is not None and dt.tzinfo is not None) else dt


def day_index(enrollment, now: datetime | None = None) -> int:
    """1-based warm-up day since authorization (day 1 = first 24h). 0 if not started.
    Tolerant of mixed aware/naive datetimes (day granularity is coarse enough)."""
    anchor = getattr(enrollment, "authorized_at", None) or getattr(enrollment, "started_at", None)
    if not anchor:
        return 0
    now = now or datetime.utcnow()
    return max(1, (_naive(now) - _naive(anchor)).days + 1)


def _recovery_target_state_for_day(day: int) -> str:
    """V41 PART 1 — the state a RECOVERY-mode number should be in on `day` (day_index),
    following Green API's exact sequence. See the RECOVERY_* boundaries above."""
    if day <= 1:
        return WarmupState.COOLDOWN.value                    # GA Day 1 no-link + Day 2 authorize-only
    if day in RECOVERY_RECEIVING_DAYS:
        return WarmupState.RECEIVING.value                   # GA Days 3–5, receiving-only ~every 2h
    if day == RECOVERY_REPLY_START_DAY:
        return WarmupState.REPLYING.value                    # GA Day 6 — replies begin ~every 2h
    if RECOVERY_REPLY_START_DAY < day < RECOVERY_GRADUATE_DAY:
        return WarmupState.RAMPING.value                     # GA Days 7–12 — ramp 12→100
    return WarmupState.GRADUATED.value                       # day_index >= 12


def target_state_for_day(day: int, current: str, cfg=DEFAULT_WARMUP_CONFIG,
                         recovery: bool = False) -> str:
    """The state a number should be in on `day` given the schedule. Side states
    (PAUSED/YELLOWCARD/BLOCKED_RESET) are sticky — the scheduler never overrides them.
    `recovery=True` follows the V41 recovery-mode sequence instead of the general timeline."""
    if current in (WarmupState.PAUSED.value, WarmupState.YELLOWCARD.value,
                   WarmupState.BLOCKED_RESET.value):
        return current
    if recovery:
        return _recovery_target_state_for_day(day)
    if day <= 1:
        return WarmupState.COOLDOWN.value
    if day in cfg.receiving_days and day < cfg.reply_start_day:
        return WarmupState.RECEIVING.value           # days 2–3
    if day == cfg.reply_start_day:
        return WarmupState.REPLYING.value            # day 4 — replies begin
    if cfg.reply_start_day < day <= 10:
        return WarmupState.RAMPING.value             # days 5–10
    if 10 < day < 25:
        return WarmupState.MATURING.value            # days 11–24
    if day >= 25:
        return WarmupState.GRADUATED.value           # day 25+ clean → graduated
    return current


# ── daily targets per stage ──────────────────────────────────────────────────
def receiving_inbound_target(day: int) -> int:
    """Inbound messages the new number should RECEIVE on a RECEIVING day (D2≈6,D3≈8,D4≈10)."""
    return {2: 6, 3: 8, 4: 10}.get(day, 6)


def ramp_daily_target(day: int, cfg=DEFAULT_WARMUP_CONFIG) -> int:
    """Combined daily events on a RAMPING day, following the authoritative ramp_curve.
    Days 4→10 map to ramp_curve[0..6] (12 → 100)."""
    curve = cfg.ramp_curve
    idx = day - cfg.reply_start_day          # day 4 → 0
    idx = max(0, min(len(curve) - 1, idx))
    return curve[idx]


def maturing_daily_target(rng: random.Random | None = None) -> int:
    """MATURING band: ~80–120 mixed events/day with natural variation, no spikes."""
    r = rng or random
    return r.randint(80, 120)


def daily_target(enrollment, now: datetime | None = None, cfg=DEFAULT_WARMUP_CONFIG,
                 rng: random.Random | None = None) -> int:
    """Total warm-up events targeted for this number today, per its stage/day. A recovery-mode
    enrollment uses the recovery config (day-5 reply start → correct ramp indexing) and timeline."""
    recovery = recovery_enabled(enrollment)
    if recovery:
        cfg = RECOVERY_WARMUP_CONFIG
    day = day_index(enrollment, now)
    state = target_state_for_day(day, getattr(enrollment, "state", ""), cfg, recovery=recovery)
    if state == WarmupState.RECEIVING.value:
        return receiving_inbound_target(day)
    if state == WarmupState.REPLYING.value:
        return ramp_daily_target(day, cfg)
    if state == WarmupState.RAMPING.value:
        return ramp_daily_target(day, cfg)
    if state == WarmupState.MATURING.value:
        return maturing_daily_target(rng)
    if state == WarmupState.GRADUATED.value:
        return 0                                     # governed by real campaigns, not warm-up
    return 0                                          # COOLDOWN / side states → nothing


# ── reply-ratio guard (keep >= 0.50) ─────────────────────────────────────────
def allowed_outbound(received: int, min_ratio: float = 0.50) -> int:
    """Max outbound the new number may send given how many it has received, so that
    reply_ratio (received/sent) stays >= min_ratio. sent <= received / min_ratio.
    Always allows at least 1 so replying can start."""
    if min_ratio <= 0:
        return 10_000
    return max(1, int(received / min_ratio))


# ── per-tick send permission ─────────────────────────────────────────────────
def can_send_now(now: datetime, last_send_at: datetime | None, active_seconds_today: int,
                 cfg=DEFAULT_WARMUP_CONFIG) -> bool:
    """Enforce the two hard rate caps: >= 30s since the last send (2/min) AND under the
    daily active-hours budget. Active-hours check is the caller's (in_active_hours)."""
    if last_send_at is not None:
        if (now - last_send_at).total_seconds() < HARD_MIN_GAP_SECONDS:
            return False
    if active_seconds_today >= cfg.max_active_hours_per_day * 3600:
        return False
    return True


def read_delay_seconds(rng: random.Random | None = None) -> float:
    """Randomized delay before marking an inbound message read (human-like), 3–90s."""
    r = rng or random
    return r.uniform(3, 90)
