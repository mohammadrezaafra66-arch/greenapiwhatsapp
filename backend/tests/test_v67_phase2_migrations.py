"""V67 Phase 2 — migration upgrade/downgrade verification (disposable migtest DB only)."""
from __future__ import annotations
import os

import pytest
from sqlalchemy import text

from tests.migration_test_db import (
    migration_test_engine,
    reset_additive_fleet_schema_for_alembic,
    run_alembic,
)


@pytest.mark.skipif(
    not os.path.exists("/app/alembic.ini"),
    reason="migration tests run inside backend container",
)
def test_alembic_heads_and_history():
    heads = run_alembic("heads")
    assert heads.returncode == 0, heads.stderr
    assert "v67_0" in heads.stdout and "(head)" in heads.stdout
    hist = run_alembic("history")
    assert hist.returncode == 0
    assert "v67_01_baseline_stamp" in hist.stdout
    assert "v67_02_fleet_policies" in hist.stdout
    assert "v67_03_fleet_accounts" in hist.stdout


@pytest.mark.skipif(
    not os.path.exists("/app/alembic.ini"),
    reason="migration tests run inside backend container",
)
def test_upgrade_downgrade_reupgrade_fleet_tables():
    reset_additive_fleet_schema_for_alembic()
    eng = migration_test_engine()
    stamp = run_alembic("stamp", "v67_01_baseline_stamp")
    assert stamp.returncode == 0, stamp.stderr + stamp.stdout

    up = run_alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr + up.stdout

    with eng.connect() as conn:
        for table in ("fleet_policies", "fleet_accounts"):
            exists = conn.execute(text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name=:t"
            ), {"t": table}).scalar()
            assert exists == 1, f"missing {table}"
        uq = conn.execute(text(
            "SELECT 1 FROM pg_constraint WHERE conname='uq_fleet_accounts_account_id'"
        )).scalar()
        assert uq == 1
        ck = conn.execute(text(
            "SELECT 1 FROM pg_constraint WHERE conname='ck_fleet_accounts_fleet_state'"
        )).scalar()
        assert ck == 1

    down = run_alembic("downgrade", "v67_01_baseline_stamp")
    assert down.returncode == 0, down.stderr + down.stdout

    with eng.connect() as conn:
        for table in ("fleet_policies", "fleet_accounts"):
            exists = conn.execute(text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name=:t"
            ), {"t": table}).scalar()
            assert exists is None, f"{table} should be dropped on downgrade"

    reup = run_alembic("upgrade", "head")
    assert reup.returncode == 0, reup.stderr + reup.stdout

    with eng.connect() as conn:
        exists = conn.execute(text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='fleet_accounts'"
        )).scalar()
        assert exists == 1
    eng.dispose()
