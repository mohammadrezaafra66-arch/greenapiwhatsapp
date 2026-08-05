"""V67 Phase 4 — evidence snapshot migration tests (migtest DB only)."""
from __future__ import annotations
import os

import pytest
from sqlalchemy import text

from tests.migration_test_db import (
    migration_test_engine,
    reset_additive_fleet_schema_for_alembic,
    run_alembic,
)


@pytest.mark.skipif(not os.path.exists("/app/alembic.ini"), reason="container only")
def test_phase4_evidence_migration_roundtrip():
    reset_additive_fleet_schema_for_alembic()
    eng = migration_test_engine()
    assert run_alembic("stamp", "v67_01_baseline_stamp").returncode == 0
    assert run_alembic("upgrade", "v67_04_account_journeys").returncode == 0

    up = run_alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr + up.stdout

    with eng.connect() as conn:
        assert conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name='fleet_evidence_snapshots'"
        )).scalar() == 1
        assert conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='fleet_accounts' AND column_name='fleet_state'"
        )).scalar() == "fleet_state"

    down = run_alembic("downgrade", "v67_04_account_journeys")
    assert down.returncode == 0, down.stderr
    with eng.connect() as conn:
        assert conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name='fleet_evidence_snapshots'"
        )).scalar() is None
        assert conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name='account_journeys'"
        )).scalar() == 1

    assert run_alembic("upgrade", "head").returncode == 0
    eng.dispose()
