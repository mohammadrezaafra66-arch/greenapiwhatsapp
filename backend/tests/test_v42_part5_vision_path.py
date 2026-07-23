"""V42 PART 5 — the story-image vision path uses the discovered model, not a hardcoded name.

Proves: extract_product_from_image resolves the model via the discovery/cache layer and calls the
provider with THAT model (never 'gpt-4o-mini'/'gemini-2.0-flash'); when no vision model can be
resolved it reports unavailable (None) exactly like the V40 guard, without crashing; and the V40
success/failure distinction ({"text": None} vs None) is preserved.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import story_vision
from app.services.story_vision import extract_product_from_image


class _Key(SimpleNamespace):
    pass


def _key(provider, kid="k1"):
    return _Key(id=kid, provider=provider, api_key=f"{provider}-key")


def _patches(*, key, resolved_model=None, gemini_call=None, openai_call=None,
             resolve_result=None):
    """Common monkeypatch bundle for the vision path. Returns a contextmanager list."""
    async def _get_working_key(provider=None):
        # return the key only for its own provider, else None (so provider order is honored)
        return key if (provider == key.provider or provider is None) else None

    async def _resolve(provider, api_key, **kw):
        if resolve_result is not None:
            return resolve_result
        return {"model": resolved_model, "from_cache": False, "candidates": [resolved_model],
                "changed_from": None, "discovery_error": None}

    cms = [
        patch("app.services.ai_key_pool.get_working_key", _get_working_key),
        patch("app.services.ai_key_pool.mark_success", AsyncMock()),
        patch("app.services.ai_key_pool.mark_failure", AsyncMock()),
        patch("app.services.ai_vision_model_cache.resolve_vision_model", _resolve),
        patch.object(story_vision, "_read_b64", lambda p: ("b64data", "image/jpeg")),
        patch("os.path.exists", lambda p: True),
    ]
    if gemini_call is not None:
        cms.append(patch.object(story_vision, "_call_gemini_vision", gemini_call))
    if openai_call is not None:
        cms.append(patch.object(story_vision, "_call_openai_vision", openai_call))
    return cms


def _enter(cms):
    for cm in cms:
        cm.start()


def _exit(cms):
    for cm in reversed(cms):
        cm.stop()


@pytest.mark.asyncio
async def test_uses_discovered_gemini_model_not_hardcoded():
    seen = {}
    async def _gem(api_key, model, b64, mime):
        seen["model"] = model
        return "کولر گازی اسنوا"
    cms = _patches(key=_key("gemini"), resolved_model="gemini-flash-lite-latest", gemini_call=_gem)
    _enter(cms)
    try:
        res = await extract_product_from_image("/x/i.jpg")
    finally:
        _exit(cms)
    assert seen["model"] == "gemini-flash-lite-latest", "must call the DISCOVERED model"
    assert seen["model"] != "gemini-2.0-flash", "the dead hardcoded name must be gone"
    assert res == {"text": "کولر گازی اسنوا", "provider": "gemini"}


@pytest.mark.asyncio
async def test_uses_discovered_openai_model_not_hardcoded():
    seen = {}
    async def _oai(api_key, model, b64, mime):
        seen["model"] = model
        return "ماشین لباسشویی ال جی"
    cms = _patches(key=_key("openai"), resolved_model="gpt-4.1-mini", openai_call=_oai)
    _enter(cms)
    try:
        res = await extract_product_from_image("/x/i.jpg")
    finally:
        _exit(cms)
    assert seen["model"] == "gpt-4.1-mini"
    assert seen["model"] != "gpt-4o-mini"
    assert res["provider"] == "openai"


@pytest.mark.asyncio
async def test_no_vision_model_reports_unavailable_like_v40_guard():
    """resolve returns None (no vision model) → the path returns None (vision could not run),
    never a false empty result, and never crashes."""
    async def _never(*a, **k):
        raise AssertionError("provider must not be called when no model resolves")
    cms = _patches(key=_key("gemini"),
                   resolve_result={"model": None, "from_cache": False, "candidates": [],
                                   "changed_from": None, "discovery_error": "auth"},
                   gemini_call=_never)
    _enter(cms)
    try:
        res = await extract_product_from_image("/x/i.jpg")
    finally:
        _exit(cms)
    assert res is None, "no model → vision unavailable (None), matching the V40 guard"


@pytest.mark.asyncio
async def test_successful_but_empty_result_is_text_none_not_none():
    """The V40 distinction must survive: model ran, saw no product → {'text': None}, NOT None."""
    async def _gem(api_key, model, b64, mime):
        return "نامشخص"        # _clean() maps this to None
    cms = _patches(key=_key("gemini"), resolved_model="gemini-flash-lite-latest", gemini_call=_gem)
    _enter(cms)
    try:
        res = await extract_product_from_image("/x/i.jpg")
    finally:
        _exit(cms)
    assert res == {"text": None, "provider": "gemini"}, "ran-but-empty must be {'text': None}"


@pytest.mark.asyncio
async def test_vision_call_failure_returns_none_and_records_failure():
    calls = {"fail": 0}
    async def _boom(api_key, model, b64, mime):
        raise RuntimeError("404 model not found")
    def _rec_fail(provider, model):
        calls["fail"] += 1
    cms = _patches(key=_key("gemini"), resolved_model="gemini-flash-lite-latest", gemini_call=_boom)
    cms.append(patch("app.services.ai_vision_model_cache.record_failure", _rec_fail))
    _enter(cms)
    try:
        res = await extract_product_from_image("/x/i.jpg")
    finally:
        _exit(cms)
    assert res is None, "every attempt failed → vision unavailable"
    assert calls["fail"] >= 1, "the model failure must be forwarded to the self-heal counter"


@pytest.mark.asyncio
async def test_missing_image_returns_none_without_resolving():
    cms = [patch("os.path.exists", lambda p: False)]
    _enter(cms)
    try:
        res = await extract_product_from_image("/x/missing.jpg")
    finally:
        _exit(cms)
    assert res is None


def test_no_hardcoded_vision_model_name_remains_in_the_path():
    """Static guard: the dead constants must not appear in story_vision's source anymore."""
    import inspect
    src = inspect.getsource(story_vision)
    call_src = src[src.index("async def extract_product_from_image"):]
    assert "gemini-2.0-flash" not in call_src
    assert "gpt-4o-mini" not in call_src
    assert "PROVIDER_MODELS" not in call_src
