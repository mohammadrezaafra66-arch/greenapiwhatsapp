"""Protect PRODUCTION_LIKE ENV-A from destructive Alembic downgrades.

Observation DB (whatsapp_sender) must never be used as the migration-test target.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

# Compose ENV-A primary database name (D-SE-01).
ENV_A_PROTECTED_DB_NAMES = frozenset(
    {
        "whatsapp_sender",
    }
)

DEFAULT_MIGRATION_TEST_DB_NAME = "whatsapp_sender_migtest"
ALLOW_ENV_A_DOWNGRADE_ENV = "V67_ALLOW_ENV_A_ALEMBIC_DOWNGRADE"


def database_name_from_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    name = (parsed.path or "").lstrip("/")
    # Strip query fragments if any driver embeds them oddly.
    return name.split("?")[0].strip()


def is_env_a_protected_database(url: str) -> bool:
    return database_name_from_url(url) in ENV_A_PROTECTED_DB_NAMES


def env_a_downgrade_explicitly_allowed() -> bool:
    return os.getenv(ALLOW_ENV_A_DOWNGRADE_ENV, "").strip() == "1"


def assert_alembic_downgrade_allowed(url: str) -> None:
    """Fail closed: refuse downgrade against ENV-A unless explicitly overridden."""
    if not is_env_a_protected_database(url):
        return
    if env_a_downgrade_explicitly_allowed():
        return
    db = database_name_from_url(url)
    raise RuntimeError(
        f"Refusing Alembic downgrade against protected ENV-A database {db!r}. "
        f"Use disposable migration-test DB ({DEFAULT_MIGRATION_TEST_DB_NAME}) "
        f"or set {ALLOW_ENV_A_DOWNGRADE_ENV}=1 only for authorized emergency ops."
    )


def assert_migration_test_target_allowed(url: str) -> None:
    """Fail closed: migration round-trip tests must never target ENV-A."""
    if is_env_a_protected_database(url):
        db = database_name_from_url(url)
        raise RuntimeError(
            f"Migration tests must not target ENV-A database {db!r}. "
            f"Configure V67_MIGRATION_TEST_DATABASE_URL to "
            f"{DEFAULT_MIGRATION_TEST_DB_NAME} (or another disposable DB)."
        )


def replace_database_in_url(url: str, database_name: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(path=f"/{database_name}").geturl()
