"""V15 PART 2 — GPT prompt rules: group greeting, detail level, list format, name rules."""
import asyncio
import pytest
from app.services import gpt_service


def _capture_system(monkeypatch):
    """Stub _chat to record the system prompt it was called with; returns a dict."""
    seen = {}

    async def fake_chat(system, user, max_tokens, temperature):
        seen.setdefault("system", system)
        seen.setdefault("user", user)
        return "سلام\n✅ محصول — ۱۰۰ تومان"

    monkeypatch.setattr(gpt_service, "_chat", fake_chat)
    return seen


def test_group_prompt_forbids_group_name(monkeypatch):
    seen = _capture_system(monkeypatch)
    asyncio.run(gpt_service.generate_message(
        first_name="گروه", last_name="", gpt_prompt="پیام",
        products=[{"name": "a", "price": 100}], is_group=True, opening_mode="ai", include_opt_out=False))
    assert "سلام به گروه" in seen["system"]        # the forbidding rule mentions the banned phrase
    assert "نام فردی" in seen["system"]
    assert "اسم مشتری" not in seen["user"]          # no name line passed for a group


def test_pv_without_name_rule(monkeypatch):
    seen = _capture_system(monkeypatch)
    asyncio.run(gpt_service.generate_message(
        first_name="", last_name="", gpt_prompt="پیام",
        products=None, is_group=False, opening_mode="ai", include_opt_out=False))
    assert "اگر نام مخاطب مشخص نیست" in seen["system"]
    assert "اسم مشتری" not in seen["user"]


def test_pv_with_name_personalizes(monkeypatch):
    seen = _capture_system(monkeypatch)
    asyncio.run(gpt_service.generate_message(
        first_name="محمد", last_name="", gpt_prompt="پیام",
        products=None, is_group=False, opening_mode="ai", include_opt_out=False))
    assert "با نام مخاطب شخصی" in seen["system"]
    assert "اسم مشتری: محمد" in seen["user"]


@pytest.mark.parametrize("level,needle", [
    ("minimal", "فقط نام و قیمت"),
    ("medium", "حداکثر ۲ مشخصه"),
])
def test_detail_level_rule(monkeypatch, level, needle):
    seen = _capture_system(monkeypatch)
    asyncio.run(gpt_service.generate_message(
        first_name="", last_name="", gpt_prompt="پیام",
        products=[{"name": "a", "price": 100}], product_detail_level=level, include_opt_out=False))
    assert needle in seen["system"]


def test_detailed_level_no_restriction(monkeypatch):
    seen = _capture_system(monkeypatch)
    asyncio.run(gpt_service.generate_message(
        first_name="", last_name="", gpt_prompt="پیام",
        products=[{"name": "a", "price": 100}], product_detail_level="detailed", include_opt_out=False))
    assert "فقط نام و قیمت" not in seen["system"]
    assert "حداکثر ۲ مشخصه" not in seen["system"]


def test_list_format_rule_present_with_products(monkeypatch):
    seen = _capture_system(monkeypatch)
    asyncio.run(gpt_service.generate_message(
        first_name="", last_name="", gpt_prompt="پیام",
        products=[{"name": "a", "price": 100}], include_opt_out=False))
    assert "لیست مرتب" in seen["system"] and "✅" in seen["system"]


# ── fallback template (AI down) ─────────────────────────────────────────────
def test_fallback_group_no_name_and_checklist_format():
    out = gpt_service._fallback_message("گروه", [{"name": "کولر", "price": 100}], True, "ai", None, is_group=True)
    assert "دوست عزیز" not in out
    assert "گروه" not in out                       # group name never used
    assert "✅ کولر — 100 تومان" in out


def test_fallback_no_name_uses_plain_hello():
    out = gpt_service._fallback_message("", None, True, "ai", None)
    assert out.startswith("سلام!")
    assert "دوست عزیز" not in out
