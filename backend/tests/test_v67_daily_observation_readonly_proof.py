"""Behavioral read-only proof: service session must not commit/write."""
from __future__ import annotations
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.daily_observation.service import DailyObservationReportService


class _TrackingSession:
    def __init__(self):
        self.committed = False
        self.added = []
        self.flushed = False
        self._result = MagicMock()

    async def execute(self, *a, **k):
        # Minimal result shapes for successive queries — return zeros/empty
        m = MagicMock()
        m.mappings.return_value.one.return_value = {
            "n": 0,
            "accounts": 0,
            "first_at": None,
            "last_at": None,
            "policy_version": None,
        }
        m.mappings.return_value.all.return_value = []
        m.scalar.return_value = 0
        m.fetchall.return_value = []
        return m

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed = True

    async def commit(self):
        self.committed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


@pytest.mark.asyncio
async def test_service_build_does_not_commit_or_add(monkeypatch):
    sess = _TrackingSession()

    def factory():
        return sess

    # Avoid real infra probes
    async def _fill(self, report, *, last_periodic_at, now):
        report.database_status = "HEALTHY"
        report.redis_status = "HEALTHY"
        report.celery_worker_status = "HEALTHY"
        report.celery_beat_status = "UNKNOWN"
        report.scheduler_status = "UNKNOWN"
        report.shadow_runtime_flag_status = "HEALTHY"
        report.shadow_scheduler_flag_status = "HEALTHY"

    monkeypatch.setattr(DailyObservationReportService, "_fill_infra", _fill)
    svc = DailyObservationReportService(session_factory=factory)
    report = await svc.build("2026-08-06", probe_infra=True, now_utc=__import__("datetime").datetime(2026, 8, 6, 12, 0, 0))
    assert sess.committed is False
    assert sess.added == []
    assert sess.flushed is False
    assert report.phase7_fully_accepted is False
    assert report.phase8_allowed is False
    assert report.read_only is True


def test_service_source_bounded_queries():
    src = inspect.getsource(DailyObservationReportService._load_day_snapshot_stats)
    assert "observed_at >=" in src
    assert "observed_at <" in src
    assert "LIMIT 20" in src
