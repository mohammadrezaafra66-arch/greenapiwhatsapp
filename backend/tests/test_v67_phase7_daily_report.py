"""Tests for read-only Shadow daily report helper."""
from __future__ import annotations
import inspect

from app.scripts import fleet_shadow_daily_report as mod


def test_daily_report_is_read_only_source():
    src = inspect.getsource(mod)
    assert "read_only" in src
    assert "Green API" in mod.__doc__ or "Green API" in src or "never calls Green API" in (mod.__doc__ or "")
    assert "v67_shadow_runtime_enabled=True" not in src
    assert "sendMessage" not in src
    assert "FLUSH" not in src
    assert "DELETE FROM" not in src


def test_day_bounds():
    start, end = mod._day_bounds("2026-08-05")
    assert start.year == 2026 and start.month == 8 and start.day == 5
    assert (end - start).days == 1


def test_markdown_render_no_secrets():
    report = {
        "date_utc": "2026-08-05",
        "snapshots_total": 1,
        "accounts_covered": 1,
        "high_critical_count": 1,
        "v67_shadow_runtime_enabled": False,
        "v67_shadow_scheduler_enabled": False,
        "dangerous_threshold_status": "UNRATIFIED",
        "stop_condition_status": "REVIEW_REQUIRED",
        "by_mismatch_class": {"RUNTIME_UNKNOWN": 1},
        "by_severity": {"HIGH": 1},
    }
    md = mod.to_markdown(report)
    assert "RUNTIME_UNKNOWN" in md
    assert "token" not in md.lower()
