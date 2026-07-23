"""V42 PART 4 — cache the selection + automatic re-discovery on repeated failure.

Proves: a fresh cached model is reused WITHOUT re-calling list-models; the TTL forces re-validation;
FAILURE_THRESHOLD consecutive failures trigger a fresh discovery that switches to a different valid
model (logged old→new) or reports none if nothing qualifies; a transient discovery blip keeps the
prior working model instead of going dark.
"""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.services import ai_vision_model_cache as cache
from app.services.ai_vision_model_cache import (
    resolve_vision_model, record_success, record_failure, reset, peek, TTL, FAILURE_THRESHOLD,
)

NOW = datetime(2026, 7, 23, 12, 0, 0)


@pytest.fixture(autouse=True)
def _clean():
    reset()
    yield
    reset()


def _disc(models, ok=True, error_kind=None):
    """Fake discover_available_models result."""
    async def _fn(provider, api_key, **kw):
        return {"provider": provider, "ok": ok, "models": models,
                "error": None if ok else "boom", "error_kind": error_kind}
    return _fn


def _gemini(*ids):
    return [{"id": i, "methods": ["generateContent"]} for i in ids]


# ── caching: discover once, then serve from cache ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_first_resolve_discovers_then_cache_is_reused():
    calls = {"n": 0}
    async def _counted(provider, api_key, **kw):
        calls["n"] += 1
        return {"provider": provider, "ok": True, "models": _gemini("gemini-2.5-flash-lite"),
                "error": None, "error_kind": None}

    with patch.object(cache, "discover_available_models", _counted):
        r1 = await resolve_vision_model("gemini", "k", now=NOW)
        r2 = await resolve_vision_model("gemini", "k", now=NOW + timedelta(minutes=5))
        r3 = await resolve_vision_model("gemini", "k", now=NOW + timedelta(hours=1))

    assert r1["model"] == "gemini-2.5-flash-lite" and r1["from_cache"] is False
    assert r2["from_cache"] is True and r3["from_cache"] is True
    assert calls["n"] == 1, "list-models must be called once, not per request"


@pytest.mark.asyncio
async def test_ttl_expiry_triggers_revalidation():
    with patch.object(cache, "discover_available_models",
                      _disc(_gemini("gemini-2.5-flash-lite"))):
        await resolve_vision_model("gemini", "k", now=NOW)
        after_ttl = NOW + TTL + timedelta(minutes=1)
        r = await resolve_vision_model("gemini", "k", now=after_ttl)
    assert r["from_cache"] is False, "past the TTL the model must be re-validated"


# ── self-heal on repeated failure ──────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_repeated_failures_force_rediscovery_and_switch(caplog):
    # First discovery yields the (soon-to-fail) model; second yields a healthy replacement.
    seq = [_gemini("gemini-old-flash"), _gemini("gemini-new-flash-lite")]
    async def _seq(provider, api_key, **kw):
        models = seq[min(len(seq) - 1, _seq.i)]
        _seq.i += 1
        return {"provider": provider, "ok": True, "models": models, "error": None, "error_kind": None}
    _seq.i = 0

    with patch.object(cache, "discover_available_models", _seq):
        first = await resolve_vision_model("gemini", "k", now=NOW)
        assert first["model"] == "gemini-old-flash"

        # Fewer than threshold: cache still serves the old model, no re-discovery.
        for _ in range(FAILURE_THRESHOLD - 1):
            record_failure("gemini", "gemini-old-flash")
        mid = await resolve_vision_model("gemini", "k", now=NOW + timedelta(minutes=1))
        assert mid["model"] == "gemini-old-flash" and mid["from_cache"] is True

        # Crossing the threshold arms a forced re-discovery.
        record_failure("gemini", "gemini-old-flash")
        assert peek("gemini")["force"] is True

        with caplog.at_level("INFO"):
            healed = await resolve_vision_model("gemini", "k", now=NOW + timedelta(minutes=2))

    assert healed["model"] == "gemini-new-flash-lite"
    assert healed["changed_from"] == "gemini-old-flash"
    assert healed["from_cache"] is False
    assert any("gemini-old-flash" in m and "gemini-new-flash-lite" in m for m in caplog.messages)


@pytest.mark.asyncio
async def test_success_resets_failure_streak():
    with patch.object(cache, "discover_available_models", _disc(_gemini("gemini-2.5-flash-lite"))):
        await resolve_vision_model("gemini", "k", now=NOW)
    record_failure("gemini", "gemini-2.5-flash-lite")
    record_failure("gemini", "gemini-2.5-flash-lite")
    record_success("gemini", "gemini-2.5-flash-lite")     # streak broken
    record_failure("gemini", "gemini-2.5-flash-lite")
    assert peek("gemini")["force"] is False, "a success in between must reset the streak"


@pytest.mark.asyncio
async def test_failure_on_untracked_model_is_ignored():
    with patch.object(cache, "discover_available_models", _disc(_gemini("gemini-2.5-flash-lite"))):
        await resolve_vision_model("gemini", "k", now=NOW)
    for _ in range(FAILURE_THRESHOLD + 2):
        record_failure("gemini", "some-other-model")      # not the cached one
    assert peek("gemini")["force"] is False and peek("gemini")["failures"] == 0


@pytest.mark.asyncio
async def test_rediscovery_to_no_vision_model_reports_none():
    seq = [_gemini("gemini-old-flash"), []]     # second discovery returns nothing usable
    async def _seq(provider, api_key, **kw):
        models = seq[min(len(seq) - 1, _seq.i)]
        _seq.i += 1
        return {"provider": provider, "ok": True, "models": models, "error": None, "error_kind": None}
    _seq.i = 0
    with patch.object(cache, "discover_available_models", _seq):
        await resolve_vision_model("gemini", "k", now=NOW)
        healed = await resolve_vision_model("gemini", "k", now=NOW, force=True)
    assert healed["model"] is None, "no vision model available → clear None, not a crash"


# ── resilience: a transient list-models blip keeps the working model ───────────────────────────
@pytest.mark.asyncio
async def test_discovery_blip_keeps_prior_model():
    async def _first(provider, api_key, **kw):
        return {"provider": provider, "ok": True, "models": _gemini("gemini-2.5-flash-lite"),
                "error": None, "error_kind": None}
    with patch.object(cache, "discover_available_models", _first):
        await resolve_vision_model("gemini", "k", now=NOW)

    with patch.object(cache, "discover_available_models",
                      _disc([], ok=False, error_kind="network")):
        r = await resolve_vision_model("gemini", "k", now=NOW + TTL + timedelta(minutes=1))

    assert r["model"] == "gemini-2.5-flash-lite", "a transient blip must not lose a working model"
    assert r["discovery_error"] == "network"


@pytest.mark.asyncio
async def test_no_prior_model_and_discovery_fails_returns_none():
    with patch.object(cache, "discover_available_models",
                      _disc([], ok=False, error_kind="auth")):
        r = await resolve_vision_model("openai", "bad-key", now=NOW)
    assert r["model"] is None and r["discovery_error"] == "auth"
