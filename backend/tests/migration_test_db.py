"""Disposable migration-test database helpers (never ENV-A whatsapp_sender)."""
from __future__ import annotations

import os
import subprocess
from typing import Dict

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import settings
from app.database import Base
import app.models  # noqa: F401
from app.services.migration_db_guard import (
    DEFAULT_MIGRATION_TEST_DB_NAME,
    assert_migration_test_target_allowed,
    database_name_from_url,
    replace_database_in_url,
)


def migration_test_database_url() -> str:
    explicit = os.getenv("V67_MIGRATION_TEST_DATABASE_URL", "").strip()
    if explicit:
        assert_migration_test_target_allowed(explicit)
        return explicit
    base = os.getenv("SYNC_DATABASE_URL", settings.sync_database_url)
    name = os.getenv("V67_MIGRATION_TEST_DB_NAME", DEFAULT_MIGRATION_TEST_DB_NAME).strip()
    url = replace_database_in_url(base, name)
    assert_migration_test_target_allowed(url)
    return url


def _admin_url_for(url: str) -> str:
    return replace_database_in_url(url, "postgres")


def ensure_migration_test_database() -> str:
    """Create disposable DB if needed and bootstrap baseline schema via create_all."""
    url = migration_test_database_url()
    db_name = database_name_from_url(url)
    admin = create_engine(_admin_url_for(url), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"),
            {"n": db_name},
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    admin.dispose()

    eng = create_engine(url)
    with eng.connect() as conn:
        has_accounts = conn.execute(text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='accounts'"
        )).scalar()
    if not has_accounts:
        # Bootstrap legacy baseline once; Alembic owns additive fleet_* revisions after that.
        Base.metadata.create_all(eng)
    eng.dispose()
    return url


_FLEET_ADDITIVE_TABLES = (
    "fleet_shadow_snapshots",
    "fleet_plan_snapshots",
    "fleet_evidence_snapshots",
    "journey_actions",
    "account_journeys",
    "fleet_accounts",
    "fleet_policies",
)


def reset_additive_fleet_schema_for_alembic() -> str:
    """Drop Alembic-owned fleet tables so upgrade recreates constraints correctly.

    Leaves legacy baseline tables (e.g. accounts) intact. Never touches ENV-A.
    """
    url = ensure_migration_test_database()
    assert_migration_test_target_allowed(url)
    eng = create_engine(url)
    with eng.begin() as conn:
        for table in _FLEET_ADDITIVE_TABLES:
            conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    eng.dispose()
    return url


def migration_test_engine() -> Engine:
    url = ensure_migration_test_database()
    return create_engine(url)


def alembic_env_for_migration_tests() -> Dict[str, str]:
    url = ensure_migration_test_database()
    env = os.environ.copy()
    env["SYNC_DATABASE_URL"] = url
    # Ensure app.config settings reload path also sees the disposable URL if imported fresh.
    env["V67_MIGRATION_TEST_DATABASE_URL"] = url
    # Never allow ENV-A override during tests.
    env.pop("V67_ALLOW_ENV_A_ALEMBIC_DOWNGRADE", None)
    return env


def run_alembic(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["alembic", *args],
        cwd="/app",
        capture_output=True,
        text=True,
        env=alembic_env_for_migration_tests(),
    )
