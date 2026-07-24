"""V44 PART 1 — investigation (findings only): how the top-products report currently groups names.

Finding: `product_reports.top_products_rows` does `GROUP BY ProductMentionLog.product_name` — a naive
EXACT-string match with no normalization. So the SAME real product, written slightly differently by
different contacts (ZWNJ vs space, Persian vs Latin digits, model-code case, Arabic vs Persian
letters), fragments into MULTIPLE report rows, undercounting its true repeat frequency.

The fixtures below are REAL near-duplicate `product_name` values pulled from the live
product_mention_logs table (not invented). These tests document the CURRENT (buggy) exact-match
behavior and prove the same pairs collapse under the project's EXISTING normalizers — the fix wired
in PART 2. No production code is changed in PART 1.
"""
from collections import defaultdict

from app.services.group_detection import normalize_fa
from app.services.product_match import _TOKEN_RE


# Real pairs from the live DB: (variant_a, count_a, variant_b, count_b). Same product, two spellings.
NEAR_DUP_PAIRS = [
    # LG side-by-side fridge — ZWNJ (‌) vs plain space inside «ال‌جی» / «ال جی» (top product).
    ("یخچال ساید بای ساید ال‌جی", 8, "یخچال ساید بای ساید ال جی", 3),
    # Bosch vacuum «سری ۸» — Latin digit 8 vs Persian digit ۸.
    ("جاروبرقی بوش سری 8", 2, "جاروبرقی بوش سری ۸", 1),
    # Ninja ice-cream maker — model-code case NC701 vs Nc701.
    ("دستگاه بستنی ساز نینجا مدل NC701", 2, "دستگاه بستنی ساز نینجا مدل Nc701", 1),
    # DENAY party speaker — Arabic «پارتى» (U+0649) vs Persian «پارتی» (U+06CC).
    ("باند پارتى باکس DENAY", 1, "باند پارتی باکس DENAY", 1),
]


def _norm_key(name: str) -> str:
    """The grouping key from the project's EXISTING normalizers, composed: normalize_fa (Arabic→
    Persian letters, digit scripts, diacritics/tatweel, case, whitespace) then the same token regex
    product_match uses (drops spacing/punctuation/ZWNJ). This is what PART 2 will group by."""
    return " ".join(_TOKEN_RE.findall(normalize_fa(name)))


def _exact_group(rows):
    """Simulate the CURRENT SQL semantics: GROUP BY the exact product_name string."""
    g = defaultdict(int)
    for name, c in rows:
        g[name] += c
    return g


# ── documents the bug: exact grouping splits real near-duplicates into separate rows ──
def test_current_exact_grouping_fragments_real_near_duplicates():
    for a, ca, b, cb in NEAR_DUP_PAIRS:
        grouped = _exact_group([(a, ca), (b, cb)])
        # Two DISTINCT rows today — the same product counted twice, never combined.
        assert set(grouped) == {a, b}
        assert len(grouped) == 2
        assert grouped[a] == ca and grouped[b] == cb
        # ...and the TRUE combined frequency (what the report should show) is undercounted as two rows.
        assert ca + cb > max(ca, cb)


# ── proves each real pair is genuinely the SAME product under the existing normalizers ──
def test_real_variants_share_one_normalized_key():
    for a, _ca, b, _cb in NEAR_DUP_PAIRS:
        assert a != b                       # genuinely different raw text (so exact grouping splits)
        assert _norm_key(a) == _norm_key(b)  # ...but one product after the existing normalization


# ── guard: genuinely different products keep DISTINCT keys (no over-merge risk) ──
def test_distinct_products_keep_distinct_keys():
    distinct = [
        "یخچال ساید بای ساید ال‌جی",
        "مایکروویو سولاردام ال‌جی",
        "جاروبرقی بوش سری 8",
        "دستگاه بستنی ساز نینجا مدل NC701",
        "باند پارتی باکس DENAY",
    ]
    keys = {_norm_key(n) for n in distinct}
    assert len(keys) == len(distinct)       # every distinct product → its own key
