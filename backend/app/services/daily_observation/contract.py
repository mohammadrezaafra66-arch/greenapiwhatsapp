"""Versioned Daily Observation Report data contract (Phase A)."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from app.services.daily_observation.session_meta import REPORT_VERSION


class OverallStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class InfraStatus(str, Enum):
    HEALTHY = "HEALTHY"
    UNHEALTHY = "UNHEALTHY"
    DEGRADED = "DEGRADED"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EvidenceStatus(str, Enum):
    HEALTHY = "HEALTHY"
    UNHEALTHY = "UNHEALTHY"
    DEGRADED = "DEGRADED"
    UNKNOWN = "UNKNOWN"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass
class DailyObservationReport:
    """v67.owner.daily-observation.1 — read-only structured daily report."""

    report_version: str = REPORT_VERSION
    session_id: str = "session-2"
    session_label: str = "نشست دوم (Session 2)"
    report_date_utc: str = ""
    generated_at_utc: str = ""
    generated_at_tehran: str = ""
    observation_started_at_utc: str = ""
    observation_started_at_tehran: str = ""
    calendar_day_index: int | None = None
    expected_total_days: int = 14
    source_environment: str = "ENV-A"
    shadow_version: str | None = None
    policy_version: int | None = None
    migration_revision: str | None = None

    overall_status: str = OverallStatus.INSUFFICIENT_EVIDENCE.value
    overall_reason_codes: list[str] = field(default_factory=list)
    blocking_findings: list[str] = field(default_factory=list)
    review_findings: list[str] = field(default_factory=list)
    unknown_findings: list[str] = field(default_factory=list)
    can_count_as_valid_day: bool = False
    requires_human_review: bool = True
    requires_restart: bool = False
    phase7_fully_accepted: bool = False
    phase8_allowed: bool = False

    expected_periodic_ticks: int | None = None
    actual_periodic_snapshots: int = 0
    manual_snapshots: int = 0
    total_snapshots: int = 0
    previous_day_total_snapshots: int | None = None
    snapshot_delta_vs_previous_day: int | None = None
    first_snapshot_at: str | None = None
    last_snapshot_at: str | None = None
    latest_snapshot_age_seconds: int | None = None
    accounts_expected: int = 0
    accounts_covered: int = 0
    coverage_ratio: float | None = None
    missing_accounts: list[str] = field(default_factory=list)
    duplicate_count: int = 0
    idempotency_conflict_count: int = 0
    append_only_integrity_status: str = EvidenceStatus.UNKNOWN.value

    by_mismatch_class: dict[str, int] = field(default_factory=dict)
    by_severity: dict[str, int] = field(default_factory=dict)
    runtime_unknown_count: int = 0
    sensor_stale_count: int = 0
    dangerous_mismatch_count: int = 0
    legacy_more_permissive_count: int = 0
    v67_more_permissive_count: int = 0
    policy_version_mismatch_count: int = 0
    insufficient_evidence_count: int = 0
    live_state_missing_count: int = 0
    top_reason_codes: list[dict[str, Any]] = field(default_factory=list)
    top_missing_evidence: list[dict[str, Any]] = field(default_factory=list)

    database_status: str = InfraStatus.UNKNOWN.value
    redis_status: str = InfraStatus.UNKNOWN.value
    celery_worker_status: str = InfraStatus.UNKNOWN.value
    celery_beat_status: str = InfraStatus.UNKNOWN.value
    scheduler_status: str = InfraStatus.UNKNOWN.value
    shadow_runtime_flag_status: str = InfraStatus.UNKNOWN.value
    shadow_scheduler_flag_status: str = InfraStatus.UNKNOWN.value
    last_periodic_tick_status: str = InfraStatus.UNKNOWN.value
    last_periodic_tick_at: str | None = None
    lock_failure_count: int | None = None
    task_failure_count: int | None = None
    task_success_count: int | None = None
    task_skipped_count: int | None = None

    cutover_true_count: int = 0
    invalid_snapshot_flag_count: int = 0
    simulation_only_violations: int = 0
    mutates_runtime_violations: int = 0
    executes_violations: int = 0
    send_path_evidence_status: str = EvidenceStatus.INSUFFICIENT_EVIDENCE.value
    green_api_send_evidence_status: str = EvidenceStatus.INSUFFICIENT_EVIDENCE.value
    campaign_execution_evidence_status: str = EvidenceStatus.INSUFFICIENT_EVIDENCE.value
    journey_mutation_evidence_status: str = EvidenceStatus.INSUFFICIENT_EVIDENCE.value
    fleet_state_mutation_evidence_status: str = EvidenceStatus.INSUFFICIENT_EVIDENCE.value
    send_gate_integrity_evidence_status: str = EvidenceStatus.INSUFFICIENT_EVIDENCE.value
    operational_mutation_evidence_status: str = EvidenceStatus.INSUFFICIENT_EVIDENCE.value
    runtime_observed_evidence: list[str] = field(default_factory=list)
    static_test_evidence: list[str] = field(default_factory=list)

    minimum_evidence_complete: bool = False
    tick_completeness_status: str = EvidenceStatus.UNKNOWN.value
    cohort_coverage_status: str = EvidenceStatus.UNKNOWN.value
    snapshot_integrity_status: str = EvidenceStatus.UNKNOWN.value
    infrastructure_health_status: str = EvidenceStatus.UNKNOWN.value
    safety_invariants_status: str = EvidenceStatus.UNKNOWN.value
    critical_findings_status: str = EvidenceStatus.UNKNOWN.value
    daily_validity_status: str = OverallStatus.INSUFFICIENT_EVIDENCE.value
    validity_reason_codes: list[str] = field(default_factory=list)
    tick_tolerance_status: str = "UNRATIFIED"
    not_applicable: bool = False
    owner_action_fa: str = ""

    read_only: bool = True
    simulation_only: bool = True
    mutates_runtime: bool = False
    executes: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Hard invariants — never claim acceptance / Phase 8.
        d["phase7_fully_accepted"] = False
        d["phase8_allowed"] = False
        d["report_version"] = REPORT_VERSION
        d["read_only"] = True
        return d


def empty_report(**kwargs: Any) -> DailyObservationReport:
    r = DailyObservationReport()
    for k, v in kwargs.items():
        if hasattr(r, k):
            setattr(r, k, v)
    r.phase7_fully_accepted = False
    r.phase8_allowed = False
    return r
