"""v67_06_fleet_plan_snapshots — optional Phase 5 simulation plan history.

Revision ID: v67_06_fleet_plan_snapshots
Revises: v67_05_fleet_evidence_snapshots
Create Date: 2026-08-05

Append-only simulation plan records. Never executes plans.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "v67_06_fleet_plan_snapshots"
down_revision: Union[str, None] = "v67_05_fleet_evidence_snapshots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS fleet_plan_snapshots (
        id UUID PRIMARY KEY,
        plan_type VARCHAR(40) NOT NULL,
        payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        planner_version VARCHAR(40) NOT NULL,
        simulation_only BOOLEAN NOT NULL DEFAULT true,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
    )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fleet_plan_snapshots_type_created "
        "ON fleet_plan_snapshots (plan_type, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_fleet_plan_snapshots_type_created")
    op.execute("DROP TABLE IF EXISTS fleet_plan_snapshots")
