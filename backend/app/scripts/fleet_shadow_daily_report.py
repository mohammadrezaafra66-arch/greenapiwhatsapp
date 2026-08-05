"""V67 Phase 7.3 — read-only daily Shadow observation report (UTC day).

Never enables flags, never deletes, never calls Green API / send / campaign / Journey.
"""
from __future__ import annotations
import argparse
import asyncio
import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.config import settings


def _day_bounds(day_utc: str) -> tuple[datetime, datetime]:
    start = datetime.strptime(day_utc, "%Y-%m-%d")
    end = start + timedelta(days=1)
    return start, end


async def build_report(day_utc: str) -> dict[str, Any]:
    start, end = _day_bounds(day_utc)
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            text(
                """
                SELECT mismatch_class, severity, COUNT(*) AS n
                FROM fleet_shadow_snapshots
                WHERE observed_at >= :start AND observed_at < :end
                GROUP BY 1, 2
                ORDER BY 1, 2
                """
            ),
            {"start": start, "end": end},
        )).mappings().all()
        total = (await db.execute(
            text(
                """
                SELECT COUNT(*) AS n,
                       COUNT(DISTINCT account_id) AS accounts,
                       MIN(observed_at) AS first_at,
                       MAX(observed_at) AS last_at
                FROM fleet_shadow_snapshots
                WHERE observed_at >= :start AND observed_at < :end
                """
            ),
            {"start": start, "end": end},
        )).mappings().one()
        critical = (await db.execute(
            text(
                """
                SELECT COUNT(*) AS n FROM fleet_shadow_snapshots
                WHERE observed_at >= :start AND observed_at < :end
                  AND severity IN ('HIGH','CRITICAL')
                """
            ),
            {"start": start, "end": end},
        )).scalar() or 0
    by_class: dict[str, int] = {}
    by_sev: dict[str, int] = {}
    for r in rows:
        by_class[r["mismatch_class"]] = by_class.get(r["mismatch_class"], 0) + int(r["n"])
        by_sev[r["severity"]] = by_sev.get(r["severity"], 0) + int(r["n"])
    return {
        "date_utc": day_utc,
        "read_only": True,
        "simulation_only": True,
        "mutates_runtime": False,
        "executes": False,
        "v67_shadow_runtime_enabled": bool(settings.v67_shadow_runtime_enabled),
        "v67_shadow_scheduler_enabled": bool(settings.v67_shadow_scheduler_enabled),
        "dangerous_threshold_status": "UNRATIFIED",
        "snapshots_total": int(total["n"] or 0),
        "accounts_covered": int(total["accounts"] or 0),
        "first_observed_at": total["first_at"].isoformat() if total["first_at"] else None,
        "last_observed_at": total["last_at"].isoformat() if total["last_at"] else None,
        "by_mismatch_class": by_class,
        "by_severity": by_sev,
        "high_critical_count": int(critical),
        "stop_condition_status": "REVIEW_REQUIRED" if int(critical) else "OK_NO_AUTO_ACTION",
        "notes": "Pre-enable / manual snapshots do not count toward observation days.",
    }


def to_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Shadow daily report {report['date_utc']} (UTC)",
        "",
        f"- snapshots: {report['snapshots_total']}",
        f"- accounts: {report['accounts_covered']}",
        f"- high/critical: {report['high_critical_count']}",
        f"- runtime_flag: {report['v67_shadow_runtime_enabled']}",
        f"- scheduler_flag: {report['v67_shadow_scheduler_enabled']}",
        f"- threshold: {report['dangerous_threshold_status']}",
        f"- stop_status: {report['stop_condition_status']}",
        "",
        "## By mismatch class",
    ]
    for k, v in sorted(report["by_mismatch_class"].items()):
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## By severity")
    for k, v in sorted(report["by_severity"].items()):
        lines.append(f"- {k}: {v}")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Read-only Shadow daily report")
    p.add_argument("--date", default=datetime.utcnow().strftime("%Y-%m-%d"), help="UTC YYYY-MM-DD")
    p.add_argument("--format", choices=("json", "markdown"), default="json")
    args = p.parse_args(argv)
    report = asyncio.run(build_report(args.date))
    if args.format == "markdown":
        print(to_markdown(report))
    else:
        print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
