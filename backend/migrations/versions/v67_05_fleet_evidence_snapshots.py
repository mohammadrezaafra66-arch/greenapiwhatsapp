"""v67_05_fleet_evidence_snapshots — Phase 4 immutable evidence/score history.

Revision ID: v67_05_fleet_evidence_snapshots
Revises: v67_04_account_journeys
Create Date: 2026-08-05

Simulation-only scoring history. Does not alter fleet_accounts.fleet_state.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "v67_05_fleet_evidence_snapshots"
down_revision: Union[str, None] = "v67_04_account_journeys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RISK = ("NORMAL", "LOW", "MEDIUM", "HIGH", "CRITICAL")
_READY = ("NOT_READY", "READY_FOR_TRIAL", "READY_FOR_CAMPAIGN", "READY_FOR_MATURE")


def upgrade() -> None:
    risk = ", ".join(f"'{r}'" for r in _RISK)
    ready = ", ".join(f"'{r}'" for r in _READY)
    op.execute(f"""
    CREATE TABLE IF NOT EXISTS fleet_evidence_snapshots (
        id UUID PRIMARY KEY,
        account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        fleet_account_id UUID REFERENCES fleet_accounts(id) ON DELETE SET NULL,
        trust_score NUMERIC(6,2) NOT NULL,
        risk_score NUMERIC(6,2) NOT NULL,
        risk_level VARCHAR(20) NOT NULL,
        readiness_score NUMERIC(6,2) NOT NULL,
        readiness_label VARCHAR(40) NOT NULL,
        evidence_version VARCHAR(40) NOT NULL,
        evidence_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
        explanation_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
        calculated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
        simulation_only BOOLEAN NOT NULL DEFAULT true,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
        CONSTRAINT ck_fleet_evidence_risk_level CHECK (risk_level IN ({risk})),
        CONSTRAINT ck_fleet_evidence_readiness CHECK (readiness_label IN ({ready}))
    )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fleet_evidence_account_calc "
        "ON fleet_evidence_snapshots (account_id, calculated_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fleet_evidence_version "
        "ON fleet_evidence_snapshots (evidence_version)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_fleet_evidence_version")
    op.execute("DROP INDEX IF EXISTS ix_fleet_evidence_account_calc")
    op.execute("DROP TABLE IF EXISTS fleet_evidence_snapshots")
