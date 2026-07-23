"""V42 PART 6 — end-to-end: a discontinued model self-heals through the real vision stack.

Drives the ACTUAL chain — extract_product_from_image → resolve_vision_model (real cache) → real
select_vision_model — with only the outermost edges mocked (the key lookup, the list-models HTTP via
discover, and the provider vision HTTP). Proves the whole feature works together: a cached model that
starts 404-ing gets re-discovered and switched to a currently-available model, the pipeline then
produces a real detection, the switch is logged, and a provider with no valid key is skipped cleanly.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import story_vision
from app.services import ai_vision_model_cache as cache
from app.services.story_vision import extract_product_from_image


def _key(provider):
    return SimpleNamespace(id=f"{provider}-k", provider=provider, api_key=f"{provider}-key")


@pytest.mark.asyncio
async def test_discontinued_model_is_rediscovered_and_pipeline_recovers(caplog):
    # discover: first call yields the (soon-discontinued) model, every later call yields its
    # currently-available replacement — i.e. the provider retired the model between calls.
    disc = {"n": 0}
    async def _discover(provider, api_key, **kw):
        disc["n"] += 1
        mid = "gemini-old-flash" if disc["n"] == 1 else "gemini-new-flash-lite"
        return {"provider": provider, "ok": True,
                "models": [{"id": mid, "methods": ["generateContent"]}],
                "error": None, "error_kind": None}

    # the provider vision endpoint: the old model is gone (404); the new one works.
    async def _gem(api_key, model, b64, mime):
        if model == "gemini-old-flash":
            raise RuntimeError("404 model not found: gemini-old-flash")
        return "یخچال ساید بای ساید سامسونگ"

    async def _get_key(provider=None):
        return _key("gemini") if provider in ("gemini", None) else None

    with patch.object(cache, "discover_available_models", _discover), \
         patch.object(story_vision, "_call_gemini_vision", _gem), \
         patch("app.services.ai_key_pool.get_working_key", _get_key), \
         patch("app.services.ai_key_pool.mark_success", AsyncMock()), \
         patch("app.services.ai_key_pool.mark_failure", AsyncMock()), \
         patch.object(story_vision, "_read_b64", lambda p: ("b64", "image/jpeg")), \
         patch("os.path.exists", lambda p: True), \
         caplog.at_level("INFO"):

        # Three failing calls on the cached old model drive it over FAILURE_THRESHOLD.
        for _ in range(cache.FAILURE_THRESHOLD):
            assert await extract_product_from_image("/x/i.jpg") is None
        assert cache.peek("gemini")["model"] == "gemini-old-flash"
        assert cache.peek("gemini")["force"] is True

        # Next call self-heals: re-discovers, switches model, and the pipeline recovers.
        healed = await extract_product_from_image("/x/i.jpg")

    assert healed == {"text": "یخچال ساید بای ساید سامسونگ", "provider": "gemini"}
    assert cache.peek("gemini")["model"] == "gemini-new-flash-lite"
    assert disc["n"] == 2, "list-models called exactly twice: initial + one self-heal re-discovery"
    assert any("gemini-old-flash" in m and "gemini-new-flash-lite" in m for m in caplog.messages), \
        "the model switch must be logged old->new"


@pytest.mark.asyncio
async def test_provider_with_no_valid_key_is_skipped_and_healthy_one_used():
    """openai's list-models auth-fails (no valid key) → skipped; gemini works → used. No crash."""
    async def _discover(provider, api_key, **kw):
        if provider == "openai":
            return {"provider": "openai", "ok": False, "models": [],
                    "error": "auth", "error_kind": "auth"}
        return {"provider": "gemini", "ok": True,
                "models": [{"id": "gemini-flash-lite-latest", "methods": ["generateContent"]}],
                "error": None, "error_kind": None}

    async def _gem(api_key, model, b64, mime):
        return "ماشین ظرفشویی بوش"

    # both providers have a key; VISION_PROVIDERS order is [openai, gemini] so openai is tried first.
    keys = {"openai": _key("openai"), "gemini": _key("gemini")}
    async def _get_key(provider=None):
        return keys.get(provider)

    with patch.object(cache, "discover_available_models", _discover), \
         patch.object(story_vision, "_call_gemini_vision", _gem), \
         patch.object(story_vision, "_call_openai_vision",
                      AsyncMock(side_effect=AssertionError("openai must be skipped, not called"))), \
         patch("app.services.ai_key_pool.get_working_key", _get_key), \
         patch("app.services.ai_key_pool.mark_success", AsyncMock()), \
         patch("app.services.ai_key_pool.mark_failure", AsyncMock()), \
         patch.object(story_vision, "_read_b64", lambda p: ("b64", "image/jpeg")), \
         patch("os.path.exists", lambda p: True):
        res = await extract_product_from_image("/x/i.jpg")

    assert res == {"text": "ماشین ظرفشویی بوش", "provider": "gemini"}


@pytest.mark.asyncio
async def test_no_provider_has_a_vision_model_reports_unavailable():
    """Every provider's discovery yields no vision model → the path reports unavailable (None),
    exactly matching the V40 guard, never a false empty result."""
    async def _discover(provider, api_key, **kw):
        # returns only non-vision models → select yields None
        return {"provider": provider, "ok": True,
                "models": [{"id": "text-embedding-004", "methods": ["embedContent"]}],
                "error": None, "error_kind": None}

    async def _get_key(provider=None):
        return _key("gemini") if provider in ("gemini", None) else None

    with patch.object(cache, "discover_available_models", _discover), \
         patch.object(story_vision, "_call_gemini_vision",
                      AsyncMock(side_effect=AssertionError("must not call a provider with no model"))), \
         patch("app.services.ai_key_pool.get_working_key", _get_key), \
         patch("app.services.ai_key_pool.mark_success", AsyncMock()), \
         patch("app.services.ai_key_pool.mark_failure", AsyncMock()), \
         patch.object(story_vision, "_read_b64", lambda p: ("b64", "image/jpeg")), \
         patch("os.path.exists", lambda p: True):
        res = await extract_product_from_image("/x/i.jpg")

    assert res is None, "no vision model anywhere → unavailable (None), not a crash or false empty"
