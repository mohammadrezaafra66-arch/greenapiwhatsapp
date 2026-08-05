"""V67 Phase 3 — pure transition engine unit tests (no DB / no Green API)."""
from __future__ import annotations
from datetime import datetime, timedelta

from app.services.journey_transition import evaluate_transition
from app.services.fleet_state import FleetState, SEED_FORBIDDEN_AUTO_STATES
from app.services.fleet_policy_defaults import CONSERVATIVE_POLICY_SETTINGS
from app.services.journey_types import JourneyType, JourneyActionType

NOW = datetime(2026, 8, 5, 12, 0, 0)
POL = {"name": "CONSERVATIVE", "version": 1, "settings_json": dict(CONSERVATIVE_POLICY_SETTINGS)}


def _ev(**kw):
    base = {"journey_started_at": NOW - timedelta(hours=48), "registered_at": NOW - timedelta(hours=48)}
    base.update(kw)
    return base


def test_new_to_precheck():
    d = evaluate_transition("NEW", JourneyType.NEW_ACCOUNT.value, POL, {}, "notauthorized", [], False, NOW)
    assert d.allowed and d.recommended_next_state == "PRECHECK"


def test_precheck_blocked_missing_flag():
    d = evaluate_transition("PRECHECK", JourneyType.NEW_ACCOUNT.value, POL,
                            {"precheck_ok": False}, None, [], False, NOW)
    assert not d.allowed and "precheck_ok" in d.missing_evidence


def test_precheck_to_qr():
    d = evaluate_transition("PRECHECK", JourneyType.NEW_ACCOUNT.value, POL, {}, None, [], False, NOW)
    assert d.allowed and d.recommended_next_state == "QR_WAITING"


def test_qr_wait_incomplete():
    d = evaluate_transition("QR_WAITING", JourneyType.NEW_ACCOUNT.value, POL,
                            {"journey_started_at": NOW - timedelta(hours=1)}, None, [], False, NOW)
    assert not d.allowed and d.required_wait_seconds and d.required_wait_seconds > 0


def test_qr_wait_complete():
    d = evaluate_transition("QR_WAITING", JourneyType.NEW_ACCOUNT.value, POL, _ev(), None, [], False, NOW)
    assert d.allowed and d.recommended_next_state == "READY_TO_LINK"


def test_authorized_quiet_and_inbound():
    d = evaluate_transition("READY_TO_LINK", JourneyType.NEW_ACCOUNT.value, POL,
                            {"linked": True}, "authorized", [], False, NOW)
    assert d.allowed and d.recommended_next_state == "AUTHORIZED_QUIET"
    d2 = evaluate_transition("AUTHORIZED_QUIET", JourneyType.NEW_ACCOUNT.value, POL,
                             {"linked_at": NOW - timedelta(hours=2)}, "authorized", [], False, NOW)
    assert d2.allowed and d2.recommended_next_state == "INBOUND_BUILDING"


def test_inbound_and_bidirectional_evidence():
    d = evaluate_transition("INBOUND_BUILDING", JourneyType.NEW_ACCOUNT.value, POL, {}, "authorized", [], False, NOW)
    assert not d.allowed and "first_real_inbound" in d.missing_evidence
    d2 = evaluate_transition("INBOUND_BUILDING", JourneyType.NEW_ACCOUNT.value, POL,
                             {"has_real_inbound": True}, "authorized", [], False, NOW)
    assert d2.allowed and d2.recommended_next_state == "BIDIRECTIONAL_BUILDING"
    d3 = evaluate_transition("BIDIRECTIONAL_BUILDING", JourneyType.NEW_ACCOUNT.value, POL,
                             {"has_real_outbound": True}, "authorized", [], False, NOW)
    assert d3.allowed and d3.recommended_next_state == "CONTROLLED_RAMP"


def test_day10_to_warmup_ready_never_campaign_or_mature():
    d = evaluate_transition("CONTROLLED_RAMP", JourneyType.NEW_ACCOUNT.value, POL,
                            {"day10_complete": True, "total_flow": 100,
                             "real_inbound_count": 50, "real_outbound_count": 50},
                            "authorized", [], False, NOW)
    assert d.allowed and d.recommended_next_state == FleetState.WARMUP_READY.value
    assert d.recommended_next_state not in SEED_FORBIDDEN_AUTO_STATES
    d2 = evaluate_transition("WARMUP_READY", JourneyType.NEW_ACCOUNT.value, POL, {}, "authorized", [], False, NOW)
    assert d2.recommended_next_state == "WARMUP_READY"
    assert not d2.allowed


def test_connected_at_alone_insufficient_for_inbound_skip():
    d = evaluate_transition("INBOUND_BUILDING", JourneyType.NEW_ACCOUNT.value, POL,
                            {"connected_at_only_claim": True, "connected_at": NOW.isoformat()},
                            "authorized", [], False, NOW)
    assert not d.allowed


def test_incident_and_breaker_precedence():
    for state, live, incidents, expect in [
        ("CONTROLLED_RAMP", "suspended", [], "SUSPENDED"),
        ("CONTROLLED_RAMP", "blocked", [], "BLOCKED"),
        ("CONTROLLED_RAMP", "authorized", ["forced_logout"], "FORCED_LOGOUT"),
        ("CONTROLLED_RAMP", "authorized", ["device_restriction"], "FORCED_LOGOUT"),
    ]:
        d = evaluate_transition(state, JourneyType.NEW_ACCOUNT.value, POL, {}, live, incidents, False, NOW)
        assert d.recommended_next_state == expect
        assert not d.allowed
    d = evaluate_transition("CONTROLLED_RAMP", JourneyType.NEW_ACCOUNT.value, POL, {}, "authorized", [], True, NOW)
    assert d.recommended_next_state == "PAUSED"


def test_missing_and_invalid_policy_fail_closed():
    d = evaluate_transition("NEW", JourneyType.NEW_ACCOUNT.value, None, {}, None, [], False, NOW)
    assert not d.allowed
    assert "missing_policy" in d.reason_codes
    bad = {"version": 1, "settings_json": {"flow_metric": "outbound_only", "ramp_curve": [1, 2]}}
    d2 = evaluate_transition("NEW", JourneyType.NEW_ACCOUNT.value, bad, {}, None, [], False, NOW)
    assert not d2.allowed


def test_total_flow_is_inbound_plus_outbound_semantics():
    settings = dict(CONSERVATIVE_POLICY_SETTINGS)
    assert settings["flow_metric"] == "incoming_plus_outgoing"
    d = evaluate_transition(
        "CONTROLLED_RAMP", JourneyType.NEW_ACCOUNT.value, POL,
        {"ramp_day_index": 0, "real_inbound_count": 5, "real_outbound_count": 5, "total_flow": 10},
        "authorized", [], False, NOW,
    )
    # below progressing to day10 — stay on ramp
    assert d.recommended_next_state == "CONTROLLED_RAMP"


def test_rewarm_path_and_no_forbidden_actions():
    d = evaluate_transition("REWARM_REQUIRED", JourneyType.REWARM.value, POL, {}, "notauthorized", [], False, NOW)
    assert d.recommended_next_state == "PRECHECK"
    assert JourneyActionType.WAIT.value in d.planned_action_types or JourneyActionType.VERIFY_STATE.value in d.planned_action_types
    assert "SEND_MESSAGE" not in d.planned_action_types


def test_deterministic_same_input():
    args = ("AUTHORIZED_QUIET", JourneyType.NEW_ACCOUNT.value, POL,
            {"linked_at": NOW - timedelta(hours=3)}, "authorized", [], False, NOW)
    assert evaluate_transition(*args) == evaluate_transition(*args)


def test_pause_precedence():
    d = evaluate_transition("PAUSED", JourneyType.NEW_ACCOUNT.value, POL, {"explicit_paused": True},
                            "authorized", [], False, NOW)
    assert d.recommended_next_state == "PAUSED" and not d.allowed
