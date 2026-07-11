"""Tests for phone_extract — Iranian mobile/landline extraction across digit scripts."""
from app.services.phone_extract import (
    normalize_digits,
    normalize_iranian_mobile,
    extract_phones_from_text,
    normalize_sender_phone,
    contacts_for,
)


def test_normalize_persian_digits():
    assert normalize_digits("۰۹۱۲۳۴۵۶۷۸۹") == "09123456789"


def test_normalize_arabic_digits():
    assert normalize_digits("٠٩١٢") == "0912"


def test_normalize_iranian_mobile_variants():
    assert normalize_iranian_mobile("09123456789") == "09123456789"
    assert normalize_iranian_mobile("989123456789") == "09123456789"
    assert normalize_iranian_mobile("9123456789") == "09123456789"
    assert normalize_iranian_mobile("+989123456789") == "09123456789"


def test_normalize_iranian_mobile_rejects_invalid():
    assert normalize_iranian_mobile("021887766") is None
    assert normalize_iranian_mobile("12345") is None
    assert normalize_iranian_mobile("") is None


def test_extract_persian_digit_mobile():
    assert extract_phones_from_text("شماره من ۰۹۱۲۳۴۵۶۷۸۹ است") == ["09123456789"]


def test_extract_plus98_mobile():
    assert extract_phones_from_text("call +989123456789 now") == ["09123456789"]


def test_extract_plain_mobile():
    assert extract_phones_from_text("09123456789") == ["09123456789"]


def test_extract_landline():
    out = extract_phones_from_text("تماس: 021-88776655")
    assert "02188776655" in out


def test_extract_no_number_returns_empty():
    assert extract_phones_from_text("سلام بدون شماره") == []


def test_extract_dedupes_repeats():
    out = extract_phones_from_text("۰۹۱۲۳۴۵۶۷۸۹ و همچنین 09123456789")
    assert out == ["09123456789"]


def test_extract_multiple_distinct():
    out = extract_phones_from_text("۰۹۱۲۳۴۵۶۷۸۹ یا 09351112233")
    assert set(out) == {"09123456789", "09351112233"}


def test_normalize_sender_phone_strips_suffix():
    assert normalize_sender_phone("989123456789@c.us") == "09123456789"
    assert normalize_sender_phone("") == ""


def test_contacts_for_puts_sender_first_and_dedupes():
    sender, in_msg, allc = contacts_for("989123456789@c.us", "تماس با ۰۹۳۵۱۱۱۲۲۳۳ یا 09123456789")
    assert sender == "09123456789"
    assert "09351112233" in in_msg
    # sender must be first; the in-message duplicate of the sender is collapsed
    assert allc[0] == "09123456789"
    assert allc == ["09123456789", "09351112233"]
