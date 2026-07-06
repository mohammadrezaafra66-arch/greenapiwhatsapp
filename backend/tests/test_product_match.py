"""Tests for token-based product-mention matching."""
from app.services.product_match import match_products

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
