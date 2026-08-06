"""Read-only Daily Observation Report aggregation service (Phase A)."""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services.daily_observation.contract import (
    DailyObservationReport,
    EvidenceStatus,
    InfraStatus,
    OverallStatus,
    empty_report,
)
from app.services.daily_observation import infra_health
from app.services.daily_observation.session_meta import (
    EXPECTED_TOTAL_DAYS,
    PERIODIC_SOURCE,
    PERIODIC_TICK_INTERVAL_SECONDS,
    REPORT_VERSION,
    SESSION_2_ID,
    SESSION_2_LABEL,
    SESSION_2_STARTED_AT_UTC,
    SOURCE_ENVIRONMENT,
    TICK_TOLERANCE_STATUS,
)
from app.services.daily_observation.ticks import (
    calendar_day_index,
    day_bounds_utc,
    format_tehran,
    observation_window_for_day,
)
from app.services.daily_observation.validator import DailyObservationValidator
from app.services.shadow_types import SHADOW_VERSION


class DailyObservationReportService:
    """Aggregate existing evidence into versioned DailyObservationReport. No writes."""

    def __init__(self, session_factory=None, validator: DailyObservationValidator | None = None):
        self._session_factory = session_factory or AsyncSessionLocal
        self._validator = validator or DailyObservationValidator()

    async def build(
        self,
        day_utc: str,
        *,
        now_utc: datetime | None = None,
        probe_infra: bool = True,
        strict: bool = False,
    ) -> DailyObservationReport:
        self._validate_date(day_utc)
        now = now_utc or datetime.utcnow()
        window = observation_window_for_day(day_utc, now_utc=now)
        day_start, day_end = day_bounds_utc(day_utc)
        # Query lower bound never before Session 2
        query_start = max(day_start, SESSION_2_STARTED_AT_UTC)
        query_end = day_end

        report = empty_report(
            report_version=REPORT_VERSION,
            session_id=SESSION_2_ID,
            session_label=SESSION_2_LABEL,
            report_date_utc=day_utc,
            generated_at_utc=now.isoformat() + "Z",
            generated_at_tehran=format_tehran(now),
            observation_started_at_utc=SESSION_2_STARTED_AT_UTC.isoformat() + "Z",
            observation_started_at_tehran=format_tehran(SESSION_2_STARTED_AT_UTC),
            calendar_day_index=calendar_day_index(day_utc),
            expected_total_days=EXPECTED_TOTAL_DAYS,
            source_environment=SOURCE_ENVIRONMENT,
            shadow_version=SHADOW_VERSION,
            tick_tolerance_status=TICK_TOLERANCE_STATUS,
            phase7_fully_accepted=False,
            phase8_allowed=False,
        )

        if window["not_applicable"]:
            report.not_applicable = True
            report.overall_status = OverallStatus.NOT_APPLICABLE.value
            if probe_infra:
                await self._fill_infra(report, last_periodic_at=None, now=now)
            return self._validator.validate(report)

        report.expected_periodic_ticks = int(window["expected_periodic_ticks"])
        last_periodic = None

        async with self._session_factory() as db:
            cohort = await self._load_cohort(db)
            report.accounts_expected = len(cohort)
            expected_ids = set(cohort)

            snap = await self._load_day_snapshot_stats(db, query_start, query_end)
            prev_date = (day_start - timedelta(days=1)).strftime("%Y-%m-%d")
            prev_start, prev_end = day_bounds_utc(prev_date)
            prev_q_start = max(prev_start, SESSION_2_STARTED_AT_UTC)
            if prev_q_start < prev_end:
                prev_total = await self._count_snapshots(db, prev_q_start, prev_end)
            else:
                prev_total = 0

            report.previous_day_total_snapshots = prev_total
            report.total_snapshots = snap["total"]
            report.actual_periodic_snapshots = snap["periodic"]
            report.manual_snapshots = snap["manual"]
            report.snapshot_delta_vs_previous_day = report.total_snapshots - prev_total
            report.first_snapshot_at = snap["first_at"].isoformat() if snap["first_at"] else None
            report.last_snapshot_at = snap["last_at"].isoformat() if snap["last_at"] else None
            if snap["last_at"]:
                # Age relative to report-day end for past days; live now for current day.
                age_ref = now if day_start.date() == now.date() else min(now, day_end)
                report.latest_snapshot_age_seconds = int((age_ref - snap["last_at"]).total_seconds())
            # Cohort coverage counts only CELERY_PERIODIC accounts (not manual CLI/API).
            report.accounts_covered = snap["periodic_accounts_covered"]
            covered_ids = set(snap["periodic_account_ids"])
            missing = sorted(str(a) for a in (expected_ids - covered_ids))
            report.missing_accounts = [a[:8] for a in missing]
            report.coverage_ratio = (
                (report.accounts_covered / report.accounts_expected)
                if report.accounts_expected
                else None
            )

            report.by_mismatch_class = snap["by_class"]
            report.by_severity = snap["by_sev"]
            report.runtime_unknown_count = snap["by_class"].get("RUNTIME_UNKNOWN", 0)
            report.sensor_stale_count = snap["by_class"].get("SENSOR_STALE", 0)
            report.dangerous_mismatch_count = snap["by_class"].get("DANGEROUS_MISMATCH", 0)
            report.legacy_more_permissive_count = snap["by_class"].get("LEGACY_MORE_PERMISSIVE", 0)
            report.v67_more_permissive_count = snap["by_class"].get("V67_MORE_PERMISSIVE", 0)
            report.policy_version_mismatch_count = snap["by_class"].get("POLICY_VERSION_MISMATCH", 0)
            report.insufficient_evidence_count = snap["by_class"].get("INSUFFICIENT_EVIDENCE", 0)
            report.live_state_missing_count = snap["live_state_missing"]
            report.top_reason_codes = snap["top_reasons"]
            report.top_missing_evidence = snap["top_missing"]
            report.idempotency_conflict_count = snap["idempotency_conflicts"]
            report.duplicate_count = snap["idempotency_conflicts"]
            report.append_only_integrity_status = (
                EvidenceStatus.HEALTHY.value
                if snap["idempotency_conflicts"] == 0
                else EvidenceStatus.UNHEALTHY.value
            )

            report.simulation_only_violations = snap["sim_violations"]
            report.mutates_runtime_violations = snap["mut_violations"]
            report.executes_violations = snap["exec_violations"]
            report.invalid_snapshot_flag_count = (
                report.simulation_only_violations
                + report.mutates_runtime_violations
                + report.executes_violations
            )
            report.cutover_true_count = await self._cutover_true_count(db)
            report.policy_version = snap["policy_version"]
            report.migration_revision = await self._alembic_version(db)

            last_periodic = snap["last_periodic_at"]
            report.last_periodic_tick_at = last_periodic.isoformat() if last_periodic else None
            report.last_periodic_tick_status = (
                InfraStatus.HEALTHY.value if last_periodic else InfraStatus.UNKNOWN.value
            )

            report.runtime_observed_evidence = [
                "snapshot_simulation_only_check",
                "snapshot_mutates_runtime_check",
                "snapshot_executes_check",
                "fleet_account_cutover_count",
            ]
            report.static_test_evidence = [
                "phase7_isolation_tests",
                "send_gate_untouched_by_shadow_path_tests",
            ]
            report.send_path_evidence_status = EvidenceStatus.INSUFFICIENT_EVIDENCE.value
            report.green_api_send_evidence_status = EvidenceStatus.INSUFFICIENT_EVIDENCE.value
            report.campaign_execution_evidence_status = EvidenceStatus.INSUFFICIENT_EVIDENCE.value
            report.journey_mutation_evidence_status = EvidenceStatus.INSUFFICIENT_EVIDENCE.value
            report.fleet_state_mutation_evidence_status = EvidenceStatus.INSUFFICIENT_EVIDENCE.value
            report.send_gate_integrity_evidence_status = EvidenceStatus.INSUFFICIENT_EVIDENCE.value
            report.operational_mutation_evidence_status = EvidenceStatus.INSUFFICIENT_EVIDENCE.value

            try:
                from app.services import shadow_metrics

                m = shadow_metrics.snapshot()
                report.lock_failure_count = int(m.get("shadow_lock_failures", 0)) if isinstance(m, dict) else None
                report.task_success_count = int(m.get("shadow_runs_success", 0)) if isinstance(m, dict) else None
                report.task_failure_count = int(m.get("shadow_runs_failed", 0)) if isinstance(m, dict) else None
                report.task_skipped_count = int(m.get("shadow_skipped_disabled", 0)) if isinstance(m, dict) else None
            except Exception:
                report.lock_failure_count = None
                report.task_failure_count = None
                report.task_success_count = None
                report.task_skipped_count = None

        if probe_infra:
            await self._fill_infra(
                report,
                last_periodic_at=last_periodic,
                now=now,
                is_current_day=(day_start.date() == now.date()),
                had_periodic=(report.actual_periodic_snapshots > 0),
            )
        else:
            flags = infra_health.read_shadow_flags()
            report.shadow_runtime_flag_status = flags["runtime_status"]
            report.shadow_scheduler_flag_status = flags["scheduler_flag_status"]
            # Without live probes, keep connectivity UNKNOWN (fail-closed) but
            # still derive day-scoped scheduler evidence from periodic snapshots.
            report.database_status = InfraStatus.UNKNOWN.value
            report.redis_status = InfraStatus.UNKNOWN.value
            report.celery_worker_status = InfraStatus.UNKNOWN.value
            is_current = day_start.date() == now.date()
            if is_current:
                report.scheduler_status = InfraStatus.UNKNOWN.value
                report.celery_beat_status = InfraStatus.UNKNOWN.value
            else:
                report.scheduler_status = infra_health.derive_scheduler_status_historical(
                    scheduler_flag=flags["scheduler_enabled"],
                    had_periodic=(report.actual_periodic_snapshots > 0),
                )
                report.celery_beat_status = (
                    InfraStatus.HEALTHY.value
                    if flags["scheduler_enabled"] and report.actual_periodic_snapshots > 0
                    else InfraStatus.UNKNOWN.value
                )

        validated = self._validator.validate(report)
        if strict and validated.overall_status != OverallStatus.PASS.value:
            validated.requires_human_review = True
        return validated

    async def build_owner_payload(
        self,
        day_utc: str,
        *,
        include_timeline: bool = True,
        now_utc: datetime | None = None,
    ) -> dict[str, Any]:
        """Sanitized owner payload: primary day + optional Session 2 timeline (0..14)."""
        now = now_utc or datetime.utcnow()
        primary = await self.build(day_utc, now_utc=now, probe_infra=True)
        payload: dict[str, Any] = {
            "delivery": "v67.owner.daily-observation.delivery.1",
            "read_only": True,
            "report": sanitize_owner_report(primary),
            "timeline": [],
        }
        if not include_timeline:
            return payload

        day0 = datetime(
            SESSION_2_STARTED_AT_UTC.year,
            SESSION_2_STARTED_AT_UTC.month,
            SESSION_2_STARTED_AT_UTC.day,
        )
        for i in range(0, EXPECTED_TOTAL_DAYS + 1):
            d = day0 + timedelta(days=i)
            d_str = d.strftime("%Y-%m-%d")
            if d.date() > now.date():
                payload["timeline"].append(
                    {
                        "calendar_day_index": i,
                        "report_date_utc": d_str,
                        "ui_status": "WAITING",
                        "ui_status_fa": "در انتظار",
                        "overall_status": OverallStatus.NOT_APPLICABLE.value,
                        "can_count_as_valid_day": False,
                        "actual_periodic_snapshots": None,
                        "accounts_covered": None,
                        "accounts_expected": None,
                        "top_reason": None,
                    }
                )
                continue
            # Reuse live connectivity from primary; day build without re-probing.
            day_report = await self.build(d_str, now_utc=now, probe_infra=False)
            day_report.database_status = primary.database_status
            day_report.redis_status = primary.redis_status
            day_report.celery_worker_status = primary.celery_worker_status
            day_report.shadow_runtime_flag_status = primary.shadow_runtime_flag_status
            day_report.shadow_scheduler_flag_status = primary.shadow_scheduler_flag_status
            if d.date() == now.date():
                day_report.scheduler_status = primary.scheduler_status
                day_report.celery_beat_status = primary.celery_beat_status
            day_report = self._validator.validate(day_report)
            payload["timeline"].append(timeline_entry(day_report, now=now))
        return payload

    async def _fill_infra(
        self,
        report: DailyObservationReport,
        *,
        last_periodic_at,
        now: datetime,
        is_current_day: bool = True,
        had_periodic: bool = False,
    ) -> None:
        report.database_status = await infra_health.probe_database(self._session_factory)
        report.redis_status = await infra_health.probe_redis()
        report.celery_worker_status = infra_health.probe_celery_workers(timeout=1.0)
        flags = infra_health.read_shadow_flags()
        report.shadow_runtime_flag_status = flags["runtime_status"]
        report.shadow_scheduler_flag_status = flags["scheduler_flag_status"]
        max_age = PERIODIC_TICK_INTERVAL_SECONDS * 3
        if is_current_day:
            report.scheduler_status = infra_health.derive_scheduler_status(
                scheduler_flag=flags["scheduler_enabled"],
                last_periodic_at=last_periodic_at,
                now=now,
                max_age_seconds=max_age,
            )
            report.celery_beat_status = infra_health.derive_beat_status(
                last_periodic_at=last_periodic_at,
                scheduler_flag=flags["scheduler_enabled"],
            )
        else:
            # Historical day: do not age yesterday's last tick against live now.
            report.scheduler_status = infra_health.derive_scheduler_status_historical(
                scheduler_flag=flags["scheduler_enabled"],
                had_periodic=had_periodic,
            )
            report.celery_beat_status = (
                InfraStatus.HEALTHY.value
                if flags["scheduler_enabled"] and had_periodic
                else InfraStatus.UNKNOWN.value
            )

    @staticmethod
    def _validate_date(day_utc: str) -> None:
        try:
            datetime.strptime(day_utc, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"invalid_date:{day_utc}") from e

    async def _load_cohort(self, db) -> list[Any]:
        rows = (
            await db.execute(
                text("SELECT account_id FROM fleet_accounts WHERE cutover = false")
            )
        ).fetchall()
        return [r[0] for r in rows]

    async def _cutover_true_count(self, db) -> int:
        n = (
            await db.execute(text("SELECT COUNT(*) FROM fleet_accounts WHERE cutover = true"))
        ).scalar()
        return int(n or 0)

    async def _count_snapshots(self, db, start: datetime, end: datetime) -> int:
        n = (
            await db.execute(
                text(
                    "SELECT COUNT(*) FROM fleet_shadow_snapshots "
                    "WHERE observed_at >= :start AND observed_at < :end"
                ),
                {"start": start, "end": end},
            )
        ).scalar()
        return int(n or 0)

    async def _alembic_version(self, db) -> str | None:
        try:
            v = (await db.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))).scalar()
            return str(v) if v else None
        except Exception:
            return None

    async def _load_day_snapshot_stats(self, db, start: datetime, end: datetime) -> dict[str, Any]:
        total_row = (
            await db.execute(
                text(
                    """
                    SELECT COUNT(*) AS n,
                           COUNT(DISTINCT account_id) AS accounts,
                           MIN(observed_at) AS first_at,
                           MAX(observed_at) AS last_at,
                           MAX(policy_version) AS policy_version
                    FROM fleet_shadow_snapshots
                    WHERE observed_at >= :start AND observed_at < :end
                    """
                ),
                {"start": start, "end": end},
            )
        ).mappings().one()

        periodic = (
            await db.execute(
                text(
                    """
                    SELECT COUNT(*) FROM fleet_shadow_snapshots
                    WHERE observed_at >= :start AND observed_at < :end
                      AND source = :src
                    """
                ),
                {"start": start, "end": end, "src": PERIODIC_SOURCE},
            )
        ).scalar() or 0

        manual = (
            await db.execute(
                text(
                    """
                    SELECT COUNT(*) FROM fleet_shadow_snapshots
                    WHERE observed_at >= :start AND observed_at < :end
                      AND source <> :src
                    """
                ),
                {"start": start, "end": end, "src": PERIODIC_SOURCE},
            )
        ).scalar() or 0

        last_periodic = (
            await db.execute(
                text(
                    """
                    SELECT MAX(observed_at) FROM fleet_shadow_snapshots
                    WHERE observed_at >= :start AND observed_at < :end
                      AND source = :src
                    """
                ),
                {"start": start, "end": end, "src": PERIODIC_SOURCE},
            )
        ).scalar()

        class_rows = (
            await db.execute(
                text(
                    """
                    SELECT mismatch_class, COUNT(*) AS n
                    FROM fleet_shadow_snapshots
                    WHERE observed_at >= :start AND observed_at < :end
                    GROUP BY 1
                    """
                ),
                {"start": start, "end": end},
            )
        ).mappings().all()
        by_class = {r["mismatch_class"]: int(r["n"]) for r in class_rows}

        sev_rows = (
            await db.execute(
                text(
                    """
                    SELECT severity, COUNT(*) AS n
                    FROM fleet_shadow_snapshots
                    WHERE observed_at >= :start AND observed_at < :end
                    GROUP BY 1
                    """
                ),
                {"start": start, "end": end},
            )
        ).mappings().all()
        by_sev = {r["severity"]: int(r["n"]) for r in sev_rows}

        # live_state_missing is a reason_code inside JSONB
        live_missing = (
            await db.execute(
                text(
                    """
                    SELECT COUNT(*) FROM fleet_shadow_snapshots
                    WHERE observed_at >= :start AND observed_at < :end
                      AND reason_codes @> '["live_state_missing"]'::jsonb
                    """
                ),
                {"start": start, "end": end},
            )
        ).scalar() or 0

        reason_rows = (
            await db.execute(
                text(
                    """
                    SELECT code, COUNT(*) AS n FROM (
                      SELECT jsonb_array_elements_text(reason_codes) AS code
                      FROM fleet_shadow_snapshots
                      WHERE observed_at >= :start AND observed_at < :end
                    ) t
                    GROUP BY 1
                    ORDER BY n DESC
                    LIMIT 20
                    """
                ),
                {"start": start, "end": end},
            )
        ).mappings().all()
        top_reasons = [{"code": r["code"], "count": int(r["n"])} for r in reason_rows]

        missing_rows = (
            await db.execute(
                text(
                    """
                    SELECT code, COUNT(*) AS n FROM (
                      SELECT jsonb_array_elements_text(missing_evidence) AS code
                      FROM fleet_shadow_snapshots
                      WHERE observed_at >= :start AND observed_at < :end
                    ) t
                    GROUP BY 1
                    ORDER BY n DESC
                    LIMIT 20
                    """
                ),
                {"start": start, "end": end},
            )
        ).mappings().all()
        top_missing = [{"code": r["code"], "count": int(r["n"])} for r in missing_rows]

        # Unique constraint makes true duplicates impossible; detect empty keys / collisions via HAVING
        conflicts = (
            await db.execute(
                text(
                    """
                    SELECT COUNT(*) FROM (
                      SELECT idempotency_key, COUNT(*) AS c
                      FROM fleet_shadow_snapshots
                      WHERE observed_at >= :start AND observed_at < :end
                      GROUP BY 1
                      HAVING COUNT(*) > 1
                    ) x
                    """
                ),
                {"start": start, "end": end},
            )
        ).scalar() or 0

        # Flag violations should be impossible under CHECK constraints; still count for fail-closed honesty
        sim_v = (
            await db.execute(
                text(
                    """
                    SELECT COUNT(*) FROM fleet_shadow_snapshots
                    WHERE observed_at >= :start AND observed_at < :end
                      AND simulation_only IS NOT TRUE
                    """
                ),
                {"start": start, "end": end},
            )
        ).scalar() or 0
        mut_v = (
            await db.execute(
                text(
                    """
                    SELECT COUNT(*) FROM fleet_shadow_snapshots
                    WHERE observed_at >= :start AND observed_at < :end
                      AND mutates_runtime IS TRUE
                    """
                ),
                {"start": start, "end": end},
            )
        ).scalar() or 0
        exec_v = (
            await db.execute(
                text(
                    """
                    SELECT COUNT(*) FROM fleet_shadow_snapshots
                    WHERE observed_at >= :start AND observed_at < :end
                      AND executes IS TRUE
                    """
                ),
                {"start": start, "end": end},
            )
        ).scalar() or 0

        periodic_acct_rows = (
            await db.execute(
                text(
                    """
                    SELECT DISTINCT account_id FROM fleet_shadow_snapshots
                    WHERE observed_at >= :start AND observed_at < :end
                      AND source = :src
                    """
                ),
                {"start": start, "end": end, "src": PERIODIC_SOURCE},
            )
        ).fetchall()
        periodic_account_ids = [r[0] for r in periodic_acct_rows]

        return {
            "total": int(total_row["n"] or 0),
            "accounts_covered": int(total_row["accounts"] or 0),
            "periodic_accounts_covered": len(periodic_account_ids),
            "periodic_account_ids": periodic_account_ids,
            "first_at": total_row["first_at"],
            "last_at": total_row["last_at"],
            "policy_version": total_row["policy_version"],
            "periodic": int(periodic),
            "manual": int(manual),
            "last_periodic_at": last_periodic,
            "by_class": by_class,
            "by_sev": by_sev,
            "live_state_missing": int(live_missing),
            "top_reasons": top_reasons,
            "top_missing": top_missing,
            "idempotency_conflicts": int(conflicts),
            "sim_violations": int(sim_v),
            "mut_violations": int(mut_v),
            "exec_violations": int(exec_v),
        }


def sanitize_owner_report(report: DailyObservationReport) -> dict[str, Any]:
    """Strip/keep only owner-safe fields. No phones, secrets, or raw UUIDs."""
    d = report.to_dict()
    d["phase7_fully_accepted"] = False
    d["phase8_allowed"] = False
    d["read_only"] = True
    return d


def timeline_entry(report: DailyObservationReport, *, now: datetime) -> dict[str, Any]:
    day_start, _ = day_bounds_utc(report.report_date_utc)
    is_current = day_start.date() == now.date()
    status = report.overall_status
    if report.not_applicable:
        ui, fa = "NOT_APPLICABLE", "قابل‌اعمال نیست"
    elif is_current and status not in (OverallStatus.FAIL.value,):
        ui, fa = "IN_PROGRESS", "در حال جمع‌آوری"
    elif status == OverallStatus.PASS.value:
        ui, fa = "VALID", "معتبر"
    elif status == OverallStatus.FAIL.value:
        ui, fa = "INVALID", "نامعتبر"
    elif status == OverallStatus.REVIEW_REQUIRED.value:
        ui, fa = "REVIEW", "نیازمند بررسی"
    elif status == OverallStatus.INSUFFICIENT_EVIDENCE.value:
        ui, fa = "INSUFFICIENT", "شواهد ناکافی"
    else:
        ui, fa = status, status
    top = None
    if report.overall_reason_codes:
        top = report.overall_reason_codes[0]
    return {
        "calendar_day_index": report.calendar_day_index,
        "report_date_utc": report.report_date_utc,
        "ui_status": ui,
        "ui_status_fa": fa,
        "overall_status": status,
        "can_count_as_valid_day": report.can_count_as_valid_day,
        "actual_periodic_snapshots": report.actual_periodic_snapshots,
        "accounts_covered": report.accounts_covered,
        "accounts_expected": report.accounts_expected,
        "top_reason": top,
        "runtime_unknown_count": report.runtime_unknown_count,
        "live_state_missing_count": report.live_state_missing_count,
    }
