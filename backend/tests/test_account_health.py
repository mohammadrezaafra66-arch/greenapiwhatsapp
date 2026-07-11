"""V13.2 — health score + weighted account selection."""
import random
import uuid
from types import SimpleNamespace

from app.services.account_health import compute_score, pick_account_weighted


def test_score_bounds_and_weighting():
    # perfect: full capacity, no yellowCards
    assert compute_score(1.0, 0.0) == 1.0
    # worst: no capacity, all yellowCards
    assert compute_score(0.0, 1.0) == 0.0
    # mid
    s = compute_score(0.5, 0.5)
    assert 0.0 < s < 1.0


def test_capacity_weighted_60_yellow_40():
    # only capacity (no yellow) -> 0.6 weight
    assert compute_score(1.0, 0.0) == 1.0
    assert round(compute_score(0.0, 0.0), 3) == 0.4   # full clean history, zero capacity
    assert round(compute_score(1.0, 1.0), 3) == 0.6   # full capacity, all yellow


def _acct():
    return SimpleNamespace(id=uuid.uuid4())


def test_pick_weighted_prefers_high_score():
    healthy, sick = _acct(), _acct()
    scores = {str(healthy.id): 0.95, str(sick.id): 0.05}
    random.seed(5)
    picks = [pick_account_weighted([healthy, sick], scores).id for _ in range(300)]
    assert picks.count(healthy.id) > picks.count(sick.id) * 3


def test_pick_weighted_missing_score_defaults_neutral():
    a, b = _acct(), _acct()
    random.seed(1)
    # no scores at all -> both default 0.5 -> both get picked over many draws
    got = {pick_account_weighted([a, b], {}).id for _ in range(50)}
    assert a.id in got and b.id in got


def test_pick_weighted_empty_returns_none():
    assert pick_account_weighted([], {}) is None
