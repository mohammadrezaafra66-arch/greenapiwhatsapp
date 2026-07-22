"""V41 PART 2 — restart-on-disruption guard for recovery-mode enrollments.

Proves Green API's "if anything changes, start over from Day 1" rule is ENFORCED, not left to
someone remembering to check:
  • a recovery-mode enrollment mid-cycle (day 5) that hits a fresh disconnect / card / relink is
    reset to day_index 0 / COOLDOWN, the reset is COUNTED and LOGGED (reason + timestamp), and it
    still feeds the mesh-wide chain-ban breaker for real card/block signals;
  • a genuine mid-cycle reconnect resets it; the expected first authorize (initial cooldown) and a
    heartbeat 'authorized' do NOT;
  • an undisrupted recovery enrollment progresses normally through its days;
  • a NON-recovery enrollment's existing kill-switch behavior is unchanged (regression).
"""
import uuid
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest

from app.models.warmup_mesh import WarmupEnrollment, WarmupEventLog
from app.services import warmup_killswitch as ks
from app.services.warmup_killswitch import (
    recovery_disruption_reason, recovery_disruption_reset, _mid_recovery_cycle,
    handle_warmup_state_signal,
)
from app.services.warmup_engine import _advance_state
from app.services.warmup_state import WarmupState


# ── FakeSession (same shape as test_v17_part5) ───────────────────────────────
class FakeScalars:
    def __init__(self, items): self._items = list(items)
    def all(self): return list(self._items)


class FakeResult:
    def __init__(self, scalars=None, scalar=None):
        self._scalars = scalars if scalars is not None else []
        self._scalar = scalar
    def scalars(self): return FakeScalars(self._scalars)
    def scalar_one_or_none(self): return self._scalars[0] if self._scalars else None
    def scalar(self): return self._scalar


class FakeSession:
    def __init__(self, results=None):
        self._results = list(results or [])
        self.added = []
        self.commits = 0
    async def execute(self, query):
        return self._results.pop(0) if self._results else FakeResult()
    def add(self, obj): self.added.append(obj)
    async def commit(self): self.commits += 1


NOW = datetime(2026, 7, 22, 12, 0, 0)


def _recovery_enr(day=5, state=WarmupState.RAMPING.value, **kw):
    """A recovery-mode enrollment whose computed day_index == `day`."""
    base = dict(
        instance_id="7105325764", state=state, is_enabled=True, recovery_mode=True,
        sent_today=7, received_today=6, reply_ratio=0.85, rest_until=None, day_index=day,
        authorized_at=NOW - timedelta(days=day - 1), started_at=NOW - timedelta(days=day - 1),
        last_activity_at=NOW, next_action_at=None,
        recovery_reset_count=0, recovery_last_reset_at=None, recovery_last_reset_reason=None,
    )
    base.update(kw)
    e = SimpleNamespace(**base)
    e.id = kw.get("id", uuid.uuid4())
    return e


def _events(db, event_type):
    return [a for a in db.added if getattr(a, "event_type", None) == event_type]


# ── pure mapping ─────────────────────────────────────────────────────────────
def test_recovery_disruption_reason_mapping():
    assert recovery_disruption_reason("yellowCard") == "yellowCard"
    assert recovery_disruption_reason("blocked") == "blocked"
    assert recovery_disruption_reason("notAuthorized") == "notAuthorized"
    assert recovery_disruption_reason("logout") == "logout"
    # not disruptive
    assert recovery_disruption_reason("authorized") is None
    assert recovery_disruption_reason("starting") is None
    assert recovery_disruption_reason("") is None


def test_mid_recovery_cycle_boundary():
    assert _mid_recovery_cycle(_recovery_enr(day=1), NOW) is False   # initial cooldown
    assert _mid_recovery_cycle(_recovery_enr(day=2), NOW) is True    # receiving onward
    assert _mid_recovery_cycle(_recovery_enr(day=5), NOW) is True


# ── the reset itself ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_recovery_disruption_reset_returns_to_day1_and_counts():
    db = FakeSession()
    e = _recovery_enr(day=5, state=WarmupState.RAMPING.value, recovery_reset_count=1)
    res = await recovery_disruption_reset(db, e, "yellowCard", NOW)
    # Back to Day 1.
    assert e.state == WarmupState.COOLDOWN.value
    assert e.day_index == 0
    assert e.authorized_at == NOW and e.started_at == NOW
    assert e.sent_today == 0 and e.received_today == 0 and e.reply_ratio == 0.0
    assert e.rest_until is None
    assert e.next_action_at == NOW + timedelta(hours=24)
    # Counted + reason/time recorded.
    assert e.recovery_reset_count == 2
    assert e.recovery_last_reset_at == NOW
    assert e.recovery_last_reset_reason == "yellowCard"
    assert res["reset_count"] == 2 and res["reason"] == "yellowCard"
    # Durably logged (reason + timestamp) and surfaced as an alert.
    logs = _events(db, "recovery_reset")
    assert len(logs) == 1
    payload = json.loads(logs[0].payload_json)
    assert payload["reason"] == "yellowCard" and payload["reset_count"] == 2
    assert payload["at"] == NOW.isoformat() and payload["from"] == WarmupState.RAMPING.value
    assert len(_events(db, "alert")) == 1


@pytest.mark.asyncio
async def test_reset_is_enabled_stays_true():
    db = FakeSession()
    e = _recovery_enr(day=6)
    await recovery_disruption_reset(db, e, "notAuthorized", NOW)
    assert e.is_enabled is True          # still warming, just from Day 1 again
    assert e.recovery_mode is True       # stays a recovery enrollment


# ── routed through the webhook signal handler ────────────────────────────────
@pytest.mark.asyncio
async def test_signal_yellowcard_resets_recovery_instead_of_resting():
    e = _recovery_enr(day=5, state=WarmupState.RAMPING.value)
    db = FakeSession(results=[FakeResult(scalars=[e]), FakeResult(scalars=[])])
    res = await handle_warmup_state_signal(db, e.instance_id, "yellowCard", NOW)
    assert res["action"] == "recovery_reset"
    # NOT the general YELLOWCARD/rest path.
    assert e.state == WarmupState.COOLDOWN.value
    assert e.day_index == 0
    assert e.recovery_reset_count == 1
    # Real card signal still records an incident for the mesh-wide breaker.
    assert _events(db, "incident")


@pytest.mark.asyncio
async def test_signal_notauthorized_resets_recovery():
    e = _recovery_enr(day=4, state=WarmupState.RECEIVING.value)
    db = FakeSession(results=[FakeResult(scalars=[e]), FakeResult(scalars=[])])
    res = await handle_warmup_state_signal(db, e.instance_id, "notAuthorized", NOW)
    assert res["action"] == "recovery_reset"
    assert e.state == WarmupState.COOLDOWN.value and e.day_index == 0
    assert e.recovery_last_reset_reason == "notAuthorized"


@pytest.mark.asyncio
async def test_signal_genuine_reconnect_midcycle_resets():
    e = _recovery_enr(day=5, state=WarmupState.RAMPING.value)
    db = FakeSession(results=[FakeResult(scalars=[e])])
    res = await handle_warmup_state_signal(db, e.instance_id, "authorized", NOW,
                                           genuine_reconnect=True)
    assert res["action"] == "recovery_reset"
    assert e.recovery_last_reset_reason == "reconnect"
    # A pure relink is not a card/block → no incident recorded.
    assert not _events(db, "incident")


@pytest.mark.asyncio
async def test_signal_expected_first_authorize_does_not_reset():
    # Genuine authorize during the initial cooldown (day 1) is Green API's expected Day-2
    # authorization, not a disruption.
    e = _recovery_enr(day=1, state=WarmupState.COOLDOWN.value)
    db = FakeSession(results=[FakeResult(scalars=[e])])
    res = await handle_warmup_state_signal(db, e.instance_id, "authorized", NOW,
                                           genuine_reconnect=True)
    assert res is None
    assert e.recovery_reset_count == 0 and e.state == WarmupState.COOLDOWN.value


@pytest.mark.asyncio
async def test_signal_authorized_heartbeat_never_resets():
    # A repeated 'authorized' heartbeat (not a genuine transition) must never reset a healthy cycle.
    e = _recovery_enr(day=6, state=WarmupState.RAMPING.value)
    db = FakeSession(results=[FakeResult(scalars=[e])])
    res = await handle_warmup_state_signal(db, e.instance_id, "authorized", NOW,
                                           genuine_reconnect=False)
    assert res is None
    assert e.recovery_reset_count == 0
    assert e.state == WarmupState.RAMPING.value and e.day_index == 6


# ── undisrupted recovery enrollment progresses normally ──────────────────────
@pytest.mark.asyncio
async def test_undisrupted_recovery_progresses_through_days():
    e = _recovery_enr(day=1, state=WarmupState.COOLDOWN.value)
    # No disruption signal — advance the state machine day by day.
    seq = {}
    for day in (1, 2, 5, 6, 12):
        e.authorized_at = NOW - timedelta(days=day - 1)
        e.counters_date = None  # allow counter reset
        await _advance_state(FakeSession(), e, NOW, cfg=None)
        seq[day] = e.state
    assert seq[1] == WarmupState.COOLDOWN.value
    assert seq[2] == WarmupState.RECEIVING.value
    assert seq[5] == WarmupState.REPLYING.value
    assert seq[6] == WarmupState.RAMPING.value
    assert seq[12] == WarmupState.GRADUATED.value
    assert e.recovery_reset_count == 0    # never reset without a disruption


# ── regression: NON-recovery kill-switch behavior unchanged ──────────────────
@pytest.mark.asyncio
async def test_non_recovery_yellowcard_still_rests_not_resets():
    e = _recovery_enr(day=5, state=WarmupState.RAMPING.value, recovery_mode=False)
    db = FakeSession(results=[FakeResult(scalars=[e]), FakeResult(scalars=[])])
    res = await handle_warmup_state_signal(db, e.instance_id, "yellowCard", NOW)
    assert res["action"] == "yellowCard"
    assert e.state == WarmupState.YELLOWCARD.value     # general path: rest, not day-1 reset
    assert e.rest_until == NOW + timedelta(hours=48)
    assert getattr(e, "recovery_reset_count", 0) == 0


@pytest.mark.asyncio
async def test_non_recovery_notauthorized_still_blocked_reset():
    e = _recovery_enr(day=5, state=WarmupState.RAMPING.value, recovery_mode=False)
    db = FakeSession(results=[FakeResult(scalars=[e]), FakeResult(scalars=[])])
    res = await handle_warmup_state_signal(db, e.instance_id, "notAuthorized", NOW)
    assert res["action"] == "reset"
    assert e.state == WarmupState.BLOCKED_RESET.value  # general path: BLOCKED_RESET, restart on re-auth
