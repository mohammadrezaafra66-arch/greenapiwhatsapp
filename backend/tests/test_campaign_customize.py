"""V-campaign-customize: product selection (variation/weights) + opening/opt-out helpers."""
import random
import pytest

from app.services.product_selection import weighted_sample, select_group_products
from app.services.gpt_service import _apply_opening, _apply_opt_out, _is_optout_line, DEFAULT_OPT_OUT


def _prods(*names):
    return [{"name": n} for n in names]


# ── weighted_sample ────────────────────────────────────────────
def test_weighted_sample_returns_k_distinct():
    random.seed(1)
    out = weighted_sample(_prods("a", "b", "c", "d"), {}, 2)
    assert len(out) == 2
    assert len({p["name"] for p in out}) == 2  # distinct


def test_weighted_sample_k_larger_than_pool():
    out = weighted_sample(_prods("a", "b"), {}, 5)
    assert len(out) == 2  # capped at pool size


def test_weighted_sample_high_weight_appears_more_often():
    random.seed(7)
    pool = _prods("heavy", "light")
    weights = {"heavy": 100, "light": 1}
    firsts = [weighted_sample(pool, weights, 1)[0]["name"] for _ in range(200)]
    assert firsts.count("heavy") > firsts.count("light") * 3  # dominates


def test_weighted_sample_bad_weight_defaults_to_one():
    random.seed(3)
    out = weighted_sample(_prods("a", "b"), {"a": "not-a-number"}, 2)
    assert len(out) == 2  # doesn't crash, treats bad weight as 1


# ── select_group_products ──────────────────────────────────────
def test_select_same_is_identical_across_groups():
    pool = _prods("a", "b", "c", "d", "e")
    g0 = select_group_products(pool, "same", 3, {}, 0)
    g1 = select_group_products(pool, "same", 3, {}, 1)
    assert [p["name"] for p in g0] == [p["name"] for p in g1] == ["a", "b", "c"]


def test_select_rotate_differs_across_consecutive_groups():
    pool = _prods("a", "b", "c", "d", "e", "f")
    g0 = [p["name"] for p in select_group_products(pool, "rotate", 2, {}, 0)]
    g1 = [p["name"] for p in select_group_products(pool, "rotate", 2, {}, 1)]
    g2 = [p["name"] for p in select_group_products(pool, "rotate", 2, {}, 2)]
    assert g0 == ["a", "b"] and g1 == ["c", "d"] and g2 == ["e", "f"]
    assert g0 != g1 != g2


def test_select_per_group_random_varies():
    random.seed(11)
    pool = _prods(*[f"p{i}" for i in range(15)])
    sets = {tuple(sorted(p["name"] for p in select_group_products(pool, "per_group_random", 3, {}, i))) for i in range(8)}
    assert len(sets) >= 2  # not all groups get the same subset


def test_select_empty_pool():
    assert select_group_products([], "rotate", 3, {}, 0) == []


# ── opening line ───────────────────────────────────────────────
def test_apply_opening_fixed_prepends():
    out = _apply_opening("متن اصلی پیام", "fixed", "سلام دوستان")
    assert out.startswith("سلام دوستان")
    assert "متن اصلی پیام" in out


def test_apply_opening_no_dup_when_already_present():
    out = _apply_opening("سلام دوستان\nبقیه پیام", "fixed", "سلام دوستان")
    assert out.count("سلام دوستان") == 1


def test_apply_opening_ai_and_none_leave_text():
    assert _apply_opening("hello", "ai", None) == "hello"
    assert _apply_opening("hello", "none", None) == "hello"


# ── opt-out ────────────────────────────────────────────────────
def test_optout_appended_when_enabled():
    out = _apply_opt_out("سلام\nپیشنهاد ویژه", True, None)
    assert out.rstrip().endswith(DEFAULT_OPT_OUT)


def test_optout_removed_when_disabled():
    text = "سلام\nپیشنهاد ویژه\nبرای لغو عدد ۱۱ ارسال کنید"
    out = _apply_opt_out(text, False, None)
    assert "لغو" not in out
    assert "پیشنهاد ویژه" in out


def test_optout_custom_replaces_default_no_dup():
    text = "سلام\nبرای لغو عدد ۱۱ ارسال کنید"
    out = _apply_opt_out(text, True, "برای قطع تبلیغات عدد ۰ بفرستید")
    assert "برای قطع تبلیغات عدد ۰ بفرستید" in out
    assert "عدد ۱۱" not in out  # old default stripped
    assert out.count("لغو") <= 1


def test_optout_custom_already_present_not_duplicated():
    # GPT already wrote the custom opt-out (no word 'لغو'); applying same must not dup.
    text = "سلام\nپیشنهاد ویژه\nبرای قطع تبلیغات عدد ۰ بفرستید"
    out = _apply_opt_out(text, True, "برای قطع تبلیغات عدد ۰ بفرستید")
    assert out.count("برای قطع تبلیغات عدد ۰ بفرستید") == 1
    assert out.rstrip().endswith("برای قطع تبلیغات عدد ۰ بفرستید")


def test_is_optout_line_detection():
    assert _is_optout_line("برای لغو عدد ۱۱ ارسال کنید")
    assert _is_optout_line("لغو اشتراک: عدد ۲")
    assert not _is_optout_line("ساید ال جی X24 دودی")
    assert not _is_optout_line("")
