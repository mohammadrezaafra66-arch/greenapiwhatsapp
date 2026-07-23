"""V42 PART 2 — live model discovery per provider.

Mocks each provider's list-models HTTP response with its REAL documented shape and confirms the
parser extracts ids (+ Gemini capability methods), and that auth/network/parse failures come back as
a clear non-crashing result rather than an exception.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import ai_model_discovery
from app.services.ai_model_discovery import discover_available_models


# ── realistic response bodies ──────────────────────────────────────────────────────────────────
# OpenAI GET /v1/models — {"object":"list","data":[{"id":...,"object":"model",...}]}
OPENAI_BODY = {
    "object": "list",
    "data": [
        {"id": "gpt-4o", "object": "model", "created": 1715367049, "owned_by": "system"},
        {"id": "gpt-4o-mini", "object": "model", "created": 1721172741, "owned_by": "system"},
        {"id": "o1-mini", "object": "model", "created": 1725649008, "owned_by": "system"},
        {"id": "text-embedding-3-small", "object": "model", "created": 1705948997, "owned_by": "system"},
        {"id": "whisper-1", "object": "model", "created": 1677532384, "owned_by": "openai-internal"},
    ],
}

# Gemini GET /v1beta/models?key= — {"models":[{name, baseModelId, supportedGenerationMethods,...}]}
GEMINI_BODY = {
    "models": [
        {"name": "models/gemini-1.5-flash", "baseModelId": "gemini-1.5-flash", "version": "001",
         "displayName": "Gemini 1.5 Flash",
         "supportedGenerationMethods": ["generateContent", "countTokens"]},
        {"name": "models/gemini-2.5-flash", "baseModelId": "gemini-2.5-flash", "version": "001",
         "supportedGenerationMethods": ["generateContent", "countTokens"]},
        {"name": "models/text-embedding-004", "baseModelId": "text-embedding-004",
         "supportedGenerationMethods": ["embedContent"]},
    ],
    "nextPageToken": "abc",
}


def _fake_client(*, json_body=None, status_code=200, raises=None):
    """MagicMock standing in for httpx.AsyncClient() as an async CM, whose .get returns a response."""
    client = MagicMock()
    if raises is not None:
        client.get = AsyncMock(side_effect=raises)
    else:
        resp = MagicMock()
        resp.status_code = status_code
        resp.json = MagicMock(return_value=json_body)
        client.get = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


# ── OpenAI ──────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_openai_parses_all_model_ids():
    with patch.object(ai_model_discovery.httpx, "AsyncClient",
                      return_value=_fake_client(json_body=OPENAI_BODY)):
        res = await discover_available_models("openai", "sk-test")
    assert res["ok"] is True
    ids = [m["id"] for m in res["models"]]
    assert ids == ["gpt-4o", "gpt-4o-mini", "o1-mini", "text-embedding-3-small", "whisper-1"]
    assert all(m["methods"] == [] for m in res["models"])   # OpenAI list has no capability metadata


@pytest.mark.asyncio
async def test_openai_sends_bearer_auth():
    fake = _fake_client(json_body=OPENAI_BODY)
    with patch.object(ai_model_discovery.httpx, "AsyncClient", return_value=fake):
        await discover_available_models("openai", "sk-secret")
    _args, kwargs = fake.get.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer sk-secret"


# ── Gemini ────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_gemini_parses_ids_and_capability_methods():
    with patch.object(ai_model_discovery.httpx, "AsyncClient",
                      return_value=_fake_client(json_body=GEMINI_BODY)):
        res = await discover_available_models("gemini", "AIza-test")
    assert res["ok"] is True
    by_id = {m["id"]: m for m in res["models"]}
    assert set(by_id) == {"gemini-1.5-flash", "gemini-2.5-flash", "text-embedding-004"}
    # capability signal preserved verbatim for PART 3 to filter on
    assert "generateContent" in by_id["gemini-1.5-flash"]["methods"]
    assert by_id["text-embedding-004"]["methods"] == ["embedContent"]


@pytest.mark.asyncio
async def test_gemini_strips_models_prefix_when_base_id_absent():
    body = {"models": [{"name": "models/gemini-3.0-pro",
                        "supportedGenerationMethods": ["generateContent"]}]}
    with patch.object(ai_model_discovery.httpx, "AsyncClient",
                      return_value=_fake_client(json_body=body)):
        res = await discover_available_models("gemini", "AIza-test")
    assert res["models"][0]["id"] == "gemini-3.0-pro"


@pytest.mark.asyncio
async def test_gemini_passes_key_as_query_param():
    fake = _fake_client(json_body=GEMINI_BODY)
    with patch.object(ai_model_discovery.httpx, "AsyncClient", return_value=fake):
        await discover_available_models("gemini", "AIza-secret")
    _args, kwargs = fake.get.call_args
    assert kwargs["params"] == {"key": "AIza-secret"}


# ── failure modes: clear, non-crashing results ──────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_auth_failure_is_reported_not_raised():
    with patch.object(ai_model_discovery.httpx, "AsyncClient",
                      return_value=_fake_client(status_code=401, json_body={})):
        res = await discover_available_models("openai", "sk-bad")
    assert res["ok"] is False and res["error_kind"] == "auth"
    assert res["models"] == []


@pytest.mark.asyncio
async def test_403_is_auth():
    with patch.object(ai_model_discovery.httpx, "AsyncClient",
                      return_value=_fake_client(status_code=403, json_body={})):
        res = await discover_available_models("gemini", "AIza-unfunded")
    assert res["ok"] is False and res["error_kind"] == "auth"


@pytest.mark.asyncio
async def test_other_http_error_is_reported():
    with patch.object(ai_model_discovery.httpx, "AsyncClient",
                      return_value=_fake_client(status_code=500, json_body={})):
        res = await discover_available_models("openai", "sk-test")
    assert res["ok"] is False and res["error_kind"] == "http"


@pytest.mark.asyncio
async def test_network_error_is_reported_not_raised():
    with patch.object(ai_model_discovery.httpx, "AsyncClient",
                      return_value=_fake_client(raises=httpx_connect_error())):
        res = await discover_available_models("gemini", "AIza-test")
    assert res["ok"] is False and res["error_kind"] == "network"


@pytest.mark.asyncio
async def test_empty_model_list_is_not_ok():
    with patch.object(ai_model_discovery.httpx, "AsyncClient",
                      return_value=_fake_client(json_body={"data": []})):
        res = await discover_available_models("openai", "sk-test")
    assert res["ok"] is False and res["error_kind"] == "parse"


@pytest.mark.asyncio
async def test_missing_key_short_circuits_to_auth():
    res = await discover_available_models("openai", "")
    assert res["ok"] is False and res["error_kind"] == "auth"


@pytest.mark.asyncio
async def test_unknown_provider_is_unsupported():
    res = await discover_available_models("deepseek", "sk-test")
    assert res["ok"] is False and res["error_kind"] == "unsupported"


def httpx_connect_error():
    import httpx
    return httpx.ConnectError("connection refused")
