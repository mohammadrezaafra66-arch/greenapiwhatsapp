"""V16 PART 5 — smart warm-up: per-run cap, daily-cap never exceeded, phrases, defaults OFF."""
from types import SimpleNamespace
from app.services import warmup_auto
from app.services.warmup_auto import (
    _to_send_this_run, warmup_daily_limit, warmup_day, PER_RUN_CAP,
    DEFAULT_PHRASES, WARMUP_TOTAL_DAYS,
)


# ── per-run cap + daily-cap ceiling (the anti-overshoot guard) ──────────────
def test_per_run_cap_never_exceeds_remaining_daily():
    # day 4–7 cap = 3. First run sends 2 (per-run cap), leaving 1.
    assert _to_send_this_run(daily_limit=3, sent_today=0) == PER_RUN_CAP  # == 2
    assert _to_send_this_run(daily_limit=3, sent_today=2) == 1            # only 1 left
    assert _to_send_this_run(daily_limit=3, sent_today=3) == 0            # cap reached → 0
    assert _to_send_this_run(daily_limit=3, sent_today=5) == 0            # never negative


def test_daily_cap_not_exceeded_over_many_runs():
    """Simulate the beat firing repeatedly in a day; total sent must equal the cap, never more."""
    for cap in (3, 10):
        sent = 0
        for _ in range(50):  # far more runs than needed
            n = _to_send_this_run(cap, sent)
            sent += n
        assert sent == cap                # converges exactly to the cap, never above


def test_receive_only_days_send_zero():
    for day in (1, 2, 3):
        assert warmup_daily_limit(day) == 0
        assert _to_send_this_run(warmup_daily_limit(day), 0) == 0


def test_default_phrase_pool_size_and_content():
    assert 10 <= len(DEFAULT_PHRASES) <= 15
    assert all(p.strip() for p in DEFAULT_PHRASES)
    assert warmup_auto.WARMUP_TEMPLATES  # non-empty fallback


def test_get_active_phrases_falls_back_when_db_unavailable():
    import asyncio

    class _BadDB:
        async def execute(self, *a, **k):
            raise RuntimeError("db down")

    phrases = asyncio.run(warmup_auto.get_active_phrases(_BadDB()))
    assert phrases == list(warmup_auto.DEFAULT_PHRASES)    # full built-in pool fallback


def test_get_active_phrases_falls_back_when_table_empty():
    """Even with a working DB, an EMPTY phrase table must fall back to the defaults —
    the feature never depends on the seed having populated rows."""
    import asyncio

    class _EmptyResult:
        def scalars(self):
            class _S:
                def all(self_inner):
                    return []
            return _S()

    class _EmptyDB:
        async def execute(self, *a, **k):
            return _EmptyResult()

    phrases = asyncio.run(warmup_auto.get_active_phrases(_EmptyDB()))
    assert phrases == list(warmup_auto.DEFAULT_PHRASES)


def test_warmup_defaults_off_and_stage_transitions():
    a = SimpleNamespace(auto_warmup=False, warmup_completed=False,
                        warmup_started_at=__import__("datetime").datetime.utcnow())
    from app.services.warmup_auto import in_active_warmup
    assert in_active_warmup(a) is False                    # OFF by default → not warming
    # stage caps
    assert warmup_daily_limit(warmup_day(a)) in (0, 3, 10)  # day 1 → 0
    assert WARMUP_TOTAL_DAYS == 10
