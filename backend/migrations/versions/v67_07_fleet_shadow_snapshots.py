"""v67_07_fleet_shadow_snapshots — Phase 7 observational Shadow history (D-P7-09).

Revision ID: v67_07_fleet_shadow_snapshots
Revises: v67_06_fleet_plan_snapshots
Create Date: 2026-08-05

Additive reversible. Never executes sends. simulation_only forced true.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "v67_07_fleet_shadow_snapshots"
down_revision: Union[str, None] = "v67_06_fleet_plan_snapshots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS fleet_shadow_snapshots (
        id UUID PRIMARY KEY,
        run_id UUID NOT NULL,
        account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        fleet_account_id UUID NOT NULL REFERENCES fleet_accounts(id) ON DELETE CASCADE,
        observed_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        scheduled_slot TIMESTAMP WITHOUT TIME ZONE,
        source VARCHAR(40) NOT NULL,
        shadow_version VARCHAR(40) NOT NULL,
        policy_id UUID,
        policy_version INTEGER,
        legacy_state VARCHAR(80),
        canonical_fleet_state VARCHAR(40),
        adapter_recommended_state VARCHAR(40),
        journey_recommended_state VARCHAR(40),
        trust_score DOUBLE PRECISION,
        risk_level VARCHAR(20),
        readiness_label VARCHAR(40),
        daily_capacity INTEGER,
        recommended_usage INTEGER,
        eligibility_decision VARCHAR(60),
        legacy_eligibility VARCHAR(80),
        mismatch_class VARCHAR(40) NOT NULL,
        severity VARCHAR(20) NOT NULL,
        reason_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
        missing_evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
        sensor_versions JSONB NOT NULL DEFAULT '{}'::jsonb,
        sensor_freshness JSONB NOT NULL DEFAULT '{}'::jsonb,
        legacy_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
        v67_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
        comparison_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
        dangerous_threshold_status VARCHAR(20) NOT NULL DEFAULT 'UNRATIFIED',
        simulation_only BOOLEAN NOT NULL DEFAULT true,
        mutates_runtime BOOLEAN NOT NULL DEFAULT false,
        executes BOOLEAN NOT NULL DEFAULT false,
        idempotency_key VARCHAR(200) NOT NULL,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_fleet_shadow_snapshots_idempotency UNIQUE (idempotency_key),
        CONSTRAINT ck_fleet_shadow_mismatch_class CHECK (mismatch_class IN (
            'MATCH','SAFE_MISMATCH','DANGEROUS_MISMATCH','INSUFFICIENT_EVIDENCE',
            'LEGACY_MORE_PERMISSIVE','V67_MORE_PERMISSIVE','POLICY_VERSION_MISMATCH',
            'SENSOR_STALE','RUNTIME_UNKNOWN'
        )),
        CONSTRAINT ck_fleet_shadow_severity CHECK (severity IN (
            'INFO','LOW','MEDIUM','HIGH','CRITICAL'
        )),
        CONSTRAINT ck_fleet_shadow_threshold_status CHECK (
            dangerous_threshold_status IN ('UNRATIFIED')
        ),
        CONSTRAINT ck_fleet_shadow_simulation_only CHECK (simulation_only IS TRUE),
        CONSTRAINT ck_fleet_shadow_mutates_runtime CHECK (mutates_runtime IS FALSE),
        CONSTRAINT ck_fleet_shadow_executes CHECK (executes IS FALSE)
    )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fleet_shadow_account_observed "
        "ON fleet_shadow_snapshots (account_id, observed_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fleet_shadow_fleet_account_observed "
        "ON fleet_shadow_snapshots (fleet_account_id, observed_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fleet_shadow_mismatch_observed "
        "ON fleet_shadow_snapshots (mismatch_class, observed_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fleet_shadow_severity_observed "
        "ON fleet_shadow_snapshots (severity, observed_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fleet_shadow_run_id "
        "ON fleet_shadow_snapshots (run_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fleet_shadow_policy_version "
        "ON fleet_shadow_snapshots (policy_version)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fleet_shadow_threshold_status "
        "ON fleet_shadow_snapshots (dangerous_threshold_status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fleet_shadow_high_critical "
        "ON fleet_shadow_snapshots (observed_at DESC) "
        "WHERE severity IN ('HIGH','CRITICAL')"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_fleet_shadow_high_critical")
    op.execute("DROP INDEX IF EXISTS ix_fleet_shadow_threshold_status")
    op.execute("DROP INDEX IF EXISTS ix_fleet_shadow_policy_version")
    op.execute("DROP INDEX IF EXISTS ix_fleet_shadow_run_id")
    op.execute("DROP INDEX IF EXISTS ix_fleet_shadow_severity_observed")
    op.execute("DROP INDEX IF EXISTS ix_fleet_shadow_mismatch_observed")
    op.execute("DROP INDEX IF EXISTS ix_fleet_shadow_fleet_account_observed")
    op.execute("DROP INDEX IF EXISTS ix_fleet_shadow_account_observed")
    op.execute("DROP TABLE IF EXISTS fleet_shadow_snapshots")
