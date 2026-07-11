"""V13.3 — best-hours ranking logic (pure)."""


def _pct(part, total):
    return round(100 * part / total, 1) if total else 0.0


def _best_hours(by_hour, min_sample=5, top=3):
    """Mirror the endpoint's ranking: top hours by read% then delivered%, min sample."""
    ranked = sorted(
        [b for b in by_hour if b["sent"] >= min_sample],
        key=lambda b: (b["read_pct"], b["delivered_pct"]),
        reverse=True,
    )
    return [b["hour"] for b in ranked[:top]]


def test_pct_math():
    assert _pct(7, 10) == 70.0
    assert _pct(0, 0) == 0.0


def test_best_hours_excludes_low_sample():
    by_hour = [
        {"hour": 9, "sent": 3, "read_pct": 100.0, "delivered_pct": 100.0},   # too few
        {"hour": 10, "sent": 20, "read_pct": 60.0, "delivered_pct": 90.0},
        {"hour": 11, "sent": 50, "read_pct": 55.0, "delivered_pct": 95.0},
    ]
    best = _best_hours(by_hour)
    assert 9 not in best             # excluded by min sample
    assert best[0] == 10             # highest read% among eligible
    assert best[1] == 11


def test_best_hours_tiebreak_on_delivered():
    by_hour = [
        {"hour": 8, "sent": 10, "read_pct": 50.0, "delivered_pct": 80.0},
        {"hour": 9, "sent": 10, "read_pct": 50.0, "delivered_pct": 95.0},
    ]
    assert _best_hours(by_hour)[0] == 9   # same read%, higher delivered% wins


def test_best_hours_empty_when_no_volume():
    by_hour = [{"hour": h, "sent": 0, "read_pct": 0.0, "delivered_pct": 0.0} for h in range(24)]
    assert _best_hours(by_hour) == []
