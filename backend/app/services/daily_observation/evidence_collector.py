"""Read-only Daily Observation Evidence Collector (Phase C).

Bounded SQL only. No writes. No Green API. No Celery dispatch. No unbounded log scan.
Does not compute overall PASS/FAIL — feeds the Phase A validator via report fields.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any

from sqlalchemy import text

from app.services.daily_observation.evidence_model import (
    EVIDENCE_BUNDLE_VERSION,
    DailyObservationEvidenceBundle,
    EvidenceClass,
    EvidenceItem,
    EvidenceItemStatus,
)
from app.services.daily_observation.session_meta import PERIODIC_SOURCE, SESSION_2_ID
from app.services.daily_observation.static_manifest import (
    ObservationStaticProofManifest,
    build_static_manifest,
)
from app.services.shadow_types import SHADOW_VERSION


# Hard cap on correlation sample rows (bounded queryability).
_CORRELATION_SAMPLE_LIMIT = 12


class DailyObservationEvidenceCollector:
    """Collect runtime/static/partial/missing evidence for one UTC day window."""

    async def collect(
        self,
        db,
        *,
        report_date_utc: str,
        query_start: datetime,
        query_end: datetime,
        now_utc: datetime,
        policy_version: int | None,
        migration_revision: str | None,
        snapshot_summary: dict[str, Any],
        cutover_true_count: int,
    ) -> tuple[DailyObservationEvidenceBundle, ObservationStaticProofManifest]:
        generated = now_utc.isoformat() + "Z"
        time_range = f"{query_start.isoformat()}..{query_end.isoformat()}"
        manifest = build_static_manifest(
            migration_revision=migration_revision,
            now_utc=now_utc,
        )

        bundle = DailyObservationEvidenceBundle(
            evidence_version=EVIDENCE_BUNDLE_VERSION,
            report_date_utc=report_date_utc,
            session_id=SESSION_2_ID,
            generated_at_utc=generated,
            deployed_git_sha=manifest.deployed_git_sha,
            shadow_version=SHADOW_VERSION,
            policy_version=policy_version,
            migration_revision=migration_revision,
            false_pass_guards=[
                "STATIC_ONLY_CANNOT_PASS",
                "ABSENCE_OF_ERROR_IS_NOT_ABSENCE_OF_MUTATION",
                "UNKNOWN_CRITICAL_EVIDENCE_BLOCKS_PASS",
                "UNATTRIBUTED_UPDATED_AT_IS_NOT_RUNTIME_VERIFIED",
            ],
        )

        # --- RUNTIME_VERIFIED: day-scoped snapshot flags / coverage / cutover ---
        sim_v = int(snapshot_summary.get("sim_violations") or 0)
        mut_v = int(snapshot_summary.get("mut_violations") or 0)
        exec_v = int(snapshot_summary.get("exec_violations") or 0)
        periodic = int(snapshot_summary.get("periodic") or 0)

        bundle.runtime_items.append(
            EvidenceItem(
                invariant="snapshot_flags",
                evidence_class=EvidenceClass.RUNTIME_VERIFIED.value,
                status=(
                    EvidenceItemStatus.VIOLATION.value
                    if (sim_v or mut_v or exec_v)
                    else EvidenceItemStatus.PRESENT.value
                ),
                source="fleet_shadow_snapshots",
                confidence_class="high",
                freshness="day_scoped",
                time_range=time_range,
                reason_codes=[
                    f"sim_violations={sim_v}",
                    f"mut_violations={mut_v}",
                    f"exec_violations={exec_v}",
                ],
                notes="CHECK + day query; proves snapshot-declared flags only",
            )
        )
        bundle.runtime_items.append(
            EvidenceItem(
                invariant="periodic_coverage",
                evidence_class=EvidenceClass.RUNTIME_VERIFIED.value,
                status=(
                    EvidenceItemStatus.PRESENT.value
                    if periodic > 0
                    else EvidenceItemStatus.MISSING.value
                ),
                source="fleet_shadow_snapshots.source=CELERY_PERIODIC",
                confidence_class="high",
                freshness="day_scoped",
                time_range=time_range,
                reason_codes=[f"periodic_count={periodic}"],
            )
        )
        bundle.runtime_items.append(
            EvidenceItem(
                invariant="cutover",
                evidence_class=EvidenceClass.RUNTIME_VERIFIED.value,
                status=(
                    EvidenceItemStatus.VIOLATION.value
                    if cutover_true_count > 0
                    else EvidenceItemStatus.PRESENT.value
                ),
                source="fleet_accounts.cutover",
                confidence_class="high",
                freshness="point_in_time_query",
                reason_codes=[f"cutover_true_count={cutover_true_count}"],
                notes="Point-in-time count; not a historical end-of-day ledger",
            )
        )

        # Correlation sample from snapshots (bounded).
        corr = await self._correlation_sample(db, query_start, query_end)
        bundle.correlation_sample = corr
        bundle.correlation_status = (
            "HEALTHY" if corr else ("MISSING" if periodic == 0 else "PARTIAL")
        )

        # --- PARTIAL: day-scoped updated_at / sent_at probes (unattributed) ---
        probes = await self._mutation_probes(db, query_start, query_end)
        for name, count, source in probes:
            bundle.partial_items.append(
                EvidenceItem(
                    invariant=name,
                    evidence_class=EvidenceClass.PARTIALLY_OBSERVED.value,
                    status=EvidenceItemStatus.PRESENT.value,
                    source=source,
                    confidence_class="low",
                    freshness="day_scoped",
                    time_range=time_range,
                    reason_codes=[f"rows_touched={count}"],
                    notes=(
                        "Counts day-window row activity only. Cannot attribute to Shadow. "
                        "Cannot prove absolute absence of mutation."
                    ),
                )
            )

        # --- STATIC_VERIFIED from manifest ---
        for ref in manifest.proof_refs:
            bundle.static_items.append(
                EvidenceItem(
                    invariant="static_proof_ref",
                    evidence_class=EvidenceClass.STATIC_VERIFIED.value,
                    status=(
                        EvidenceItemStatus.PRESENT.value
                        if manifest.manifest_status in ("MATCH", "UNKNOWN")
                        else EvidenceItemStatus.MISSING.value
                    ),
                    source="ObservationStaticProofManifest",
                    confidence_class="medium",
                    freshness="release",
                    raw_ref_sanitized=ref,
                    reason_codes=list(manifest.reason_codes),
                )
            )
        bundle.static_items.append(
            EvidenceItem(
                invariant="deployed_sha",
                evidence_class=EvidenceClass.STATIC_VERIFIED.value,
                status=(
                    EvidenceItemStatus.PRESENT.value
                    if manifest.manifest_status == "MATCH"
                    else EvidenceItemStatus.MISSING.value
                    if manifest.manifest_status == "MISSING"
                    else EvidenceItemStatus.MALFORMED.value
                ),
                source="static_manifest",
                confidence_class="medium",
                freshness="release",
                raw_ref_sanitized=(manifest.deployed_git_sha or "")[:12] or None,
                reason_codes=list(manifest.reason_codes),
            )
        )

        # --- NOT_OBSERVABLE / missing for PASS-critical attribution ---
        for inv, reason in (
            ("send_path_shadow_attribution", "NO_SHADOW_ATTRIBUTED_SEND_LEDGER"),
            ("green_api_send_absolute_absence", "NO_APPEND_ONLY_GREEN_API_DENY_LOG"),
            ("campaign_execution_shadow_attribution", "NO_SHADOW_CAMPAIGN_LEDGER"),
            ("journey_mutation_shadow_attribution", "NO_SHADOW_JOURNEY_LEDGER"),
            ("fleet_state_mutation_shadow_attribution", "NO_SHADOW_FLEETSTATE_LEDGER"),
            ("operational_mutation_shadow_attribution", "NO_ATTRIBUTED_MUTATION_LEDGER"),
            ("feature_flag_history", "NO_FLAG_HISTORY_STORE"),
            ("redis_lock_historical", "LOCK_METRICS_PROCESS_LOCAL_NOT_DAY_HISTORY"),
            ("application_log_scan", "UNBOUNDED_LOG_SCAN_FORBIDDEN"),
        ):
            bundle.missing_items.append(
                EvidenceItem(
                    invariant=inv,
                    evidence_class=EvidenceClass.NOT_OBSERVABLE.value,
                    status=EvidenceItemStatus.MISSING.value,
                    source="none",
                    confidence_class="none",
                    freshness="n/a",
                    reason_codes=[reason],
                    notes="Cannot support RUNTIME_VERIFIED daily PASS for this invariant",
                )
            )

        # Honesty: without attributed mutation ledger, bundle cannot support PASS.
        bundle.can_support_daily_pass = False
        return bundle, manifest

    async def _correlation_sample(
        self, db, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT run_id, account_id, source, observed_at, shadow_version,
                           policy_version, mismatch_class, severity, idempotency_key
                    FROM fleet_shadow_snapshots
                    WHERE observed_at >= :start AND observed_at < :end
                      AND source = :src
                    ORDER BY observed_at DESC
                    LIMIT :lim
                    """
                ),
                {
                    "start": start,
                    "end": end,
                    "src": PERIODIC_SOURCE,
                    "lim": _CORRELATION_SAMPLE_LIMIT,
                },
            )
        ).mappings().all()
        out: list[dict[str, Any]] = []
        for r in rows:
            aid = str(r["account_id"]) if r["account_id"] is not None else ""
            out.append(
                {
                    "run_id": str(r["run_id"]) if r["run_id"] is not None else None,
                    "account_id_masked": (aid[:8] if aid else None),
                    "source": r["source"],
                    "observed_at": r["observed_at"].isoformat() if r["observed_at"] else None,
                    "shadow_version": r["shadow_version"],
                    "policy_version": r["policy_version"],
                    "mismatch_class": r["mismatch_class"],
                    "severity": r["severity"],
                    "idempotency_key": r["idempotency_key"],
                }
            )
        return out

    async def _mutation_probes(
        self, db, start: datetime, end: datetime
    ) -> list[tuple[str, int, str]]:
        """Bounded COUNT probes — activity presence, not Shadow attribution."""
        probes_sql = (
            (
                "fleet_account_updates",
                "SELECT COUNT(*) FROM fleet_accounts "
                "WHERE updated_at >= :start AND updated_at < :end",
                "fleet_accounts.updated_at",
            ),
            (
                "account_journey_updates",
                "SELECT COUNT(*) FROM account_journeys "
                "WHERE updated_at >= :start AND updated_at < :end",
                "account_journeys.updated_at",
            ),
            (
                "journey_action_updates",
                "SELECT COUNT(*) FROM journey_actions "
                "WHERE updated_at >= :start AND updated_at < :end",
                "journey_actions.updated_at",
            ),
            (
                "campaign_contact_sends",
                "SELECT COUNT(*) FROM campaign_contacts "
                "WHERE sent_at IS NOT NULL AND sent_at >= :start AND sent_at < :end",
                "campaign_contacts.sent_at",
            ),
            (
                "daily_send_log_rows",
                "SELECT COUNT(*) FROM daily_send_logs "
                "WHERE sent_at IS NOT NULL AND sent_at >= :start AND sent_at < :end",
                "daily_send_logs.sent_at",
            ),
        )
        results: list[tuple[str, int, str]] = []
        for name, sql, source in probes_sql:
            try:
                n = (
                    await db.execute(text(sql), {"start": start, "end": end})
                ).scalar()
                results.append((name, int(n or 0), source))
            except Exception:
                results.append((name, -1, source + ":query_failed"))
        return results


def map_evidence_to_report_statuses(bundle: DailyObservationEvidenceBundle) -> dict[str, str]:
    """Map honesty classes onto Phase A EvidenceStatus fields (fail-closed)."""
    from app.services.daily_observation.contract import EvidenceStatus

    # Attributed mutation proof is NOT_OBSERVABLE → keep INSUFFICIENT for PASS ladder.
    insufficient = EvidenceStatus.INSUFFICIENT_EVIDENCE.value
    return {
        "send_path_evidence_status": insufficient,
        "green_api_send_evidence_status": insufficient,
        "campaign_execution_evidence_status": insufficient,
        "journey_mutation_evidence_status": insufficient,
        "fleet_state_mutation_evidence_status": insufficient,
        "send_gate_integrity_evidence_status": insufficient,
        "operational_mutation_evidence_status": insufficient,
        "runtime_observed_evidence": [
            f"{i.invariant}:{i.status}" for i in bundle.runtime_items
        ],
        "static_test_evidence": [
            (i.raw_ref_sanitized or i.invariant) for i in bundle.static_items if i.raw_ref_sanitized
        ],
    }
