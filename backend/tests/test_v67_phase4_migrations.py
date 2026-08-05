"""V67 Phase 4 — evidence snapshot migration tests."""
from __future__ import annotations
import os
import subprocess
import pytest


def _run(*args: str):
    return subprocess.run(
        ["alembic", *args], cwd="/app", capture_output=True, text=True, env=os.environ.copy(),
    )


@pytest.mark.skipif(not os.path.exists("/app/alembic.ini"), reason="container only")
def test_phase4_evidence_migration_roundtrip():
    cur = _run("current")
    if "v67_04" not in (cur.stdout or "") and "v67_05" not in (cur.stdout or ""):
        assert _run("stamp", "v67_04_account_journeys").returncode == 0

    up = _run("upgrade", "head")
    assert up.returncode == 0, up.stderr + up.stdout

    from sqlalchemy import create_engine, text
    from app.config import settings
    eng = create_engine(settings.sync_database_url)
    with eng.connect() as conn:
        assert conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name='fleet_evidence_snapshots'"
        )).scalar() == 1
        # FleetState column still present; Phase 4 must not remove it
        assert conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='fleet_accounts' AND column_name='fleet_state'"
        )).scalar() == "fleet_state"

    down = _run("downgrade", "v67_04_account_journeys")
    assert down.returncode == 0, down.stderr
    with eng.connect() as conn:
        assert conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name='fleet_evidence_snapshots'"
        )).scalar() is None
        assert conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name='account_journeys'"
        )).scalar() == 1

    assert _run("upgrade", "head").returncode == 0
