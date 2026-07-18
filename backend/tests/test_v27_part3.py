"""V27 PART 3 — minimum real age + clean history for warm-peer eligibility.

Proves:
  • a <14-day instance is rejected (too_young) with the Persian error;
  • an instance with a yellowCard in the last 14 days is rejected (recent_incident);
  • a genuinely 14+ day, clean-history instance is accepted;
  • the retroactive audit reports failing existing peers WITHOUT changing them.
"""
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest

from app.services import warmup_peer_eligibility as elig
from app.services.warmup_peer_eligibility import (
    evaluate_peer_eligibility, connected_since, peer_age_days,
    MIN_PEER_AGE_DAYS, TOO_YOUNG_FA, RECENT_INCIDENT_FA,
)

NOW = datetime(2026, 7, 18, 12, 0, 0)


def _acc(created_days_ago=30, instance_id="P", name="peer", is_warm_peer=True):
    return SimpleNamespace(
        id=uuid.uuid4(), instance_id=instance_id, name=name, phone="98912",
        created_at=NOW - timedelta(days=created_days_ago),
        partner_created_at=None, is_warm_peer=is_warm_peer,
    )


# ── pure evaluator ───────────────────────────────────────────────────────────
def test_connected_since_prefers_earliest():
    acc = _acc(created_days_ago=10)
    enr = SimpleNamespace(authorized_at=NOW - timedelta(days=20))
    assert connected_since(acc, enr) == NOW - timedelta(days=20)   # enrollment older → wins
    assert round(peer_age_days(acc, enr, NOW)) == 20


def test_fresh_number_rejected_too_young():
    ok, reason, msg = evaluate_peer_eligibility(_acc(created_days_ago=3), None, 0, NOW)
    assert ok is False and reason == "too_young" and msg == TOO_YOUNG_FA


def test_just_under_14_days_rejected():
    ok, reason, _ = evaluate_peer_eligibility(_acc(created_days_ago=13), None, 0, NOW)
    assert ok is False and reason == "too_young"


def test_recent_incident_rejected():
    ok, reason, msg = evaluate_peer_eligibility(_acc(created_days_ago=40), None, 1, NOW)
    assert ok is False and reason == "recent_incident" and msg == RECENT_INCIDENT_FA


def test_established_clean_number_accepted():
    ok, reason, msg = evaluate_peer_eligibility(_acc(created_days_ago=40), None, 0, NOW)
    assert ok is True and reason == "ok" and msg is None


def test_no_timestamp_is_rejected():
    acc = SimpleNamespace(id=uuid.uuid4(), instance_id="X", name="x", phone=None,
                          created_at=None, partner_created_at=None)
    ok, reason, _ = evaluate_peer_eligibility(acc, None, 0, NOW)
    assert ok is False and reason == "too_young"


# ── async wrappers with a fake DB ────────────────────────────────────────────
class _FakeResult:
    def __init__(self, scalars=None, scalar=None):
        self._scalars = scalars if scalars is not None else []
        self._scalar = scalar
    def scalars(self):
        items = self._scalars
        class _S:
            def all(self_): return list(items)
        return _S()
    def scalar_one_or_none(self): return self._scalars[0] if self._scalars else None
    def scalar(self): return self._scalar


class _FakeDB:
    def __init__(self, results): self._results = list(results)
    async def execute(self, *a, **k): return self._results.pop(0)


@pytest.mark.asyncio
async def test_check_peer_eligibility_counts_incidents():
    acc = _acc(created_days_ago=40)
    # 1) enrollment lookup (none) → 2) incident count = 2
    db = _FakeDB([_FakeResult(scalars=[]), _FakeResult(scalar=2)])
    ok, reason, _ = await elig.check_peer_eligibility(db, acc, NOW)
    assert ok is False and reason == "recent_incident"


@pytest.mark.asyncio
async def test_check_peer_eligibility_clean_established():
    acc = _acc(created_days_ago=40)
    db = _FakeDB([_FakeResult(scalars=[]), _FakeResult(scalar=0)])
    ok, reason, _ = await elig.check_peer_eligibility(db, acc, NOW)
    assert ok is True and reason == "ok"


@pytest.mark.asyncio
async def test_audit_reports_failing_peers_without_changing_them():
    fresh = _acc(created_days_ago=4, instance_id="FRESH", name="صالحی")
    good = _acc(created_days_ago=40, instance_id="GOOD", name="محمدرضا")
    # audit: 1) select flagged peers → [fresh, good]
    #   per peer: enrollment lookup (none) + incident count (0)
    db = _FakeDB([
        _FakeResult(scalars=[fresh, good]),
        _FakeResult(scalars=[]), _FakeResult(scalar=0),   # fresh
        _FakeResult(scalars=[]), _FakeResult(scalar=0),   # good
    ])
    failing = await elig.audit_existing_peers(db, NOW)
    assert len(failing) == 1
    assert failing[0]["instance_id"] == "FRESH"
    assert failing[0]["reason"] == "too_young"
    # NOT auto-unflagged — still a warm peer
    assert fresh.is_warm_peer is True
