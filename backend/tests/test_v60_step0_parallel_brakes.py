"""V60 STEP 0 — the parallel campaign path must honour the SAME brakes as the sequential one.

`run_campaign_parallel` used to go straight from "here are the account ids" to
asyncio.gather(_send_chunk(...)). It applied none of the pre-flight brakes that
`_run_campaign_inner` applies, so switching a campaign to `parallel_accounts=true` silently
turned OFF four of them:

  • the single-run lock (two concurrent runs could double-send)
  • the scheduled date window (schedule_start / schedule_end ignored)
  • the send-hour window (08:00–22:00 Tehran ignored)
  • the drip daily quota (drip_per_day ignored)
  • the fail-closed account selection / FanOutGuard
  • the young-account new-contact cap (<10 days → 20 new contacts/day)

Turning ON multi-account sending must never turn OFF a brake. These tests pin the shared
decisions in campaign_preflight and the wiring in campaign_runner.
"""
import inspect
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services import campaign_preflight as pf
from app.services import campaign_runner as cr

NOW = datetime(2026, 8, 2, 12, 0)


# ── scheduled date window ────────────────────────────────────────────────────
def test_no_window_configured_runs():
    assert pf.check_schedule_window(None, None, NOW) == (pf.SCHEDULE_OK, 0)


def test_past_schedule_end_completes():
    decision, wait = pf.check_schedule_window(None, NOW - timedelta(hours=1), NOW)
    assert decision == pf.SCHEDULE_COMPLETE and wait == 0


def test_before_schedule_start_parks_with_a_positive_wait():
    start = NOW + timedelta(hours=3)
    decision, wait = pf.check_schedule_window(start, None, NOW)
    assert decision == pf.SCHEDULE_PARK
    assert wait == pytest.approx(3 * 3600, abs=2)


def test_inside_the_window_runs():
    decision, _ = pf.check_schedule_window(
        NOW - timedelta(days=1), NOW + timedelta(days=1), NOW)
    assert decision == pf.SCHEDULE_OK


def test_park_wait_is_never_zero_or_negative():
    """A zero countdown would busy-loop the broker."""
    _, wait = pf.check_schedule_window(NOW + timedelta(microseconds=1), None, NOW)
    assert wait >= 1


# ── drip quota ───────────────────────────────────────────────────────────────
def test_drip_off_returns_none_not_zero():
    """None means 'no campaign-level cap'. Reading it as 0 would stop every send."""
    assert pf.drip_remaining(False, 50, 0) is None
    assert pf.drip_remaining(False, None, 999) is None


def test_drip_remaining_counts_down():
    assert pf.drip_remaining(True, 50, 0) == 50
    assert pf.drip_remaining(True, 50, 20) == 30
    assert pf.drip_remaining(True, 50, 50) == 0


def test_drip_never_goes_negative():
    assert pf.drip_remaining(True, 10, 99) == 0


def test_drip_defaults_to_50_when_unset():
    assert pf.drip_remaining(True, None, 0) == 50


# ── send-hour window ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_hour_window_open_when_any_account_can_send(monkeypatch):
    async def caps(aid):
        return 0 if aid.endswith("A") else 30

    monkeypatch.setattr("app.services.rate_limiter.get_max_per_hour_for_account", caps)
    accounts = [SimpleNamespace(id="acc-A"), SimpleNamespace(id="acc-B")]
    assert await pf.hour_window_wait_seconds(accounts) == 0


@pytest.mark.asyncio
async def test_hour_window_returns_the_earliest_reopen(monkeypatch):
    async def caps(_aid):
        return 0

    async def waits(aid):
        return 7200 if aid.endswith("A") else 1800

    monkeypatch.setattr("app.services.rate_limiter.get_max_per_hour_for_account", caps)
    monkeypatch.setattr("app.services.rate_limiter.seconds_until_account_window", waits)
    accounts = [SimpleNamespace(id="acc-A"), SimpleNamespace(id="acc-B")]
    assert await pf.hour_window_wait_seconds(accounts) == 1800


@pytest.mark.asyncio
async def test_hour_window_falls_back_to_an_hour_when_nothing_reopens(monkeypatch):
    async def caps(_aid):
        return 0

    async def waits(_aid):
        return 0

    monkeypatch.setattr("app.services.rate_limiter.get_max_per_hour_for_account", caps)
    monkeypatch.setattr("app.services.rate_limiter.seconds_until_account_window", waits)
    assert await pf.hour_window_wait_seconds([SimpleNamespace(id="a")]) == 3600


# ── young-account new-contact cap ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_existing_contact_is_never_new_contact_capped(monkeypatch):
    async def never(*_a, **_k):
        raise AssertionError("the cap must not be consulted for an existing contact")

    monkeypatch.setattr("app.services.governors.warmup_new_contact_allowed", never)
    contact = SimpleNamespace(first_messaged_at=NOW)
    assert await pf.new_contact_allowed(SimpleNamespace(id="a", days_active=1), contact) is True


@pytest.mark.asyncio
async def test_new_contact_defers_to_the_governor(monkeypatch):
    calls = []

    async def gov(account_id, days):
        calls.append((account_id, days))
        return False

    monkeypatch.setattr("app.services.governors.warmup_new_contact_allowed", gov)
    contact = SimpleNamespace(first_messaged_at=None)
    account = SimpleNamespace(id="acc-1", days_active=3)
    assert await pf.new_contact_allowed(account, contact) is False
    assert calls == [("acc-1", 3)]


# ── the wiring: the parallel path really uses them ──────────────────────────
def test_parallel_path_takes_the_single_run_lock():
    src = inspect.getsource(cr.run_campaign_parallel)
    assert "campaign_lock:" in src
    assert "nx=True" in src


def test_parallel_path_checks_schedule_hour_window_and_drip():
    src = inspect.getsource(cr._run_campaign_parallel_inner)
    assert "check_schedule_window" in src
    assert "hour_window_wait_seconds" in src
    assert "drip_remaining" in src


def test_parallel_path_applies_the_fanout_guard():
    src = inspect.getsource(cr._run_campaign_parallel_inner)
    assert "resolve_sending_accounts" in src


def test_parallel_path_sends_only_to_resolved_accounts():
    """The round-robin must key off the GUARD's output, not the raw caller list."""
    src = inspect.getsource(cr._run_campaign_parallel_inner)
    assert "allowed_ids" in src
    assert "allowed_ids[i % len(allowed_ids)]" in src


def test_chunk_enforces_new_contact_cap_and_drip_share():
    src = inspect.getsource(cr._send_chunk)
    assert "new_contact_allowed" in src
    assert "drip_quota" in src


def test_every_brake_parks_the_campaign_rather_than_completing_it():
    """The B-2 hazard, pinned for the parallel path.

    A brake must leave the campaign RESUMABLE (`paused` + a reason), never `completed` —
    otherwise a temporary condition (outside the hour window, drip quota spent, an unhealthy
    account) would permanently retire a campaign that still has contacts to reach.

    Two `completed` transitions are legitimate and expected:
      1. inside the SCHEDULE_COMPLETE branch — now is past schedule_end, it really is over;
      2. the end-of-run check — no pending contacts remain, so the work is genuinely done.
    Anything else setting `completed` would be a bug.
    """
    src = inspect.getsource(cr._run_campaign_parallel_inner)

    # every brake pauses
    for brake in ("SCHEDULE_PARK", "WINDOW_WAIT_REASON", "PAUSE_REASON", "abort_reason"):
        assert brake in src, f"{brake} brake missing from the parallel path"
    assert src.count("CampaignStatus.paused") >= 4

    # `completed` appears exactly twice, and the FIRST one is the schedule-end branch
    assert src.count("CampaignStatus.completed") == 2
    first_completed = src.index("CampaignStatus.completed")
    schedule_branch = src.index("SCHEDULE_COMPLETE")
    assert abs(first_completed - schedule_branch) < 300

    # the second one is guarded by "no pending contacts remain"
    tail = src[first_completed + 1:]
    second_completed = tail.index("CampaignStatus.completed")
    assert "remaining.scalars().first()" in tail[:second_completed]


def test_the_window_and_drip_brakes_reschedule_or_wait_for_the_daily_beat():
    """A parked campaign must have a way back: the window brake re-queues itself."""
    src = inspect.getsource(cr._run_campaign_parallel_inner)
    # the SETTING of the reason (the brake), not the auto-resume comparison above it
    window_at = src.index("pause_reason = WINDOW_WAIT_REASON")
    assert "_reschedule(" in src[window_at:window_at + 400]


def test_reschedule_preserves_the_account_list():
    """Re-queuing must keep the SAME accounts, or a parked parallel run would silently
    resume as an all-accounts run — re-opening the fan-out hole this step closes."""
    src = inspect.getsource(cr._reschedule)
    assert "list(account_ids)" in src
