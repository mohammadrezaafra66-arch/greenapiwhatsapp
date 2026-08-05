"""v67_02_fleet_policies — additive fleet policy storage.

Revision ID: v67_02_fleet_policies
Revises: v67_01_baseline_stamp
Create Date: 2026-08-05

Idempotent: safe if create_all already created the table during hybrid period.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "v67_02_fleet_policies"
down_revision: Union[str, None] = "v67_01_baseline_stamp"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS fleet_policies (
        id UUID PRIMARY KEY,
        name VARCHAR(80) NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        is_active BOOLEAN NOT NULL DEFAULT true,
        is_default BOOLEAN NOT NULL DEFAULT false,
        policy_type VARCHAR(40) NOT NULL DEFAULT 'CONSERVATIVE',
        settings_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_fleet_policies_name_version UNIQUE (name, version)
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_fleet_policies_active ON fleet_policies (is_active)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_fleet_policies_one_default "
        "ON fleet_policies (is_default) WHERE is_default IS TRUE"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_fleet_policies_one_default")
    op.execute("DROP INDEX IF EXISTS ix_fleet_policies_active")
    op.execute("DROP TABLE IF EXISTS fleet_policies")
