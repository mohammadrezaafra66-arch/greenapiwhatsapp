"""Derive owner-facing Stop Condition display from report evidence (read-only)."""
from __future__ import annotations
from typing import Any

from app.services.daily_observation.contract import DailyObservationReport, OverallStatus


def derive_stop_conditions(report: DailyObservationReport) -> list[dict[str, Any]]:
    """Return Stop Conditions with Persian owner guidance. No automatic actions."""

    def item(
        key: str,
        title_fa: str,
        state: str,
        reason: str,
        severity: str,
        source: str,
        when: str | None = None,
    ) -> dict[str, Any]:
        action = (
            "تنظیمات را تغییر ندهید و گزارش را برای بررسی فنی ارسال کنید."
            if state == "فعال شده"
            else (
                "شواهد کافی برای قضاوت قطعی نیست؛ نتیجه را PASS حساب نکنید."
                if state == "نامشخص"
                else "اقدامی لازم نیست؛ Observation را ادامه دهید."
            )
        )
        return {
            "key": key,
            "title_fa": title_fa,
            "state": state,
            "state_code": (
                "ACTIVE" if state == "فعال شده" else "INACTIVE" if state == "فعال نشده" else "UNKNOWN"
            ),
            "reason": reason,
            "severity": severity,
            "evidence_source": source,
            "observed_at": when,
            "owner_action_fa": action,
        }

    out: list[dict[str, Any]] = []

    out.append(
        item(
            "cutover_true",
            "Cutover روشن",
            "فعال شده" if report.cutover_true_count > 0 else "فعال نشده",
            f"cutover_true_count={report.cutover_true_count}",
            "CRITICAL" if report.cutover_true_count > 0 else "INFO",
            "fleet_accounts.cutover",
        )
    )
    out.append(
        item(
            "snapshot_flag_violation",
            "نقض پرچم Snapshot",
            "فعال شده" if report.invalid_snapshot_flag_count > 0 else "فعال نشده",
            (
                f"sim={report.simulation_only_violations},"
                f"mut={report.mutates_runtime_violations},"
                f"exec={report.executes_violations}"
            ),
            "CRITICAL" if report.invalid_snapshot_flag_count > 0 else "INFO",
            "fleet_shadow_snapshots",
            report.last_snapshot_at,
        )
    )
    out.append(
        item(
            "scheduler_unhealthy",
            "Scheduler ناسالم",
            (
                "فعال شده"
                if report.scheduler_status == "UNHEALTHY"
                else "نامشخص"
                if report.scheduler_status in ("UNKNOWN", "INSUFFICIENT_EVIDENCE")
                else "فعال نشده"
            ),
            f"scheduler_status={report.scheduler_status}",
            "HIGH" if report.scheduler_status == "UNHEALTHY" else "INFO",
            "infra_health+periodic_snapshots",
            report.last_periodic_tick_at,
        )
    )
    out.append(
        item(
            "infra_unhealthy",
            "زیرساخت ناسالم",
            (
                "فعال شده"
                if any(
                    s == "UNHEALTHY"
                    for s in (
                        report.database_status,
                        report.redis_status,
                        report.celery_worker_status,
                    )
                )
                else "نامشخص"
                if any(
                    s in ("UNKNOWN", "INSUFFICIENT_EVIDENCE")
                    for s in (
                        report.database_status,
                        report.redis_status,
                        report.celery_worker_status,
                    )
                )
                else "فعال نشده"
            ),
            (
                f"db={report.database_status},redis={report.redis_status},"
                f"worker={report.celery_worker_status}"
            ),
            "HIGH",
            "infra_health_probes",
        )
    )
    out.append(
        item(
            "mutation_evidence_gap",
            "شکاف شواهد Mutation",
            "نامشخص",
            "attributed_runtime_mutation_ledger_missing",
            "HIGH",
            "evidence_collector",
        )
    )
    out.append(
        item(
            "high_critical_mismatch",
            "اختلاف HIGH/CRITICAL",
            (
                "فعال شده"
                if (report.by_severity.get("HIGH", 0) or report.by_severity.get("CRITICAL", 0))
                else "فعال نشده"
            ),
            f"HIGH={report.by_severity.get('HIGH', 0)},CRITICAL={report.by_severity.get('CRITICAL', 0)}",
            "HIGH",
            "fleet_shadow_snapshots.severity",
        )
    )

    # Overall day invalidity as soft stop signal (display only).
    if report.overall_status == OverallStatus.FAIL.value:
        out.append(
            item(
                "daily_fail",
                "روز نامعتبر",
                "فعال شده",
                ",".join(report.overall_reason_codes[:6]) or "FAIL",
                "CRITICAL",
                "DailyObservationValidator",
            )
        )
    return out
