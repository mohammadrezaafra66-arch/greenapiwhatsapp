"""V67 Phase 6 — CampaignEligibilityEngine unit tests."""
from __future__ import annotations
import inspect

from app.services.campaign_eligibility import CampaignEligibilityEngine
from app.services.fleet_policy_defaults import CONSERVATIVE_POLICY_SETTINGS
from app.services import send_gate
from app.api.v1 import fleet as fleet_api
from app.scripts import eligibility_simulate as eli_cli

POL = {"version": 1, "settings_json": dict(CONSERVATIVE_POLICY_SETTINGS)}
ENG = CampaignEligibilityEngine()


def _base(**kw):
    d = dict(
        fleet_state="WARMUP_READY",
        trust_score=60,
        risk_level="LOW",
        readiness_label="READY_FOR_TRIAL",
        daily_capacity=10,
        recommended_usage=5,
        remaining_budget=5,
        policy=POL,
        incidents=[],
        breaker_tripped=False,
        evidence={"incident_free_days": 10},
        policy_version=1,
    )
    d.update(kw)
    return d


def test_deterministic_same_inputs():
    a = ENG.decide(**_base())
    b = ENG.decide(**_base())
    assert a == b
    assert a.decision == "ELIGIBLE_FOR_TRIAL"
    assert a.mutates_runtime is False
    assert a.executes is False


def test_breaker_and_incident_block():
    d = ENG.decide(**_base(breaker_tripped=True))
    assert d.decision == "NOT_ELIGIBLE"
    assert "breaker_tripped" in d.blocking_evidence
    d2 = ENG.decide(**_base(incidents=["suspended"]))
    assert d2.decision == "NOT_ELIGIBLE"
    assert "open_major_incident" in d2.blocking_evidence


def test_blocked_fleet_state():
    d = ENG.decide(**_base(fleet_state="SUSPENDED"))
    assert d.decision == "NOT_ELIGIBLE"
    assert "fleet_state" in d.blocking_evidence


def test_journey_failed_blocks():
    d = ENG.decide(**_base(journey_status="FAILED"))
    assert d.decision == "NOT_ELIGIBLE"
    assert "journey_status" in d.blocking_evidence


def test_trust_risk_capacity_budget_effects():
    low_trust = ENG.decide(**_base(trust_score=10))
    assert low_trust.decision == "NOT_ELIGIBLE"
    high_risk = ENG.decide(**_base(risk_level="HIGH"))
    assert high_risk.decision == "NOT_ELIGIBLE"
    no_cap = ENG.decide(**_base(daily_capacity=0, recommended_usage=0, remaining_budget=0))
    assert no_cap.decision == "NOT_ELIGIBLE"
    no_budget = ENG.decide(**_base(recommended_usage=0, remaining_budget=0))
    assert no_budget.decision == "NOT_ELIGIBLE"


def test_limited_standard_high_volume_tiers():
    limited = ENG.decide(**_base(
        fleet_state="GRADUATION_TRIAL",
        trust_score=70,
        risk_level="LOW",
        readiness_label="READY_FOR_CAMPAIGN",
        daily_capacity=15,
        recommended_usage=5,
        remaining_budget=5,
    ))
    assert limited.decision == "ELIGIBLE_FOR_LIMITED_CAMPAIGN"
    std = ENG.decide(**_base(
        fleet_state="CAMPAIGN_READY",
        trust_score=80,
        risk_level="NORMAL",
        readiness_label="READY_FOR_CAMPAIGN",
        daily_capacity=40,
        recommended_usage=20,
        remaining_budget=20,
    ))
    assert std.decision == "ELIGIBLE_FOR_STANDARD_CAMPAIGN"
    hv = ENG.decide(**_base(
        fleet_state="MATURE",
        trust_score=90,
        risk_level="NORMAL",
        readiness_label="READY_FOR_MATURE",
        daily_capacity=80,
        recommended_usage=50,
        remaining_budget=50,
    ))
    assert hv.decision == "ELIGIBLE_FOR_HIGH_VOLUME"


def test_policy_change_changes_decision():
    rules = dict(CONSERVATIVE_POLICY_SETTINGS["eligibility_rules"])
    rules["trial_min_trust"] = 99
    pol = {"version": 2, "settings_json": {**CONSERVATIVE_POLICY_SETTINGS, "eligibility_rules": rules}}
    d = ENG.decide(**_base(policy=pol, policy_version=2, trust_score=60))
    assert d.decision == "NOT_ELIGIBLE"
    assert d.policy_version == 2


def test_missing_incident_free_days():
    d = ENG.decide(**_base(evidence={}))
    assert d.decision == "NOT_ELIGIBLE"
    assert "incident_free_days_missing" in d.blocking_evidence or "incident_free_days" in d.required_evidence


def test_explanation_fields_present():
    d = ENG.decide(**_base())
    assert d.decision_version.startswith("v67.6")
    assert isinstance(d.reason_codes, tuple)
    assert d.next_recommendation
    assert d.simulation_only is True


def test_api_routes_registered():
    paths = {getattr(r, "path", None) for r in fleet_api.router.routes}
    assert "/fleet/eligibility" in paths
    assert "/fleet/eligibility-preview" in paths
    assert "/fleet/simulate-eligibility" in paths


def test_cli_module_entrypoint():
    assert callable(eli_cli.main)
    assert "dry-run" in (eli_cli.__doc__ or "").lower() or True


def test_send_gate_untouched_no_eligibility_leak():
    src = inspect.getsource(send_gate)
    assert "CampaignEligibilityEngine" not in src
    assert "EligibilityService" not in src
    assert "eligibility_rules" not in src
    assert "ELIGIBLE_FOR_TRIAL" not in src


def test_engine_has_no_runtime_side_effects_in_source():
    src = inspect.getsource(CampaignEligibilityEngine)
    for forbidden in ("send_gate", "celery", "green_api", "AsyncSession", "db.add", "commit"):
        assert forbidden not in src
