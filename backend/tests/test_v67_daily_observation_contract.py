"""Contract tests for Daily Observation Report Phase A."""
from __future__ import annotations
import json

from app.services.daily_observation.contract import (
    REPORT_VERSION,
    DailyObservationReport,
    OverallStatus,
)
from app.services.daily_observation.persian_render import render_persian_text
from app.services.daily_observation.session_meta import PERIODIC_TICK_INTERVAL_SECONDS
from app.workers.celery_app import celery_app


def test_report_version_constant():
    assert REPORT_VERSION == "v67.owner.daily-observation.1"
    r = DailyObservationReport()
    assert r.report_version == REPORT_VERSION


def test_serialization_stable_and_hard_false_flags():
    r = DailyObservationReport(report_date_utc="2026-08-06", overall_status=OverallStatus.PASS.value)
    r.phase7_fully_accepted = True  # attempt tamper
    r.phase8_allowed = True
    d = r.to_dict()
    assert d["phase7_fully_accepted"] is False
    assert d["phase8_allowed"] is False
    assert d["report_version"] == REPORT_VERSION
    json.dumps(d, default=str)  # must serialize


def test_enum_values():
    assert OverallStatus.PASS.value == "PASS"
    assert OverallStatus.FAIL.value == "FAIL"
    assert OverallStatus.REVIEW_REQUIRED.value == "REVIEW_REQUIRED"
    assert OverallStatus.INSUFFICIENT_EVIDENCE.value == "INSUFFICIENT_EVIDENCE"


def test_null_unknown_defaults():
    r = DailyObservationReport()
    assert r.database_status == "UNKNOWN"
    assert r.operational_mutation_evidence_status == "INSUFFICIENT_EVIDENCE"
    assert r.can_count_as_valid_day is False


def test_persian_output_stable_title():
    r = DailyObservationReport(
        report_date_utc="2026-08-06",
        overall_status="INSUFFICIENT_EVIDENCE",
        owner_action_fa="اطلاعات کافی برای معتبر دانستن این روز وجود ندارد. نتیجه را PASS تلقی نکنید.",
        calendar_day_index=1,
    )
    txt = render_persian_text(r)
    assert "گزارش روزانه دوره مشاهده Phase 7" in txt
    assert "PHASE 7 FULLY ACCEPTED" not in txt
    assert "Phase 7 کامل پذیرفته شده؟ خیر" in txt


def test_tick_interval_matches_celery_beat():
    entry = celery_app.conf.beat_schedule["fleet-shadow-tick"]
    assert float(entry["schedule"]) == float(PERIODIC_TICK_INTERVAL_SECONDS)
