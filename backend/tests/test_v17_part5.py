"""V17 PART 5 — kill-switch + chain-ban breaker + reset detection.

Simulates webhook signals (via the kill-switch handlers) and asserts: yellowCard pauses
one number and starts its rest/resume curve; 2 incidents in the window trip the global
breaker; block→re-auth restarts from Day 1; low delivery throttles; and peers of a paused
node keep operating unless the breaker trips.
"""
import uuid
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest

from app.models.warmup_mesh import WarmupEnrollment, WarmupMeshEdge, WarmupEventLog
from app.services import warmup_killswitch as ks
from app.services.warmup_killswitch import (
    delivery_ratio, is_soft_ban, post_rest_volume_fraction, reduced_target,
    should_trip_breaker, idle_reset_reason, state_reset_reason, is_resting, rest_until,
    on_yellow_card, on_block_or_logout, on_reauthorized, evaluate_delivery,
    maybe_resume_after_rest, record_incident, count_recent_incidents,
    most_connected_instance, trip_global_breaker, check_and_maybe_trip_breaker,
)
from app.services.warmup_state import WarmupState


# ── FakeSession supporting func.count() scalar + object lists ────────────────
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


def _enr(**kw):
    base = dict(instance_id="NEW", state=WarmupState.RAMPING.value, is_enabled=True,
                sent_today=5, received_today=6, reply_ratio=0.0, rest_until=None,
                day_index=6, started_at=datetime(2026, 4, 25), authorized_at=datetime(2026, 4, 25),
                last_activity_at=datetime(2026, 5, 1), next_action_at=None)
    base.update(kw)
    e = SimpleNamespace(**base)
    e.id = kw.get("id", uuid.uuid4())
    return e


NOW = datetime(2026, 5, 1, 12, 0, 0)


# ════════════════════════ pure helpers ════════════════════════
def test_delivery_ratio_and_soft_ban():
    assert delivery_ratio(60, 100) == 0.60
    assert delivery_ratio(0, 0) == 1.0                # nothing sent → not a signal
    assert is_soft_ban(0.59) is True
    assert is_soft_ban(0.60) is False                 # threshold is < 0.60


def test_post_rest_ramp_5pct_then_10pct_week():
    assert post_rest_volume_fraction(0) == pytest.approx(0.05)         # resume at ~5%
    assert post_rest_volume_fraction(1) == pytest.approx(0.055)        # +10% → 5.5%
    assert post_rest_volume_fraction(52) == 1.0                         # capped at 100%
    assert reduced_target(100, 0) == 5                                  # 5% of 100
    assert reduced_target(10, 0) >= 1                                   # never zero


def test_should_trip_breaker_threshold():
    assert should_trip_breaker(1) is False
    assert should_trip_breaker(2) is True
    assert should_trip_breaker(3) is True


def test_idle_reset_reason():
    assert idle_reset_reason(5) is None
    assert idle_reset_reason(14) == "erosion"
    assert idle_reset_reason(29) == "erosion"
    assert idle_reset_reason(30) == "auto_logout"


def test_state_reset_reason():
    assert state_reset_reason("blocked") == "blocked"
    assert state_reset_reason("notAuthorized") == "notAuthorized"
    assert state_reset_reason("authorized") is None
    assert state_reset_reason("yellowCard") is None    # yellowCard rests, not resets


def test_is_resting():
    e = _enr(rest_until=NOW + timedelta(hours=10))
    assert is_resting(e, NOW) is True
    assert is_resting(_enr(rest_until=NOW - timedelta(hours=1)), NOW) is False


# ════════════════════════ per-number kill-switch ════════════════════════
@pytest.mark.asyncio
async def test_yellow_card_pauses_and_rests():
    db = FakeSession()
    e = _enr(state=WarmupState.RAMPING.value)
    res = await on_yellow_card(db, e, NOW)
    assert e.state == WarmupState.YELLOWCARD.value
    assert e.rest_until == NOW + timedelta(hours=48)   # >=48h rest
    assert res["rest_until"] == e.rest_until
    # a kill event + a Persian alert were logged
    kinds = [x.event_type for x in db.added if isinstance(x, WarmupEventLog)]
    assert "kill" in kinds and "alert" in kinds


@pytest.mark.asyncio
async def test_rest_then_resume_at_reduced_volume():
    db = FakeSession()
    e = _enr(state=WarmupState.YELLOWCARD.value, rest_until=NOW - timedelta(minutes=1))
    resumed = await maybe_resume_after_rest(db, e, NOW)
    assert resumed is True
    assert e.state == WarmupState.REPLYING.value        # resumes into replying
    # still resting → no resume
    e2 = _enr(state=WarmupState.YELLOWCARD.value, rest_until=NOW + timedelta(hours=5))
    assert await maybe_resume_after_rest(FakeSession(), e2, NOW) is False
    assert e2.state == WarmupState.YELLOWCARD.value


@pytest.mark.asyncio
async def test_block_then_reauth_restarts_from_day_one():
    db = FakeSession()
    e = _enr(state=WarmupState.RAMPING.value, day_index=6, sent_today=40, received_today=42)
    await on_block_or_logout(db, e, "blocked", NOW)
    assert e.state == WarmupState.BLOCKED_RESET.value
    # re-auth → restart from Day 1
    await on_reauthorized(db, e, NOW)
    assert e.state == WarmupState.COOLDOWN.value
    assert e.day_index == 0
    assert e.sent_today == 0 and e.received_today == 0
    assert e.authorized_at == NOW and e.started_at == NOW


@pytest.mark.asyncio
async def test_reauth_without_block_does_not_restart():
    db = FakeSession()
    e = _enr(state=WarmupState.RAMPING.value, day_index=6)
    res = await on_reauthorized(db, e, NOW)
    assert res["restarted"] is False
    assert e.state == WarmupState.RAMPING.value and e.day_index == 6


@pytest.mark.asyncio
async def test_low_delivery_throttles():
    db = FakeSession()
    e = _enr()
    res = await evaluate_delivery(db, e, delivered=40, sent=100, now=NOW)  # 40% < 60%
    assert res["soft_ban"] is True
    assert e.rest_until is not None                      # throttled via a rest window
    assert any(x.event_type == "alert" for x in db.added if isinstance(x, WarmupEventLog))
    # healthy delivery → no throttle
    e2 = _enr()
    res2 = await evaluate_delivery(FakeSession(), e2, delivered=80, sent=100, now=NOW)
    assert res2["soft_ban"] is False and e2.rest_until is None


# ════════════════════════ chain-ban circuit breaker ════════════════════════
def _incident(iid, when):
    """A warmup_event_log incident row (payload carries the instance + kind)."""
    return SimpleNamespace(
        event_type="incident", created_at=when,
        payload_json=json.dumps({"instance_id": iid, "kind": "yellowCard"}))


@pytest.mark.asyncio
async def test_breaker_trips_on_two_distinct_numbers():
    # V21 PART 3 — 2 DISTINCT numbers carded in the window → trip.
    e1 = _enr(instance_id="A", state=WarmupState.RAMPING.value)
    e2 = _enr(instance_id="B", state=WarmupState.REPLYING.value)
    edges = [SimpleNamespace(new_instance_id="A", peer_instance_id="HUB"),
             SimpleNamespace(new_instance_id="B", peer_instance_id="HUB")]
    db = FakeSession(results=[
        FakeResult(scalars=[_incident("A", NOW), _incident("B", NOW)]),  # recent incidents (2 distinct)
        FakeResult(scalars=[e1, e2]),  # enabled enrollments to pause
        FakeResult(scalars=edges),     # edges for most_connected_instance
    ])
    res = await check_and_maybe_trip_breaker(db, NOW)
    assert res["tripped"] is True
    assert res["paused"] == 2
    assert res["quarantine"] == "HUB"                   # most-connected node quarantined
    assert {o["instance_id"] for o in res["offenders"]} == {"A", "B"}   # offenders recorded
    assert e1.state == WarmupState.PAUSED.value and e2.state == WarmupState.PAUSED.value


@pytest.mark.asyncio
async def test_breaker_does_not_trip_on_three_incidents_one_number():
    # V21 PART 3 — 3 incidents but ALL from ONE number → distinct=1 → NO global trip.
    db = FakeSession(results=[FakeResult(scalars=[
        _incident("A", NOW), _incident("A", NOW), _incident("A", NOW),
    ])])
    res = await check_and_maybe_trip_breaker(db, NOW)
    assert res["tripped"] is False
    assert res["incidents"] == 1                          # distinct count, not raw 3
    assert res["distinct_numbers"] == ["A"]


@pytest.mark.asyncio
async def test_single_yellowcard_does_not_trip_breaker_peers_keep_running():
    """One carded number pauses ITSELF but, with only 1 distinct number, the breaker stays
    open so its peers keep operating."""
    db = FakeSession(results=[
        FakeResult(scalars=[_enr(instance_id="NEW")]),  # handle_warmup_state_signal: lookup enrollment
        FakeResult(scalars=[_incident("NEW", NOW)]),     # recent incidents → 1 distinct (no trip)
    ])
    res = await ks.handle_warmup_state_signal(db, "NEW", "yellowCard", NOW)
    assert res["action"] == "yellowCard"
    assert res["breaker"]["tripped"] is False            # peers unaffected


@pytest.mark.asyncio
async def test_repeated_cards_same_number_never_trip_even_across_ticks():
    """Even many cards from one flaky number → still 1 distinct → global breaker never trips."""
    db = FakeSession(results=[FakeResult(scalars=[_incident("A", NOW) for _ in range(6)])])
    res = await check_and_maybe_trip_breaker(db, NOW)
    assert res["tripped"] is False and res["incidents"] == 1


@pytest.mark.asyncio
async def test_most_connected_instance():
    edges = [
        SimpleNamespace(new_instance_id="A", peer_instance_id="HUB"),
        SimpleNamespace(new_instance_id="B", peer_instance_id="HUB"),
        SimpleNamespace(new_instance_id="C", peer_instance_id="HUB"),
        SimpleNamespace(new_instance_id="A", peer_instance_id="B"),
    ]
    db = FakeSession(results=[FakeResult(scalars=edges)])
    assert await most_connected_instance(db) == "HUB"    # degree 3, the hub


# ════════════════════════ webhook routing (simulated) ════════════════════════
@pytest.mark.asyncio
async def test_state_signal_noop_when_not_enrolled():
    db = FakeSession(results=[FakeResult(scalars=[])])   # no enrollment for instance
    assert await ks.handle_warmup_state_signal(db, "UNKNOWN", "yellowCard", NOW) is None


@pytest.mark.asyncio
async def test_state_signal_block_resets_and_records_incident():
    e = _enr(instance_id="NEW", state=WarmupState.RAMPING.value)
    db = FakeSession(results=[
        FakeResult(scalars=[e]),   # enrollment lookup
        FakeResult(scalar=1),      # breaker incident count (no trip)
    ])
    res = await ks.handle_warmup_state_signal(db, "NEW", "blocked", NOW)
    assert res["action"] == "reset"
    assert e.state == WarmupState.BLOCKED_RESET.value
    # an incident row was recorded for the breaker
    assert any(x.event_type == "incident" for x in db.added if isinstance(x, WarmupEventLog))
