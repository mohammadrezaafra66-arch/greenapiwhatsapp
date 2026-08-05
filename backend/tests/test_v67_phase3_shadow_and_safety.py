"""V67 Phase 3 — shadow, send_gate isolation, action idempotency helpers."""
from __future__ import annotations
import inspect

from app.services.journey_shadow import compare_shadow
from app.services.journey_transition import make_idempotency_key
from app.services import send_gate
from app.services.journey_orchestrator import JourneyOrchestrator


def test_shadow_graduated_vs_warmup_ready_safe():
    c = compare_shadow(
        canonical="WARMUP_READY",
        adapter_recommended="WARMUP_READY",
        journey_recommended="WARMUP_READY",
        account_status="active",
        warmup_state="GRADUATED",
        live_state="authorized",
        incidents=[],
    )
    assert c.label == "SAFE_MISMATCH"


def test_shadow_dangerous_active_vs_suspended():
    c = compare_shadow(
        canonical="CONTROLLED_RAMP",
        adapter_recommended="SUSPENDED",
        journey_recommended="SUSPENDED",
        account_status="active",
        warmup_state="RAMPING",
        live_state="suspended",
        incidents=["suspended"],
    )
    assert c.label == "DANGEROUS_MISMATCH"


def test_shadow_insufficient_evidence():
    c = compare_shadow(
        canonical="NEW", adapter_recommended="PRECHECK", journey_recommended="PRECHECK",
        account_status="pending", warmup_state=None, live_state=None, incidents=[],
        evidence_complete=False,
    )
    assert c.label == "INSUFFICIENT_EVIDENCE"


def test_send_gate_unchanged_no_journey_cutover():
    src = inspect.getsource(send_gate)
    assert "FleetState" not in src
    assert "account_journeys" not in src
    assert "evaluate_transition" not in src
    assert "JourneyOrchestrator" not in src
    assert hasattr(send_gate, "gate_check_automated")


def test_orchestrator_never_sets_live_mode_constant():
    assert JourneyOrchestrator.MODE_SIMULATION == "SIMULATION"
    assert JourneyOrchestrator.MODE_SHADOW == "SHADOW"
    assert not hasattr(JourneyOrchestrator, "MODE_LIVE")


def test_idempotency_key_stable():
    k1 = make_idempotency_key("a", "j", "WAIT", "2026080512")
    k2 = make_idempotency_key("a", "j", "WAIT", "2026080512")
    assert k1 == k2
    assert "WAIT" in k1
