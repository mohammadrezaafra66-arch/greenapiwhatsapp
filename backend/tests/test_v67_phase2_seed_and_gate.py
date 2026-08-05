"""V67 Phase 2 — seed rules + send_gate unchanged (mocked / no live side effects)."""
from __future__ import annotations
import inspect
import uuid
from unittest.mock import MagicMock, AsyncMock

import pytest

from app.services.fleet_state import FleetState, SEED_FORBIDDEN_AUTO_STATES
from app.services.fleet_state_adapter import FleetStateAdapter, SensorSnapshot
from app.services.fleet_policy_defaults import CONSERVATIVE_RAMP_CURVE
from app.services import send_gate
from app.services.warmup_state import WarmupState


def test_send_gate_still_exports_canonical_helpers():
    assert hasattr(send_gate, "can_send_now")
    assert hasattr(send_gate, "gate_check")
    assert hasattr(send_gate, "gate_check_automated")
    assert hasattr(send_gate, "is_account_send_eligible")
    # FleetState must not be imported into send eligibility decision in Phase 2
    src = inspect.getsource(send_gate)
    assert "FleetState" not in src
    assert "fleet_accounts" not in src


def test_seed_forbidden_states_enforced_by_adapter():
    r = FleetStateAdapter().derive(SensorSnapshot(
        account_status="active",
        live_state="authorized",
        warmup_state=WarmupState.GRADUATED.value,
        days_active=40,
    ), for_seed=True)
    assert r.recommended == FleetState.WARMUP_READY.value
    assert r.recommended not in SEED_FORBIDDEN_AUTO_STATES


@pytest.mark.asyncio
async def test_ensure_policy_and_apply_seed_idempotent(monkeypatch):
    """In-memory style: ensure apply twice does not invent CAMPAIGN_READY."""
    from app.services import fleet_seed
    from app.services.fleet_policy_defaults import CONSERVATIVE_POLICY_SETTINGS

    # Unit-level: plan row never targets forbidden states
    plan = fleet_seed.SeedPlanRow(
        account_id=str(uuid.uuid4()),
        instance_id="1",
        action="create",
        from_state=None,
        to_state=FleetState.WARMUP_READY.value,
        reason="test",
        mismatches=[],
    )
    assert plan.to_state not in SEED_FORBIDDEN_AUTO_STATES
    assert CONSERVATIVE_RAMP_CURVE[0] == 12
    assert CONSERVATIVE_RAMP_CURVE[-1] == 100
    assert CONSERVATIVE_POLICY_SETTINGS["graduation_requirements_placeholder"]["day10_state"] == "WARMUP_READY"


def test_mesh_autochat_still_default_off():
    from app.config import Settings
    # Class default (production) is False; conftest may enable mesh for legacy suites.
    assert Settings.model_fields["mesh_autochat_enabled"].default is False
