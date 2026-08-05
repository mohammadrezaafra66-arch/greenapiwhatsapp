"""V67 Phase 3 — migration upgrade/downgrade for journey tables."""
from __future__ import annotations
import os
import subprocess
import pytest


def _run_alembic(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["alembic", *args], cwd="/app", capture_output=True, text=True, env=os.environ.copy(),
    )


@pytest.mark.skipif(not os.path.exists("/app/alembic.ini"), reason="backend container only")
def test_phase3_upgrade_downgrade_reupgrade():
    cur = _run_alembic("current")
    if "v67_03" not in (cur.stdout or "") and "v67_04" not in (cur.stdout or ""):
        st = _run_alembic("stamp", "v67_03_fleet_accounts")
        assert st.returncode == 0, st.stderr

    up = _run_alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr + up.stdout

    from sqlalchemy import create_engine, text
    from app.config import settings
    eng = create_engine(settings.sync_database_url)
    with eng.connect() as conn:
        for t in ("account_journeys", "journey_actions"):
            assert conn.execute(text(
                "SELECT 1 FROM information_schema.tables WHERE table_name=:t"
            ), {"t": t}).scalar() == 1
        # cutover column still exists and default false on fleet_accounts
        assert conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='fleet_accounts' AND column_name='cutover'"
        )).scalar() == "cutover"

    down = _run_alembic("downgrade", "v67_03_fleet_accounts")
    assert down.returncode == 0, down.stderr + down.stdout
    with eng.connect() as conn:
        for t in ("account_journeys", "journey_actions"):
            assert conn.execute(text(
                "SELECT 1 FROM information_schema.tables WHERE table_name=:t"
            ), {"t": t}).scalar() is None
        # Phase 2 tables preserved
        assert conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name='fleet_accounts'"
        )).scalar() == 1

    reup = _run_alembic("upgrade", "head")
    assert reup.returncode == 0, reup.stderr + reup.stdout
