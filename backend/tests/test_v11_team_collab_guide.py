"""V11 — the numbers TEAM_COLLABORATION_ACTIVATION_7STEPS.md tells operators to rely on.

The 7-step activation guide quotes concrete, load-bearing constants: the 14-day sender rule,
the ceiling of 2 cold accounts per contact, the 10-day cycle with its 1/day → 2/day ramp, the
0–100 warmth formula and its «کم/متوسط/بالا» thresholds, and the soft-warning threshold of 30
that must never block. An operator plans a real 10-day run around those numbers.

This file pins them. If someone changes the ramp, the ceiling, the age rule or the scoring
weights, these tests fail and the guide gets corrected in the SAME commit instead of quietly
becoming wrong. Everything here is pure and `now`-injectable — no DB, no network.

Proves:
  • the sender gate is exactly >=14 days AND a clean 14-day incident window, and which incident
    types disqualify;
  • the cycle is exactly 10 days, day 0–1 → 1 step/day, day 2–9 → 2/day, day >=10 → 0;
  • `team_day_index` counts by Tehran calendar date and never goes negative;
  • warmth composes 50/30/20, the level cut-offs are 70/40, and a sender failing the binary gate
    can never reach «بالا»;
  • the soft warning is advisory only — it appears above the threshold and is absent at/below it.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services import warmup_helper_service as hs
from app.services import warmup_team_schedule as ts
from app.services.warmup_peer_eligibility import (
    MIN_PEER_AGE_DAYS,
    PEER_HISTORY_WINDOW_DAYS,
    DISQUALIFYING_INCIDENT_TYPES,
    evaluate_peer_eligibility,
    peer_age_days,
)
from app.services.warmup_warmth import (
    AGE_MAX,
    INCIDENT_MAX,
    ACTIVITY_MAX,
    LEVEL_HIGH_MIN,
    LEVEL_MID_MIN,
    LEVEL_HIGH_FA,
    LEVEL_MID_FA,
    LEVEL_LOW_FA,
    compute_warmth,
    level_for_score,
)

NOW = datetime(2026, 8, 1, 12, 0, 0)


def _acct(created_at=None, partner_created_at=None):
    return SimpleNamespace(created_at=created_at, partner_created_at=partner_created_at)


# ── Step 1 — the sender eligibility rule the guide states ─────────────────────
def test_guide_sender_rule_is_14_days_and_14_day_history():
    assert MIN_PEER_AGE_DAYS == 14
    assert PEER_HISTORY_WINDOW_DAYS == 14


def test_guide_lists_the_disqualifying_incident_types():
    # V65 — `suspended` joined the set. It is Green API's spam restriction and the strongest
    # signal a number has been flagged, but nothing counted it: on 2026-08-03 instance
    # 770022683838 was suspended for seven days and still scored warmth 80 «بالا» with a clean
    # 14-day window, so it stayed eligible to be picked for the next campaign.
    assert set(DISQUALIFYING_INCIDENT_TYPES) == {
        "yellowCard", "blocked", "notAuthorized", "logout", "suspended"
    }


@pytest.mark.parametrize("age_days,expected", [
    (0.0, "too_young"),
    (13.9, "too_young"),
    (14.0, "ok"),
    (30.0, "ok"),
])
def test_guide_age_boundary_is_inclusive_at_14_days(age_days, expected):
    acct = _acct(created_at=NOW - timedelta(days=age_days))
    eligible, reason, msg = evaluate_peer_eligibility(acct, None, 0, NOW)
    assert reason == expected
    assert eligible is (expected == "ok")
    # A rejection always carries a Persian explanation for the UI; an accept carries none.
    assert (msg is None) is (expected == "ok")


def test_guide_recent_incident_disqualifies_even_an_old_account():
    acct = _acct(created_at=NOW - timedelta(days=365))
    eligible, reason, msg = evaluate_peer_eligibility(acct, None, 1, NOW)
    assert (eligible, reason) == (False, "recent_incident")
    assert msg


def test_guide_unknown_connect_time_is_treated_as_too_young_not_as_eligible():
    # Fails safe: no trustworthy "connected since" must never read as an established sender.
    assert peer_age_days(_acct(), None, NOW) is None
    eligible, reason, _ = evaluate_peer_eligibility(_acct(), None, 0, NOW)
    assert (eligible, reason) == (False, "too_young")


# ── Step 4 — the ceiling the guide promises ───────────────────────────────────
def test_guide_ceiling_is_two_cold_accounts_per_contact():
    assert hs.MAX_COLD_ACCOUNTS_PER_CONTACT == 2


# ── Step 6 — the 10-day cycle and its ramp ────────────────────────────────────
def test_guide_cycle_is_ten_days():
    assert ts.TEAM_CYCLE_DAYS == 10


@pytest.mark.parametrize("day,budget", [
    (0, 1), (1, 1),                             # conservative start
    (2, 2), (5, 2), (9, 2),                     # steady state
    (10, 0), (11, 0), (13, 0), (99, 0),         # past the window: cycle complete
])
def test_guide_daily_step_budget_ramp(day, budget):
    assert ts.daily_step_budget(day) == budget


def test_guide_budget_drops_to_zero_exactly_at_the_cycle_boundary():
    assert ts.daily_step_budget(ts.TEAM_CYCLE_DAYS - 1) == 2
    assert ts.daily_step_budget(ts.TEAM_CYCLE_DAYS) == 0


def test_guide_day_index_counts_calendar_days_and_floors_at_zero():
    enrolled = datetime(2026, 7, 20, 8, 0, 0)
    assert ts.team_day_index(enrolled, enrolled) == 0
    assert ts.team_day_index(enrolled, enrolled + timedelta(days=1)) == 1
    assert ts.team_day_index(enrolled, enrolled + timedelta(days=13)) == 13
    # A clock skew backwards must never produce a negative day index.
    assert ts.team_day_index(enrolled, enrolled - timedelta(days=3)) == 0
    # An unknown enrollment time reads as day 0, not as "cycle complete".
    assert ts.team_day_index(None, NOW) == 0


# ── Step 1 — the warmth score the guide explains ──────────────────────────────
def test_guide_warmth_components_sum_to_100():
    assert (AGE_MAX, INCIDENT_MAX, ACTIVITY_MAX) == (50, 30, 20)
    assert AGE_MAX + INCIDENT_MAX + ACTIVITY_MAX == 100


def test_guide_warmth_level_thresholds():
    assert (LEVEL_HIGH_MIN, LEVEL_MID_MIN) == (70, 40)
    assert level_for_score(70) == LEVEL_HIGH_FA
    assert level_for_score(69) == LEVEL_MID_FA
    assert level_for_score(40) == LEVEL_MID_FA
    assert level_for_score(39) == LEVEL_LOW_FA


def test_guide_perfect_sender_scores_100_high():
    out = compute_warmth(age_days=30, recent_incident_count=0,
                         days_since_activity=1, eligible=True)
    assert out["score"] == 100
    assert out["level"] == LEVEL_HIGH_FA
    assert out["components"] == {"age": 50, "incident_free": 30, "activity": 20}


def test_guide_any_incident_zeroes_the_incident_component():
    out = compute_warmth(age_days=30, recent_incident_count=1,
                         days_since_activity=1, eligible=False)
    assert out["components"]["incident_free"] == 0


@pytest.mark.parametrize("days_since,expected", [
    (0, 20), (7, 20),          # fresh
    (8, 10), (14, 10),         # ok
    (15, 0), (90, 0),          # stale
    (None, 0),                 # unknown
])
def test_guide_activity_component_windows(days_since, expected):
    out = compute_warmth(age_days=30, recent_incident_count=0,
                         days_since_activity=days_since, eligible=True)
    assert out["components"]["activity"] == expected


def test_guide_ineligible_sender_can_never_reach_high():
    """«بالا» must imply the account already passes the binary 14-day gate."""
    out = compute_warmth(age_days=30, recent_incident_count=0,
                         days_since_activity=0, eligible=False)
    assert out["score"] == LEVEL_HIGH_MIN - 1 == 69
    assert out["level"] == LEVEL_MID_FA


def test_guide_age_component_saturates_at_the_14_day_floor():
    assert compute_warmth(age_days=MIN_PEER_AGE_DAYS, recent_incident_count=0,
                          days_since_activity=None)["components"]["age"] == AGE_MAX
    assert compute_warmth(age_days=MIN_PEER_AGE_DAYS * 10, recent_incident_count=0,
                          days_since_activity=None)["components"]["age"] == AGE_MAX
    assert compute_warmth(age_days=0, recent_incident_count=0,
                          days_since_activity=None)["components"]["age"] == 0


def test_guide_score_is_always_within_0_100():
    for age in (None, 0, 7, 14, 1000):
        for inc in (0, 1, 5):
            for act in (None, 0, 7, 14, 100):
                s = compute_warmth(age_days=age, recent_incident_count=inc,
                                   days_since_activity=act)["score"]
                assert 0 <= s <= 100


# ── Step 2 — the soft warning is advisory, never a block ──────────────────────
def test_guide_soft_warning_threshold_default_is_30():
    assert hs.DEFAULT_SOFT_WARNING_THRESHOLD == 30


def test_guide_soft_warning_appears_only_above_the_threshold():
    assert hs.soft_warning_notice(29, 30) is None
    assert hs.soft_warning_notice(30, 30) is None      # at the threshold: still silent
    banner = hs.soft_warning_notice(31, 30)
    assert isinstance(banner, str) and banner.strip()  # above it: a Persian banner appears
