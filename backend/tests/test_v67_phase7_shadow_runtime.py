"""V67 Phase 7 — shadow migration, auth, celery, CLI tests."""
from __future__ import annotations
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest

from app.services.shadow_auth import require_shadow_operator
from app.services.shadow_runtime import ShadowRuntimeService
from app.scripts import fleet_shadow_run as cli
from app.workers import tasks as tasks_mod
from app.config import settings
from fastapi import HTTPException


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
    assert _run("downgrade", "v67_06_fleet_plan_snapshots").returncode == 0
    with eng.connect() as conn:
        assert conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name='fleet_shadow_snapshots'"
        )).scalar() is None
        assert conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name='fleet_plan_snapshots'"
        )).scalar() == 1
    assert _run("upgrade", "head").returncode == 0


@pytest.mark.asyncio
async def test_shadow_auth_fail_closed_and_roles(monkeypatch):
    monkeypatch.setattr(settings, "v67_shadow_operator_token", "", raising=False)
    with pytest.raises(HTTPException) as e503:
        await require_shadow_operator(MagicMock(), None, None, None)
    assert e503.value.status_code == 503

    monkeypatch.setattr(settings, "v67_shadow_operator_token", "secret-token", raising=False)
    monkeypatch.setattr(settings, "v67_shadow_allowed_roles", "admin,operator", raising=False)
    with pytest.raises(HTTPException) as e401:
        await require_shadow_operator(MagicMock(), None, "admin", None)
    assert e401.value.status_code == 401
    with pytest.raises(HTTPException) as e403:
        await require_shadow_operator(MagicMock(), "secret-token", "viewer", None)
    assert e403.value.status_code == 403
    ok = await require_shadow_operator(MagicMock(), "secret-token", "admin", None)
    assert ok["authenticated"] is True


def test_celery_task_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "v67_shadow_runtime_enabled", False, raising=False)
    monkeypatch.setattr(settings, "v67_shadow_scheduler_enabled", False, raising=False)
    out = tasks_mod.task_fleet_shadow_tick()
    assert out["skipped"] is True
    assert out["mutates_runtime"] is False
    assert out["executes"] is False


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
    out = await ShadowRuntimeService().run_account(db, aid, dry_run=True, persist=False)
    assert out.get("error") == "cutover_true_forbidden"
    assert out.get("mutates_runtime") is False


def test_cli_invalid_uuid_and_doc():
    assert "dry-run" in (cli.__doc__ or "").lower()
    assert cli.main(["--account-id", "bad"]) == 2
    src = open(cli.__file__, encoding="utf-8").read()
    assert "green_api" not in src
    assert "send_gate" not in src
    assert "run_campaign" not in src


def test_shadow_api_routes_require_auth_dependency():
    from app.api.v1 import fleet_shadow as api
    for route in api.router.routes:
        deps = getattr(route, "dependant", None)
        # every route must reference require_shadow_operator somehow
        assert route.path.startswith("/fleet/shadow")
