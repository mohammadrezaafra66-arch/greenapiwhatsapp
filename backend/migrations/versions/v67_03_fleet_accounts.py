"""v67_03_fleet_accounts — additive canonical fleet_accounts.

Revision ID: v67_03_fleet_accounts
Revises: v67_02_fleet_policies
Create Date: 2026-08-05

Idempotent: safe if create_all already created the table during hybrid period.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "v67_03_fleet_accounts"
down_revision: Union[str, None] = "v67_02_fleet_policies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATES = (
    "NEW", "PRECHECK", "QR_WAITING", "READY_TO_LINK", "AUTHORIZED_QUIET",
    "INBOUND_BUILDING", "BIDIRECTIONAL_BUILDING", "CONTROLLED_RAMP",
    "WARMUP_READY", "GRADUATION_TRIAL", "CAMPAIGN_READY", "MATURE",
    "MAINTENANCE", "AT_RISK", "PAUSED", "SUSPENDED", "BLOCKED",
    "FORCED_LOGOUT", "RECOVERY_COOLDOWN", "REWARM_REQUIRED", "FAILED", "RETIRED",
)


def upgrade() -> None:
    check = ", ".join(f"'{s}'" for s in _STATES)
    op.execute(f"""
    CREATE TABLE IF NOT EXISTS fleet_accounts (
        id UUID PRIMARY KEY,
        account_id UUID NOT NULL,
        fleet_state VARCHAR(40) NOT NULL DEFAULT 'NEW',
        journey_type VARCHAR(40),
        journey_profile_id UUID,
        policy_id UUID,
        risk_budget VARCHAR(40) NOT NULL DEFAULT 'NORMAL',
        cutover BOOLEAN NOT NULL DEFAULT false,
        registered_at TIMESTAMP WITHOUT TIME ZONE,
        linked_at TIMESTAMP WITHOUT TIME ZONE,
        first_real_inbound_at TIMESTAMP WITHOUT TIME ZONE,
        last_real_inbound_at TIMESTAMP WITHOUT TIME ZONE,
        first_real_outbound_at TIMESTAMP WITHOUT TIME ZONE,
        last_real_outbound_at TIMESTAMP WITHOUT TIME ZONE,
        campaign_ready_at TIMESTAMP WITHOUT TIME ZONE,
        mature_at TIMESTAMP WITHOUT TIME ZONE,
        next_action_at TIMESTAMP WITHOUT TIME ZONE,
        paused_reason TEXT,
        state_reason TEXT,
        state_changed_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
        version INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_fleet_accounts_account_id UNIQUE (account_id),
        CONSTRAINT ck_fleet_accounts_fleet_state CHECK (fleet_state IN ({check})),
        CONSTRAINT fk_fleet_accounts_account_id FOREIGN KEY (account_id)
            REFERENCES accounts(id) ON DELETE CASCADE,
        CONSTRAINT fk_fleet_accounts_policy_id FOREIGN KEY (policy_id)
            REFERENCES fleet_policies(id) ON DELETE SET NULL
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_fleet_accounts_fleet_state ON fleet_accounts (fleet_state)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fleet_accounts_cutover_state "
        "ON fleet_accounts (cutover, fleet_state)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_fleet_accounts_policy_id ON fleet_accounts (policy_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fleet_accounts_next_action_at ON fleet_accounts (next_action_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_fleet_accounts_next_action_at")
    op.execute("DROP INDEX IF EXISTS ix_fleet_accounts_policy_id")
    op.execute("DROP INDEX IF EXISTS ix_fleet_accounts_cutover_state")
    op.execute("DROP INDEX IF EXISTS ix_fleet_accounts_fleet_state")
    op.execute("DROP TABLE IF EXISTS fleet_accounts")
