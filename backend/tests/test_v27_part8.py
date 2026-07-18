"""V27 PART 8 — live quality-score auto-throttle.

Proves:
  • healthy engagement (decent replies, low failures) yields a high score → NOT throttled;
  • a reply-rate drop / failure-rate rise yields a low score → outbound throttled + Persian notice;
  • too few recent sends → score None → never throttled on noise;
  • the throttle is not re-applied if the instance is already throttled;
  • the monitor task is scheduled.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest

from app.services import quality_score as qs
from app.services.quality_score import (
    compute_quality_score, is_low_quality, evaluate_and_act,
    QUALITY_THRESHOLD, MIN_SAMPLE, LOW_QUALITY_FA, THROTTLE_FACTOR,
)

NOW = datetime(2026, 7, 18, 12, 0, 0)


# ── pure score ───────────────────────────────────────────────────────────────
def test_healthy_scores_high():
    s = compute_quality_score(reply_rate=0.25, failure_rate=0.02)
    assert s > QUALITY_THRESHOLD and is_low_quality(s) is False


def test_low_reply_and_high_failure_scores_low():
    s = compute_quality_score(reply_rate=0.01, failure_rate=0.45)
    assert s < QUALITY_THRESHOLD and is_low_quality(s) is True


def test_high_failure_alone_scores_low():
    s = compute_quality_score(reply_rate=0.1, failure_rate=0.6)
    assert is_low_quality(s) is True


def test_score_bounded():
    assert compute_quality_score(5.0, -1.0) <= 1.0
    assert compute_quality_score(0.0, 5.0) >= 0.0


# ── evaluate_and_act with a fake DB ──────────────────────────────────────────
class _Result:
    def __init__(self, scalar): self._scalar = scalar
    def scalar(self): return self._scalar


class _DB:
    """Returns queued scalar counts in order: total, replied, failed."""
    def __init__(self, counts):
        self._counts = list(counts)
        self.added = []
    async def execute(self, *a, **k): return _Result(self._counts.pop(0))
    def add(self, x): self.added.append(x)
    async def commit(self): pass


def _acct(instance_id="Q"):
    return SimpleNamespace(id="acc-id", instance_id=instance_id, throttle_factor=1.0,
                           throttle_until=None, cooldown_until=None, last_incident_at=None)


@pytest.mark.asyncio
async def test_low_quality_triggers_throttle_and_notice():
    # total=100, replied=1 (1%), failed=40 (40%) → low
    db = _DB([100, 1, 40])
    acc = _acct()
    res = await evaluate_and_act(db, acc, NOW)
    assert res["acted"] == "throttled" and res["notice"] == LOW_QUALITY_FA
    assert acc.throttle_factor == THROTTLE_FACTOR
    assert acc.throttle_until == NOW + timedelta(days=qs.THROTTLE_DAYS)
    from app.models.incident import AccountIncident
    assert any(isinstance(x, AccountIncident) for x in db.added)


@pytest.mark.asyncio
async def test_healthy_engagement_not_throttled():
    # total=100, replied=25 (25%), failed=1 (1%) → healthy
    db = _DB([100, 25, 1])
    acc = _acct()
    res = await evaluate_and_act(db, acc, NOW)
    assert res["acted"] is None and acc.throttle_factor == 1.0
    assert db.added == []


@pytest.mark.asyncio
async def test_insufficient_sample_never_throttles():
    db = _DB([MIN_SAMPLE - 1])   # only the total query runs
    acc = _acct()
    res = await evaluate_and_act(db, acc, NOW)
    assert res["score"] is None and res["acted"] is None


@pytest.mark.asyncio
async def test_already_throttled_not_reapplied():
    db = _DB([100, 1, 40])
    acc = _acct()
    acc.throttle_factor = 0.5
    acc.throttle_until = NOW + timedelta(days=1)
    res = await evaluate_and_act(db, acc, NOW)
    assert res["acted"] == "already_throttled" and db.added == []


def test_monitor_task_scheduled():
    from app.workers.celery_app import celery_app
    sched = celery_app.conf.beat_schedule
    assert "quality-score-monitor" in sched
    assert sched["quality-score-monitor"]["task"] == "tasks.quality_score_monitor"
