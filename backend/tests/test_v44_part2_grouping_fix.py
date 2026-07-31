"""V44 PART 2 — fix: top_products_rows now merges near-identical product-name spellings into one row.

Uses the SAME real near-duplicate fixtures found in PART 1 (pulled from the live product_mention_logs
table). Proves the fix reuses the existing normalizers (product_match.product_group_key) so the real
pairs collapse into a single row with a COMBINED mention_count, while genuinely different products
stay separate (no over-merge).
"""
from datetime import datetime
from types import SimpleNamespace
import pytest

from app.services import product_reports as prs
from app.services.product_match import product_canonical_key, product_group_key

LAST = datetime(2026, 7, 23, 20, 0)


class _FakeResult:
    def __init__(self, rows): self._rows = rows
    def all(self): return list(self._rows)
    def scalars(self):
        outer = self
        class _S:
            def all(s): return list(outer._rows)
        return _S()


class _FakeDB:
    """Returns per-RAW-name aggregate rows for the grouped top-products query (the SQL shape)."""
    def __init__(self, agg_rows, mention_rows=None):
        self._agg = agg_rows
        self._mentions = mention_rows if mention_rows is not None else agg_rows
    async def execute(self, q):
        return _FakeResult(self._agg if "group by" in str(q).lower() else self._mentions)


def _agg(name, mention_count, *, product_id=None, group_count=1, sender_count=1,
         sources="group", last_mention=LAST):
    return SimpleNamespace(product_name=name, product_id=product_id, mention_count=mention_count,
                           group_count=group_count, sender_count=sender_count,
                           sources=sources, last_mention=last_mention)


def _mention(name, *, sender_phone="989121112233", text="موجود", last_mention=LAST):
    return SimpleNamespace(product_name=name, product_id=None, sender_phone=sender_phone,
                           sender_name="seller", group_name="group", message_text=text,
                           mentioned_at=last_mention)


# ── the normalized key (reused existing normalizers) ─────────────────────────
def test_product_group_key_collapses_real_variants():
    assert product_group_key("یخچال ساید بای ساید ال‌جی") == product_group_key("یخچال ساید بای ساید ال جی")
    assert product_group_key("جاروبرقی بوش سری 8") == product_group_key("جاروبرقی بوش سری ۸")
    assert product_group_key("دستگاه بستنی ساز نینجا مدل NC701") == product_group_key("دستگاه بستنی ساز نینجا مدل Nc701")
    assert product_group_key("باند پارتى باکس DENAY") == product_group_key("باند پارتی باکس DENAY")
    # ...but two genuinely different products keep different keys.
    assert product_group_key("یخچال ساید بای ساید ال‌جی") != product_group_key("مایکروویو سولاردام ال‌جی")


def test_product_canonical_key_merges_model_shorthand_but_not_distinct_models():
    assert (
        product_canonical_key("ماشین ظرفشویی بوش مدل SMS46NW01")
        == product_canonical_key("🎈 ظرفشویی بوش ترکیه سفید 46NW01B")
        == product_canonical_key("🎈 ظرفشویی بوش سری 4 ترکیه سفید مدل 46nw01B")
    )
    assert product_canonical_key("ماشین ظرفشویی بوش مدل SMS46NW01") != product_canonical_key(
        "ماشین ظرفشویی بوش مدل SMS46NI01")
    assert product_canonical_key("ماشین ظرفشویی بوش مدل SMS46NW01") != product_canonical_key(
        "SMS46DW01B ماشین ظرفشویی بوش سفید سری 4")


# ── the LG fridge pair (real top product) now merges into ONE row, count 8+3=11 ──
@pytest.mark.asyncio
async def test_real_near_duplicates_merge_into_one_row():
    db = _FakeDB([
        _agg("یخچال ساید بای ساید ال‌جی", 8, group_count=6, sender_count=6, sources="group,pv,status"),
        _agg("یخچال ساید بای ساید ال جی", 3, group_count=2, sender_count=2, sources="pv"),
    ])
    out = await prs.top_products_rows(db, days=30, limit=150)
    assert len(out) == 1                                   # was two rows before the fix
    row = out[0]
    assert row["mention_count"] == 11                      # 8 + 3 combined (exact)
    assert row["product_name"] == "یخچال ساید بای ساید ال‌جی"   # most-common spelling shown
    assert set(row["sources"]) == {"group", "pv", "status"}     # unioned
    assert row["rank"] == 1


# ── a mixed batch: each real pair merges; distinct products remain separate ──
@pytest.mark.asyncio
async def test_mixed_batch_merges_pairs_keeps_distinct():
    db = _FakeDB([
        _agg("یخچال ساید بای ساید ال‌جی", 8),
        _agg("یخچال ساید بای ساید ال جی", 3),
        _agg("جاروبرقی بوش سری 8", 2),
        _agg("جاروبرقی بوش سری ۸", 1),
        _agg("مایکروویو سولاردام ال‌جی", 4),          # genuinely different product
        _agg("دستگاه بستنی ساز نینجا مدل NC701", 2, product_id="CAT-NINJA"),
        _agg("دستگاه بستنی ساز نینجا مدل Nc701", 1),
    ])
    out = await prs.top_products_rows(db, days=30, limit=150)
    by_name = {r["product_name"]: r for r in out}
    # 4 distinct products (3 merged pairs + 1 standalone), not 7 fragmented rows.
    assert len(out) == 4
    assert by_name["یخچال ساید بای ساید ال‌جی"]["mention_count"] == 11
    assert by_name["جاروبرقی بوش سری 8"]["mention_count"] == 3
    assert by_name["دستگاه بستنی ساز نینجا مدل NC701"]["mention_count"] == 3
    # the standalone product is untouched (no over-merge).
    assert by_name["مایکروویو سولاردام ال‌جی"]["mention_count"] == 4
    # a catalog match on ANY spelling makes the merged row in-assistant.
    assert by_name["دستگاه بستنی ساز نینجا مدل NC701"]["in_assistant"] is True
    # ranking by combined count: the LG fridge (11) is #1.
    assert out[0]["product_name"] == "یخچال ساید بای ساید ال‌جی" and out[0]["rank"] == 1


# ── guard: distinct products are never over-merged, even when superficially similar ──
@pytest.mark.asyncio
async def test_does_not_over_merge_distinct_products():
    db = _FakeDB([
        _agg("کولر گازی ال‌جی 18000", 5),
        _agg("کولر گازی ال‌جی 24000", 4),      # same brand, DIFFERENT capacity → must stay separate
        _agg("کولر گازی ال‌جی 30000", 3),
    ])
    out = await prs.top_products_rows(db, days=30, limit=150)
    assert len(out) == 3
    assert {r["mention_count"] for r in out} == {5, 4, 3}


@pytest.mark.asyncio
async def test_bosch_dishwasher_shorthand_merges_keeps_other_models_distinct():
    db = _FakeDB([
        _agg("ماشین ظرفشویی بوش مدل SMS46NW01", 8, product_id="CAT-NW01", group_count=4, sender_count=2),
        _agg("🎈 ظرفشویی بوش ترکیه سفید 46NW01B", 4, group_count=2, sender_count=1),
        _agg("🎈 ظرفشویی بوش سری 4 ترکیه سفید مدل 46nw01B", 1, group_count=1, sender_count=1),
        _agg("ماشین ظرفشویی بوش مدل SMS46NI01", 4, product_id="CAT-NI01", group_count=4, sender_count=1),
        _agg("SMS46DW01B ماشین ظرفشویی بوش سفید سری 4", 1, group_count=0, sender_count=1),
    ])
    # Default path: the deterministic canonical key merges the NW01 spellings but keeps NI01
    # and DW01B distinct. Passing ai_merge=True here would ALSO run the AI alias pass, which
    # merges NI01 in as well (17 != 13) — that is what this test exists to catch.
    out = await prs.top_products_rows(db, days=7, limit=150)
    by_name = {r["product_name"]: r for r in out}

    assert by_name["ماشین ظرفشویی بوش مدل SMS46NW01"]["mention_count"] == 13
    assert by_name["ماشین ظرفشویی بوش مدل SMS46NW01"]["in_assistant"] is True
    assert by_name["ماشین ظرفشویی بوش مدل SMS46NI01"]["mention_count"] == 4
    assert by_name["SMS46DW01B ماشین ظرفشویی بوش سفید سری 4"]["mention_count"] == 1
    assert len(out) == 3


@pytest.mark.asyncio
async def test_mentioners_drilldown_includes_every_merged_variant():
    db = _FakeDB([], [
        _mention("ماشین ظرفشویی بوش مدل SMS46NW01", sender_phone="989121111111"),
        _mention("🎈 ظرفشویی بوش ترکیه سفید 46NW01B", sender_phone="989122222222"),
        _mention("ماشین ظرفشویی بوش مدل SMS46NI01", sender_phone="989123333333"),
    ])

    rows = await prs.product_mentioners_rows(
        db, product_name="ماشین ظرفشویی بوش مدل SMS46NW01", days=7, limit=100)

    assert len(rows) == 2
    assert {r["sender_phone"] for r in rows} == {"09121111111", "09122222222"}
