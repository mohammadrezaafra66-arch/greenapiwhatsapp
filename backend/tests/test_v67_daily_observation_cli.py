"""CLI consumer tests for daily observation report."""
from __future__ import annotations
import inspect
from unittest.mock import AsyncMock, patch

import pytest

from app.scripts import fleet_shadow_daily_report as cli
from app.services.daily_observation.contract import DailyObservationReport, OverallStatus


def test_cli_no_mutation_options():
    src = inspect.getsource(cli)
    for banned in ("--enable", "--disable", "--persist", "--cutover", "--send", "Green API"):
        if banned == "Green API":
            assert "never calls Green API" in (cli.__doc__ or "") or "Green API" in src
            continue
        assert banned not in src


def test_cli_uses_service_not_parallel_sql():
    src = inspect.getsource(cli)
    assert "DailyObservationReportService" in src
    assert "FROM fleet_shadow_snapshots" not in src


def test_invalid_date_exit_2():
    assert cli.main(["--date", "not-a-date"]) == cli.EXIT_INVALID_DATE


def test_unsupported_session_exit():
    code = cli.main(["--date", "2026-08-06", "--session", "session-1"])
    assert code == cli.EXIT_ERROR


@pytest.mark.parametrize(
    "status,expected",
    [
        (OverallStatus.PASS.value, cli.EXIT_PASS),
        (OverallStatus.FAIL.value, cli.EXIT_FAIL),
        (OverallStatus.REVIEW_REQUIRED.value, cli.EXIT_REVIEW_REQUIRED),
        (OverallStatus.INSUFFICIENT_EVIDENCE.value, cli.EXIT_INSUFFICIENT_EVIDENCE),
        (OverallStatus.NOT_APPLICABLE.value, cli.EXIT_NOT_APPLICABLE),
    ],
)
def test_exit_codes(status, expected, capsys):
    report = DailyObservationReport(
        report_date_utc="2026-08-06",
        overall_status=status,
        database_status="HEALTHY",
        owner_action_fa="x",
    )

    async def _build(*a, **k):
        return report

    with patch.object(cli.DailyObservationReportService, "build", new=AsyncMock(side_effect=_build)):
        code = cli.main(["--date", "2026-08-06", "--format", "json"])
    assert code == expected
    out = capsys.readouterr().out
    assert "phase7_fully_accepted" in out
    assert '"phase7_fully_accepted": false' in out.lower() or '"phase7_fully_accepted": false' in out


def test_default_persian_format(capsys):
    report = DailyObservationReport(
        report_date_utc="2026-08-06",
        overall_status=OverallStatus.INSUFFICIENT_EVIDENCE.value,
        database_status="HEALTHY",
        owner_action_fa="اطلاعات کافی",
        calendar_day_index=1,
    )

    with patch.object(
        cli.DailyObservationReportService,
        "build",
        new=AsyncMock(return_value=report),
    ):
        code = cli.main(["--date", "2026-08-06"])
    out = capsys.readouterr().out
    assert "گزارش روزانه دوره مشاهده Phase 7" in out
    assert code == cli.EXIT_INSUFFICIENT_EVIDENCE


def test_markdown_and_text_formats(capsys):
    report = DailyObservationReport(
        report_date_utc="2026-08-06",
        overall_status=OverallStatus.REVIEW_REQUIRED.value,
        database_status="HEALTHY",
    )
    with patch.object(
        cli.DailyObservationReportService,
        "build",
        new=AsyncMock(return_value=report),
    ):
        assert cli.main(["--date", "2026-08-06", "--format", "markdown"]) == cli.EXIT_REVIEW_REQUIRED
        assert "overall_status" in capsys.readouterr().out
        assert cli.main(["--date", "2026-08-06", "--format", "text"]) == cli.EXIT_REVIEW_REQUIRED
