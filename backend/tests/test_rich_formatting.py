"""V13.5 — rich WhatsApp formatting: opt-out/opening post-processing must not strip
formatting markers, and the AI rich instruction is gated by use_rich_formatting."""
import inspect

from app.services.gpt_service import _apply_opening, _apply_opt_out, generate_message


def test_opt_out_preserves_whatsapp_markers():
    text = "*ساید ال جی* با قیمت _ویژه_\n~قیمت قبلی~"
    out = _apply_opt_out(text, True, None)
    assert "*ساید ال جی*" in out
    assert "_ویژه_" in out
    assert "~قیمت قبلی~" in out


def test_opening_preserves_markers():
    out = _apply_opening("*پیشنهاد ویژه* امروز", "fixed", "سلام دوستان")
    assert out.startswith("سلام دوستان")
    assert "*پیشنهاد ویژه*" in out


def test_mono_triple_backtick_survives():
    text = "```کد تخفیف: NOROOZ30```"
    out = _apply_opt_out(text, False, None)
    assert "```کد تخفیف: NOROOZ30```" in out


def test_generate_message_accepts_use_rich_formatting_param():
    sig = inspect.signature(generate_message)
    assert "use_rich_formatting" in sig.parameters
    assert sig.parameters["use_rich_formatting"].default is False
