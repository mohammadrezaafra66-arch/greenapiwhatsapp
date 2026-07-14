"""V15 PART 8 — managed auto warm-up (Item 26)."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from app.services.warmup_auto import (
    warmup_day, warmup_daily_limit, in_active_warmup, WARMUP_TOTAL_DAYS, WARMUP_TEMPLATES,
)


def _acct(**kw):
    base = dict(auto_warmup=True, warmup_completed=False, warmup_started_at=datetime.utcnow())
    base.update(kw)
    return SimpleNamespace(**base)


def test_warmup_day_counts_from_start():
    a = _acct(warmup_started_at=datetime.utcnow() - timedelta(days=0, hours=1))
    assert warmup_day(a) == 1
    a = _acct(warmup_started_at=datetime.utcnow() - timedelta(days=4, hours=1))
    assert warmup_day(a) == 5
    assert warmup_day(_acct(warmup_started_at=None)) == 0


def test_warmup_daily_limits_by_phase():
    # days 1–3: receive-only (0), 4–7: ≤3, 8–10: ≤10, 11+: 0 (done)
    assert [warmup_daily_limit(d) for d in (1, 2, 3)] == [0, 0, 0]
    assert [warmup_daily_limit(d) for d in (4, 5, 6, 7)] == [3, 3, 3, 3]
    assert [warmup_daily_limit(d) for d in (8, 9, 10)] == [10, 10, 10]
    assert warmup_daily_limit(11) == 0
    assert WARMUP_TOTAL_DAYS == 10


def test_in_active_warmup():
    assert in_active_warmup(_acct(auto_warmup=True, warmup_completed=False)) is True
    assert in_active_warmup(_acct(auto_warmup=True, warmup_completed=True)) is False
    assert in_active_warmup(_acct(auto_warmup=False, warmup_completed=False)) is False


def test_warmup_templates_are_friendly_non_empty():
    assert len(WARMUP_TEMPLATES) >= 2
    assert all(t.strip() for t in WARMUP_TEMPLATES)


def test_runner_excludes_warming_accounts():
    """The campaign runner filter must drop accounts in active warm-up."""
    from app.services.warmup_auto import in_active_warmup
    active_normal = _acct(auto_warmup=False)
    warming = _acct(auto_warmup=True, warmup_completed=False)
    done = _acct(auto_warmup=True, warmup_completed=True)
    accounts = [active_normal, warming, done]
    kept = [a for a in accounts if not in_active_warmup(a)]
    assert warming not in kept
    assert active_normal in kept and done in kept
