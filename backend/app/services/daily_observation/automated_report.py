"""Read-only automated daily observation report generation helpers (Phase C).

No notifications. No business DB writes. Optional atomic file write under /app/var.
"""
from __future__ import annotations
import json
import logging
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.services.daily_observation.persian_render import render_markdown, render_persian_text
from app.services.daily_observation.service import DailyObservationReportService

logger = logging.getLogger(__name__)

# Compose mounts ./backend → /app; keep reports under backend tree.
DEFAULT_REPORT_DIR = Path(os.environ.get("V67_DAILY_OBS_REPORT_DIR", "/app/var/daily_observation_reports"))


def previous_completed_utc_day(now_utc: datetime | None = None) -> str:
    now = now_utc or datetime.utcnow()
    d = (now - timedelta(days=1)).date()
    return d.strftime("%Y-%m-%d")


def safe_report_paths(day_utc: str, base: Path | None = None) -> tuple[Path, Path]:
    """Reject path traversal; only YYYY-MM-DD filenames under base."""
    if len(day_utc) != 10 or day_utc[4] != "-" or day_utc[7] != "-":
        raise ValueError("invalid_date")
    datetime.strptime(day_utc, "%Y-%m-%d")
    if ".." in day_utc or "/" in day_utc or "\\" in day_utc:
        raise ValueError("path_traversal")
    root = (base or DEFAULT_REPORT_DIR).resolve()
    json_path = (root / f"{day_utc}.json").resolve()
    md_path = (root / f"{day_utc}.fa.md").resolve()
    if not str(json_path).startswith(str(root)) or not str(md_path).startswith(str(root)):
        raise ValueError("path_traversal")
    return json_path, md_path


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp_obs_", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


async def generate_daily_observation_report(
    *,
    day_utc: str | None = None,
    write_files: bool = True,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Build previous (or given) UTC day report via the single Phase A/C engine."""
    now = now_utc or datetime.utcnow()
    day = day_utc or previous_completed_utc_day(now)
    service = DailyObservationReportService()
    report = await service.build(day, now_utc=now, probe_infra=True)
    payload = report.to_dict()
    # Attach Phase C owner sections if present on report object
    for attr in ("evidence_bundle", "static_manifest", "stop_conditions", "automated_report_meta"):
        if hasattr(report, attr):
            val = getattr(report, attr)
            if val is not None:
                payload[attr] = val

    fa_text = render_persian_text(report, show_evidence=True)
    md_text = render_markdown(report)

    logger.info(
        "daily_observation_report day=%s status=%s can_count=%s reasons=%s "
        "read_only=true mutates_runtime=false executes=false",
        day,
        report.overall_status,
        report.can_count_as_valid_day,
        ",".join(report.overall_reason_codes[:12]),
    )

    files_written: list[str] = []
    if write_files:
        try:
            jp, mp = safe_report_paths(day)
            _atomic_write(jp, json.dumps(payload, ensure_ascii=False, indent=2, default=str))
            _atomic_write(mp, fa_text if fa_text.strip() else md_text)
            files_written = [str(jp), str(mp)]
        except Exception as e:
            logger.warning("daily_observation_report_file_write_failed day=%s err=%s", day, type(e).__name__)

    return {
        "day_utc": day,
        "overall_status": report.overall_status,
        "can_count_as_valid_day": report.can_count_as_valid_day,
        "reason_codes": list(report.overall_reason_codes),
        "files_written": files_written,
        "read_only": True,
        "mutates_runtime": False,
        "executes": False,
        "report_version": report.report_version,
    }
