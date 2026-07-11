"""V13.6 — live preview must use the SAME build path as the runner (build_message_text),
so a preview equals what the runner would produce for the same config + contact."""
import asyncio
from types import SimpleNamespace

from app.services.campaign_runner import build_message_text


def _campaign(**over):
    base = dict(
        use_gpt=False, gpt_prompt=None, message_template="سلام {نام} عزیز! پیشنهاد ویژه امروز.",
        include_products=False, product_count=3, show_prices=True, show_product_prices=True,
        emoji_level="medium", opening_mode="none", opening_line=None, opening_variants=None,
        include_opt_out=True, opt_out_text=None, use_rich_formatting=False,
        append_seller_name=False, seller_name=None, append_seller_phone=False,
        seller_phone=None, seller_phone2=None, append_date=False,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _contact(first="علی", last="رضایی", city="تهران", province="تهران"):
    return SimpleNamespace(first_name=first, last_name=last, city=city, province=province)


def test_template_substitution_and_optout_in_preview():
    c = _campaign()
    text = asyncio.run(build_message_text(c, _contact(), [], None, c.message_template, False))
    assert "سلام علی عزیز" in text            # {نام} substituted
    assert "برای لغو عدد ۱۱ ارسال کنید" in text  # opt-out appended


def test_preview_matches_runner_for_same_inputs():
    c = _campaign(message_template="متن *پررنگ* برای {نام}")
    contact = _contact(first="مریم")
    # Two independent builds with identical inputs must be identical (deterministic template path).
    a = asyncio.run(build_message_text(c, contact, [], None, c.message_template, False))
    b = asyncio.run(build_message_text(c, contact, [], None, c.message_template, False))
    assert a == b
    assert "*پررنگ*" in a                       # formatting markers preserved
    assert "مریم" in a


def test_optout_disabled_and_fixed_opening_in_preview():
    c = _campaign(message_template="بدنه پیام", include_opt_out=False,
                  opening_mode="fixed", opening_line="سلام دوستان")
    text = asyncio.run(build_message_text(c, _contact(), [], None, c.message_template, False))
    assert text.startswith("سلام دوستان")
    assert "لغو" not in text


def test_seller_signature_appended_in_preview():
    c = _campaign(append_seller_name=True, seller_name="فروشگاه افرا",
                  append_seller_phone=True, seller_phone="09120000000")
    text = asyncio.run(build_message_text(c, _contact(), [], None, c.message_template, False))
    assert "فروشگاه افرا" in text
    assert "09120000000" in text
