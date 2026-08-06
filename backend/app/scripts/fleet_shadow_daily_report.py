"""V67 Owner Change — Read-Only Daily Observation Report CLI (Phase A).

Consumes DailyObservationReportService. Never enables flags, never deletes,
never calls Green API / send / campaign / Journey, never mutates runtime.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import sys

from app.services.daily_observation.contract import OverallStatus
from app.services.daily_observation.persian_render import (
    render_markdown,
    render_persian_text,
    render_text,
)
from app.services.daily_observation.service import DailyObservationReportService
from app.services.daily_observation.session_meta import SESSION_2_ID

# Documented exit codes
EXIT_PASS = 0
EXIT_INVALID_DATE = 2
EXIT_DB_UNAVAILABLE = 3
EXIT_REVIEW_REQUIRED = 10
EXIT_INSUFFICIENT_EVIDENCE = 11
EXIT_FAIL = 12
EXIT_NOT_APPLICABLE = 13
EXIT_ERROR = 1


def _exit_for_status(status: str) -> int:
    return {
        OverallStatus.PASS.value: EXIT_PASS,
        OverallStatus.REVIEW_REQUIRED.value: EXIT_REVIEW_REQUIRED,
        OverallStatus.INSUFFICIENT_EVIDENCE.value: EXIT_INSUFFICIENT_EVIDENCE,
        OverallStatus.FAIL.value: EXIT_FAIL,
        OverallStatus.NOT_APPLICABLE.value: EXIT_NOT_APPLICABLE,
    }.get(status, EXIT_ERROR)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Read-only Daily Observation Report (Owner Change Phase A)"
    )
    p.add_argument("--date", required=False, default=None, help="UTC YYYY-MM-DD (default: today UTC)")
    p.add_argument(
        "--format",
        choices=("json", "markdown", "text", "persian-text"),
        default="persian-text",
    )
    p.add_argument("--session", default=SESSION_2_ID, help="Logical session id (session-2)")
    p.add_argument("--show-evidence", action="store_true")
    p.add_argument("--strict", action="store_true")
    args = p.parse_args(argv)

    if args.session != SESSION_2_ID:
        print(json.dumps({"error": "unsupported_session", "session": args.session}), file=sys.stderr)
        return EXIT_ERROR

    from datetime import datetime

    day = args.date or datetime.utcnow().strftime("%Y-%m-%d")
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        print(json.dumps({"error": "invalid_date", "date": day}), file=sys.stderr)
        return EXIT_INVALID_DATE

    try:
        report = asyncio.run(
            DailyObservationReportService().build(day, strict=bool(args.strict))
        )
    except ValueError as e:
        if str(e).startswith("invalid_date"):
            print(json.dumps({"error": "invalid_date", "date": day}), file=sys.stderr)
            return EXIT_INVALID_DATE
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return EXIT_ERROR
    except Exception as e:
        # DB / infra hard failure
        print(json.dumps({"error": "report_failed", "detail": str(e)}), file=sys.stderr)
        if "database" in str(e).lower() or "connect" in str(e).lower():
            return EXIT_DB_UNAVAILABLE
        return EXIT_ERROR

    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2, default=str, ensure_ascii=False))
    elif args.format == "markdown":
        print(render_markdown(report), end="")
    elif args.format == "text":
        print(render_text(report), end="")
    else:
        print(render_persian_text(report, show_evidence=bool(args.show_evidence)), end="")

    if report.database_status == "UNHEALTHY":
        return EXIT_DB_UNAVAILABLE
    return _exit_for_status(report.overall_status)


if __name__ == "__main__":
    raise SystemExit(main())
