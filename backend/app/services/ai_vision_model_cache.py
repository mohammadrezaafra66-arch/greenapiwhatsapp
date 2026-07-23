"""V42 PART 4 — cache the resolved vision model per provider, and self-heal when it starts failing.

`resolve_vision_model` is the single entry point the vision path (PART 5) calls to learn which model
to use. It caches the discovered/selected model per provider with a timestamp so normal vision calls
do NOT hit the list-models endpoint every time — at most once per TTL.

Self-healing: the vision path already knows when a call succeeds or fails (the V40 signal — the same
place it marks the key). It forwards that verdict here via `record_success` / `record_failure`; this
module does NOT introduce a second failure detector. After FAILURE_THRESHOLD consecutive failures on
the currently-cached model, the cache forces a fresh discovery + re-selection on the next resolve, so
a provider-side model retirement (exactly the gemini-2.0-flash case) heals itself with no code change.
Every switch is logged old→new for auditability.

Process-global in-memory, matching this project's other in-memory caches (peer_pacer). Each worker
process re-discovers at most once per TTL independently; `reset()` exists for test isolation.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta

from app.services.ai_model_discovery import discover_available_models
from app.services.ai_vision_select import select_vision_model

logger = logging.getLogger("afrakala.ai_vision_model_cache")

# Re-validate the discovered model at most this often under normal operation.
TTL = timedelta(hours=6)
# Consecutive failures on the cached model before we assume it may be gone and re-discover.
FAILURE_THRESHOLD = 3

# provider -> {"model": str|None, "at": datetime, "candidates": [str], "failures": int,
#              "force": bool}
_cache: dict[str, dict] = {}


def reset() -> None:
    """Clear the cache — test isolation only (production never calls this)."""
    _cache.clear()


def peek(provider: str) -> dict | None:
    """Current cache entry for a provider, or None. Read-only; for diagnostics/tests."""
    return _cache.get((provider or "").strip().lower())


def _fresh(entry: dict | None, now: datetime) -> bool:
    if not entry or not entry.get("model") or entry.get("force"):
        return False
    return (now - entry["at"]) < TTL


async def resolve_vision_model(provider: str, api_key: str, *, now: datetime | None = None,
                               force: bool = False) -> dict:
    """Return the vision model to use for `provider`, discovering + selecting only when needed.

    Result: {"model": str|None, "from_cache": bool, "candidates": [str],
             "changed_from": str|None, "discovery_error": str|None}.
    model is None only when the provider genuinely has no usable vision model AND we have no prior
    working model to fall back on — the caller then skips the provider (the dead-Gemini case).
    """
    provider = (provider or "").strip().lower()
    now = now or datetime.utcnow()
    entry = _cache.get(provider)

    if not force and _fresh(entry, now):
        return {"model": entry["model"], "from_cache": True, "candidates": entry["candidates"],
                "changed_from": None, "discovery_error": None}

    disc = await discover_available_models(provider, api_key)
    old = entry.get("model") if entry else None

    if not disc["ok"]:
        # A transient list-models failure must not throw away a model that was working. Keep the
        # prior model (if any) rather than going dark on a blip; only report None if we have nothing.
        if old:
            logger.warning("vision re-discovery failed for %s (%s); keeping cached model %s",
                           provider, disc["error_kind"], old)
            entry["at"] = now            # back off so we don't retry list-models on every call
            entry["force"] = False
            return {"model": old, "from_cache": True, "candidates": entry.get("candidates", []),
                    "changed_from": None, "discovery_error": disc["error_kind"]}
        _cache[provider] = {"model": None, "at": now, "candidates": [], "failures": 0, "force": False}
        return {"model": None, "from_cache": False, "candidates": [],
                "changed_from": None, "discovery_error": disc["error_kind"]}

    sel = select_vision_model(provider, disc["models"])
    new = sel["model"]
    changed = old if (old and old != new) else None
    if changed:
        logger.info("vision model for %s re-discovered: %s -> %s", provider, old, new)
    elif old is None and new:
        logger.info("vision model for %s discovered: %s", provider, new)

    _cache[provider] = {"model": new, "at": now, "candidates": sel["candidates"],
                        "failures": 0, "force": False}
    return {"model": new, "from_cache": False, "candidates": sel["candidates"],
            "changed_from": changed, "discovery_error": None}


def record_success(provider: str, model: str) -> None:
    """A vision call using `model` succeeded — clear the failure streak (reuses the V40 verdict)."""
    entry = _cache.get((provider or "").strip().lower())
    if entry and entry.get("model") == model:
        entry["failures"] = 0
        entry["force"] = False


def record_failure(provider: str, model: str) -> None:
    """A vision call using `model` failed (the V40 verdict). After FAILURE_THRESHOLD in a row, arm a
    forced re-discovery so the next resolve re-selects instead of retrying a possibly-dead model."""
    provider = (provider or "").strip().lower()
    entry = _cache.get(provider)
    if not entry or entry.get("model") != model:
        return                                   # not the model we're tracking — ignore
    entry["failures"] = entry.get("failures", 0) + 1
    if entry["failures"] >= FAILURE_THRESHOLD and not entry.get("force"):
        logger.warning("vision model %s for %s failed %d× consecutively — forcing re-discovery",
                       model, provider, entry["failures"])
        entry["force"] = True
