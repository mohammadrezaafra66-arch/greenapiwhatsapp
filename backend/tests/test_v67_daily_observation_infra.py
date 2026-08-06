"""Infrastructure adapter and honesty tests."""
from __future__ import annotations
from datetime import datetime, timedelta

from app.services.daily_observation.infra_health import (
    derive_beat_status,
    derive_scheduler_status,
    derive_scheduler_status_historical,
)
from app.services.daily_observation.contract import InfraStatus


def test_scheduler_flag_false_unhealthy():
    assert (
        derive_scheduler_status(
            scheduler_flag=False,
            last_periodic_at=datetime.utcnow(),
            now=datetime.utcnow(),
            max_age_seconds=900,
        )
        == InfraStatus.UNHEALTHY.value
    )


def test_scheduler_flag_true_no_snapshot_degraded():
    assert (
        derive_scheduler_status(
            scheduler_flag=True,
            last_periodic_at=None,
            now=datetime.utcnow(),
            max_age_seconds=900,
        )
        == InfraStatus.DEGRADED.value
    )


def test_scheduler_stale_snapshot_degraded():
    now = datetime.utcnow()
    assert (
        derive_scheduler_status(
            scheduler_flag=True,
            last_periodic_at=now - timedelta(hours=2),
            now=now,
            max_age_seconds=900,
        )
        == InfraStatus.DEGRADED.value
    )


def test_scheduler_recent_healthy():
    now = datetime.utcnow()
    assert (
        derive_scheduler_status(
            scheduler_flag=True,
            last_periodic_at=now - timedelta(seconds=100),
            now=now,
            max_age_seconds=900,
        )
        == InfraStatus.HEALTHY.value
    )


def test_scheduler_historical_with_periodic_healthy():
    assert (
        derive_scheduler_status_historical(scheduler_flag=True, had_periodic=True)
        == InfraStatus.HEALTHY.value
    )


def test_scheduler_historical_without_periodic_degraded():
    assert (
        derive_scheduler_status_historical(scheduler_flag=True, had_periodic=False)
        == InfraStatus.DEGRADED.value
    )


def test_beat_unknown_when_no_evidence():
    assert (
        derive_beat_status(last_periodic_at=None, scheduler_flag=False)
        == InfraStatus.UNKNOWN.value
    )


def test_beat_healthy_when_periodic_seen():
    assert (
        derive_beat_status(last_periodic_at=datetime.utcnow(), scheduler_flag=True)
        == InfraStatus.HEALTHY.value
    )
