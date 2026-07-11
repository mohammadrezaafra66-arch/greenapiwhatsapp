"""V13.4 — opt-out keyword detection."""
from app.services.optout import is_opt_out


def test_persian_eleven():
    assert is_opt_out("۱۱")
    assert is_opt_out("11")


def test_persian_cancel_words():
    assert is_opt_out("لغو")
    assert is_opt_out("لغو ۱۱")
    assert is_opt_out("لغو۱۱")
    assert is_opt_out("لغو عضویت")


def test_english_keywords_case_insensitive():
    assert is_opt_out("STOP")
    assert is_opt_out("Unsubscribe")


def test_whitespace_trimmed():
    assert is_opt_out("  ۱۱  ")
    assert is_opt_out("لغو\n")


def test_non_optout_messages():
    assert not is_opt_out("سلام")
    assert not is_opt_out("لغو نکن")          # 'don't cancel' must NOT opt out
    assert not is_opt_out("قیمت یخچال چنده؟")
    assert not is_opt_out("")
    assert not is_opt_out(None)
    assert not is_opt_out("11 عدد میخوام")     # not an exact opt-out message
