"""V15 PART 1 — price enforcement (Item 12) + no duplicate products across groups (Item 22)."""
import asyncio
import pytest
from app.services import gpt_service
from app.services.product_selection import select_group_products, _weight_key


# ── Item 12 — price enforcement ─────────────────────────────────────────────
def test_price_helpers():
    assert gpt_service._products_have_prices([{"name": "a", "price": 100}]) is True
    assert gpt_service._products_have_prices([{"name": "a"}]) is False
    assert gpt_service._has_call_phrase("برای اطلاع تماس بگیرید") is True
    assert gpt_service._has_call_phrase("قیمت ۷۶,۹۰۰,۰۰۰ تومان") is False


def test_price_list_fallback_text():
    txt = gpt_service._price_list_text([{"name": "کولر", "price": 76900000}])
    assert "76,900,000" in txt and "کولر" in txt


def test_show_prices_true_output_has_price_no_call(monkeypatch):
    """With show_prices=True + priced products, the model keeps writing «تماس بگیرید»;
    the enforcement must retry and, if still bad, append a real price so the output
    contains a number and NOT a call-us phrase."""
    async def fake_chat(system, user, max_tokens, temperature):
        return "سلام، برای قیمت تماس بگیرید"   # stubborn model — never writes a price

    monkeypatch.setattr(gpt_service, "_chat", fake_chat)
    out = asyncio.run(gpt_service.generate_message(
        first_name="علی", last_name="", gpt_prompt="یک پیام بنویس",
        products=[{"name": "کولر گازی", "price": 76900000}],
        show_prices=True, include_opt_out=False,
    ))
    assert "76,900,000" in out            # a numeric price is present
    assert "تماس بگیرید" not in out       # the call-us phrase was removed/superseded


def test_show_prices_false_allows_call(monkeypatch):
    """show_prices=False → «تماس بگیرید» is acceptable; no enforcement kicks in."""
    async def fake_chat(system, user, max_tokens, temperature):
        return "سلام، برای قیمت تماس بگیرید"
    monkeypatch.setattr(gpt_service, "_chat", fake_chat)
    out = asyncio.run(gpt_service.generate_message(
        first_name="علی", last_name="", gpt_prompt="یک پیام",
        products=[{"name": "کولر"}], show_prices=False, include_opt_out=False,
    ))
    assert "تماس بگیرید" in out


# ── Item 22 — no duplicate products across groups ───────────────────────────
def _prods(n):
    return [{"name": f"p{i}", "price": (i + 1) * 1000} for i in range(n)]


def test_no_duplicates_when_pool_sufficient():
    """5 groups × 2 from a pool of 10 → all 10 picks distinct (per_group_random)."""
    pool = _prods(10)
    used, last, all_keys = set(), [], []
    for gi in range(5):
        picks = select_group_products(pool, "per_group_random", 2, {}, gi, used=used, last_picks=last)
        last = picks
        all_keys += [_weight_key(p) for p in picks]
    assert len(all_keys) == 10
    assert len(set(all_keys)) == 10          # zero duplicates


def test_consecutive_groups_differ_when_pool_small():
    """5 groups × 2 from only 3 products → consecutive groups never get the identical pair."""
    pool = _prods(3)
    used, last, per_group_sets = set(), [], []
    for gi in range(5):
        picks = select_group_products(pool, "per_group_random", 2, {}, gi, used=used, last_picks=last)
        last = picks
        per_group_sets.append(frozenset(_weight_key(p) for p in picks))
    for a, b in zip(per_group_sets, per_group_sets[1:]):
        assert a != b                         # no two consecutive groups get the same pair


def test_rotate_no_repeat_until_cycled():
    """rotate: 4 products, 2 each → first two groups cover all 4 distinct products."""
    pool = _prods(4)
    used, last = set(), []
    g0 = select_group_products(pool, "rotate", 2, {}, 0, used=used, last_picks=last)
    g1 = select_group_products(pool, "rotate", 2, {}, 1, used=used, last_picks=g0)
    keys = {_weight_key(p) for p in g0 + g1}
    assert len(keys) == 4                      # full list cycled with no repeat


def test_same_mode_unchanged():
    """'same' mode still returns the identical first-N for every group (backward compat)."""
    pool = _prods(5)
    a = select_group_products(pool, "same", 3, {}, 0, used=set(), last_picks=[])
    b = select_group_products(pool, "same", 3, {}, 1, used=set(), last_picks=[])
    assert [p["name"] for p in a] == [p["name"] for p in b] == ["p0", "p1", "p2"]
