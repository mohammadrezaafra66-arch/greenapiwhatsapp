"""V12 — unit tests for the AI key-pool selection logic (pure, no DB/network)."""
import uuid
import random
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.services.ai_key_pool import select_key


def _key(status="unknown", rate_limited_until=None, provider="openai"):
    return SimpleNamespace(
        id=uuid.uuid4(), provider=provider, status=status,
        rate_limited_until=rate_limited_until,
    )


NOW = datetime(2026, 7, 11, 12, 0, 0)


def test_empty_pool_returns_none():
    assert select_key([], NOW) is None


def test_invalid_keys_are_skipped():
    keys = [_key(status="invalid"), _key(status="invalid")]
    assert select_key(keys, NOW) is None


def test_currently_rate_limited_key_is_skipped():
    future = NOW + timedelta(minutes=10)
    keys = [_key(status="rate_limited", rate_limited_until=future)]
    assert select_key(keys, NOW) is None


def test_expired_rate_limit_is_usable_again():
    past = NOW - timedelta(minutes=1)
    k = _key(status="rate_limited", rate_limited_until=past)
    assert select_key([k], NOW) is k


def test_working_key_is_preferred_over_unknown():
    unknown = _key(status="unknown")
    working = _key(status="working")
    # Even across many draws, a 'working' key must always win over 'unknown'.
    random.seed(1)
    for _ in range(50):
        assert select_key([unknown, working], NOW) is working


def test_falls_back_to_unknown_when_no_working():
    unknown = _key(status="unknown")
    failed = _key(status="failed")
    random.seed(2)
    picks = {id(select_key([unknown, failed], NOW)) for _ in range(50)}
    # Both unknown and failed are "usable" (only invalid/rate-limited are excluded),
    # so selection is random among them and never returns None.
    assert None not in [select_key([unknown, failed], NOW) for _ in range(10)]
    assert id(unknown) in picks or id(failed) in picks


def test_random_selection_distributes_across_working_keys():
    a = _key(status="working")
    b = _key(status="working")
    c = _key(status="working")
    random.seed(42)
    chosen = [select_key([a, b, c], NOW) for _ in range(300)]
    distinct = {k.id for k in chosen}
    # Over 300 draws we should hit more than one key (not always the same one).
    assert len(distinct) >= 2


def test_only_rate_limited_and_invalid_returns_none():
    future = NOW + timedelta(minutes=5)
    keys = [_key(status="invalid"), _key(status="rate_limited", rate_limited_until=future)]
    assert select_key(keys, NOW) is None
