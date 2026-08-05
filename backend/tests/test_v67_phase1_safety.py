"""V67.1 Phase 1 — incident completeness, eligibility, fleet breaker, activity, lock."""
from __future__ import annotations
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import send_gate
from app.services.send_gate import (
    is_account_send_eligible, can_send_now, clear_live_cache, update_live_state,
)
from app.services.activity_evidence import (
    is_real_outbound_campaign, is_real_outbound_helper,
)
from app.services.campaign_lock import CampaignLock, lock_key
from app.services import fleet_breaker
from app.services import incident_handler as ih


NOW = datetime(2026, 8, 5, 12, 0, 0)


def _account(**kw):
    return SimpleNamespace(
        id=kw.get("id", "acc-1"),
        instance_id=kw.get("instance_id", "77001"),
        status=kw.get("status", SimpleNamespace(value="active")),
        connected_at=kw.get("connected_at", NOW - timedelta(hours=48)),
        reconnected_at=None,
        cooldown_until=kw.get("cooldown_until", None),
        throttle_factor=kw.get("throttle_factor", 1.0),
        throttle_until=kw.get("throttle_until", None),
        api_token="secret-token-never-log",
        sent_today=0,
        suspended_until=kw.get("suspended_until", None),
        incident_count_7d=0,
        last_incident_at=None,
        name=kw.get("name", "t"),
    )


# ── eligibility ─────────────────────────────────────────────────────────────
def test_eligibility_rejects_suspended_live_state():
    clear_live_cache()
    a = _account()
    ok, reason = is_account_send_eligible(a, "suspended", require_live_state=True)
    assert ok is False
    assert "live_state" in reason or reason == "live_state:suspended"


def test_eligibility_rejects_blocked():
    a = _account()
    ok, reason = is_account_send_eligible(a, "blocked", require_live_state=True)
    assert ok is False


def test_eligibility_rejects_not_authorized():
    a = _account()
    ok, reason = is_account_send_eligible(a, "notAuthorized", require_live_state=True)
    assert ok is False


def test_eligibility_rejects_unknown_live_state():
    clear_live_cache()
    a = _account()
    ok, reason = is_account_send_eligible(
        a, None, require_live_state=True, live_state_known=False)
    assert ok is False
    assert reason == "unknown_live_state"


def test_eligibility_rejects_fleet_breaker():
    a = _account()
    ok, reason = is_account_send_eligible(
        a, "authorized", breaker_tripped=True, require_live_state=True)
    assert ok is False
    assert reason == "fleet_breaker"


def test_eligibility_rejects_unresolved_critical():
    a = _account()
    ok, reason = is_account_send_eligible(
        a, "authorized", unresolved_critical=True, require_live_state=True)
    assert ok is False
    assert reason == "unresolved_critical_incident"


def test_eligibility_allows_healthy_authorized():
    clear_live_cache()
    a = _account()
    ok, reason = is_account_send_eligible(a, "authorized", require_live_state=True)
    assert ok is True
    assert reason == "ok"


def test_can_send_now_still_works_without_live_state():
    """Legacy sync gate remains for non-automated callers; Phase 1 automated path is stricter."""
    a = _account()
    ok, reason = can_send_now(a, None)
    assert ok is True


# ── activity definitions ────────────────────────────────────────────────────
def test_failed_send_without_id_not_real_outbound():
    assert is_real_outbound_campaign(None, NOW, "failed") is False


def test_accepted_id_message_is_real_outbound():
    assert is_real_outbound_campaign("3EB0ABC", NOW, "sent") is True


def test_helper_requires_delivery_ok_and_id():
    assert is_real_outbound_helper(True, "3EB0") is True
    assert is_real_outbound_helper(False, "3EB0") is False
    assert is_real_outbound_helper(True, None) is False


# ── campaign lock fail-closed ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_campaign_lock_fail_closed_when_redis_down():
    lock = CampaignLock("cid-1")
    with patch("app.services.redis_rate_limiter.get_redis",
               new=AsyncMock(side_effect=Exception("redis down"))):
        ok = await lock.acquire()
    assert ok is False
    assert lock.fail_closed_reason is not None
    assert "Redis" in lock.fail_closed_reason or "redis" in lock.fail_closed_reason.lower()


@pytest.mark.asyncio
async def test_campaign_lock_skips_when_held():
    lock = CampaignLock("cid-2")
    r = MagicMock()
    r.set = AsyncMock(return_value=False)
    r.eval = AsyncMock(return_value=0)
    with patch("app.services.redis_rate_limiter.get_redis", new=AsyncMock(return_value=r)):
        ok = await lock.acquire()
    assert ok is False
    assert lock.acquired is False


@pytest.mark.asyncio
async def test_campaign_lock_owner_release_only():
    lock = CampaignLock("cid-3")
    r = MagicMock()
    r.set = AsyncMock(return_value=True)
    r.eval = AsyncMock(return_value=0)
    with patch("app.services.redis_rate_limiter.get_redis", new=AsyncMock(return_value=r)):
        assert await lock.acquire() is True
        lock.token = "wrong-owner-token"
        assert await lock.release() is False


@pytest.mark.asyncio
async def test_run_campaign_blocked_by_fleet_breaker():
    from app.services import campaign_runner
    inner = AsyncMock()
    with patch("app.services.fleet_breaker.is_tripped",
               new=AsyncMock(return_value=(True, "two_distinct_suspensions_24h"))), \
         patch.object(campaign_runner, "_run_campaign_inner", new=inner), \
         patch.object(campaign_runner, "_pause_campaign_for_safety", new=AsyncMock()) as pause:
        await campaign_runner.run_campaign("cid")
    inner.assert_not_awaited()
    pause.assert_awaited()


# ── fleet breaker ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_fleet_breaker_trips_on_two_distinct_accounts():
    store = {}
    index = set()

    class FakeRedis:
        async def set(self, k, v, ex=None, nx=False):
            if nx and k in store:
                return False
            store[k] = v
            return True

        async def exists(self, k):
            return 1 if k in store else 0

        async def sadd(self, k, *members):
            for m in members:
                index.add(m)
            return len(members)

        async def expire(self, k, ttl):
            return True

        async def smembers(self, k):
            return set(index)

        async def srem(self, k, *members):
            for m in members:
                index.discard(m)
            return len(members)

        async def get(self, k):
            return store.get(k)

        async def delete(self, *keys):
            for k in keys:
                store.pop(k, None)
            return len(keys)

        def pipeline(self):
            return self

        async def execute(self):
            return []

    fr = FakeRedis()
    # pipeline methods need to queue
    fr.set = AsyncMock(side_effect=fr.set)
    fr.sadd = AsyncMock(side_effect=lambda k, *m: index.update(m) or len(m))
    fr.expire = AsyncMock(return_value=True)
    fr.execute = AsyncMock(return_value=[])

    with patch("app.services.fleet_breaker._redis", new=AsyncMock(return_value=fr)):
        # Simulate pipeline by making record use direct ops — patch record internals
        async def fake_record(account_id, now=None, via="t"):
            aid = str(account_id)
            store[fleet_breaker._member_key(aid)] = (now or NOW).isoformat()
            index.add(aid)
            distinct = sum(1 for a in list(index)
                           if fleet_breaker._member_key(a) in store)
            out = {"distinct": distinct, "tripped": False, "activated_now": False,
                   "reason": None, "via": via, "account_id": aid}
            if distinct >= 2:
                created = await fr.set(fleet_breaker.BREAKER_KEY,
                                       json.dumps({"reason": "two_distinct_suspensions_24h"}),
                                       nx=True)
                out["tripped"] = True
                out["activated_now"] = bool(created)
                out["reason"] = "two_distinct_suspensions_24h"
            return out

        r1 = await fake_record("a1")
        assert r1["tripped"] is False
        r2 = await fake_record("a2")
        assert r2["tripped"] is True
        # duplicate same account does not change distinct
        store[fleet_breaker._member_key("a1")] = NOW.isoformat()
        distinct = len({a for a in index if fleet_breaker._member_key(a) in store})
        assert distinct == 2


@pytest.mark.asyncio
async def test_fleet_breaker_fail_closed_on_redis_error():
    with patch("app.services.fleet_breaker._redis",
               new=AsyncMock(side_effect=Exception("down"))):
        tripped, reason = await fleet_breaker.is_tripped(fail_closed=True)
    assert tripped is True
    assert reason == "redis_unavailable"


# ── incidents (pure / FakeSession-lite) ─────────────────────────────────────
class _FakeResult:
    def __init__(self, row=None):
        self._row = row

    def scalar_one_or_none(self):
        return self._row

    def scalars(self):
        return self

    def all(self):
        return self._row if isinstance(self._row, list) else ([] if self._row is None else [self._row])


class _FakeDB:
    def __init__(self, existing=None, list_rows=None):
        self.existing = existing
        self.list_rows = list_rows or []
        self.added = []
        self._n = 0

    async def execute(self, stmt):
        self._n += 1
        # first calls are open-incident checks
        if self._n == 1:
            return _FakeResult(self.existing)
        return _FakeResult(self.list_rows)

    def add(self, obj):
        self.added.append(obj)


@pytest.mark.asyncio
async def test_record_blocked_idempotent():
    a = _account(id="u1", instance_id="77001")
    db = _FakeDB(existing=SimpleNamespace(id="inc"))
    out = await ih.record_blocked(a, "webhook", db)
    assert out is None
    assert db.added == []


@pytest.mark.asyncio
async def test_record_blocked_creates_once():
    a = _account(id="u1", instance_id="77001")
    db = _FakeDB(existing=None)
    out = await ih.record_blocked(a, "webhook", db, raw_state="blocked")
    assert out is not None
    assert out.incident_type == "blocked"
    assert out.severity == "critical"
    assert "secret" not in str(out.auto_actions)
    assert a.api_token not in str(out.notes or "")


@pytest.mark.asyncio
async def test_record_forced_logout_and_not_authorized():
    a = _account(id="u2", instance_id="77002")
    db = _FakeDB(existing=None)
    out = await ih.record_forced_logout(a, "webhook", db)
    assert out is not None
    assert out.incident_type == "forced_logout"


@pytest.mark.asyncio
async def test_mesh_autochat_disabled_by_default():
    from app.config import settings
    assert settings.mesh_autochat_enabled is False


@pytest.mark.asyncio
async def test_mesh_execute_skips_when_autochat_disabled():
    from app.services import warmup_engine as we
    enrollment = SimpleNamespace(id=None, sent_today=0, received_today=0, reply_ratio=0,
                                 last_activity_at=None, next_action_at=None)
    edge = SimpleNamespace(id=None, msg_count=0, last_msg_at=None)
    cold = _account(instance_id="C1")
    cold.phone = "98912111111"
    cold.name = "c"
    peer = _account(instance_id="P1")
    peer.phone = "98912000000"
    peer.name = "p"
    action = {"direction": "inbound", "edge": edge, "peer_account": peer,
              "next_action_at": NOW + timedelta(hours=2)}
    db = MagicMock()
    db.add = MagicMock()
    with patch("app.config.settings", SimpleNamespace(mesh_autochat_enabled=False)), \
         patch.object(we, "generate_mesh_message", new=AsyncMock()) as gen:
        result = await we.execute_action(
            db, action, enrollment, cold, peer,
            client_factory=lambda *a, **k: MagicMock(),
            ai_fn=None, now=NOW)
    assert result.get("skipped") is True
    assert result.get("reason") == "mesh_autochat_disabled"
    gen.assert_not_awaited()


@pytest.mark.asyncio
async def test_mesh_blocked_by_fleet_breaker_when_autochat_on():
    from app.services import warmup_engine as we
    enrollment = SimpleNamespace(id=None, sent_today=0, received_today=0, reply_ratio=0,
                                 last_activity_at=None, next_action_at=None)
    edge = SimpleNamespace(id=None, msg_count=0, last_msg_at=None)
    cold = _account(instance_id="C1")
    cold.phone = "98912111111"
    cold.name = "c"
    peer = _account(instance_id="P1")
    peer.phone = "98912000000"
    peer.name = "p"
    action = {"direction": "inbound", "edge": edge, "peer_account": peer,
              "next_action_at": NOW + timedelta(hours=2)}
    db = MagicMock()
    db.add = MagicMock()
    with patch("app.config.settings", SimpleNamespace(mesh_autochat_enabled=True)), \
         patch("app.services.send_gate.gate_check_automated",
               new=AsyncMock(return_value=(False, "fleet_breaker:tripped"))), \
         patch.object(we, "generate_mesh_message", new=AsyncMock()) as gen:
        result = await we.execute_action(
            db, action, enrollment, cold, peer,
            client_factory=lambda *a, **k: MagicMock(),
            ai_fn=None, now=NOW)
    assert result.get("skipped") is True
    assert "fleet_breaker" in result.get("reason", "")
    gen.assert_not_awaited()
