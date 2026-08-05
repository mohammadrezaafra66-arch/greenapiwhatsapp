"""v67_01_baseline_stamp — empty baseline for existing schema.

Revision ID: v67_01_baseline_stamp
Revises:
Create Date: 2026-08-05

Represents the current create_all + main.py IF NOT EXISTS schema.
Upgrade/downgrade are no-ops. Existing databases should be stamped to this
revision before applying additive fleet migrations. Does not recreate tables.
"""
from typing import Sequence, Union

from alembic import op  # noqa: F401


revision: str = "v67_01_baseline_stamp"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Intentionally empty — current schema already exists via create_all / main.py DDL.
    pass


def downgrade() -> None:
    # Intentionally empty — baseline does not own existing tables.
    pass
