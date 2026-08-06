"""Phase C — evidence model, collector honesty, static manifest, automated report, no false PASS."""
from __future__ import annotations
import inspect
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.daily_observation.automated_report import (
    previous_completed_utc_day,
    safe_report_paths,
)
from app.services.daily_observation.contract import EvidenceStatus, InfraStatus, OverallStatus
from app.services.daily_observation.evidence_collector import (
    DailyObservationEvidenceCollector,
    map_evidence_to_report_statuses,
)
from app.services.daily_observation.evidence_model import EVIDENCE_BUNDLE_VERSION
from app.services.daily_observation.static_manifest import (
    STATIC_PROOF_VERSION,
    build_static_manifest,
    evaluate_sha_against_manifest,
)
from app.services.daily_observation.validator import validate_report_dict
from app.workers import celery_app as celery_mod
from app.workers import tasks as tasks_mod


def test_evidence_bundle_version():
    assert EVIDENCE_BUNDLE_VERSION == "v67.owner.daily-observation.evidence.1"


def test_static_proof_version():
    assert STATIC_PROOF_VERSION == "v67.owner.daily-observation.static-proof.1"


def test_static_only_cannot_pass():
    """HEALTHY infra + MATCH manifest but insufficient mutation → no PASS."""
    r = validate_report_dict(
        dict(
            accounts_expected=1,
            accounts_covered=1,
            expected_periodic_ticks=10,
            actual_periodic_snapshots=10,
            database_status=InfraStatus.HEALTHY.value,
            redis_status=InfraStatus.HEALTHY.value,
            celery_worker_status=InfraStatus.HEALTHY.value,
            celery_beat_status=InfraStatus.HEALTHY.value,
            scheduler_status=InfraStatus.HEALTHY.value,
            shadow_scheduler_flag_status=InfraStatus.HEALTHY.value,
            send_path_evidence_status=EvidenceStatus.INSUFFICIENT_EVIDENCE.value,
            green_api_send_evidence_status=EvidenceStatus.INSUFFICIENT_EVIDENCE.value,
            campaign_execution_evidence_status=EvidenceStatus.INSUFFICIENT_EVIDENCE.value,
            journey_mutation_evidence_status=EvidenceStatus.INSUFFICIENT_EVIDENCE.value,
            fleet_state_mutation_evidence_status=EvidenceStatus.INSUFFICIENT_EVIDENCE.value,
            send_gate_integrity_evidence_status=EvidenceStatus.INSUFFICIENT_EVIDENCE.value,
            operational_mutation_evidence_status=EvidenceStatus.INSUFFICIENT_EVIDENCE.value,
            static_manifest_status="MATCH",
            evidence_bundle={
                "can_support_daily_pass": False,
                "missing_items": [{"invariant": "send_path"}],
            },
        )
    )
    assert r.overall_status != OverallStatus.PASS.value
    assert r.can_count_as_valid_day is False


def test_manifest_mismatch_fail():
    r = validate_report_dict(
        dict(
            accounts_expected=1,
            accounts_covered=1,
            expected_periodic_ticks=1,
            actual_periodic_snapshots=1,
            database_status=InfraStatus.HEALTHY.value,
            redis_status=InfraStatus.HEALTHY.value,
            celery_worker_status=InfraStatus.HEALTHY.value,
            celery_beat_status=InfraStatus.HEALTHY.value,
            scheduler_status=InfraStatus.HEALTHY.value,
            shadow_scheduler_flag_status=InfraStatus.HEALTHY.value,
            send_path_evidence_status=EvidenceStatus.HEALTHY.value,
            green_api_send_evidence_status=EvidenceStatus.HEALTHY.value,
            campaign_execution_evidence_status=EvidenceStatus.HEALTHY.value,
            journey_mutation_evidence_status=EvidenceStatus.HEALTHY.value,
            fleet_state_mutation_evidence_status=EvidenceStatus.HEALTHY.value,
            send_gate_integrity_evidence_status=EvidenceStatus.HEALTHY.value,
            operational_mutation_evidence_status=EvidenceStatus.HEALTHY.value,
            static_manifest_status="MISMATCH",
            evidence_bundle={"can_support_daily_pass": True, "missing_items": []},
        )
    )
    assert r.overall_status == OverallStatus.FAIL.value
    assert "STATIC_MANIFEST_MISMATCH" in r.validity_reason_codes


def test_false_pass_guard_when_bundle_claims_support_with_insufficient_mutation():
    r = validate_report_dict(
        dict(
            accounts_expected=1,
            accounts_covered=1,
            expected_periodic_ticks=10,
            actual_periodic_snapshots=10,
            database_status=InfraStatus.HEALTHY.value,
            redis_status=InfraStatus.HEALTHY.value,
            celery_worker_status=InfraStatus.HEALTHY.value,
            celery_beat_status=InfraStatus.HEALTHY.value,
            scheduler_status=InfraStatus.HEALTHY.value,
            shadow_scheduler_flag_status=InfraStatus.HEALTHY.value,
            send_path_evidence_status=EvidenceStatus.INSUFFICIENT_EVIDENCE.value,
            green_api_send_evidence_status=EvidenceStatus.INSUFFICIENT_EVIDENCE.value,
            campaign_execution_evidence_status=EvidenceStatus.INSUFFICIENT_EVIDENCE.value,
            journey_mutation_evidence_status=EvidenceStatus.INSUFFICIENT_EVIDENCE.value,
            fleet_state_mutation_evidence_status=EvidenceStatus.INSUFFICIENT_EVIDENCE.value,
            send_gate_integrity_evidence_status=EvidenceStatus.INSUFFICIENT_EVIDENCE.value,
            operational_mutation_evidence_status=EvidenceStatus.INSUFFICIENT_EVIDENCE.value,
            static_manifest_status="MATCH",
            evidence_bundle={"can_support_daily_pass": True, "missing_items": []},
        )
    )
    assert r.overall_status != OverallStatus.PASS.value
    assert "EVIDENCE_CANNOT_SUPPORT_PASS" in r.validity_reason_codes


def test_map_evidence_keeps_mutation_insufficient():
    from app.services.daily_observation.evidence_model import DailyObservationEvidenceBundle

    mapped = map_evidence_to_report_statuses(DailyObservationEvidenceBundle())
    assert mapped["operational_mutation_evidence_status"] == EvidenceStatus.INSUFFICIENT_EVIDENCE.value
    assert mapped["send_path_evidence_status"] == EvidenceStatus.INSUFFICIENT_EVIDENCE.value


def test_build_static_manifest_single_source_is_unknown_not_match():
    """P1 honesty: resolving one SHA must not self-compare into MATCH."""
    with patch(
        "app.services.daily_observation.static_manifest.resolve_deployed_git_sha",
        return_value="abc123",
    ), patch(
        "app.services.daily_observation.static_manifest.resolve_expected_git_sha",
        return_value=None,
    ):
        m = build_static_manifest()
    assert m.manifest_status == "UNKNOWN"
    assert m.sha_match is None
    assert "DEPLOYED_SHA_SINGLE_SOURCE" in m.reason_codes
    assert m.deployed_git_sha == "abc123"


def test_build_static_manifest_match_requires_independent_expected():
    with patch(
        "app.services.daily_observation.static_manifest.resolve_deployed_git_sha",
        return_value="abc123",
    ):
        m = build_static_manifest(expected_sha="abc123")
    assert m.manifest_status == "MATCH"
    assert m.sha_match is True
    assert "DEPLOYED_SHA_INDEPENDENT_MATCH" in m.reason_codes


def test_build_static_manifest_independent_mismatch():
    with patch(
        "app.services.daily_observation.static_manifest.resolve_deployed_git_sha",
        return_value="aaa",
    ):
        m = build_static_manifest(expected_sha="bbb")
    assert m.manifest_status == "MISMATCH"
    assert m.sha_match is False


def test_evaluate_sha_mismatch():
    with patch(
        "app.services.daily_observation.static_manifest.resolve_deployed_git_sha",
        return_value="aaa",
    ):
        m = build_static_manifest(expected_sha="aaa")
    m = evaluate_sha_against_manifest(m, runtime_sha="bbb")
    assert m.manifest_status == "MISMATCH"


def test_previous_completed_utc_day():
    assert previous_completed_utc_day(datetime(2026, 8, 6, 7, 0, 0)) == "2026-08-05"


def test_safe_report_paths_rejects_traversal(tmp_path):
    with pytest.raises(ValueError):
        safe_report_paths("../evil", base=tmp_path)
    jp, mp = safe_report_paths("2026-08-05", base=tmp_path)
    assert jp.name == "2026-08-05.json"
    assert mp.name == "2026-08-05.fa.md"


def test_beat_schedule_registers_daily_observation():
    entry = celery_mod.celery_app.conf.beat_schedule.get("daily-observation-report")
    assert entry is not None
    assert entry["task"] == "tasks.daily_observation_report"


def test_daily_task_source_is_readonly():
    src = inspect.getsource(tasks_mod.task_daily_observation_report)
    assert "generate_daily_observation_report" in src
    assert "sendMessage" not in src
    assert "GreenAPI" not in src
    assert "run_campaign" not in src
    assert "cutover" not in src.lower() or "mutates_runtime" in src


@pytest.mark.asyncio
async def test_collector_marks_mutation_not_observable():
    db = MagicMock()

    async def _execute(sql, params=None):
        q = str(sql)
        result = MagicMock()
        if "LIMIT" in q and "run_id" in q:
            result.mappings.return_value.all.return_value = []
        else:
            result.scalar.return_value = 0
        return result

    db.execute = AsyncMock(side_effect=_execute)
    with patch(
        "app.services.daily_observation.evidence_collector.build_static_manifest"
    ) as bm:
        from app.services.daily_observation.static_manifest import ObservationStaticProofManifest

        bm.return_value = ObservationStaticProofManifest(
            deployed_git_sha="deadbeef",
            manifest_status="MATCH",
            sha_match=True,
        )
        bundle, manifest = await DailyObservationEvidenceCollector().collect(
            db,
            report_date_utc="2026-08-05",
            query_start=datetime(2026, 8, 5, 0, 0, 0),
            query_end=datetime(2026, 8, 6, 0, 0, 0),
            now_utc=datetime(2026, 8, 6, 1, 0, 0),
            policy_version=1,
            migration_revision="rev",
            snapshot_summary={"sim_violations": 0, "mut_violations": 0, "exec_violations": 0, "periodic": 3},
            cutover_true_count=0,
        )
    assert bundle.can_support_daily_pass is False
    assert any(i.evidence_class == "NOT_OBSERVABLE" for i in bundle.missing_items)
    assert any(i.invariant == "snapshot_flags" for i in bundle.runtime_items)
    assert manifest.manifest_status == "MATCH"
    assert "STATIC_ONLY_CANNOT_PASS" in bundle.false_pass_guards


def test_collector_no_write_in_source():
    src = inspect.getsource(DailyObservationEvidenceCollector)
    assert "INSERT " not in src.upper()
    assert "UPDATE " not in src.upper()
    assert "DELETE " not in src.upper()
    assert "commit(" not in src


def test_automated_report_no_notification_imports():
    from app.services.daily_observation import automated_report as ar

    src = inspect.getsource(ar)
    assert "send_night_report" not in src
    assert "whatsapp" not in src.lower()
    assert "smtp" not in src.lower()


def test_phase_c_modules_exist():
    assert Path("app/services/daily_observation/evidence_model.py").exists() or Path(
        "backend/app/services/daily_observation/evidence_model.py"
    ).exists()
