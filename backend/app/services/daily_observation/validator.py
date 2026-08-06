"""Pure fail-closed Daily Observation validator — no DB / network I/O."""
from __future__ import annotations
from typing import Any

from app.services.daily_observation.contract import (
    DailyObservationReport,
    EvidenceStatus,
    InfraStatus,
    OverallStatus,
)


_UNHEALTHY = {InfraStatus.UNHEALTHY.value, EvidenceStatus.UNHEALTHY.value}
_UNKNOWNISH = {
    InfraStatus.UNKNOWN.value,
    EvidenceStatus.UNKNOWN.value,
    EvidenceStatus.INSUFFICIENT_EVIDENCE.value,
}


class DailyObservationValidator:
    """Deterministic validity engine. Input: aggregated report fields. No side effects."""

    OWNER_ACTION = {
        OverallStatus.PASS.value: (
            "این روز از نظر داده‌های موجود معتبر است. تنظیمی را تغییر ندهید و Observation را ادامه دهید."
        ),
        OverallStatus.REVIEW_REQUIRED.value: (
            "این روز نیازمند بررسی فنی است. تا زمان بررسی، Phase 8 نباید شروع شود."
        ),
        OverallStatus.FAIL.value: (
            "این روز نامعتبر است. بدون تصمیم مالک Observation را Restart نکنید."
        ),
        OverallStatus.INSUFFICIENT_EVIDENCE.value: (
            "اطلاعات کافی برای معتبر دانستن این روز وجود ندارد. نتیجه را PASS تلقی نکنید."
        ),
        OverallStatus.NOT_APPLICABLE.value: (
            "این تاریخ خارج از پنجره Session 2 است. نتیجه PASS یا FAIL برای Observation ندارد."
        ),
    }

    def validate(self, report: DailyObservationReport) -> DailyObservationReport:
        report.phase7_fully_accepted = False
        report.phase8_allowed = False

        if report.not_applicable:
            return self._finalize(
                report,
                OverallStatus.NOT_APPLICABLE.value,
                ["DATE_BEFORE_SESSION_2"],
                can_count=False,
                review=False,
                restart=False,
            )

        blocking: list[str] = []
        review: list[str] = []
        unknown: list[str] = []
        reasons: list[str] = []

        # --- Precedence ladder (first match wins for FAIL/INSUFFICIENT) ---
        if report.cutover_true_count > 0:
            blocking.append("CUTOVER_TRUE_PRESENT")
            reasons.append("CUTOVER_TRUE")
            return self._finalize(report, OverallStatus.FAIL.value, reasons, blocking=blocking, can_count=False, restart=True)

        if report.executes_violations > 0:
            blocking.append("EXECUTES_VIOLATION")
            reasons.append("EXECUTES_TRUE")
            return self._finalize(report, OverallStatus.FAIL.value, reasons, blocking=blocking, can_count=False, restart=True)

        if report.mutates_runtime_violations > 0:
            blocking.append("MUTATES_RUNTIME_VIOLATION")
            reasons.append("MUTATES_RUNTIME_TRUE")
            return self._finalize(report, OverallStatus.FAIL.value, reasons, blocking=blocking, can_count=False, restart=True)

        if report.simulation_only_violations > 0:
            blocking.append("SIMULATION_ONLY_VIOLATION")
            reasons.append("SIMULATION_ONLY_FALSE")
            return self._finalize(report, OverallStatus.FAIL.value, reasons, blocking=blocking, can_count=False, restart=True)

        if report.accounts_expected <= 0:
            blocking.append("MISSING_FLEET_COHORT")
            reasons.append("NO_COHORT")
            return self._finalize(report, OverallStatus.FAIL.value, reasons, blocking=blocking, can_count=False)

        if (report.expected_periodic_ticks or 0) > 0 and report.actual_periodic_snapshots == 0:
            blocking.append("ZERO_PERIODIC_COVERAGE")
            reasons.append("NO_PERIODIC_SNAPSHOTS")
            return self._finalize(report, OverallStatus.FAIL.value, reasons, blocking=blocking, can_count=False)

        if report.shadow_scheduler_flag_status in _UNHEALTHY or report.scheduler_status in _UNHEALTHY:
            blocking.append("SCHEDULER_NOT_RUNNING")
            reasons.append("SCHEDULER_UNHEALTHY")
            return self._finalize(report, OverallStatus.FAIL.value, reasons, blocking=blocking, can_count=False)

        if report.database_status in _UNHEALTHY:
            blocking.append("DATABASE_UNAVAILABLE")
            reasons.append("DATABASE_UNHEALTHY")
            return self._finalize(report, OverallStatus.FAIL.value, reasons, blocking=blocking, can_count=False)

        if report.redis_status in _UNHEALTHY:
            blocking.append("REDIS_UNAVAILABLE")
            reasons.append("REDIS_UNHEALTHY")
            return self._finalize(report, OverallStatus.FAIL.value, reasons, blocking=blocking, can_count=False)

        if report.celery_worker_status in _UNHEALTHY:
            blocking.append("CELERY_WORKER_UNAVAILABLE")
            reasons.append("CELERY_WORKER_UNHEALTHY")
            return self._finalize(report, OverallStatus.FAIL.value, reasons, blocking=blocking, can_count=False)

        if report.idempotency_conflict_count > 0 or report.duplicate_count > 0:
            blocking.append("IDEMPOTENCY_OR_DUPLICATE_VIOLATION")
            reasons.append("IDEMPOTENCY_CONFLICT")
            return self._finalize(report, OverallStatus.FAIL.value, reasons, blocking=blocking, can_count=False)

        # Snapshot gap — tolerance UNRATIFIED → any shortfall blocks PASS
        exp = report.expected_periodic_ticks
        act = report.actual_periodic_snapshots
        if exp is not None and act < exp:
            if report.tick_tolerance_status == "UNRATIFIED":
                review.append("SNAPSHOT_GAP_TOLERANCE_UNRATIFIED")
                reasons.append("TICK_GAP_UNRATIFIED")
            else:
                review.append("SNAPSHOT_GAP_BEYOND_TOLERANCE")
                reasons.append("TICK_GAP")

        if report.by_severity.get("CRITICAL", 0) > 0 or report.by_severity.get("HIGH", 0) > 0:
            review.append("HIGH_OR_CRITICAL_MISMATCH")
            reasons.append("HIGH_CRITICAL_PRESENT")

        if report.runtime_unknown_count > 0:
            review.append("RUNTIME_UNKNOWN_PRESENT")
            reasons.append("RUNTIME_UNKNOWN")

        if report.sensor_stale_count > 0:
            review.append("SENSOR_STALE_PRESENT")
            reasons.append("SENSOR_STALE")

        if report.live_state_missing_count > 0:
            review.append("LIVE_STATE_MISSING_PRESENT")
            reasons.append("LIVE_STATE_MISSING")

        # Infrastructure UNKNOWN → cannot PASS
        for label, status in (
            ("DATABASE_UNKNOWN", report.database_status),
            ("REDIS_UNKNOWN", report.redis_status),
            ("CELERY_WORKER_UNKNOWN", report.celery_worker_status),
            ("SCHEDULER_UNKNOWN", report.scheduler_status),
        ):
            if status in _UNKNOWNISH:
                unknown.append(label)
                reasons.append(label)

        # Mutation honesty — missing runtime ledger ≠ PASS
        mutation_fields = (
            report.send_path_evidence_status,
            report.green_api_send_evidence_status,
            report.campaign_execution_evidence_status,
            report.journey_mutation_evidence_status,
            report.fleet_state_mutation_evidence_status,
            report.send_gate_integrity_evidence_status,
            report.operational_mutation_evidence_status,
        )
        if any(s in _UNKNOWNISH for s in mutation_fields):
            unknown.append("MUTATION_RUNTIME_EVIDENCE_UNAVAILABLE")
            reasons.append("MUTATION_EVIDENCE_INSUFFICIENT")

        if report.celery_beat_status in _UNKNOWNISH:
            unknown.append("CELERY_BEAT_UNKNOWN")
            reasons.append("BEAT_UNKNOWN")

        # Dimension statuses
        report.tick_completeness_status = self._tick_status(exp, act, report.tick_tolerance_status)
        report.cohort_coverage_status = (
            EvidenceStatus.HEALTHY.value
            if report.accounts_expected > 0 and report.accounts_covered >= report.accounts_expected
            else EvidenceStatus.UNHEALTHY.value
            if report.accounts_expected > 0
            else EvidenceStatus.UNKNOWN.value
        )
        report.snapshot_integrity_status = (
            EvidenceStatus.UNHEALTHY.value
            if report.invalid_snapshot_flag_count or report.idempotency_conflict_count
            else EvidenceStatus.HEALTHY.value
            if report.total_snapshots > 0
            else EvidenceStatus.UNKNOWN.value
        )
        report.infrastructure_health_status = self._infra_rollup(report)
        report.safety_invariants_status = (
            EvidenceStatus.HEALTHY.value
            if report.cutover_true_count == 0
            and report.simulation_only_violations == 0
            and report.mutates_runtime_violations == 0
            and report.executes_violations == 0
            else EvidenceStatus.UNHEALTHY.value
        )
        report.critical_findings_status = (
            EvidenceStatus.UNHEALTHY.value
            if (report.by_severity.get("CRITICAL", 0) or report.by_severity.get("HIGH", 0))
            else EvidenceStatus.HEALTHY.value
        )

        # Decide overall
        if blocking:
            status = OverallStatus.FAIL.value
        elif unknown and not review:
            status = OverallStatus.INSUFFICIENT_EVIDENCE.value
        elif unknown and review:
            # Prefer honest insufficient when evidence missing; still surface review
            status = OverallStatus.INSUFFICIENT_EVIDENCE.value
            review = list(dict.fromkeys(review + ["ALSO_HAS_REVIEW_FINDINGS"]))
        elif review:
            status = OverallStatus.REVIEW_REQUIRED.value
        elif (
            report.tick_completeness_status == EvidenceStatus.HEALTHY.value
            and report.cohort_coverage_status == EvidenceStatus.HEALTHY.value
            and report.infrastructure_health_status == EvidenceStatus.HEALTHY.value
            and report.safety_invariants_status == EvidenceStatus.HEALTHY.value
            and report.critical_findings_status == EvidenceStatus.HEALTHY.value
            and not any(s in _UNKNOWNISH for s in mutation_fields)
        ):
            status = OverallStatus.PASS.value
            reasons.append("ALL_AVAILABLE_EVIDENCE_OK")
        else:
            status = OverallStatus.INSUFFICIENT_EVIDENCE.value
            reasons.append("EVIDENCE_INCOMPLETE")
            unknown.append("EVIDENCE_INCOMPLETE")

        can_count = status == OverallStatus.PASS.value
        report.minimum_evidence_complete = can_count
        return self._finalize(
            report,
            status,
            reasons,
            blocking=blocking,
            review=review,
            unknown=unknown,
            can_count=can_count,
            review_flag=status in (
                OverallStatus.REVIEW_REQUIRED.value,
                OverallStatus.INSUFFICIENT_EVIDENCE.value,
                OverallStatus.FAIL.value,
            ),
            restart=False,
        )

    def _tick_status(self, exp: int | None, act: int, tolerance_status: str) -> str:
        if exp is None:
            return EvidenceStatus.UNKNOWN.value
        if act >= exp:
            return EvidenceStatus.HEALTHY.value
        if tolerance_status == "UNRATIFIED":
            return EvidenceStatus.INSUFFICIENT_EVIDENCE.value
        return EvidenceStatus.UNHEALTHY.value

    def _infra_rollup(self, report: DailyObservationReport) -> str:
        statuses = [
            report.database_status,
            report.redis_status,
            report.celery_worker_status,
            report.scheduler_status,
        ]
        if any(s in _UNHEALTHY for s in statuses):
            return EvidenceStatus.UNHEALTHY.value
        if any(s in _UNKNOWNISH or s == InfraStatus.DEGRADED.value for s in statuses):
            return EvidenceStatus.UNKNOWN.value
        if all(s == InfraStatus.HEALTHY.value for s in statuses):
            return EvidenceStatus.HEALTHY.value
        return EvidenceStatus.UNKNOWN.value

    def _finalize(
        self,
        report: DailyObservationReport,
        status: str,
        reasons: list[str],
        *,
        blocking: list[str] | None = None,
        review: list[str] | None = None,
        unknown: list[str] | None = None,
        can_count: bool = False,
        review_flag: bool | None = None,
        restart: bool = False,
    ) -> DailyObservationReport:
        report.overall_status = status
        report.daily_validity_status = status
        report.overall_reason_codes = list(dict.fromkeys(reasons))
        report.validity_reason_codes = list(report.overall_reason_codes)
        report.blocking_findings = blocking or []
        report.review_findings = review or []
        report.unknown_findings = unknown or []
        report.can_count_as_valid_day = can_count
        report.requires_human_review = True if review_flag is None else review_flag
        if status == OverallStatus.PASS.value:
            report.requires_human_review = False
        report.requires_restart = restart
        report.phase7_fully_accepted = False
        report.phase8_allowed = False
        report.owner_action_fa = self.OWNER_ACTION.get(
            status, self.OWNER_ACTION[OverallStatus.INSUFFICIENT_EVIDENCE.value]
        )
        return report


def validate_report_dict(data: dict[str, Any]) -> DailyObservationReport:
    """Build report from dict fields and validate (test helper)."""
    report = DailyObservationReport()
    for k, v in data.items():
        if hasattr(report, k):
            setattr(report, k, v)
    return DailyObservationValidator().validate(report)
