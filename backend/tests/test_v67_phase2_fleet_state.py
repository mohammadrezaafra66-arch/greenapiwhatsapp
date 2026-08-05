"""V67 Phase 2 — FleetState adapter, policy, seed mapping (no DB / no Green API)."""
from __future__ import annotations
import pytest

from app.services.fleet_state import FleetState, FLEET_STATE_VALUES, SEED_FORBIDDEN_AUTO_STATES
from app.services.fleet_state_adapter import FleetStateAdapter, SensorSnapshot
from app.services.fleet_policy_defaults import (
    CONSERVATIVE_RAMP_CURVE, CONSERVATIVE_POLICY_SETTINGS, validate_policy_settings,
)
from app.services.warmup_state import WarmupState


EXPECTED_STATES = {
    "NEW", "PRECHECK", "QR_WAITING", "READY_TO_LINK", "AUTHORIZED_QUIET",
    "INBOUND_BUILDING", "BIDIRECTIONAL_BUILDING", "CONTROLLED_RAMP",
    "WARMUP_READY", "GRADUATION_TRIAL", "CAMPAIGN_READY", "MATURE",
    "MAINTENANCE", "AT_RISK", "PAUSED", "SUSPENDED", "BLOCKED",
    "FORCED_LOGOUT", "RECOVERY_COOLDOWN", "REWARM_REQUIRED", "FAILED", "RETIRED",
}


def test_fleet_state_enum_complete():
    assert set(FLEET_STATE_VALUES) == EXPECTED_STATES
    assert len(FLEET_STATE_VALUES) == 22


def test_day10_maturing_maps_warmup_ready_not_campaign():
    r = FleetStateAdapter().derive(SensorSnapshot(
        account_status="active", live_state="authorized",
        warmup_state=WarmupState.MATURING.value,
    ), for_seed=True)
    assert r.recommended == FleetState.WARMUP_READY.value
    assert "campaign" not in r.recommended.lower() or r.recommended == FleetState.WARMUP_READY.value


def test_legacy_graduated_maps_warmup_ready_never_campaign():
    r = FleetStateAdapter().derive(SensorSnapshot(
        account_status="active", live_state="authorized",
        warmup_state=WarmupState.GRADUATED.value,
    ), for_seed=True)
    assert r.recommended == FleetState.WARMUP_READY.value
    assert r.recommended not in SEED_FORBIDDEN_AUTO_STATES
    assert any("GRADUATED" in m for m in r.mismatches)


def test_no_automatic_campaign_ready_or_mature():
    for warmup in (WarmupState.GRADUATED.value, WarmupState.MATURING.value, None):
        r = FleetStateAdapter().derive(SensorSnapshot(
            account_status="active", live_state="authorized", warmup_state=warmup,
            days_active=30, has_real_inbound=True, has_real_outbound=True,
        ), for_seed=True)
        assert r.recommended not in SEED_FORBIDDEN_AUTO_STATES


def test_suspended_blocked_forced_logout_precedence():
    a = FleetStateAdapter()
    assert a.derive(SensorSnapshot(
        account_status="active", live_state="suspended",
    )).recommended == FleetState.SUSPENDED.value
    assert a.derive(SensorSnapshot(
        account_status="banned", live_state="authorized",
    )).recommended == FleetState.BLOCKED.value
    assert a.derive(SensorSnapshot(
        account_status="active", live_state="authorized",
        open_incidents=["forced_logout"],
    )).recommended == FleetState.FORCED_LOGOUT.value
    assert a.rewarm_required_after_major("blocked") == FleetState.BLOCKED.value
    assert a.rewarm_required_after_major("suspended") == FleetState.SUSPENDED.value


def test_unsafe_and_incident_precedence_over_warmup():
    r = FleetStateAdapter().derive(SensorSnapshot(
        account_status="active", live_state="authorized",
        warmup_state=WarmupState.GRADUATED.value,
        open_incidents=["suspended"],
    ), for_seed=True)
    assert r.recommended == FleetState.SUSPENDED.value


def test_ambiguous_active_conservative():
    r = FleetStateAdapter().derive(SensorSnapshot(
        account_status="active", live_state="authorized",
    ), for_seed=True)
    assert r.recommended in (
        FleetState.AUTHORIZED_QUIET.value, FleetState.PRECHECK.value,
        FleetState.INBOUND_BUILDING.value, FleetState.BIDIRECTIONAL_BUILDING.value,
    )
    assert r.recommended not in SEED_FORBIDDEN_AUTO_STATES


def test_retired_terminal():
    r = FleetStateAdapter().derive(SensorSnapshot(account_status="green_api_deleted"))
    assert r.recommended == FleetState.RETIRED.value


def test_policy_validation_and_ramp():
    assert CONSERVATIVE_RAMP_CURVE == [12, 20, 32, 48, 66, 84, 100]
    ok, msg = validate_policy_settings(CONSERVATIVE_POLICY_SETTINGS)
    assert ok and msg == "ok"
    assert CONSERVATIVE_POLICY_SETTINGS["flow_metric"] == "incoming_plus_outgoing"
    bad, _ = validate_policy_settings({"flow_metric": "outbound_only"})
    assert bad is False


def test_seed_idempotent_mapping_stable():
    sensors = SensorSnapshot(
        account_status="active", live_state="authorized",
        warmup_state=WarmupState.RAMPING.value,
    )
    a = FleetStateAdapter()
    r1 = a.derive(sensors, for_seed=True)
    r2 = a.derive(sensors, for_seed=True)
    assert r1.recommended == r2.recommended == FleetState.CONTROLLED_RAMP.value
