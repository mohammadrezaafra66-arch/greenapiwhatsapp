"""V42 PART 3 — decide which discovered models can do vision, and pick the best (cheapest) one.

Pure functions over the model lists that PART 2's discovery returns — NO HTTP, no caching. Split out
so the capability RULES live in one small, obvious block that a future model rename can be updated in
without touching discovery (PART 2) or caching/self-heal (PART 4).

The rules are grounded in what the providers' live list-models APIs actually return today:

  Gemini exposes a real capability signal — supportedGenerationMethods — but "generateContent" alone
  is not enough: the same method is served by TTS models (`*-tts`, audio out), image-GENERATION
  models (`*-image`, e.g. "nano banana"), and the computer-use preview, none of which are the
  general image-UNDERSTANDING model we want. So: a real generateContent gemini-* model, minus those
  non-understanding families.

  OpenAI's model list exposes NO vision flag, so we match its documented vision-capable families
  (gpt-4o / gpt-4.1 / gpt-4-turbo / chatgpt-4o / gpt-5), minus the audio/transcribe/tts/search/
  realtime variants that share the family prefix but do not take image input. o1/o3/o4 are
  deliberately excluded — o1-mini in particular is text-only, and "prefer mini" would mis-pick it.

Preference: cheapest capable tier first (mini / flash-lite / lite / nano), preferring a stable,
floating alias over a dated or preview snapshot, so the pick is both cheap and auto-updating.
"""
from __future__ import annotations
import re

# ── VISION-CAPABILITY RULES — the one block to edit when a provider renames things ──────────────
# Gemini: the generateContent capability comes from the live API; these NAME families are the ones
# that have generateContent but are NOT image-understanding models, so they're excluded.
_GEMINI_EXCLUDE = ("tts", "image", "computer-use", "embedding", "embed", "aqa", "imagen")

# OpenAI: documented vision-capable families (substring match on the model id)…
_OPENAI_VISION_FAMILIES = ("gpt-4o", "gpt-4.1", "gpt-4-turbo", "chatgpt-4o", "gpt-5")
# …minus these variants that carry a vision-family prefix but do not accept image input.
_OPENAI_EXCLUDE = ("transcribe", "tts", "audio", "realtime", "search", "moderation",
                   "embedding", "instruct", "whisper", "dall-e", "image", "codex")

# Cheapest-first tier keywords per provider. First match = most preferred (lowest cost).
_PREFERRED_TIERS = {
    "openai": ("mini", "nano"),
    "gemini": ("flash-lite", "flash-8b", "lite", "flash"),
}
# ── end rules block ─────────────────────────────────────────────────────────────────────────────


def _has_generate_content(model: dict) -> bool:
    """Gemini's real capability signal. If methods are absent (some payloads omit them) fall back to
    the name rule rather than wrongly rejecting everything."""
    methods = model.get("methods") or []
    return (not methods) or ("generateContent" in methods)


def is_vision_model(provider: str, model: dict) -> bool:
    """True if this discovered model can accept image input, per the isolated rules above."""
    provider = (provider or "").strip().lower()
    mid = (model.get("id") or "").strip().lower()
    if not mid:
        return False
    if provider == "gemini":
        if not mid.startswith("gemini-"):
            return False                       # gemma / lyria / nano-banana / deep-research → skip
        if any(x in mid for x in _GEMINI_EXCLUDE):
            return False                       # tts / image-gen / computer-use / embedding
        return _has_generate_content(model)
    if provider == "openai":
        if not any(fam in mid for fam in _OPENAI_VISION_FAMILIES):
            return False
        if any(x in mid for x in _OPENAI_EXCLUDE):
            return False
        return True
    return False


def _sort_key(provider: str, mid: str):
    """Cheapest, most-stable first. Tuple: (tier, preview?, not-latest?, dated?, id)."""
    low = mid.lower()
    tiers = _PREFERRED_TIERS.get(provider, ())
    tier = next((i for i, t in enumerate(tiers) if t in low), len(tiers))
    preview = 1 if ("preview" in low or "exp" in low or "experimental" in low) else 0
    not_latest = 0 if low.endswith("latest") else 1     # prefer a floating "…-latest" alias
    dated = 1 if re.search(r"-\d{4}", low) else 0        # prefer a floating name over a dated snapshot
    return (tier, preview, not_latest, dated, low)


def select_vision_model(provider: str, models: list[dict]) -> dict:
    """Choose the preferred vision model from a discovered list.

    Returns {"ok", "provider", "model", "candidates", "reason"}. ok=False with model=None when the
    provider has NO vision-capable model — so the caller skips it cleanly (the dead-Gemini case),
    never crashes or guesses.
    """
    provider = (provider or "").strip().lower()
    candidates = sorted(
        (m["id"] for m in (models or []) if is_vision_model(provider, m)),
        key=lambda mid: _sort_key(provider, mid),
    )
    if not candidates:
        return {"ok": False, "provider": provider, "model": None, "candidates": [],
                "reason": "no vision-capable model available"}
    return {"ok": True, "provider": provider, "model": candidates[0],
            "candidates": candidates, "reason": "selected cheapest available vision-capable model"}
