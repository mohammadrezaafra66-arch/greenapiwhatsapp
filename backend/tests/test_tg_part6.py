"""TG PART 6 — Telegram-specific anti-ban warm-up + breaker.

Proves:
  • the fixed Telegram warm-up schedule is DISTINCT from WhatsApp's (separate constants);
  • stages gate non-contact outbound in the first 48h, then contacts-only to day 7, then ramp;
  • the circuit breaker counts DISTINCT Telegram instances only — a WhatsApp incident never
    trips it and vice-versa;
  • the 48h gate helper (shared with PART 3) blocks strangers, allows contacts.
"""
import pytest
from datetime import datetime, timedelta

from app.services import telegram_warmup as tw
from app.services.telegram_send import telegram_can_send_to
from app.services.warmup_state import WarmupState, DEFAULT_WARMUP_CONFIG


NOW = datetime(2026, 7, 17, 12, 0)


def _auth(hours_ago):
    return NOW - timedelta(hours=hours_ago)


# ── config distinctness ──────────────────────────────────────────────────────
def test_telegram_config_differs_from_whatsapp():
    tg = tw.DEFAULT_TELEGRAM_WARMUP_CONFIG
    # Telegram uses 10–15s pacing; WhatsApp's warm-up config has none of these fields the same.
    assert (tg.min_delay_seconds, tg.max_delay_seconds) == (10, 15)
    # WhatsApp warm-up ramps on a different curve and cooldown model.
    assert tg.ramp_daily_caps != DEFAULT_WARMUP_CONFIG.ramp_curve
    assert tg.no_noncontact_gate_hours == 48
    # WhatsApp cooldown is 24h, Telegram non-contact gate is 48h — genuinely different.
    assert tg.no_noncontact_gate_hours != DEFAULT_WARMUP_CONFIG.cooldown_hours


# ── warm-up stage schedule ───────────────────────────────────────────────────
def test_first_48h_blocks_noncontact_outbound():
    s = tw.warmup_stage(_auth(10), NOW)
    assert s["stage"] == WarmupState.COOLDOWN.value
    assert s["daily_cap"] == 0 and s["allow_noncontact_outbound"] is False
    assert s["contacts_only"] is True


def test_days_3_to_7_contacts_only_low_volume():
    s = tw.warmup_stage(_auth(24 * 4), NOW)   # day 4
    assert s["stage"] == WarmupState.REPLYING.value
    assert s["daily_cap"] == 5 and s["allow_noncontact_outbound"] is False
    assert s["contacts_only"] is True


def test_day_7_plus_ramps_and_allows_noncontact():
    s = tw.warmup_stage(_auth(24 * 10), NOW)   # day 10
    assert s["stage"] == WarmupState.RAMPING.value
    assert s["allow_noncontact_outbound"] is True and s["daily_cap"] >= 5


def test_graduation_after_30_days():
    s = tw.warmup_stage(_auth(24 * 40), NOW)
    assert s["stage"] == WarmupState.GRADUATED.value
    assert s["daily_cap"] == tw.DEFAULT_TELEGRAM_WARMUP_CONFIG.ramp_daily_caps[3]


def test_ramp_is_monotonic_nondecreasing():
    caps = [tw.warmup_stage(_auth(24 * d), NOW)["daily_cap"] for d in (3, 8, 16, 25, 40)]
    assert caps == sorted(caps)


# ── circuit breaker — Telegram-only ──────────────────────────────────────────
def _ev(platform, iid, state, hours_ago=1):
    return {"platform": platform, "instance_id": iid, "state": state,
            "created_at": NOW - timedelta(hours=hours_ago)}


def test_breaker_counts_distinct_telegram_only():
    events = [
        _ev("telegram", "4100", "suspended"),
        _ev("telegram", "4100", "suspended"),   # same instance → still 1
        _ev("telegram", "4200", "blocked"),
        _ev("whatsapp", "7105", "blocked"),     # WhatsApp — MUST be ignored
    ]
    offenders = tw.distinct_telegram_offenders(events, NOW)
    assert offenders == {"4100", "4200"}
    assert tw.should_trip_telegram_breaker(len(offenders)) is True


def test_whatsapp_incident_never_trips_telegram_breaker():
    events = [_ev("whatsapp", "7105", "blocked"), _ev("whatsapp", "7106", "blocked")]
    offenders = tw.distinct_telegram_offenders(events, NOW)
    assert offenders == set()
    assert tw.should_trip_telegram_breaker(len(offenders)) is False


def test_single_telegram_offender_does_not_trip():
    events = [_ev("telegram", "4100", "suspended")]
    assert tw.should_trip_telegram_breaker(len(tw.distinct_telegram_offenders(events, NOW))) is False


def test_events_outside_window_excluded():
    events = [_ev("telegram", "4100", "suspended", hours_ago=100),
              _ev("telegram", "4200", "blocked", hours_ago=1)]
    assert tw.distinct_telegram_offenders(events, NOW) == {"4200"}


# ── shared 48h gate (PART 3/6) ───────────────────────────────────────────────
def test_gate_blocks_stranger_allows_contact():
    assert telegram_can_send_to(_auth(10), is_existing_contact=False, now=NOW) is False
    assert telegram_can_send_to(_auth(10), is_existing_contact=True, now=NOW) is True
    assert telegram_can_send_to(_auth(49), is_existing_contact=False, now=NOW) is True
