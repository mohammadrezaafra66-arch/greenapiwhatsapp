"""Phase D final acceptance — read-only, honesty, automation, security surfaces."""
from __future__ import annotations
import inspect
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.daily_observation.automated_report import (
    previous_completed_utc_day,
    safe_report_paths,
)
from app.services.daily_observation.contract import EvidenceStatus, InfraStatus, OverallStatus
from app.services.daily_observation.evidence_collector import DailyObservationEvidenceCollector
from app.services.daily_observation.static_manifest import build_static_manifest
from app.services.daily_observation.validator import validate_report_dict
from app.workers import celery_app as celery_mod
from app.workers import tasks as tasks_mod


def test_beat_schedule_is_0600_utc_via_tehran_crontab():
    entry = celery_mod.celery_app.conf.beat_schedule["daily-observation-report"]
    assert entry["task"] == "tasks.daily_observation_report"
    sched = entry["schedule"]
    # Celery timezone Asia/Tehran → 06:00 UTC == 09:30 Tehran
    assert getattr(sched, "hour", set()) == {9} or (hasattr(sched, "hour") and 9 in sched.hour)
    assert getattr(sched, "minute", set()) == {30} or (hasattr(sched, "minute") and 30 in sched.minute)
    assert celery_mod.celery_app.conf.timezone == "Asia/Tehran"


def test_task_targets_previous_completed_utc_day_only():
    assert previous_completed_utc_day(datetime(2026, 8, 6, 9, 30, 0)) == "2026-08-05"
    src = inspect.getsource(tasks_mod.task_daily_observation_report)
    assert "generate_daily_observation_report" in src
    assert tasks_mod.task_daily_observation_report.soft_time_limit == 120
    assert tasks_mod.task_daily_observation_report.time_limit == 180


def test_task_has_no_send_campaign_green_api_or_chain():
    src = inspect.getsource(tasks_mod.task_daily_observation_report)
    assert "sendMessage" not in src
    assert "GreenAPI" not in src
    assert "run_campaign" not in src
    assert ".delay(" not in src
    assert ".apply_async" not in src


def test_collector_source_read_only_and_bounded():
    src = inspect.getsource(DailyObservationEvidenceCollector)
    assert "INSERT " not in src.upper()
    assert "UPDATE " not in src.upper()
    assert "DELETE " not in src.upper()
    assert "commit(" not in src
    assert "LIMIT" in src
    assert "UNBOUNDED_LOG_SCAN_FORBIDDEN" in src or "log scan" in src.lower() or "application_log_scan" in src


def test_static_only_and_missing_ledger_never_pass():
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
            evidence_bundle={"can_support_daily_pass": False, "missing_items": [{"x": 1}]},
        )
    )
    assert r.overall_status != OverallStatus.PASS.value
    assert r.can_count_as_valid_day is False
    assert r.phase7_fully_accepted is False
    assert r.phase8_allowed is False


def test_delivery_api_get_only_no_token():
    from app.api.v1 import fleet_observation as mod

    src = inspect.getsource(mod)
    assert "@router.get" in src
    assert "@router.post" not in src
    assert "X-Fleet-Shadow-Token" not in src
    assert "DailyObservationReportService" in src


def test_frontend_page_has_evidence_and_no_actions():
    # Docker mounts only ./backend → /app; host checkout may expose sibling frontend.
    here = Path(__file__).resolve()
    candidates = []
    for p in here.parents:
        candidates.append(p / "frontend" / "src" / "pages" / "DailyObservationReport.jsx")
        candidates.append(p / "src" / "pages" / "DailyObservationReport.jsx")
    candidates.append(Path("/frontend/src/pages/DailyObservationReport.jsx"))
    src = None
    for c in candidates:
        try:
            if c.is_file():
                src = c.read_text(encoding="utf-8")
                break
        except (OSError, IndexError):
            continue
    if src is None:
        pytest.skip("frontend sources not mounted in this environment")
    assert "runtime-evidence-section" in src
    assert "stop-conditions-section" in src
    assert "ObservationApi.report" in src
    assert ".post(" not in src
    assert "X-Fleet-Shadow-Token" not in src
    assert "Phase 7 Fully Accepted" not in src


def test_path_traversal_rejected(tmp_path):
    with pytest.raises(ValueError):
        safe_report_paths("../../../etc/passwd", base=tmp_path)


def test_manifest_no_self_match_without_expected():
    with patch(
        "app.services.daily_observation.static_manifest.resolve_deployed_git_sha",
        return_value="deadbeef",
    ), patch(
        "app.services.daily_observation.static_manifest.resolve_expected_git_sha",
        return_value=None,
    ):
        m = build_static_manifest()
    assert m.manifest_status != "MATCH"
    assert m.manifest_status == "UNKNOWN"
