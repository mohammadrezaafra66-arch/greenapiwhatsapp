"""V67 Phase 3 — migration upgrade/downgrade for journey tables (migtest DB only)."""
from __future__ import annotations
import os

import pytest
from sqlalchemy import text

from tests.migration_test_db import (
    migration_test_engine,
    reset_additive_fleet_schema_for_alembic,
    run_alembic,
)


@pytest.mark.skipif(not os.path.exists("/app/alembic.ini"), reason="backend container only")
def test_phase3_upgrade_downgrade_reupgrade():
    reset_additive_fleet_schema_for_alembic()
    eng = migration_test_engine()
    assert run_alembic("stamp", "v67_01_baseline_stamp").returncode == 0
    assert run_alembic("upgrade", "v67_03_fleet_accounts").returncode == 0

    up = run_alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr + up.stdout

    with eng.connect() as conn:
        for t in ("account_journeys", "journey_actions"):
            assert conn.execute(text(
                "SELECT 1 FROM information_schema.tables WHERE table_name=:t"
            ), {"t": t}).scalar() == 1
        assert conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='fleet_accounts' AND column_name='cutover'"
        )).scalar() == "cutover"

    down = run_alembic("downgrade", "v67_03_fleet_accounts")
    assert down.returncode == 0, down.stderr + down.stdout
    with eng.connect() as conn:
        for t in ("account_journeys", "journey_actions"):
            assert conn.execute(text(
                "SELECT 1 FROM information_schema.tables WHERE table_name=:t"
            ), {"t": t}).scalar() is None
        assert conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name='fleet_accounts'"
        )).scalar() == 1

    reup = run_alembic("upgrade", "head")
    assert reup.returncode == 0, reup.stderr + reup.stdout
    eng.dispose()
