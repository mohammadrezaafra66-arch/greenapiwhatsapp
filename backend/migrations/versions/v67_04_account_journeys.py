"""v67_04_account_journeys — Phase 3 journey persistence (simulation/shadow).

Revision ID: v67_04_account_journeys
Revises: v67_03_fleet_accounts
Create Date: 2026-08-05
"""
from typing import Sequence, Union

from alembic import op

revision: str = "v67_04_account_journeys"
down_revision: Union[str, None] = "v67_03_fleet_accounts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATES = (
    "NEW", "PRECHECK", "QR_WAITING", "READY_TO_LINK", "AUTHORIZED_QUIET",
    "INBOUND_BUILDING", "BIDIRECTIONAL_BUILDING", "CONTROLLED_RAMP",
    "WARMUP_READY", "GRADUATION_TRIAL", "CAMPAIGN_READY", "MATURE",
    "MAINTENANCE", "AT_RISK", "PAUSED", "SUSPENDED", "BLOCKED",
    "FORCED_LOGOUT", "RECOVERY_COOLDOWN", "REWARM_REQUIRED", "FAILED", "RETIRED",
)
_JOURNEY_STATUS = ("ACTIVE", "PAUSED", "COMPLETED", "FAILED", "SIMULATING", "CANCELLED")
_ACTION_STATUS = ("PLANNED", "CLAIMED", "SKIPPED", "CANCELLED", "SIMULATED")
_ACTION_TYPES = (
    "WAIT", "VERIFY_STATE", "VERIFY_SETTINGS", "REQUEST_INBOUND", "PREPARE_REPLY",
    "CHECK_EVIDENCE", "CHECK_QUEUE", "CHECK_WEBHOOK", "REEVALUATE", "PAUSE",
    "REQUIRE_OWNER_REVIEW",
)


def upgrade() -> None:
    states = ", ".join(f"'{s}'" for s in _STATES)
    jstatus = ", ".join(f"'{s}'" for s in _JOURNEY_STATUS)
    astatus = ", ".join(f"'{s}'" for s in _ACTION_STATUS)
    atypes = ", ".join(f"'{s}'" for s in _ACTION_TYPES)

    op.execute(f"""
    CREATE TABLE IF NOT EXISTS account_journeys (
        id UUID PRIMARY KEY,
        account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        fleet_account_id UUID NOT NULL REFERENCES fleet_accounts(id) ON DELETE CASCADE,
        journey_type VARCHAR(40) NOT NULL,
        profile_policy_id UUID REFERENCES fleet_policies(id) ON DELETE SET NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'SIMULATING',
        current_state VARCHAR(40) NOT NULL,
        started_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
        state_changed_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
        completed_at TIMESTAMP WITHOUT TIME ZONE,
        paused_at TIMESTAMP WITHOUT TIME ZONE,
        failure_reason TEXT,
        policy_snapshot JSONB NOT NULL DEFAULT '{{}}'::jsonb,
        evidence_snapshot JSONB NOT NULL DEFAULT '{{}}'::jsonb,
        simulation_only BOOLEAN NOT NULL DEFAULT true,
        shadow_mode BOOLEAN NOT NULL DEFAULT true,
        version INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
        CONSTRAINT ck_account_journeys_status CHECK (status IN ({jstatus})),
        CONSTRAINT ck_account_journeys_current_state CHECK (current_state IN ({states}))
    )
    """)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_account_journeys_one_active "
        "ON account_journeys (fleet_account_id) "
        "WHERE status IN ('ACTIVE', 'PAUSED', 'SIMULATING')"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_account_journeys_account_id ON account_journeys (account_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_account_journeys_status ON account_journeys (status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_account_journeys_current_state ON account_journeys (current_state)")

    op.execute(f"""
    CREATE TABLE IF NOT EXISTS journey_actions (
        id UUID PRIMARY KEY,
        journey_id UUID NOT NULL REFERENCES account_journeys(id) ON DELETE CASCADE,
        account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
        action_type VARCHAR(40) NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'PLANNED',
        scheduled_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        claimed_at TIMESTAMP WITHOUT TIME ZONE,
        executed_at TIMESTAMP WITHOUT TIME ZONE,
        skipped_at TIMESTAMP WITHOUT TIME ZONE,
        idempotency_key VARCHAR(200) NOT NULL,
        source_type VARCHAR(40) NOT NULL DEFAULT 'simulation',
        target_reference VARCHAR(200),
        payload_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
        result_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
        error_code VARCHAR(80),
        simulation_only BOOLEAN NOT NULL DEFAULT true,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_journey_actions_idempotency UNIQUE (idempotency_key),
        CONSTRAINT ck_journey_actions_status CHECK (status IN ({astatus})),
        CONSTRAINT ck_journey_actions_type CHECK (action_type IN ({atypes}))
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_journey_actions_journey_id ON journey_actions (journey_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_journey_actions_due ON journey_actions (status, scheduled_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_journey_actions_account_id ON journey_actions (account_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS journey_actions")
    op.execute("DROP INDEX IF EXISTS uq_account_journeys_one_active")
    op.execute("DROP INDEX IF EXISTS ix_account_journeys_account_id")
    op.execute("DROP INDEX IF EXISTS ix_account_journeys_status")
    op.execute("DROP INDEX IF EXISTS ix_account_journeys_current_state")
    op.execute("DROP TABLE IF EXISTS account_journeys")
