"""V13.1 — A/B testing: variant assignment split + winner computation."""


def _assign_variants(n):
    """Mirror the start-endpoint assignment: alternate A/B over ordered contacts."""
    return ["A" if i % 2 == 0 else "B" for i in range(n)]


def _winner(variants):
    """Mirror ab_results winner logic: higher read%, tiebreak delivered%."""
    if "A" in variants and "B" in variants:
        a, b = variants["A"], variants["B"]
        return "A" if (a["read_pct"], a["delivered_pct"]) >= (b["read_pct"], b["delivered_pct"]) else "B"
    return None


def test_split_is_roughly_5050_even():
    v = _assign_variants(10)
    assert v.count("A") == 5 and v.count("B") == 5


def test_split_odd_gives_extra_to_A():
    v = _assign_variants(7)
    assert v.count("A") == 4 and v.count("B") == 3  # A gets the odd one


def test_split_alternates():
    assert _assign_variants(4) == ["A", "B", "A", "B"]


def test_winner_higher_read_pct_wins():
    variants = {
        "A": {"read_pct": 40.0, "delivered_pct": 80.0},
        "B": {"read_pct": 55.0, "delivered_pct": 70.0},
    }
    assert _winner(variants) == "B"


def test_winner_tiebreak_on_delivered():
    variants = {
        "A": {"read_pct": 50.0, "delivered_pct": 90.0},
        "B": {"read_pct": 50.0, "delivered_pct": 85.0},
    }
    assert _winner(variants) == "A"


def test_winner_none_when_one_variant_missing():
    assert _winner({"A": {"read_pct": 10, "delivered_pct": 20}}) is None
    assert _winner({}) is None


def test_winner_ties_favor_A():
    variants = {
        "A": {"read_pct": 50.0, "delivered_pct": 50.0},
        "B": {"read_pct": 50.0, "delivered_pct": 50.0},
    }
    assert _winner(variants) == "A"  # >= favors A
