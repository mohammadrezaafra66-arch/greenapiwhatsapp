"""V27 PART 4 — real-time instance-state monitoring (poll + webhook).

Proves:
  • apply_state refreshes the live-state cache the pre-send gate reads (poll path);
  • a webhook update lands in the same mirror immediately (faster than the next poll);
  • a `blocked` state immediately trips the per-instance kill-switch (cooldown/throttle set);
  • a `yellowCard` routes into the existing automatic incident response;
  • the poll task is scheduled on the ~60s cadence.
"""
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest

from app.services import state_monitor, send_gate
from app.services.state_monitor import apply_state


NOW = datetime(2026, 7, 18, 12, 0, 0)


class _FakeResult:
    def __init__(self, row=None): self._row = row
    def scalar_one_or_none(self): return self._row


class _FakeDB:
    def __init__(self, existing_row=None):
        self.added = []
        self._existing = existing_row
    async def execute(self, *a, **k): return _FakeResult(self._existing)
    def add(self, x): self.added.append(x)
    async def commit(self): pass


def _acc(instance_id="A"):
    return SimpleNamespace(id=uuid.uuid4(), instance_id=instance_id, api_token="t",
                           name="n", phone="98912", status=SimpleNamespace(value="active"),
                           cooldown_until=None, throttle_until=None, throttle_factor=1.0,
                           last_incident_at=None)


@pytest.fixture(autouse=True)
def _clean():
    send_gate.clear_live_cache()
    yield
    send_gate.clear_live_cache()


@pytest.mark.asyncio
async def test_poll_refreshes_live_cache():
    acc = _acc("A")
    res = await apply_state(_FakeDB(), acc, "authorized", "poll", NOW)
    assert res["state"] == "authorized" and res["acted"] is None
    assert send_gate.get_cached_live_state("A", NOW) == "authorized"


@pytest.mark.asyncio
async def test_blocked_trips_kill_switch():
    acc = _acc("B")
    res = await apply_state(_FakeDB(), acc, "blocked", "poll", NOW)
    assert res["acted"] == "blocked"
    assert acc.cooldown_until == NOW + timedelta(days=1)
    assert acc.throttle_until == NOW + timedelta(days=7)
    # and the gate now refuses it via the fresh live-state
    ok, reason = send_gate.gate_check(acc, NOW)
    assert ok is False


@pytest.mark.asyncio
async def test_yellowcard_routes_to_incident_handler(monkeypatch):
    called = {}
    async def _fake(acc, via, db): called["via"] = via; return None
    monkeypatch.setattr("app.services.incident_handler.handle_yellow_card", _fake)
    acc = _acc("Y")
    res = await apply_state(_FakeDB(), acc, "yellowCard", "poll", NOW)
    assert res["acted"] == "yellowCard" and called["via"] == "poll"
    assert send_gate.get_cached_live_state("Y", NOW) == "yellowcard"


@pytest.mark.asyncio
async def test_webhook_update_is_immediate():
    """The webhook mirror update is a plain in-memory write — instantly visible to the gate,
    faster than waiting for the next poll."""
    send_gate.update_live_state("W", "yellowCard", NOW)
    assert send_gate.get_cached_live_state("W", NOW) == "yellowcard"


@pytest.mark.asyncio
async def test_upsert_updates_existing_row():
    existing = SimpleNamespace(instance_id="A", state="authorized", source="poll",
                               checked_at=NOW - timedelta(minutes=5))
    db = _FakeDB(existing_row=existing)
    await apply_state(db, _acc("A"), "yellowCard", "poll", NOW)
    assert existing.state == "yellowcard" and existing.source == "poll"


def test_poll_task_scheduled_at_60s():
    from app.workers.celery_app import celery_app
    sched = celery_app.conf.beat_schedule
    assert "poll-instance-states" in sched
    assert sched["poll-instance-states"]["schedule"] == 60.0
    assert sched["poll-instance-states"]["task"] == "tasks.poll_instance_states"


def test_state_webhook_subscription_enabled_in_set_webhook():
    """PART 4.1 — the state-change webhook is already enabled by set_webhook (stateWebhook)."""
    import inspect
    from app.services.green_api import GreenAPIClient
    src = inspect.getsource(GreenAPIClient.set_webhook)
    assert '"stateWebhook": "yes"' in src
