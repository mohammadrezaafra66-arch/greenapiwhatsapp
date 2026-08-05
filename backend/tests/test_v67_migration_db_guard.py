"""V67 — ENV-A migration-test isolation guards."""
from __future__ import annotations

import os

import pytest

from app.services.migration_db_guard import (
    DEFAULT_MIGRATION_TEST_DB_NAME,
    assert_alembic_downgrade_allowed,
    assert_migration_test_target_allowed,
    database_name_from_url,
    is_env_a_protected_database,
    replace_database_in_url,
)


def test_database_name_parsing_and_protection():
    url = "postgresql://afrakala:password@db:5432/whatsapp_sender"
    assert database_name_from_url(url) == "whatsapp_sender"
    assert is_env_a_protected_database(url) is True
    mig = replace_database_in_url(url, DEFAULT_MIGRATION_TEST_DB_NAME)
    assert database_name_from_url(mig) == DEFAULT_MIGRATION_TEST_DB_NAME
    assert is_env_a_protected_database(mig) is False


def test_migration_tests_refuse_env_a_url():
    with pytest.raises(RuntimeError, match="must not target ENV-A"):
        assert_migration_test_target_allowed(
            "postgresql://afrakala:password@db:5432/whatsapp_sender"
        )


def test_downgrade_refuses_env_a_without_override(monkeypatch):
    monkeypatch.delenv("V67_ALLOW_ENV_A_ALEMBIC_DOWNGRADE", raising=False)
    with pytest.raises(RuntimeError, match="Refusing Alembic downgrade"):
        assert_alembic_downgrade_allowed(
            "postgresql://afrakala:password@db:5432/whatsapp_sender"
        )


def test_downgrade_allows_env_a_with_explicit_override(monkeypatch):
    monkeypatch.setenv("V67_ALLOW_ENV_A_ALEMBIC_DOWNGRADE", "1")
    assert_alembic_downgrade_allowed(
        "postgresql://afrakala:password@db:5432/whatsapp_sender"
    )


def test_downgrade_allows_migtest_without_override(monkeypatch):
    monkeypatch.delenv("V67_ALLOW_ENV_A_ALEMBIC_DOWNGRADE", raising=False)
    assert_alembic_downgrade_allowed(
        f"postgresql://afrakala:password@db:5432/{DEFAULT_MIGRATION_TEST_DB_NAME}"
    )


@pytest.mark.skipif(not os.path.exists("/app/alembic.ini"), reason="container only")
def test_alembic_cli_downgrade_env_a_fails_closed(monkeypatch):
    import subprocess

    monkeypatch.delenv("V67_ALLOW_ENV_A_ALEMBIC_DOWNGRADE", raising=False)
    env = os.environ.copy()
    env["SYNC_DATABASE_URL"] = "postgresql://afrakala:password@db:5432/whatsapp_sender"
    env.pop("V67_ALLOW_ENV_A_ALEMBIC_DOWNGRADE", None)
    proc = subprocess.run(
        ["alembic", "downgrade", "-1"],
        cwd="/app",
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode != 0
    blob = (proc.stderr or "") + (proc.stdout or "")
    assert "Refusing Alembic downgrade" in blob or "protected ENV-A" in blob
