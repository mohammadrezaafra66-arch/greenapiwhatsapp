"""V67 Phase 7 — Shadow comparison unit tests + isolation proofs."""
from __future__ import annotations
import inspect

from app.services.shadow_comparison import ShadowComparisonEngine
from app.services.shadow_types import SHADOW_VERSION, ShadowThresholdStatus
from app.services.shadow_freshness import evaluate_freshness
from app.config import settings
from app.services import send_gate
from datetime import datetime

ENG = ShadowComparisonEngine()


def _base(**kw):
    d = dict(
        canonical_fleet_state="WARMUP_READY",
        adapter_recommended_state="WARMUP_READY",
        journey_recommended_state="WARMUP_READY",
        trust_score=60,
        risk_level="LOW",
        readiness_label="READY_FOR_TRIAL",
        daily_capacity=10,
        recommended_usage=5,
        eligibility_decision="NOT_ELIGIBLE",
        legacy_account_status="active",
        legacy_warmup_state="GRADUATED",
        legacy_eligibility="ok",
        legacy_send_allowed=True,
        live_state="authorized",
        incidents=[],
        breaker_tripped=False,
        sensor_freshness={"live_state": "fresh", "policy": "fresh", "breaker": "fresh",
                          "incidents": "fresh", "eligibility": "fresh"},
        policy_version=1,
        expected_policy_version=1,
        evidence_complete=True,
        runtime_unknown=False,
        journey_status="ACTIVE",
    )
    d.update(kw)
    return d


def test_deterministic_match():
    a = ENG.compare(**_base(eligibility_decision="ELIGIBLE_FOR_TRIAL", legacy_send_allowed=True,
                            legacy_eligibility="ok", legacy_warmup_state="WARMUP_READY"))
    b = ENG.compare(**_base(eligibility_decision="ELIGIBLE_FOR_TRIAL", legacy_send_allowed=True,
                            legacy_eligibility="ok", legacy_warmup_state="WARMUP_READY"))
    assert a == b
    assert a.mismatch_class == "MATCH"
    assert a.dangerous_threshold_status == ShadowThresholdStatus.UNRATIFIED.value
    assert a.simulation_only and not a.mutates_runtime and not a.executes
    assert a.shadow_version == SHADOW_VERSION


def test_runtime_unknown_and_stale():
    assert ENG.compare(**_base(runtime_unknown=True)).mismatch_class == "RUNTIME_UNKNOWN"
    assert ENG.compare(**_base(live_state=None, runtime_unknown=False)).mismatch_class == "RUNTIME_UNKNOWN"
    stale = ENG.compare(**_base(sensor_freshness={"live_state": "stale", "_fail_closed": True}))
    assert stale.mismatch_class == "SENSOR_STALE"


def test_breaker_incident_blocked_state():
    d = ENG.compare(**_base(breaker_tripped=True, eligibility_decision="ELIGIBLE_FOR_TRIAL"))
    assert d.mismatch_class == "DANGEROUS_MISMATCH"
    assert d.v67_more_permissive
    d2 = ENG.compare(**_base(incidents=["suspended"], eligibility_decision="ELIGIBLE_FOR_TRIAL"))
    assert d2.mismatch_class == "DANGEROUS_MISMATCH"
    d3 = ENG.compare(**_base(canonical_fleet_state="SUSPENDED", eligibility_decision="ELIGIBLE_FOR_TRIAL"))
    assert d3.mismatch_class == "DANGEROUS_MISMATCH"


def test_legacy_and_v67_permissive():
    leg = ENG.compare(**_base(
        legacy_send_allowed=True, eligibility_decision="NOT_ELIGIBLE", legacy_eligibility="ok",
    ))
    assert leg.mismatch_class == "LEGACY_MORE_PERMISSIVE"
    v67 = ENG.compare(**_base(
        legacy_send_allowed=False, legacy_eligibility="cooldown",
        eligibility_decision="ELIGIBLE_FOR_TRIAL",
    ))
    assert v67.mismatch_class == "V67_MORE_PERMISSIVE"
    assert v67.severity == "CRITICAL"


def test_policy_mismatch_and_insufficient():
    p = ENG.compare(**_base(policy_version=1, expected_policy_version=2))
    assert p.mismatch_class == "POLICY_VERSION_MISMATCH"
    i = ENG.compare(**_base(evidence_complete=False))
    assert i.mismatch_class == "INSUFFICIENT_EVIDENCE"


def test_journey_fail_closed_and_high_volume():
    j = ENG.compare(**_base(journey_status=None, eligibility_decision="ELIGIBLE_FOR_TRIAL"))
    assert j.mismatch_class == "DANGEROUS_MISMATCH"
    hv = ENG.compare(**_base(
        eligibility_decision="ELIGIBLE_FOR_HIGH_VOLUME",
        readiness_label="READY_FOR_CAMPAIGN",
        legacy_send_allowed=True, legacy_eligibility="ok",
    ))
    assert hv.mismatch_class == "DANGEROUS_MISMATCH"


def test_safe_mismatch_graduated():
    s = ENG.compare(**_base(
        legacy_warmup_state="GRADUATED",
        canonical_fleet_state="WARMUP_READY",
        adapter_recommended_state="WARMUP_READY",
        journey_recommended_state="WARMUP_READY",
        eligibility_decision="NOT_ELIGIBLE",
        legacy_send_allowed=False,
        legacy_eligibility="cooldown",
    ))
    assert s.mismatch_class in ("SAFE_MISMATCH", "LEGACY_MORE_PERMISSIVE", "MATCH", "INSUFFICIENT_EVIDENCE")


def test_freshness_fail_closed_missing_policy():
    now = datetime(2026, 8, 5, 12, 0, 0)
    out = evaluate_freshness(now=now, sensor_timestamps={"live_state": now}, policy={"settings_json": {}})
    assert out.get("_fail_closed") is True


def test_feature_flags_default_false():
    from app.config import Settings
    assert Settings.model_fields["v67_shadow_runtime_enabled"].default is False
    assert Settings.model_fields["v67_shadow_scheduler_enabled"].default is False


def test_send_gate_unchanged_no_shadow_leak():
    src = inspect.getsource(send_gate)
    assert "ShadowRuntime" not in src
    assert "ShadowComparison" not in src
    assert "fleet_shadow" not in src
    assert "v67_shadow" not in src


def test_shadow_runtime_source_no_green_api_send():
    import app.services.shadow_runtime as mod
    import app.services.shadow_comparison as cmp
    for m in (mod, cmp):
        src = inspect.getsource(m)
        assert "sendMessage" not in src
        assert "green_api" not in src
        assert "run_campaign" not in src
        assert "cutover = True" not in src
        assert "cutover=True" not in src


def test_no_cutover_setter_in_shadow_api():
    import app.api.v1.fleet_shadow as api
    src = inspect.getsource(api)
    assert "cutover=True" not in src
    assert "cutover = True" not in src
    assert "enable_flag" not in src
    assert "v67_shadow_runtime_enabled=True" not in src
