"""V67 Phase 5 — Scheduling Planner (simulation windows only; no Celery/queue)."""
from __future__ import annotations
import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, time
from typing import Any
from zoneinfo import ZoneInfo

SCHEDULE_VERSION = "v67.5.schedule.1"


def _deterministic_jitter_seconds(seed: str, max_seconds: int) -> int:
    """Stable jitter from seed — not OS randomness (planner must be deterministic)."""
    if max_seconds <= 0:
        return 0
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % (max_seconds + 1)


@dataclass(frozen=True)
class SchedulePreview:
    timezone: str
    working_hours_start: str
    working_hours_end: str
    slots: tuple[dict[str, Any], ...]
    holiday_placeholder: bool
    jitter_max_seconds: int
    schedule_version: str
    simulation_only: bool = True
    executes: bool = False

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["slots"] = list(self.slots)
        return d


class SchedulePlanner:
    """Build recommended send windows. Never dispatches Celery or enqueues."""

    version = SCHEDULE_VERSION

    def preview(
        self,
        *,
        now: datetime | None = None,
        policy: dict[str, Any] | None = None,
        account_id: str = "sim",
        batch_count: int = 3,
        messages_per_batch: int = 5,
        spacing_minutes: int = 30,
    ) -> SchedulePreview:
        settings = (policy or {}).get("settings_json") or (policy or {}).get("settings") or (policy or {})
        tz_name = str(settings.get("timezone") or "Asia/Tehran")
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("UTC")
            tz_name = "UTC"
        now = now or datetime.now(tz)
        if now.tzinfo is None:
            now = now.replace(tzinfo=tz)
        else:
            now = now.astimezone(tz)

        start_h = int(settings.get("working_hour_start") or 9)
        end_h = int(settings.get("working_hour_end") or 19)
        jitter_cfg = settings.get("scheduling_jitter_placeholder")
        if isinstance(jitter_cfg, dict) and jitter_cfg.get("max_seconds") is not None:
            jitter_max = int(jitter_cfg["max_seconds"])
        elif settings.get("jitter_max_seconds") is not None:
            jitter_max = int(settings["jitter_max_seconds"])
        else:
            jitter_max = 120
        holiday = bool(settings.get("holiday_placeholder") or False)

        day = now.date()
        window_start = datetime.combine(day, time(start_h, 0), tzinfo=tz)
        window_end = datetime.combine(day, time(end_h, 0), tzinfo=tz)
        cursor = max(now, window_start)
        slots: list[dict[str, Any]] = []
        for i in range(max(0, int(batch_count))):
            if holiday:
                break
            seed = f"{account_id}:{day.isoformat()}:{i}:{SCHEDULE_VERSION}"
            jitter = _deterministic_jitter_seconds(seed, jitter_max)
            slot_at = cursor + timedelta(seconds=jitter)
            if slot_at > window_end:
                # next day same window
                day = day + timedelta(days=1)
                window_start = datetime.combine(day, time(start_h, 0), tzinfo=tz)
                window_end = datetime.combine(day, time(end_h, 0), tzinfo=tz)
                cursor = window_start
                slot_at = cursor + timedelta(seconds=jitter)
            slots.append({
                "index": i,
                "scheduled_at": slot_at.isoformat(),
                "messages": int(messages_per_batch),
                "jitter_seconds": jitter,
                "status": "SIMULATED_ONLY",
            })
            cursor = slot_at + timedelta(minutes=max(1, int(spacing_minutes)))

        return SchedulePreview(
            timezone=tz_name,
            working_hours_start=f"{start_h:02d}:00",
            working_hours_end=f"{end_h:02d}:00",
            slots=tuple(slots),
            holiday_placeholder=holiday,
            jitter_max_seconds=jitter_max,
            schedule_version=self.version,
        )
