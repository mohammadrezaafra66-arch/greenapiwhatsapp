"""V67 Phase 5 — plan snapshot migration round-trip (migtest DB only)."""
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
def test_phase5_plan_migration_roundtrip():
    reset_additive_fleet_schema_for_alembic()
    eng = migration_test_engine()
    assert run_alembic("stamp", "v67_01_baseline_stamp").returncode == 0
    assert run_alembic("upgrade", "v67_05_fleet_evidence_snapshots").returncode == 0
    assert run_alembic("upgrade", "head").returncode == 0
    with eng.connect() as conn:
        assert conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name='fleet_plan_snapshots'"
        )).scalar() == 1
    assert run_alembic("downgrade", "v67_05_fleet_evidence_snapshots").returncode == 0
    with eng.connect() as conn:
        assert conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name='fleet_plan_snapshots'"
        )).scalar() is None
        assert conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name='fleet_evidence_snapshots'"
        )).scalar() == 1
    assert run_alembic("upgrade", "head").returncode == 0
    eng.dispose()
