"""V40 PART 3 — extract a product name/description from a story IMAGE via the existing AI key pool.

Reuses the project's multi-provider key pool (ai_key_pool) and the same success/failure marking as
the text path (gpt_service._chat_via_pool), but sends the image to a VISION-capable model. Of the
three configured providers only openai and gemini accept image input — deepseek is text-only — so
this path tries just those two, in that order.

V42 — the model name is NO LONGER hardcoded. It is resolved per provider by
ai_vision_model_cache.resolve_vision_model, which discovers the provider's actually-available
vision models live and self-heals if the chosen one starts failing (so a model retirement like
gemini-2.0-flash can never again silently break this path). The V40 guard below is unchanged: if no
model can be resolved or every call fails, this returns None ("vision could not run"), never a false
empty result.

Returns {"text": <persian product description or None>, "provider": <name>} when a vision call
actually SUCCEEDED (text is None when the model saw no product), or None when vision could not run
at all — no working key, or every attempt failed. Callers MUST treat those two cases differently:
see `analyze_story_once`, which refuses to cache the "could not run" case.
Confidence is not reported by these chat/vision endpoints, so ai_confidence is left unset (the
archive/UI treat it as optional).
"""
from __future__ import annotations
import base64
import logging
import os

import httpx

logger = logging.getLogger("afrakala.story_vision")

TIMEOUT = 30  # seconds per attempt (vision responses are larger/slower than text)
MAX_ATTEMPTS = 4

# Only vision-capable providers, in preference order.
VISION_PROVIDERS = ["openai", "gemini"]

_SYSTEM = (
    "تو یک دستیار بینایی ماشین هستی که تصویر یک استوری واتساپ تبلیغاتی را می‌بینی. "
    "فقط نام یا توضیح کوتاه محصولی که در تصویر تبلیغ شده را به فارسی بده "
    "(مثلاً «کولر گازی اسپلیت ۱۸۰۰۰ گری» یا «یخچال ساید بای ساید سامسونگ»). "
    "اگر محصول مشخصی در تصویر نیست، فقط بنویس «نامشخص». "
    "هیچ توضیح اضافه، جمله، شماره تلفن یا لینک ننویس — فقط نام/نوع محصول، کوتاه."
)
_USER = "این تصویر استوری چه محصولی را تبلیغ می‌کند؟ فقط نام کوتاه محصول را بده."


def _mime_for(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}.get(ext, "image/jpeg")


def _read_b64(path: str) -> tuple[str, str]:
    with open(path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode("ascii"), _mime_for(path)


async def _call_openai_vision(key: str, model: str, b64: str, mime: str) -> str:
    from app.services.gpt_service import PROVIDER_BASE
    base = PROVIDER_BASE.get("openai") or "https://api.openai.com/v1/chat/completions"
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(
            base,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": [
                        {"type": "text", "text": _USER},
                        {"type": "image_url",
                         "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    ]},
                ],
                "max_tokens": 60,
                "temperature": 0.2,
            },
        )
        r.raise_for_status()
        d = r.json()
        return (d["choices"][0]["message"]["content"] or "").strip()


async def _call_gemini_vision(key: str, model: str, b64: str, mime: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body = {
        "systemInstruction": {"parts": [{"text": _SYSTEM}]},
        "contents": [{"role": "user", "parts": [
            {"text": _USER},
            {"inline_data": {"mime_type": mime, "data": b64}},
        ]}],
        "generationConfig": {"maxOutputTokens": 60, "temperature": 0.2},
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(url, json=body)
        r.raise_for_status()
        d = r.json()
        cands = d.get("candidates") or []
        parts = (cands[0].get("content", {}).get("parts", []) if cands else [])
        return "".join(p.get("text", "") for p in parts).strip()


def _clean(text: str) -> str | None:
    t = (text or "").strip().strip("«».:،؛-").strip()
    if not t or t == "نامشخص" or "نامشخص" in t and len(t) <= len("نامشخص") + 2:
        return None
    return t[:200]


async def extract_product_from_image(image_path: str) -> dict | None:
    """Vision-extract a product description from a local story image. None if unavailable/unmatched.
    Tries vision-capable pool keys (openai→gemini), marking success/failure like the text path."""
    if not image_path or not os.path.exists(image_path):
        return None
    try:
        b64, mime = _read_b64(image_path)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("read image failed (%s): %s", image_path, e)
        return None

    from app.services.ai_key_pool import get_working_key, mark_success, mark_failure
    from app.services.ai_vision_model_cache import (
        resolve_vision_model, record_success, record_failure)
    tried: set = set()
    for _ in range(MAX_ATTEMPTS):
        key_obj = None
        for prov in VISION_PROVIDERS:
            k = await get_working_key(prov)
            if k and k.id not in tried:
                key_obj = k
                break
        if not key_obj:
            break
        tried.add(key_obj.id)
        provider = key_obj.provider
        # V42 — resolve the model live (cached) instead of a hardcoded name. None means this
        # provider currently has NO usable vision model (the dead-Gemini case): skip it and try the
        # next key/provider. Don't mark the KEY bad — the key may be fine; the model catalog isn't.
        resolved = await resolve_vision_model(provider, key_obj.api_key)
        model = resolved.get("model")
        if not model:
            logger.warning("no vision model available for %s — skipping (%s)",
                           provider, resolved.get("discovery_error"))
            continue
        try:
            if provider == "gemini":
                raw = await _call_gemini_vision(key_obj.api_key, model, b64, mime)
            else:
                raw = await _call_openai_vision(key_obj.api_key, model, b64, mime)
            if raw:
                await mark_success(key_obj.id)
                record_success(provider, model)     # V42 — clear the model's failure streak
                # A call that SUCCEEDED but saw no product returns {"text": None} — deliberately
                # distinct from returning None, which means vision could not run at all. The caller
                # relies on that difference: caching "could not run" as if it were "saw nothing"
                # would be indistinguishable from a real empty result and would lock the story out
                # of any future re-analysis.
                return {"text": _clean(raw), "provider": provider}
            await mark_failure(key_obj.id, "empty vision response")
            record_failure(provider, model)          # V42 — count toward self-heal re-discovery
        except Exception as e:
            msg = str(e)
            low = msg.lower()
            await mark_failure(key_obj.id, msg,
                               is_rate_limit=("429" in msg or "rate" in low or "quota" in low),
                               is_invalid=("401" in msg or "invalid" in low or "unauthorized" in low))
            record_failure(provider, model)          # V42 — a failing model heals itself over time
            continue
    return None
