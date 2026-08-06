"""Compatibility + read-only tests for Shadow daily report CLI wrapper."""
from __future__ import annotations
import inspect

from app.scripts import fleet_shadow_daily_report as mod
from app.services.daily_observation.ticks import day_bounds_utc
from app.services.daily_observation.persian_render import render_markdown
from app.services.daily_observation.contract import DailyObservationReport


def test_daily_report_is_read_only_source():
    src = inspect.getsource(mod)
    assert "DailyObservationReportService" in src
    assert "read-only" in (mod.__doc__ or "").lower() or "Read-only" in (mod.__doc__ or "")
    assert "v67_shadow_runtime_enabled=True" not in src
    assert "sendMessage" not in src
    assert "FLUSH" not in src
    assert "DELETE FROM" not in src


def test_day_bounds():
    start, end = day_bounds_utc("2026-08-05")
    assert start.year == 2026 and start.month == 8 and start.day == 5
    assert (end - start).days == 1


def test_markdown_render_no_secrets():
    report = DailyObservationReport(
        report_date_utc="2026-08-05",
        total_snapshots=1,
        accounts_covered=1,
        accounts_expected=1,
        by_mismatch_class={"RUNTIME_UNKNOWN": 1},
        by_severity={"HIGH": 1},
        overall_status="REVIEW_REQUIRED",
        shadow_runtime_flag_status="HEALTHY",
        shadow_scheduler_flag_status="HEALTHY",
    )
    md = render_markdown(report)
    assert "RUNTIME_UNKNOWN" in md
    assert "token" not in md.lower()
    assert "phase7_fully_accepted: false" in md
