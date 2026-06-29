"""Alembic environment for Afrakala WhatsApp Sender.

Tables are normally auto-created on app startup via Base.metadata.create_all,
so migrations are optional. This env wires Alembic to the same models in case
you want to manage schema changes explicitly.
"""
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Import models so their metadata is registered on Base.
from app.config import settings
from app.database import Base
import app.models  # noqa: F401  (registers all models)

config = context.config

# Prefer the configured sync URL (env var wins).
sync_url = os.getenv("SYNC_DATABASE_URL", settings.sync_database_url)
config.set_main_option("sqlalchemy.url", sync_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
