"""Validator fail-closed precedence tests."""
from __future__ import annotations
from app.services.daily_observation.contract import EvidenceStatus, InfraStatus, OverallStatus
from app.services.daily_observation.validator import validate_report_dict


def _clean(**over):
    base = dict(
        not_applicable=False,
        accounts_expected=1,
        accounts_covered=1,
        expected_periodic_ticks=10,
        actual_periodic_snapshots=10,
        tick_tolerance_status="UNRATIFIED",
        cutover_true_count=0,
        simulation_only_violations=0,
        mutates_runtime_violations=0,
        executes_violations=0,
        idempotency_conflict_count=0,
        duplicate_count=0,
        database_status=InfraStatus.HEALTHY.value,
        redis_status=InfraStatus.HEALTHY.value,
        celery_worker_status=InfraStatus.HEALTHY.value,
        celery_beat_status=InfraStatus.HEALTHY.value,
        scheduler_status=InfraStatus.HEALTHY.value,
        shadow_scheduler_flag_status=InfraStatus.HEALTHY.value,
        shadow_runtime_flag_status=InfraStatus.HEALTHY.value,
        by_severity={},
        runtime_unknown_count=0,
        sensor_stale_count=0,
        live_state_missing_count=0,
        send_path_evidence_status=EvidenceStatus.HEALTHY.value,
        green_api_send_evidence_status=EvidenceStatus.HEALTHY.value,
        campaign_execution_evidence_status=EvidenceStatus.HEALTHY.value,
        journey_mutation_evidence_status=EvidenceStatus.HEALTHY.value,
        fleet_state_mutation_evidence_status=EvidenceStatus.HEALTHY.value,
        send_gate_integrity_evidence_status=EvidenceStatus.HEALTHY.value,
        operational_mutation_evidence_status=EvidenceStatus.HEALTHY.value,
    )
    base.update(over)
    return validate_report_dict(base)


def test_date_before_session_not_applicable():
    r = validate_report_dict({"not_applicable": True})
    assert r.overall_status == OverallStatus.NOT_APPLICABLE.value
    assert r.can_count_as_valid_day is False
    assert r.phase7_fully_accepted is False
    assert r.phase8_allowed is False


def test_cutover_true_fail():
    r = _clean(cutover_true_count=1)
    assert r.overall_status == OverallStatus.FAIL.value
    assert "CUTOVER_TRUE" in r.validity_reason_codes
    assert r.requires_restart is True


def test_executes_violation_fail():
    assert _clean(executes_violations=1).overall_status == OverallStatus.FAIL.value


def test_mutates_runtime_violation_fail():
    assert _clean(mutates_runtime_violations=1).overall_status == OverallStatus.FAIL.value


def test_simulation_only_violation_fail():
    assert _clean(simulation_only_violations=1).overall_status == OverallStatus.FAIL.value


def test_missing_cohort_fail():
    assert _clean(accounts_expected=0).overall_status == OverallStatus.FAIL.value


def test_zero_periodic_fail():
    r = _clean(expected_periodic_ticks=5, actual_periodic_snapshots=0)
    assert r.overall_status == OverallStatus.FAIL.value


def test_scheduler_unhealthy_fail():
    assert _clean(scheduler_status=InfraStatus.UNHEALTHY.value).overall_status == OverallStatus.FAIL.value


def test_database_unhealthy_fail():
    assert _clean(database_status=InfraStatus.UNHEALTHY.value).overall_status == OverallStatus.FAIL.value


def test_redis_unhealthy_fail():
    assert _clean(redis_status=InfraStatus.UNHEALTHY.value).overall_status == OverallStatus.FAIL.value


def test_celery_unhealthy_fail():
    assert _clean(celery_worker_status=InfraStatus.UNHEALTHY.value).overall_status == OverallStatus.FAIL.value


def test_idempotency_conflict_fail():
    assert _clean(idempotency_conflict_count=1).overall_status == OverallStatus.FAIL.value


def test_high_critical_review():
    r = _clean(by_severity={"HIGH": 2})
    # mutation evidence complete → REVIEW not INSUFFICIENT
    assert r.overall_status == OverallStatus.REVIEW_REQUIRED.value
    assert "HIGH_CRITICAL_PRESENT" in r.validity_reason_codes


def test_runtime_unknown_review():
    r = _clean(runtime_unknown_count=3)
    assert r.overall_status == OverallStatus.REVIEW_REQUIRED.value
    assert "RUNTIME_UNKNOWN" in r.validity_reason_codes


def test_sensor_stale_review():
    r = _clean(sensor_stale_count=1)
    assert r.overall_status == OverallStatus.REVIEW_REQUIRED.value


def test_live_state_missing_review():
    r = _clean(live_state_missing_count=1)
    assert r.overall_status == OverallStatus.REVIEW_REQUIRED.value


def test_tick_gap_unratified_review():
    r = _clean(expected_periodic_ticks=10, actual_periodic_snapshots=8)
    assert r.overall_status == OverallStatus.REVIEW_REQUIRED.value
    assert "TICK_GAP_UNRATIFIED" in r.validity_reason_codes


def test_unknown_infra_insufficient():
    r = _clean(database_status=InfraStatus.UNKNOWN.value)
    assert r.overall_status == OverallStatus.INSUFFICIENT_EVIDENCE.value
    assert r.can_count_as_valid_day is False


def test_missing_mutation_evidence_blocks_pass():
    r = _clean(operational_mutation_evidence_status=EvidenceStatus.INSUFFICIENT_EVIDENCE.value)
    assert r.overall_status == OverallStatus.INSUFFICIENT_EVIDENCE.value
    assert r.overall_status != OverallStatus.PASS.value


def test_clean_complete_day_pass():
    r = _clean()
    assert r.overall_status == OverallStatus.PASS.value
    assert r.can_count_as_valid_day is True
    assert r.phase7_fully_accepted is False
    assert r.phase8_allowed is False
    assert "Fully Accepted" not in r.owner_action_fa


def test_fail_precedes_review():
    r = _clean(cutover_true_count=1, by_severity={"HIGH": 9})
    assert r.overall_status == OverallStatus.FAIL.value


def test_no_false_pass_when_infra_degraded_unknown_path():
    r = _clean(redis_status=InfraStatus.UNKNOWN.value, by_severity={"HIGH": 1})
    assert r.overall_status == OverallStatus.INSUFFICIENT_EVIDENCE.value
    assert r.can_count_as_valid_day is False
