"""V17 PART 2 — warm-up state machine + mesh schema.

Covers: legal/illegal state transitions, side-state interruption + resume, the exact
shipped config defaults, daily-counter reset at Tehran-local midnight, and reply_ratio.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest
import pytz

from app.services.warmup_state import (
    WarmupState, HandshakeState, ALLOWED_TRANSITIONS, FLOW_ORDER,
    can_transition, transition, IllegalTransition,
    WarmupConfig, DEFAULT_WARMUP_CONFIG, load_config,
    reset_daily_counters_if_new_day, compute_reply_ratio,
)


def _enr(**kw):
    base = dict(state="ENROLLED", sent_today=0, received_today=0,
                counters_date=None, updated_at=None)
    base.update(kw)
    return SimpleNamespace(**base)


# ── happy-path flow transitions ─────────────────────────────────────────────
def test_full_forward_flow_is_legal():
    for a, b in zip(FLOW_ORDER, FLOW_ORDER[1:]):
        assert can_transition(a, b), f"{a} → {b} should be legal"


def test_cannot_skip_stages():
    assert not can_transition(WarmupState.ENROLLED, WarmupState.RECEIVING)
    assert not can_transition(WarmupState.COOLDOWN, WarmupState.REPLYING)
    assert not can_transition(WarmupState.RECEIVING, WarmupState.GRADUATED)


def test_cannot_go_backwards_in_flow():
    assert not can_transition(WarmupState.REPLYING, WarmupState.RECEIVING)
    assert not can_transition(WarmupState.GRADUATED, WarmupState.RAMPING)


def test_transition_mutates_and_stamps():
    e = _enr(state="COOLDOWN")
    now = datetime(2026, 1, 1, 12, 0, 0)
    transition(e, WarmupState.RECEIVING, now=now)
    assert e.state == "RECEIVING"
    assert e.updated_at == now


def test_illegal_transition_raises_and_leaves_state():
    e = _enr(state="ENROLLED")
    with pytest.raises(IllegalTransition):
        transition(e, WarmupState.GRADUATED)
    assert e.state == "ENROLLED"  # unchanged


def test_same_state_is_idempotent():
    assert can_transition(WarmupState.RECEIVING, WarmupState.RECEIVING)
    e = _enr(state="RECEIVING")
    transition(e, "RECEIVING")
    assert e.state == "RECEIVING"


# ── side states: pause / yellowCard / blocked-reset ─────────────────────────
def test_any_live_state_can_pause_and_card_and_reset():
    for s in (WarmupState.RECEIVING, WarmupState.REPLYING, WarmupState.RAMPING,
              WarmupState.MATURING, WarmupState.GRADUATED):
        assert can_transition(s, WarmupState.PAUSED)
        assert can_transition(s, WarmupState.YELLOWCARD)
        assert can_transition(s, WarmupState.BLOCKED_RESET)


def test_paused_can_resume_to_any_flow_stage():
    for s in FLOW_ORDER:
        assert can_transition(WarmupState.PAUSED, s)


def test_yellowcard_rests_then_resumes():
    assert can_transition(WarmupState.YELLOWCARD, WarmupState.PAUSED)
    assert can_transition(WarmupState.YELLOWCARD, WarmupState.REPLYING)
    # cannot jump straight back to ENROLLED from a yellowCard
    assert not can_transition(WarmupState.YELLOWCARD, WarmupState.ENROLLED)


def test_blocked_reset_restarts_from_beginning():
    assert can_transition(WarmupState.BLOCKED_RESET, WarmupState.ENROLLED)
    assert can_transition(WarmupState.BLOCKED_RESET, WarmupState.COOLDOWN)
    # a block resets warm-up — it must NOT resume mid-flow
    assert not can_transition(WarmupState.BLOCKED_RESET, WarmupState.RAMPING)


def test_handshake_states_exist():
    assert HandshakeState.NONE.value == "none"
    assert HandshakeState.CONTACT_SAVED.value == "contact_saved"
    assert HandshakeState.ACTIVE.value == "active"


# ── config defaults: the EXACT shipped values ───────────────────────────────
def test_config_defaults_are_exact():
    c = DEFAULT_WARMUP_CONFIG
    assert c.cooldown_hours == 24
    assert c.receiving_days == [2, 3, 4]
    assert c.reply_start_day == 4
    assert c.ramp_curve == [12, 20, 32, 48, 66, 84, 100]
    assert c.daily_campaign_cap == 200
    assert c.new_contacts_per_day_cap == 20
    assert c.min_reply_ratio == 0.50
    assert c.peers_per_new_number_min == 3
    assert c.peers_per_new_number_max == 6
    assert c.keepwarm_max_idle_days == 10
    assert c.max_msgs_per_minute == 2
    assert c.max_active_hours_per_day == 6
    assert c.active_hours_start == "09:00"
    assert c.active_hours_end == "21:00"
    assert c.timezone == "Asia/Tehran"
    assert c.queue_delay_ms == 15000
    assert c.auto_typing == 2


def test_ramp_curve_reaches_100_over_seven_steps():
    curve = DEFAULT_WARMUP_CONFIG.ramp_curve
    assert curve[0] == 12 and curve[-1] == 100 and len(curve) == 7
    # authoritative 12→100 curve, strictly increasing (the ≤1.5×/day step constraint
    # is enforced on actual daily counts in PART 4, not on this fixed seed curve)
    for a, b in zip(curve, curve[1:]):
        assert b > a


def test_load_config_merges_overrides():
    c = load_config({"cooldown_hours": 12, "auto_typing": 3, "unknown_key": 999})
    assert c.cooldown_hours == 12
    assert c.auto_typing == 3
    assert c.daily_campaign_cap == 200  # untouched default
    assert not hasattr(c, "unknown_key")


def test_load_config_none_returns_defaults():
    assert load_config(None).to_dict() == WarmupConfig().to_dict()


# ── daily-counter reset at Tehran-local midnight ────────────────────────────
def test_counter_reset_on_new_local_day():
    tz = pytz.timezone("Asia/Tehran")
    e = _enr(sent_today=8, received_today=6, counters_date=None)
    # First call on a given day stamps the date and (since it differs) resets.
    day1 = tz.localize(datetime(2026, 3, 20, 10, 0, 0))
    assert reset_daily_counters_if_new_day(e, now=day1) is True
    assert e.sent_today == 0 and e.received_today == 0
    assert e.counters_date == datetime(2026, 3, 20).date()


def test_counter_no_reset_same_local_day():
    tz = pytz.timezone("Asia/Tehran")
    e = _enr(sent_today=0, received_today=0, counters_date=datetime(2026, 3, 20).date())
    same_day_later = tz.localize(datetime(2026, 3, 20, 20, 0, 0))
    e.sent_today = 5
    assert reset_daily_counters_if_new_day(e, now=same_day_later) is False
    assert e.sent_today == 5  # not wiped mid-day


def test_counter_reset_across_midnight():
    tz = pytz.timezone("Asia/Tehran")
    e = _enr(sent_today=12, received_today=10, counters_date=datetime(2026, 3, 20).date())
    next_day = tz.localize(datetime(2026, 3, 21, 0, 5, 0))
    assert reset_daily_counters_if_new_day(e, now=next_day) is True
    assert e.sent_today == 0 and e.counters_date == datetime(2026, 3, 21).date()


# ── reply ratio ─────────────────────────────────────────────────────────────
def test_reply_ratio_basic():
    assert compute_reply_ratio(100, 50) == 0.5
    assert compute_reply_ratio(10, 10) == 1.0
    assert compute_reply_ratio(0, 0) == 0.0     # nothing sent → 0
    assert compute_reply_ratio(0, 5) == 0.0     # guard divide-by-zero
    assert compute_reply_ratio(4, 3) == 0.75
