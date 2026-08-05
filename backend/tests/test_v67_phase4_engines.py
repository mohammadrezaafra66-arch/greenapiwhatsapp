"""V67 Phase 4 — Trust / Risk / Graduation / Readiness unit tests."""
from __future__ import annotations
import inspect

from app.services.trust_engine import TrustEngine
from app.services.risk_engine import RiskEngine
from app.services.graduation_trial import GraduationTrialFramework
from app.services.readiness_evaluator import ReadinessEvaluator
from app.services import send_gate


RICH = {
    "account_age_days": 30,
    "active_days": 12,
    "inbound_diversity": 12,
    "outbound_diversity": 10,
    "bidirectional_chats": 6,
    "response_ratio": 0.8,
    "delivery_success": 0.95,
    "webhook_fresh": True,
    "queue_health": True,
    "incident_free_days": 20,
    "device_stability": True,
    "native_contacts": 5,
    "policy_compliance": True,
    "day10_complete": True,
}


def test_trust_deterministic():
    t = TrustEngine()
    a = t.evaluate(RICH, {"name": "CONSERVATIVE"})
    b = t.evaluate(RICH, {"name": "CONSERVATIVE"})
    assert a == b
    assert a.score == b.score
    assert 0 <= a.score <= 100
    assert a.evidence_version.startswith("v67.4.trust")


def test_trust_connected_at_alone_capped():
    t = TrustEngine().evaluate({"connected_at": "2026-01-01T00:00:00"}, {})
    assert t.score <= 15
    assert any("connected_at" in e for e in t.explanations)


def test_trust_missing_evidence_explained():
    t = TrustEngine().evaluate({}, {})
    assert t.score == 0 or t.missing
    assert len(t.missing) > 0


def test_risk_levels_and_determinism():
    r = RiskEngine()
    a = r.evaluate({}, ["suspended"], {})
    b = r.evaluate({}, ["suspended"], {})
    assert a == b
    assert a.level in ("NORMAL", "LOW", "MEDIUM", "HIGH", "CRITICAL")
    assert a.level in ("HIGH", "CRITICAL", "MEDIUM")  # suspended is significant
    healthy = r.evaluate({"incident_free_days": 20}, [], {})
    assert healthy.level == "NORMAL"


def test_risk_inject_signals():
    r = RiskEngine().evaluate({
        "breaker": True,
        "webhook_fresh": False,
        "inactivity_days": 10,
        "duplicate_sends": 2,
    }, [], {})
    assert r.score > 0
    assert r.level != "NORMAL"


def test_graduation_requires_warmup_ready():
    g = GraduationTrialFramework()
    d = g.evaluate(
        current_fleet_state="CONTROLLED_RAMP",
        trust_score=90,
        risk_level="NORMAL",
        evidence=RICH,
    )
    assert not d.eligible
    assert d.applies_fleet_state is False
    d2 = g.evaluate(
        current_fleet_state="WARMUP_READY",
        trust_score=90,
        risk_level="NORMAL",
        evidence=RICH,
    )
    assert d2.eligible
    assert d2.recommended_state == "GRADUATION_TRIAL"
    assert d2.applies_fleet_state is False
    assert d2.simulation_only is True


def test_graduation_never_campaign_ready():
    g = GraduationTrialFramework().evaluate(
        current_fleet_state="WARMUP_READY",
        trust_score=99,
        risk_level="NORMAL",
        evidence=RICH,
    )
    assert g.recommended_state == "GRADUATION_TRIAL"
    assert g.recommended_state != "CAMPAIGN_READY"
    assert g.recommended_state != "MATURE"


def test_readiness_labels():
    ev = ReadinessEvaluator()
    not_ready = ev.evaluate(
        current_fleet_state="NEW",
        trust_score=10,
        risk_level="NORMAL",
        risk_score=0,
        evidence={},
    )
    assert not_ready.label == "NOT_READY"
    assert not_ready.mutates_fleet_state is False

    trial = ev.evaluate(
        current_fleet_state="WARMUP_READY",
        trust_score=90,
        risk_level="NORMAL",
        risk_score=0,
        evidence=RICH,
    )
    assert trial.label == "READY_FOR_TRIAL"

    high_risk = ev.evaluate(
        current_fleet_state="WARMUP_READY",
        trust_score=90,
        risk_level="CRITICAL",
        risk_score=90,
        evidence=RICH,
    )
    assert high_risk.label == "NOT_READY"


def test_send_gate_and_no_phase5_leak():
    src = inspect.getsource(send_gate)
    assert "TrustEngine" not in src
    assert "RiskEngine" not in src
    assert "ReadinessEvaluator" not in src
    assert "CapacityPlanner" not in src
    assert "Autopilot" not in src
    assert "fleet_evidence" not in src
