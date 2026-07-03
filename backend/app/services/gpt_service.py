"""
Multi-provider AI text generation with automatic fallback + token-usage logging.

Providers are tried in priority order; the first one that has a non-empty API
key AND returns a successful response wins. Every attempt (success or failure)
is logged to ai_usage_logs. If all providers fail, generate_message() returns a
plain Persian template so campaigns never block on the AI.
"""
import httpx
from datetime import datetime, timedelta
from app.config import settings
from app.database import AsyncSessionLocal

TIMEOUT = 15  # seconds per provider attempt

# Priority order — first configured + successful wins.
PROVIDERS = [
    {"name": "openai",   "model": "gpt-4o-mini",       "base": "https://api.openai.com/v1/chat/completions"},
    {"name": "deepseek", "model": "deepseek-chat",     "base": "https://api.deepseek.com/v1/chat/completions"},
    {"name": "gemini",   "model": "gemini-2.0-flash",  "base": None},
]

SYSTEM_PROMPT = """
تو یک دستیار فروش افراکالا هستی که پیام‌های واتس‌اپ کوتاه، صمیمی و حرفه‌ای فارسی می‌نویسی.
قوانین:
- پیام منحصربه‌فرد، شخصی، و با اسم مشتری
- لحن صمیمی اما حرفه‌ای
- حداکثر ۳ پاراگراف کوتاه
- بدون کلمات اضافه مثل "خلاصه" یا "در نتیجه"
- در پایان: "برای لغو عدد ۱۱ ارسال کنید"
"""

CATEGORIZE_SYSTEM = (
    "Categorize the Persian WhatsApp message into exactly one: "
    "price_inquiry, complaint, order, unsubscribe, other. "
    "Reply with only the category word."
)


def _key_for(name: str) -> str:
    return {
        "openai": settings.openai_api_key,
        "deepseek": settings.deepseek_api_key,
        "gemini": settings.gemini_api_key,
    }.get(name, "") or ""


def configured_providers() -> dict:
    """{provider: bool} — whether each provider has a non-empty key. No key values."""
    return {p["name"]: bool(_key_for(p["name"]).strip()) for p in PROVIDERS}


async def _log_usage(provider, model, pt, ct, tt, success, error_text=None):
    try:
        from app.models.ai_usage import AiUsageLog
        async with AsyncSessionLocal() as db:
            db.add(AiUsageLog(
                provider=provider, model=model,
                prompt_tokens=pt or 0, completion_tokens=ct or 0, total_tokens=tt or 0,
                success=success, error_text=(error_text[:2000] if error_text else None),
            ))
            await db.commit()
    except Exception as e:  # logging must never break generation
        print(f"[AI] usage log failed (non-fatal): {e}")


async def _call_openai_compatible(base: str, key: str, model: str, system: str, user: str,
                                  max_tokens: int, temperature: float):
    """OpenAI-compatible chat endpoint (OpenAI + DeepSeek). Returns (text, pt, ct, tt)."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(
            base,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        r.raise_for_status()
        d = r.json()
        text = (d["choices"][0]["message"]["content"] or "").strip()
        u = d.get("usage") or {}
        return text, u.get("prompt_tokens", 0), u.get("completion_tokens", 0), u.get("total_tokens", 0)


async def _call_gemini(key: str, model: str, system: str, user: str,
                       max_tokens: int, temperature: float):
    """Google Gemini generateContent. Returns (text, pt, ct, tt)."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(url, json=body)
        r.raise_for_status()
        d = r.json()
        cands = d.get("candidates") or []
        parts = (cands[0].get("content", {}).get("parts", []) if cands else [])
        text = "".join(p.get("text", "") for p in parts).strip()
        um = d.get("usageMetadata") or {}
        pt = um.get("promptTokenCount", 0)
        ct = um.get("candidatesTokenCount", 0)
        tt = um.get("totalTokenCount", pt + ct)
        return text, pt, ct, tt


async def _chat(system: str, user: str, max_tokens: int, temperature: float) -> str | None:
    """Try each configured provider in order; return text on first success, else None."""
    for p in PROVIDERS:
        name, model = p["name"], p["model"]
        key = _key_for(name).strip()
        if not key:
            continue
        try:
            if name == "gemini":
                text, pt, ct, tt = await _call_gemini(key, model, system, user, max_tokens, temperature)
            else:
                text, pt, ct, tt = await _call_openai_compatible(p["base"], key, model, system, user, max_tokens, temperature)
            if text:
                await _log_usage(name, model, pt, ct, tt, True, None)
                return text
            await _log_usage(name, model, pt, ct, tt, False, "empty response")
        except Exception as e:
            await _log_usage(name, model, 0, 0, 0, False, str(e))
            continue
    return None


def _fallback_message(first_name: str, products=None) -> str:
    name = (first_name or "").strip() or "دوست عزیز"
    lines = [f"سلام {name} جان! 🌟", "از افراکالا با پیشنهادهای ویژه در خدمت شما هستیم."]
    if products:
        lines.append("")
        for prod in products[:3]:
            price = f"{prod['price']:,} تومان" if prod.get("price") else "تماس بگیرید"
            lines.append(f"• {prod['name']}: {price}")
    lines += ["", "برای لغو عدد ۱۱ ارسال کنید"]
    return "\n".join(lines)


async def generate_message(first_name: str, last_name: str, gpt_prompt: str, products: list[dict] = None) -> str:
    products_text = ""
    if products:
        products_text = "\n\nمحصولات امروز افراکالا:\n"
        for p in products[:3]:
            price = f"{p['price']:,} تومان" if p.get("price") else "تماس بگیرید"
            products_text += f"• {p['name']}: {price}\n"

    user_msg = f"اسم مشتری: {first_name} {last_name}\n{gpt_prompt}{products_text}\nپیام واتس‌اپ فارسی بنویس:"

    text = await _chat(SYSTEM_PROMPT, user_msg, max_tokens=500, temperature=0.85)
    return text if text else _fallback_message(first_name, products)


async def categorize_message(text: str) -> str:
    """Auto-categorize incoming message: price_inquiry / complaint / order / unsubscribe / other"""
    result = await _chat(CATEGORIZE_SYSTEM, text or "", max_tokens=10, temperature=0.0)
    if not result:
        return "other"
    r = result.strip().lower()
    for cat in ("price_inquiry", "complaint", "order", "unsubscribe"):
        if cat in r:
            return cat
    return "other"


async def get_ai_stats() -> dict:
    """Per-provider usage over the last 24h: {provider: {calls, total_tokens, errors}}.
    Always includes all known providers (zero-filled) for stable dashboards."""
    from app.models.ai_usage import AiUsageLog
    from sqlalchemy import select, func, case

    out = {p["name"]: {"calls": 0, "total_tokens": 0, "errors": 0} for p in PROVIDERS}
    since = datetime.utcnow() - timedelta(hours=24)
    try:
        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                select(
                    AiUsageLog.provider,
                    func.count().label("calls"),
                    func.coalesce(func.sum(AiUsageLog.total_tokens), 0).label("tokens"),
                    func.coalesce(func.sum(case((AiUsageLog.success == False, 1), else_=0)), 0).label("errors"),
                )
                .where(AiUsageLog.used_at >= since)
                .group_by(AiUsageLog.provider)
            )
            for provider, calls, tokens, errors in rows.all():
                out.setdefault(provider, {"calls": 0, "total_tokens": 0, "errors": 0})
                out[provider] = {"calls": int(calls or 0), "total_tokens": int(tokens or 0), "errors": int(errors or 0)}
    except Exception as e:
        print(f"[AI] get_ai_stats failed: {e}")
    return out
