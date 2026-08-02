"""V63 — the hand-picked product pool with a stable per-contact draw.

Before this, every recipient of a campaign received a byte-identical product list: the first
`product_count` rows Supabase happened to return, with no ORDER BY (price_service.get_products).
The operator could not say "advertise THESE fifteen products", and 30 recipients got 30 identical
messages — which is exactly the shape bulk-spam detection looks for.

Two properties matter and are pinned here:

  1. STABILITY — one contact always sees the same products. If the draw moved between sends, a
     recipient who got a second message would see a different catalogue and think the first was
     wrong. The seed is therefore derived from (campaign_id, contact_id) via SHA-256, NOT from
     Python's `hash()`, which is salted per interpreter and would differ between the two send
     paths (they run in separate worker processes).

  2. CONTAINMENT — an empty pool must behave EXACTLY as before. Every campaign that exists today
     has product_pool_ids = NULL and must be unaffected.
"""
import inspect

import pytest

from app.api.v1.campaigns import _clean_product_pool
from app.services import campaign_runner as cr
from app.services.product_selection import stable_pool_pick, stable_seed

POOL = [{"id": f"p{i}", "name": f"محصول {i}", "price": 1000 * i} for i in range(1, 16)]


# ── the seed ────────────────────────────────────────────────────────────────
def _code_lines(fn) -> str:
    """Source with the docstring stripped — so an assertion about the CODE is not satisfied
    (or broken) by prose in the docstring that merely mentions the same words."""
    src = inspect.getsource(fn)
    body = src.split('"""')
    return body[0] + "".join(body[2:]) if len(body) >= 3 else src


def test_the_seed_is_not_python_hash():
    """`hash()` on a str is salted per process. Two workers would draw different products for
    the same contact, breaking the one guarantee this feature makes."""
    code = _code_lines(stable_seed)
    assert "sha256" in code
    assert "hash(" not in code, "the builtin hash() must never seed this draw"


def test_the_same_parts_always_give_the_same_seed():
    assert stable_seed("camp", "contact") == stable_seed("camp", "contact")


def test_different_parts_give_different_seeds():
    assert stable_seed("camp", "a") != stable_seed("camp", "b")
    assert stable_seed("camp1", "a") != stable_seed("camp2", "a")


def test_none_parts_do_not_crash_and_stay_distinct():
    assert stable_seed(None, "a") == stable_seed(None, "a")
    assert stable_seed(None, "a") != stable_seed("", "b")


# ── stability: one contact, always the same products ────────────────────────
def test_the_same_contact_always_draws_the_same_products():
    first = stable_pool_pick(POOL, 3, "camp-1", "contact-A")
    for _ in range(25):
        assert stable_pool_pick(POOL, 3, "camp-1", "contact-A") == first


def test_the_draw_survives_pool_object_identity():
    """A fresh list of equal dicts (a new Supabase fetch) must draw identically."""
    fresh = [dict(p) for p in POOL]
    assert (stable_pool_pick(POOL, 3, "c", "x") == stable_pool_pick(fresh, 3, "c", "x"))


# ── variety: different contacts see different products ──────────────────────
def test_different_contacts_get_different_draws():
    draws = {tuple(p["id"] for p in stable_pool_pick(POOL, 3, "camp-1", f"contact-{i}"))
             for i in range(30)}
    assert len(draws) > 10, "30 recipients should not collapse onto a handful of identical lists"


def test_the_same_contact_in_two_campaigns_can_differ():
    a = stable_pool_pick(POOL, 3, "camp-1", "contact-A")
    b = stable_pool_pick(POOL, 3, "camp-2", "contact-A")
    assert a != b or len(POOL) <= 3


# ── shape of the draw ───────────────────────────────────────────────────────
def test_it_draws_exactly_the_requested_count():
    assert len(stable_pool_pick(POOL, 3, "c", "x")) == 3
    assert len(stable_pool_pick(POOL, 1, "c", "x")) == 1


def test_it_never_repeats_a_product_within_one_message():
    ids = [p["id"] for p in stable_pool_pick(POOL, 5, "c", "x")]
    assert len(ids) == len(set(ids))


def test_a_pool_smaller_than_the_count_returns_the_whole_pool():
    """Picking 2 products but asking for 3 per message must still send those 2, not fail."""
    small = POOL[:2]
    out = stable_pool_pick(small, 3, "c", "x")
    assert len(out) == 2


def test_an_empty_pool_draws_nothing_instead_of_raising():
    assert stable_pool_pick([], 3, "c", "x") == []
    assert stable_pool_pick(None, 3, "c", "x") == []


def test_a_junk_count_falls_back_to_one_rather_than_crashing():
    for bad in (None, 0, -5, "x"):
        assert len(stable_pool_pick(POOL, bad, "c", "x")) >= 1


def test_the_draw_only_ever_contains_pool_members():
    ids = {p["id"] for p in POOL}
    for i in range(20):
        assert all(p["id"] in ids for p in stable_pool_pick(POOL, 4, "c", str(i)))


# ── containment: an empty pool must not change anything ─────────────────────
def test_the_pool_branch_requires_both_a_pool_and_a_contact():
    """The prefetch call sites have no contact yet. Without this guard they would take an
    arbitrary draw and present it as personalised."""
    src = inspect.getsource(cr.fetch_campaign_products)
    assert "pool_ids and contact is not None" in src


def test_the_legacy_paths_are_still_reachable_below_the_pool_branch():
    src = inspect.getsource(cr.fetch_campaign_products)
    pool_at = src.index("product_pool_ids")
    assert src.index("get_products_by_label") > pool_at
    assert src.index("return await get_products(") > pool_at


def test_an_unresolvable_pool_falls_back_instead_of_sending_no_products():
    """Every picked product deleted → the message must still carry the legacy products, not be
    silently product-less."""
    src = inspect.getsource(cr.fetch_campaign_products)
    assert "if pool:" in src


def test_the_contact_is_actually_passed_at_the_send_site():
    src = inspect.getsource(cr._deliver_message)
    assert "fetch_campaign_products(campaign, contact)" in src


def test_prices_are_still_fetched_per_message():
    """V15 Item 24 must survive: the pool draw reads prices in the same live call."""
    src = inspect.getsource(cr.fetch_campaign_products)
    assert "get_products_by_ids" in src


# ── the sanitiser ───────────────────────────────────────────────────────────
def test_empty_selection_collapses_to_none_so_legacy_behaviour_returns():
    for empty in (None, [], ()):
        assert _clean_product_pool(empty) is None


def test_duplicates_are_dropped_but_order_is_kept():
    assert _clean_product_pool(["b", "a", "b", "c"]) == ["b", "a", "c"]


def test_blanks_and_non_scalars_are_dropped():
    assert _clean_product_pool(["a", "", "  ", None, {}, [], "b"]) == ["a", "b"]


def test_an_all_junk_selection_collapses_to_none_not_an_empty_pool():
    """An empty list stored literally would mean "a pool of nothing" and every message would go
    out with no products at all."""
    assert _clean_product_pool(["", None, {}]) is None


def test_ids_are_not_forced_through_uuid_parsing():
    """Supabase ids are opaque to us. Validating them as UUIDs would silently drop a product the
    operator picked if the catalogue ever used another key format."""
    assert _clean_product_pool(["not-a-uuid", "123"]) == ["not-a-uuid", "123"]


@pytest.mark.parametrize("count", [1, 2, 3, 5, 10, 15])
def test_every_reasonable_count_draws_stably(count):
    a = stable_pool_pick(POOL, count, "camp", "contact")
    b = stable_pool_pick(POOL, count, "camp", "contact")
    assert a == b and len(a) == min(count, len(POOL))
