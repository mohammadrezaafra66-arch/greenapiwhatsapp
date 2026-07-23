"""V42 PART 3 — vision-capability filtering + cheapest-first preference.

Uses realistic model lists (the exact families the live list-models APIs return today) to prove:
the right cheap vision model is chosen; a non-preferred-tier vision model is chosen when the cheap
tier is absent; and "none available" is returned (never a crash) when nothing qualifies.
"""
from app.services.ai_vision_select import is_vision_model, select_vision_model


def _m(mid, methods=None):
    return {"id": mid, "methods": methods if methods is not None else []}


# ── Gemini capability rules ─────────────────────────────────────────────────────────────────────
def test_gemini_generatecontent_flash_is_vision():
    assert is_vision_model("gemini", _m("gemini-2.5-flash", ["generateContent", "countTokens"]))


def test_gemini_embedding_is_not_vision():
    assert not is_vision_model("gemini", _m("text-embedding-004", ["embedContent"]))


def test_gemini_tts_and_image_gen_excluded():
    assert not is_vision_model("gemini", _m("gemini-2.5-flash-preview-tts", ["generateContent"]))
    assert not is_vision_model("gemini", _m("gemini-2.5-flash-image", ["generateContent"]))
    assert not is_vision_model("gemini", _m("gemini-2.5-computer-use-preview", ["generateContent"]))


def test_gemma_and_other_families_excluded():
    assert not is_vision_model("gemini", _m("gemma-4-31b-it", ["generateContent"]))
    assert not is_vision_model("gemini", _m("nano-banana-pro-preview", ["generateContent"]))


# ── OpenAI capability rules ─────────────────────────────────────────────────────────────────────
def test_openai_4o_and_41_families_are_vision():
    for mid in ("gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "gpt-4-turbo"):
        assert is_vision_model("openai", _m(mid)), mid


def test_openai_non_vision_variants_excluded():
    for mid in ("gpt-4o-mini-tts", "gpt-4o-transcribe", "gpt-4o-mini-transcribe",
                "gpt-4o-search-preview", "gpt-4o-realtime-preview", "gpt-4o-audio-preview"):
        assert not is_vision_model("openai", _m(mid)), mid


def test_openai_non_vision_model_families_excluded():
    for mid in ("gpt-3.5-turbo", "text-embedding-3-small", "whisper-1", "dall-e-3", "o1-mini",
                "gpt-5.1-codex-mini"):
        assert not is_vision_model("openai", _m(mid)), mid


# ── selection + preference ──────────────────────────────────────────────────────────────────────
GEMINI_LIVE = [
    _m("gemini-2.5-pro", ["generateContent"]),
    _m("gemini-2.0-flash", ["generateContent"]),
    _m("gemini-2.5-flash", ["generateContent"]),
    _m("gemini-2.5-flash-lite", ["generateContent"]),
    _m("gemini-flash-lite-latest", ["generateContent"]),
    _m("gemini-2.5-flash-preview-tts", ["generateContent"]),   # excluded
    _m("text-embedding-004", ["embedContent"]),                 # excluded
]


def test_gemini_prefers_cheap_flash_lite_latest_alias():
    res = select_vision_model("gemini", GEMINI_LIVE)
    assert res["ok"] is True
    assert res["model"] == "gemini-flash-lite-latest"           # cheapest tier + floating alias
    assert "gemini-2.5-flash-preview-tts" not in res["candidates"]
    assert "text-embedding-004" not in res["candidates"]


def test_gemini_falls_back_to_pro_when_no_cheap_tier():
    only_pro = [_m("gemini-2.5-pro", ["generateContent"]),
                _m("text-embedding-004", ["embedContent"])]
    res = select_vision_model("gemini", only_pro)
    assert res["ok"] is True and res["model"] == "gemini-2.5-pro"


OPENAI_LIVE = [
    _m("gpt-4o"), _m("gpt-4o-2024-08-06"), _m("gpt-4o-mini"), _m("gpt-4o-mini-2024-07-18"),
    _m("gpt-4.1"), _m("gpt-4.1-mini"), _m("gpt-4.1-nano"), _m("gpt-5"),
    _m("gpt-4o-mini-tts"), _m("gpt-4o-transcribe"), _m("gpt-3.5-turbo"),
    _m("text-embedding-3-small"),
]


def test_openai_prefers_a_mini_over_base_and_excludes_non_vision():
    res = select_vision_model("openai", OPENAI_LIVE)
    assert res["ok"] is True
    assert "mini" in res["model"], res["model"]                 # cheap tier chosen
    for bad in ("gpt-4o-mini-tts", "gpt-4o-transcribe", "gpt-3.5-turbo", "text-embedding-3-small"):
        assert bad not in res["candidates"]


def test_openai_prefers_floating_alias_over_dated_snapshot():
    res = select_vision_model("openai", OPENAI_LIVE)
    # whichever mini wins, it must be the undated floating name, not a -YYYY snapshot
    assert not any(ch.isdigit() for ch in res["model"].split("-")[-1]) or "mini" in res["model"]
    assert res["model"] in ("gpt-4.1-mini", "gpt-4o-mini")


def test_no_vision_model_returns_clear_none():
    res = select_vision_model("gemini", [_m("text-embedding-004", ["embedContent"]),
                                         _m("gemma-4-31b-it", ["generateContent"])])
    assert res["ok"] is False and res["model"] is None
    assert res["reason"] == "no vision-capable model available"


def test_empty_list_returns_clear_none():
    res = select_vision_model("openai", [])
    assert res["ok"] is False and res["model"] is None


def test_unknown_provider_selects_nothing():
    res = select_vision_model("deepseek", [_m("deepseek-chat")])
    assert res["ok"] is False and res["model"] is None
