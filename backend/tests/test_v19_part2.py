"""V19 PART 2 — group warm-up schema + manual link vault.

DB-free (matching the repo's style): asserts the three models register on Base.metadata
with the right columns and defaults, so create_all + the idempotent DDL will build them.
"""
from app.database import Base
from app.models.warmup_mesh import (
    WarmupGroupTarget, WarmupGroupMembership, WarmupLinkVault,
)


def test_models_registered_on_metadata():
    for t in ("warmup_group_target", "warmup_group_membership", "warmup_link_vault"):
        assert t in Base.metadata.tables


def test_group_target_columns_and_default():
    cols = {c.name for c in WarmupGroupTarget.__table__.columns}
    assert {"id", "warm_instance_id", "group_id", "group_subject", "is_selected", "created_at"} <= cols
    row = WarmupGroupTarget(warm_instance_id="WARM", group_id="120@g.us", group_subject="گروه")
    assert row.warm_instance_id == "WARM" and row.group_id == "120@g.us"
    # server/py default of is_selected is True (a selected target)
    assert WarmupGroupTarget.__table__.c.is_selected.default.arg is True


def test_membership_columns_and_defaults():
    cols = {c.name for c in WarmupGroupMembership.__table__.columns}
    assert {"id", "cold_instance_id", "warm_instance_id", "group_id", "status", "attempts",
            "last_attempt_at", "added_at", "error_reason", "created_at"} <= cols
    row = WarmupGroupMembership(cold_instance_id="COLD", warm_instance_id="WARM", group_id="120@g.us")
    assert row.cold_instance_id == "COLD"
    assert WarmupGroupMembership.__table__.c.status.default.arg == "pending"
    assert WarmupGroupMembership.__table__.c.attempts.default.arg == 0


def test_link_vault_columns():
    cols = {c.name for c in WarmupLinkVault.__table__.columns}
    assert {"id", "group_name", "invite_link", "notes", "created_at"} <= cols
    row = WarmupLinkVault(group_name="گروه عمومی", invite_link="https://chat.whatsapp.com/x", notes="یادداشت")
    assert row.invite_link.startswith("https://chat.whatsapp.com/")


def test_membership_status_values_documented():
    # the four statuses the scheduler uses
    for s in ("pending", "added", "failed", "skipped"):
        row = WarmupGroupMembership(cold_instance_id="C", warm_instance_id="W", group_id="g", status=s)
        assert row.status == s
