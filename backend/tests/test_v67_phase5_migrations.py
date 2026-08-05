"""V67 Phase 5 — plan snapshot migration round-trip."""
from __future__ import annotations
import os
import subprocess
import pytest


def _run(*args: str):
    return subprocess.run(
        ["alembic", *args], cwd="/app", capture_output=True, text=True, env=os.environ.copy(),
    )


@pytest.mark.skipif(not os.path.exists("/app/alembic.ini"), reason="container only")
def test_phase5_plan_migration_roundtrip():
    cur = _run("current")
    if "v67_05" not in (cur.stdout or "") and "v67_06" not in (cur.stdout or ""):
        assert _run("stamp", "v67_05_fleet_evidence_snapshots").returncode == 0
    assert _run("upgrade", "head").returncode == 0
    from sqlalchemy import create_engine, text
    from app.config import settings
    eng = create_engine(settings.sync_database_url)
    with eng.connect() as conn:
        assert conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name='fleet_plan_snapshots'"
        )).scalar() == 1
    assert _run("downgrade", "v67_05_fleet_evidence_snapshots").returncode == 0
    with eng.connect() as conn:
        assert conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name='fleet_plan_snapshots'"
        )).scalar() is None
        assert conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name='fleet_evidence_snapshots'"
        )).scalar() == 1
    assert _run("upgrade", "head").returncode == 0
