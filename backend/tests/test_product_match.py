"""Tests for token-based product-mention matching."""
from app.services.product_match import (
    catalog_brand_tokens,
    detect_product_mentions,
    is_reportable_product_name,
    match_products,
)

PRODUCTS = [
    {"name": "یونیوا 18000 مدل UN-TS 18 TITANIUM AMP INVERTER اینورتر سرد وگرم"},
    {"name": "موتور برق 21 اسب بخار جنرال برلین مدل BE_6500EIG"},
    {"name": "کولر گازی اسنوا 24000 مدل لوکس"},
]


def test_matches_brand_plus_capacity():
    hits = match_products("سلام قیمت یونیوا 18000 چنده؟", PRODUCTS)
    assert any("یونیوا 18000" in h for h in hits)


def test_no_match_on_greeting():
    assert match_products("سلام خوبی؟", PRODUCTS) == []
    assert match_products("❤️", PRODUCTS) == []


def test_brand_alone_is_not_enough():
    # brand keyword without a capacity/model token → no match (precision)
    assert match_products("قیمت اسنوا چنده؟", PRODUCTS) == []


def test_strong_model_code_matches_alone():
    hits = match_products("be_6500eig موجوده؟", PRODUCTS)
    assert any("BE_6500EIG" in h for h in hits)


def test_capacity_is_whole_token_not_substring():
    # 180000 must NOT match the 18000-capacity product
    assert match_products("قیمت 180000 تومان", PRODUCTS) == []


def test_brand_plus_capacity_other_product():
    hits = match_products("اسنوا 24000 هست؟", PRODUCTS)
    assert any("اسنوا 24000" in h for h in hits)


def test_finance_lines_are_not_unknown_products():
    samples = [
        "❌ واریز مبلغ زیر 10میلیون تومان به هیچ عنوان پذیرفته نیست",
        "یک واریزی 926.000.000ریال هم داشتم فیش نفرستادین",
        "حدودا 255میلیون تومان",
    ]
    for text in samples:
        assert detect_product_mentions(text, PRODUCTS) == []


def test_unknown_appliance_lines_still_detect():
    hits = detect_product_mentions("کولر 6000 سنگرکار پوشالی", PRODUCTS)
    assert hits and hits[0]["product_id"] is None

    hits = detect_product_mentions("پنل تک 24 هایسنس اینورتر موجود✅", PRODUCTS)
    assert hits and hits[0]["product_id"] is None


def test_legacy_finance_report_names_are_hidden():
    assert not is_reportable_product_name("❌ واریز مبلغ زیر 10میلیون تومان به هیچ عنوان پذیرفته نیست")
    assert not is_reportable_product_name("یک واریزی")
    assert not is_reportable_product_name("حدودا")
    assert is_reportable_product_name("کولر 6000 سنگرکار پوشالی")
    assert is_reportable_product_name("AF500")


# ── V49 PART 3 — capacity + catalog-brand listings (no generic noun, no model code) ───────────────
def test_brand_lexicon_is_derived_from_catalog():
    brands = catalog_brand_tokens(PRODUCTS)
    # distinctive Persian-script brand words from the catalog names are learned…
    assert {"یونیوا", "جنرال", "برلین", "اسنوا"} <= brands
    # …but generic appliance nouns, latin model/series codes, stopwords and digits are NOT brands
    for non_brand in {"کولر", "موتور", "مدل", "un-ts", "titanium", "be_6500eig", "18000", "لوکس"}:
        assert non_brand not in brands


def test_capacity_plus_brand_listing_now_detected():
    # The previously-missed shape: "<capacity> <brand> ... موجود/قیمت" with no generic appliance noun
    # (کولر/پنل/اسپلیت) and no ≥5-char model code. Real example class: «۲۴ هزار جنرال گلد اکو موجود✅».
    for text in [
        "۲۴ هزار جنرال اکو موجود✅",
        "۳۰ هزار یونیوا دیوا موجود",
        "۶۰ هزار اسنوا بیکس قیمت ۸۷ میلیون",
        "۳۰هزار جنرال موتور بزرگ ویتالی",
    ]:
        hits = detect_product_mentions(text, PRODUCTS)
        assert hits, f"should detect: {text}"
        assert hits[0]["product_id"] is None       # advertised outside the assistant catalog


def test_brand_branch_requires_both_capacity_and_a_commerce_signal():
    # A brand with a commerce word but NO capacity → not a listing (precision).
    assert detect_product_mentions("قیمت جنرال چنده؟", PRODUCTS) == []
    # A brand with a capacity but NO commerce signal (ad word / price) → not a listing.
    assert detect_product_mentions("جنرال ۲۴ هزار رنگش خیلی قشنگه", PRODUCTS) == []


def test_capacity_brand_relaxation_keeps_non_product_chatter_out():
    # Guardrail 3 — the relaxation must not turn ordinary/finance/greeting messages into detections,
    # even when they contain money amounts or a person's name that is not a catalog brand.
    for text in [
        "سلام دوستان وقت بخیر خوبید؟",
        "ممنون از لطف شما عزیزان",
        "۲۴ هزار تومان واریز کردم به حساب",
        "سام جان ۲۴ هزار تومن بهم بده لطفا",   # «سام» is deliberately NOT a brand token
        "لطفا شماره حساب رو بفرستید تسویه کنم",
        "حدودا 255میلیون تومان",
    ]:
        assert detect_product_mentions(text, PRODUCTS) == [], f"false positive on: {text}"


def test_existing_detections_unchanged_by_relaxation():
    # No regression: catalog matches, product-word lines, and model-code lines still detect as before.
    assert match_products("سلام قیمت یونیوا 18000 چنده؟", PRODUCTS)
    assert detect_product_mentions("پنل تک 24 هایسنس اینورتر موجود✅", PRODUCTS)
    assert detect_product_mentions("کولر 6000 سنگرکار پوشالی", PRODUCTS)
