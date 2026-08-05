"""V67 Phase 2 — migration upgrade/downgrade verification (dev/test DB only)."""
from __future__ import annotations
import os
import subprocess
import pytest


def _run_alembic(*args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    # Inside backend container SYNC_DATABASE_URL points at db host.
    return subprocess.run(
        ["alembic", *args],
        cwd="/app",
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.mark.skipif(
    not os.path.exists("/app/alembic.ini"),
    reason="migration tests run inside backend container",
)
def test_alembic_heads_and_history():
    heads = _run_alembic("heads")
    assert heads.returncode == 0, heads.stderr
    # Head advances with later phases; Phase 2 introduced v67_03, Phase 3 adds v67_04.
    assert "v67_03_fleet_accounts" in heads.stdout or "v67_04_account_journeys" in heads.stdout
    hist = _run_alembic("history")
    assert hist.returncode == 0
    assert "v67_01_baseline_stamp" in hist.stdout
    assert "v67_02_fleet_policies" in hist.stdout
    assert "v67_03_fleet_accounts" in hist.stdout


@pytest.mark.skipif(
    not os.path.exists("/app/alembic.ini"),
    reason="migration tests run inside backend container",
)
def test_upgrade_downgrade_reupgrade_fleet_tables():
    """Assumes DB already has baseline schema (create_all). Stamps baseline if needed."""
    # Ensure we are at least at baseline; if no version table, stamp baseline then upgrade.
    cur = _run_alembic("current")
    if cur.returncode != 0 or not cur.stdout.strip():
        stamp = _run_alembic("stamp", "v67_01_baseline_stamp")
        assert stamp.returncode == 0, stamp.stderr + stamp.stdout

    up = _run_alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr + up.stdout

    # Verify tables exist via SQLAlchemy
    from sqlalchemy import create_engine, text
    from app.config import settings
    eng = create_engine(settings.sync_database_url)
    with eng.connect() as conn:
        for table in ("fleet_policies", "fleet_accounts"):
            exists = conn.execute(text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name=:t"
            ), {"t": table}).scalar()
            assert exists == 1, f"missing {table}"
        # unique account_id
        uq = conn.execute(text(
            "SELECT 1 FROM pg_constraint WHERE conname='uq_fleet_accounts_account_id'"
        )).scalar()
        assert uq == 1
        # check constraint
        ck = conn.execute(text(
            "SELECT 1 FROM pg_constraint WHERE conname='ck_fleet_accounts_fleet_state'"
        )).scalar()
        assert ck == 1

    down = _run_alembic("downgrade", "v67_01_baseline_stamp")
    assert down.returncode == 0, down.stderr + down.stdout

    with eng.connect() as conn:
        for table in ("fleet_policies", "fleet_accounts"):
            exists = conn.execute(text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name=:t"
            ), {"t": table}).scalar()
            assert exists is None, f"{table} should be dropped on downgrade"

    reup = _run_alembic("upgrade", "head")
    assert reup.returncode == 0, reup.stderr + reup.stdout

    with eng.connect() as conn:
        exists = conn.execute(text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='fleet_accounts'"
        )).scalar()
        assert exists == 1
