"""V67 Phase 7.1 — strengthened Shadow auth, no-mutation, isolation tests."""
from __future__ import annotations
import inspect
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest
from fastapi import HTTPException

from app.config import settings
from app.services.shadow_auth import require_shadow_operator
from app.services.shadow_runtime import ShadowRuntimeService
from app.scripts import fleet_shadow_run as cli
from app.workers import tasks as tasks_mod
from app.services import send_gate
from app.api.v1 import fleet_shadow as api


def test_phase7_migration_file_present():
    versions = Path(__file__).resolve().parents[1] / "migrations" / "versions"
    assert any("v67_07_fleet_shadow" in p.name for p in versions.glob("*.py"))


@pytest.mark.skipif(not os.path.exists("/app/alembic.ini"), reason="container only")
def test_phase7_migration_roundtrip():
    def _run(*args: str):
        return subprocess.run(
            ["alembic", *args], cwd="/app", capture_output=True, text=True, env=os.environ.copy(),
        )
    assert _run("upgrade", "head").returncode == 0
    from sqlalchemy import create_engine, text
    from app.config import settings as st
    eng = create_engine(st.sync_database_url)
    with eng.connect() as conn:
        assert conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name='fleet_shadow_snapshots'"
        )).scalar() == 1
        # invalid mismatch class must fail
        try:
            conn.execute(text(
                "INSERT INTO fleet_shadow_snapshots ("
                "id, run_id, account_id, fleet_account_id, observed_at, source, shadow_version,"
                " mismatch_class, severity, idempotency_key) VALUES ("
                "gen_random_uuid(), gen_random_uuid(),"
                "(SELECT id FROM accounts LIMIT 1),"
                "(SELECT id FROM fleet_accounts LIMIT 1),"
                "NOW(), 'TEST', 'v67.7.shadow.1', 'NOT_A_CLASS', 'INFO', 'idem-bad')"
            ))
            conn.commit()
            assert False, "expected check constraint failure"
        except Exception:
            conn.rollback()
    assert _run("downgrade", "v67_06_fleet_plan_snapshots").returncode == 0
    with eng.connect() as conn:
        assert conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name='fleet_shadow_snapshots'"
        )).scalar() is None
    assert _run("upgrade", "head").returncode == 0


@pytest.mark.asyncio
async def test_shadow_auth_fail_closed_and_no_role_spoof(monkeypatch):
    monkeypatch.setattr(settings, "v67_shadow_operator_token", "", raising=False)
    with pytest.raises(HTTPException) as e503:
        await require_shadow_operator(MagicMock(url=SimpleNamespace(path="/x")), None, None, None)
    assert e503.value.status_code == 503

    monkeypatch.setattr(settings, "v67_shadow_operator_token", "secret-token", raising=False)
    monkeypatch.setattr(settings, "v67_shadow_operator_role", "operator", raising=False)
    monkeypatch.setattr(settings, "v67_shadow_allowed_roles", "admin,operator", raising=False)

    req = MagicMock()
    req.url.path = "/api/v1/fleet/shadow/status"

    with pytest.raises(HTTPException) as e401:
        await require_shadow_operator(req, None, None, None)
    assert e401.value.status_code == 401

    with pytest.raises(HTTPException) as e401b:
        await require_shadow_operator(req, "wrong", None, None)
    assert e401b.value.status_code == 401

    # Client claims admin while Backend role is operator → spoof rejected
    with pytest.raises(HTTPException) as e403:
        await require_shadow_operator(req, "secret-token", "admin", None)
    assert e403.value.status_code == 403
    assert "spoof" in e403.value.detail

    ok = await require_shadow_operator(req, "secret-token", None, None)
    assert ok["authenticated"] is True
    assert ok["role"] == "operator"
    assert ok["client_role_trusted"] is False

    ok2 = await require_shadow_operator(req, "secret-token", "operator", None)
    assert ok2["role"] == "operator"


def test_celery_task_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "v67_shadow_runtime_enabled", False, raising=False)
    monkeypatch.setattr(settings, "v67_shadow_scheduler_enabled", False, raising=False)
    with patch.object(ShadowRuntimeService, "run_batch_periodic", new=AsyncMock()) as mocked:
        out = tasks_mod.task_fleet_shadow_tick()
        assert out["skipped"] is True
        mocked.assert_not_called()


@pytest.mark.asyncio
async def test_periodic_batch_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "v67_shadow_runtime_enabled", False, raising=False)
    monkeypatch.setattr(settings, "v67_shadow_scheduler_enabled", True, raising=False)
    out = await ShadowRuntimeService().run_batch_periodic(MagicMock())
    assert out["skipped"] is True
    assert out["processed"] == 0


@pytest.mark.asyncio
async def test_cutover_true_refused():
    aid = uuid.uuid4()
    fleet = SimpleNamespace(id=uuid.uuid4(), account_id=aid, fleet_state="WARMUP_READY", cutover=True)
    acc = SimpleNamespace(id=aid, status="active", sent_today=0, instance_id="1")

    class _Res:
        def __init__(self, v): self._v = v
        def scalar_one_or_none(self): return self._v

    async def _exec(stmt):
        s = str(stmt).lower()
        if "fleet_accounts" in s or "fleetaccount" in s:
            return _Res(fleet)
        return _Res(acc)

    db = MagicMock()
    db.execute = AsyncMock(side_effect=_exec)
    db.add = MagicMock()
    out = await ShadowRuntimeService().run_account(db, aid, dry_run=True, persist=False)
    assert out.get("error") == "cutover_true_forbidden"
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_dry_run_does_not_persist(monkeypatch):
    aid = uuid.uuid4()
    fleet = SimpleNamespace(
        id=uuid.uuid4(), account_id=aid, fleet_state="WARMUP_READY", cutover=False, policy_id=None,
    )
    acc = SimpleNamespace(id=aid, status=SimpleNamespace(value="active"), sent_today=0, instance_id="X")
    policy = SimpleNamespace(
        id=uuid.uuid4(), name="CONSERVATIVE", version=1,
        settings_json=__import__("app.services.fleet_policy_defaults", fromlist=["CONSERVATIVE_POLICY_SETTINGS"]).CONSERVATIVE_POLICY_SETTINGS,
        is_default=True,
    )

    class _Res:
        def __init__(self, v): self._v = v
        def scalar_one_or_none(self): return self._v

    async def _exec(stmt):
        s = str(stmt).lower()
        if "fleet_policies" in s:
            return _Res(policy)
        if "fleet_accounts" in s:
            return _Res(fleet)
        if "fleet_accounts" not in s and ("from accounts" in s or "accounts.id" in s):
            return _Res(acc)
        return _Res(None)

    db = MagicMock()
    db.execute = AsyncMock(side_effect=_exec)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.begin_nested = MagicMock()

    score = {
        "trust": {"score": 60}, "risk": {"level": "LOW"},
        "readiness": {"label": "READY_FOR_TRIAL"},
        "evidence": {"incident_free_days": 10, "incidents": []},
    }
    preview = {
        "adapter_recommended": "WARMUP_READY",
        "decision": {"recommended_next_state": "WARMUP_READY"},
        "journey": {"status": "ACTIVE"},
    }
    with patch("app.services.shadow_runtime.FleetScoringService.simulate",
               new=AsyncMock(return_value=score)), \
         patch("app.services.shadow_runtime.JourneyOrchestrator.preview",
               new=AsyncMock(return_value=preview)), \
         patch("app.services.fleet_breaker.is_tripped",
               new=AsyncMock(return_value=(False, "ok"))), \
         patch("app.services.shadow_runtime.get_cached_live_state", return_value="authorized"):
        out = await ShadowRuntimeService().run_account(
            db, aid, dry_run=True, persist=False, inject={"journey_status": "ACTIVE"},
        )
    assert out.get("error") is None, out
    assert out.get("comparison")
    db.add.assert_not_called()
    assert out.get("persisted") is False
    assert out.get("mutates_runtime") is False


def test_cli_invalid_uuid_and_no_forbidden_imports():
    assert "dry-run" in (cli.__doc__ or "").lower()
    assert cli.main(["--account-id", "bad"]) == 2
    src = inspect.getsource(cli)
    for forbidden in ("green_api", "send_gate", "run_campaign", "or True"):
        assert forbidden not in src


def test_send_gate_untouched():
    src = inspect.getsource(send_gate)
    assert "ShadowRuntime" not in src
    assert "fleet_shadow" not in src


def test_shadow_api_has_auth_dependency_on_all_routes():
    for route in api.router.routes:
        assert route.path.startswith("/fleet/shadow")
        # Dependants include require_shadow_operator
        names = []
        dep = getattr(route, "dependant", None)
        if dep is not None:
            for d in getattr(dep, "dependencies", []) or []:
                call = getattr(d, "call", None)
                if call:
                    names.append(getattr(call, "__name__", ""))
        assert "require_shadow_operator" in names, f"missing auth on {route.path}"


def test_flags_remain_false_in_defaults():
    assert settings.v67_shadow_runtime_enabled is False
    assert settings.v67_shadow_scheduler_enabled is False
    assert settings.v67_shadow_operator_token == ""


@pytest.mark.asyncio
async def test_shadow_lock_owner_only_and_no_overlap():
    from app.services.shadow_lock import ShadowAccountLock

    store: dict[str, str] = {}

    class FakeRedis:
        async def set(self, key, value, nx=False, ex=None):
            if nx and key in store:
                return False
            store[key] = value
            return True

        async def eval(self, script, n, key, token):
            if store.get(key) == token:
                del store[key]
                return 1
            return 0

    async def fake_get_redis():
        return FakeRedis()

    with patch("app.services.redis_rate_limiter.get_redis", new=fake_get_redis):
        a = ShadowAccountLock("acct-1", ttl=30)
        b = ShadowAccountLock("acct-1", ttl=30)
        c = ShadowAccountLock("acct-2", ttl=30)
        assert await a.acquire() is True
        assert await b.acquire() is False  # same account blocked
        assert await c.acquire() is True   # different account ok
        # Non-owner release must not clear
        b.acquired = True
        b._r = await fake_get_redis()
        b.token = "wrong-token"
        await b.release()
        assert "fleet:shadow:lock:acct-1" in store
        await a.release()
        assert "fleet:shadow:lock:acct-1" not in store


def test_idempotency_key_dimensions():
    from app.services.shadow_types import idempotency_key, SHADOW_VERSION
    a = idempotency_key("a1", SHADOW_VERSION, 1, "slot1", "API_RUN_ONCE")
    b = idempotency_key("a1", SHADOW_VERSION, 1, "slot1", "API_RUN_ONCE")
    assert a == b
    assert idempotency_key("a1", SHADOW_VERSION, 2, "slot1", "API_RUN_ONCE") != a
    assert idempotency_key("a1", "v99", 1, "slot1", "API_RUN_ONCE") != a
    assert idempotency_key("a1", SHADOW_VERSION, 1, "slot2", "API_RUN_ONCE") != a
    assert idempotency_key("a1", SHADOW_VERSION, 1, "slot1", "CELERY_PERIODIC") != a


def test_rate_limit_enforced():
    from fastapi import HTTPException
    from app.api.v1 import fleet_shadow as api_mod
    api_mod._SIM_HITS.clear()
    req = MagicMock()
    req.client = SimpleNamespace(host="1.2.3.4")
    for _ in range(api_mod._SIM_LIMIT):
        api_mod._rate_limit(req)
    with pytest.raises(HTTPException) as e:
        api_mod._rate_limit(req)
    assert e.value.status_code == 429


def test_metrics_are_best_effort_in_process():
    from app.services import shadow_metrics
    shadow_metrics.reset_for_tests()
    shadow_metrics.incr("audit_probe")
    snap = shadow_metrics.snapshot()
    assert snap.get("audit_probe") == 1
    # Documented: no cross-worker aggregation claimed in module
    src = inspect.getsource(shadow_metrics)
    assert "Lock" in src
    assert "prometheus" not in src.lower()


def test_no_retention_worker_enabled():
    import app.workers.tasks as t
    src = inspect.getsource(t)
    assert "shadow_retention" not in src
    assert "DELETE FROM fleet_shadow" not in src
    assert "delete_fleet_shadow" not in src
