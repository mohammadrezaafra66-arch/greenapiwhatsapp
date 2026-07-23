"""V42 — self-healing AI model discovery.

The V40 vision pipeline called a HARDCODED Gemini model name ("gemini-2.0-flash") that Google
discontinued, so every call failed silently forever (0/537) with no way to notice the model was
gone. Instead of swapping in another name that will also die someday, this module asks each provider
which models it ACTUALLY serves right now, via that provider's own live "list models" API using the
real configured key.

PART 2 owns discovery only — the raw "what models exist" question. Vision-capability filtering and
preference (PART 3), caching + self-heal (PART 4), and wiring into the vision path (PART 5) build on
top of this. Nothing here hardcodes a model name.

Real endpoints and response shapes (verified against each provider's live API docs):

  OpenAI   GET https://api.openai.com/v1/models   (Authorization: Bearer <key>)
    {"object": "list", "data": [{"id": "gpt-4o-mini", "object": "model", ...}, ...]}

  Gemini   GET https://generativelanguage.googleapis.com/v1beta/models?key=<key>
    {"models": [{"name": "models/gemini-1.5-flash", "baseModelId": "gemini-1.5-flash",
                 "supportedGenerationMethods": ["generateContent", "countTokens"], ...}, ...],
     "nextPageToken": "..."}
    The per-model capability signal is `supportedGenerationMethods`: content models list
    "generateContent"; embedding-only models list "embedContent" instead. PART 3 uses that.
"""
from __future__ import annotations
import logging

import httpx

logger = logging.getLogger("afrakala.ai_model_discovery")

TIMEOUT = 15  # seconds for a list-models call

OPENAI_MODELS_URL = "https://api.openai.com/v1/models"
GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# Providers that expose a live list-models API this module knows how to read. DeepSeek is text-only
# and out of the vision scope, so it is intentionally not discoverable here.
DISCOVERABLE_PROVIDERS = ("openai", "gemini")


def _result(provider, *, ok, models=None, error=None, error_kind=None) -> dict:
    """The single, stable shape every discovery returns — never raises, always this dict.

    error_kind is one of: auth (bad/expired key), network (connection/timeout), http (other non-2xx),
    parse (unexpected body), unsupported (provider has no known list-models API), or None on success.
    """
    return {"provider": provider, "ok": ok, "models": models or [], "error": error,
            "error_kind": error_kind}


def _classify_http_status(status: int) -> tuple[str, str]:
    """(error_kind, message) for a non-2xx list-models status."""
    if status in (401, 403):
        return "auth", f"authentication failed (HTTP {status}) — key invalid, expired, or unfunded"
    return "http", f"list-models returned HTTP {status}"


def _parse_openai(body: dict) -> list[dict]:
    """OpenAI: data[].id. No per-model capability metadata is exposed here, so `methods` is empty and
    PART 3 decides OpenAI vision-capability by model-family rule instead."""
    out = []
    for m in (body.get("data") or []):
        mid = (m.get("id") or "").strip()
        if mid:
            out.append({"id": mid, "methods": []})
    return out


def _strip_models_prefix(name: str) -> str:
    """Gemini ids come as "models/gemini-1.5-flash"; the generateContent URL wants the bare id."""
    name = (name or "").strip()
    return name[len("models/"):] if name.startswith("models/") else name


def _parse_gemini(body: dict) -> list[dict]:
    """Gemini: models[] carrying baseModelId/name + supportedGenerationMethods (the capability
    signal PART 3 filters on)."""
    out = []
    for m in (body.get("models") or []):
        mid = (m.get("baseModelId") or "").strip() or _strip_models_prefix(m.get("name", ""))
        if not mid:
            continue
        methods = [str(x) for x in (m.get("supportedGenerationMethods") or [])]
        out.append({"id": mid, "methods": methods})
    return out


async def discover_available_models(provider: str, api_key: str, *, timeout: int = TIMEOUT) -> dict:
    """Call `provider`'s live list-models API with `api_key` and return the models it actually serves.

    Returns the stable `_result` dict. NEVER raises: auth failures, network errors, unexpected bodies
    and unknown providers all come back as ok=False with a clear error_kind, so a caller can cleanly
    skip a provider exactly like the dead-Gemini case rather than crashing.
    """
    provider = (provider or "").strip().lower()
    if not api_key or not str(api_key).strip():
        return _result(provider, ok=False, error="no api key provided", error_kind="auth")

    if provider == "openai":
        url, headers, params, parse = OPENAI_MODELS_URL, {"Authorization": f"Bearer {api_key}"}, None, _parse_openai
    elif provider == "gemini":
        url, headers, params, parse = GEMINI_MODELS_URL, None, {"key": api_key}, _parse_gemini
    else:
        return _result(provider, ok=False,
                       error=f"no known list-models API for provider '{provider}'",
                       error_kind="unsupported")

    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get(url, headers=headers, params=params)
    except Exception as e:  # httpx transport/timeout errors
        logger.warning("model discovery network error (%s): %s", provider, e)
        return _result(provider, ok=False, error=f"network error: {e}", error_kind="network")

    status = getattr(r, "status_code", 200)
    if status >= 400:
        kind, msg = _classify_http_status(status)
        logger.warning("model discovery failed (%s): %s", provider, msg)
        return _result(provider, ok=False, error=msg, error_kind=kind)

    try:
        body = r.json()
        models = parse(body if isinstance(body, dict) else {})
    except Exception as e:
        logger.warning("model discovery parse error (%s): %s", provider, e)
        return _result(provider, ok=False, error=f"could not parse response: {e}", error_kind="parse")

    if not models:
        # A 2xx with no usable models is not a crash, but it IS a "could not discover" for the caller.
        return _result(provider, ok=False, error="no models returned", error_kind="parse")

    logger.info("discovered %d models for %s", len(models), provider)
    return _result(provider, ok=True, models=models)
