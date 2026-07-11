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

# V12 — provider → (model, base endpoint). Single source of truth used by both the
# env-key path and the DB key-pool path.
PROVIDER_MODELS = {p["name"]: p["model"] for p in PROVIDERS}
PROVIDER_BASE = {p["name"]: p["base"] for p in PROVIDERS}

# Order the key-pool tries providers in (any configured key works; this is a preference).
PROVIDER_ORDER = ["openai", "deepseek", "gemini"]
POOL_MAX_ATTEMPTS = 6  # try up to this many different keys before giving up

SYSTEM_PROMPT = """
تو یک دستیار فروش افراکالا هستی که پیام‌های واتس‌اپ کوتاه، صمیمی و حرفه‌ای فارسی می‌نویسی.
قوانین:
- پیام منحصربه‌فرد، شخصی، و با اسم مشتری
- لحن صمیمی اما حرفه‌ای
- حداکثر ۳ پاراگراف کوتاه
- بدون کلمات اضافه مثل "خلاصه" یا "در نتیجه"
"""

# Default unsubscribe line (opt-out). Kept configurable per campaign.
DEFAULT_OPT_OUT = "برای لغو عدد ۱۱ ارسال کنید"


def _is_optout_line(line: str) -> bool:
    """Heuristic: is this line an opt-out/unsubscribe instruction (to strip/dedupe)?"""
    l = line.strip()
    if not l:
        return False
    if "لغو اشتراک" in l or "لغو عدد" in l:
        return True
    if "لغو" in l and ("۱۱" in l or "11" in l or "ارسال کنید" in l):
        return True
    return False


def _apply_opening(text: str, opening_mode: str, opening_line: str | None) -> str:
    """Enforce a fixed/random opening line even if the model ignored the instruction."""
    if opening_mode in ("fixed", "random") and opening_line:
        ol = opening_line.strip()
        if ol and not text.strip().startswith(ol):
            return f"{ol}\n\n{text.strip()}"
    return text


def _apply_opt_out(text: str, include_opt_out: bool, opt_text: str | None) -> str:
    """Strip any model-written opt-out line, then append the exact configured one
    (or nothing if disabled). Deterministic — guarantees no dupes and exact text.
    Strips both heuristic opt-out lines AND any line equal to the target text (so a
    custom opt-out without the word 'لغو' isn't duplicated)."""
    target = (opt_text or DEFAULT_OPT_OUT).strip()

    def _strip(line: str) -> bool:
        ls = line.strip()
        return _is_optout_line(ls) or (bool(target) and ls == target)

    body = "\n".join(l for l in text.split("\n") if not _strip(l)).rstrip()
    if include_opt_out:
        return body + "\n\n" + target
    return body

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
        # Extract token usage from the response.usage object (OpenAI/DeepSeek).
        u = d.get("usage") or {}
        pt = int(u.get("prompt_tokens", 0) or 0)
        ct = int(u.get("completion_tokens", 0) or 0)
        tt = int(u.get("total_tokens", 0) or 0) or (pt + ct)
        return text, pt, ct, tt


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


async def _call_provider(provider: str, api_key: str, user: str,
                         system: str = "You are a helpful assistant.",
                         max_tokens: int = 500, temperature: float = 0.85):
    """V12 — route a single call to the right provider API using an explicit key.
    Returns (text, pt, ct, tt). Raises on HTTP/API error (caller classifies 429/401)."""
    model = PROVIDER_MODELS.get(provider, "gpt-4o-mini")
    if provider == "gemini":
        return await _call_gemini(api_key, model, system, user, max_tokens, temperature)
    base = PROVIDER_BASE.get(provider) or "https://api.openai.com/v1/chat/completions"
    return await _call_openai_compatible(base, api_key, model, system, user, max_tokens, temperature)


def _classify_error(msg: str) -> tuple[bool, bool]:
    """(is_rate_limit, is_invalid) from an exception string."""
    low = msg.lower()
    is_rl = "429" in msg or "rate" in low or "quota" in low
    is_inv = "401" in msg or "invalid" in low or "unauthorized" in low
    return is_rl, is_inv


async def _chat_via_pool(system: str, user: str, max_tokens: int, temperature: float) -> str | None:
    """Pool-first: try up to POOL_MAX_ATTEMPTS distinct keys, preferring openai→
    deepseek→gemini and known-'working' keys. Marks success/failure so rate-limited
    and invalid keys are auto-skipped. Returns text or None if the whole pool fails."""
    from app.services.ai_key_pool import get_working_key, mark_success, mark_failure
    tried: set = set()
    for _ in range(POOL_MAX_ATTEMPTS):
        key_obj = None
        for prov in PROVIDER_ORDER:
            k = await get_working_key(prov)
            if k and k.id not in tried:
                key_obj = k
                break
        if not key_obj:
            k = await get_working_key(None)  # any provider
            if k and k.id not in tried:
                key_obj = k
        if not key_obj:
            break  # nothing usable left
        tried.add(key_obj.id)
        model = PROVIDER_MODELS.get(key_obj.provider, key_obj.provider)
        try:
            text, pt, ct, tt = await _call_provider(
                key_obj.provider, key_obj.api_key, user, system, max_tokens, temperature)
            if text:
                await mark_success(key_obj.id)
                await _log_usage(key_obj.provider, model, pt, ct, tt, True, None)
                return text
            await mark_failure(key_obj.id, "empty response")
            await _log_usage(key_obj.provider, model, 0, 0, 0, False, "empty response")
        except Exception as e:
            msg = str(e)
            is_rl, is_inv = _classify_error(msg)
            await mark_failure(key_obj.id, msg, is_rate_limit=is_rl, is_invalid=is_inv)
            await _log_usage(key_obj.provider, model, 0, 0, 0, False, msg)
            continue
    return None


async def _chat_via_env(system: str, user: str, max_tokens: int, temperature: float) -> str | None:
    """Original behavior — try each env-configured provider in order (fallback when
    the DB key pool is empty, so existing single-key setups keep working)."""
    for p in PROVIDERS:
        name, model = p["name"], p["model"]
        key = _key_for(name).strip()
        if not key:
            continue
        try:
            text, pt, ct, tt = await _call_provider(name, key, user, system, max_tokens, temperature)
            if text:
                await _log_usage(name, model, pt, ct, tt, True, None)
                return text
            await _log_usage(name, model, pt, ct, tt, False, "empty response")
        except Exception as e:
            await _log_usage(name, model, 0, 0, 0, False, str(e))
            continue
    return None


async def _chat(system: str, user: str, max_tokens: int, temperature: float) -> str | None:
    """V12 — DB key pool takes priority when it has active keys; otherwise fall back
    to env-var keys. Returns text on first success, else None (caller uses template)."""
    from app.services.ai_key_pool import pool_has_keys
    try:
        use_pool = await pool_has_keys()
    except Exception as e:
        print(f"[AI] pool_has_keys failed, using env keys: {e}")
        use_pool = False
    if use_pool:
        text = await _chat_via_pool(system, user, max_tokens, temperature)
        if text:
            return text
        # Pool exhausted this call → still try env keys as a last resort.
    return await _chat_via_env(system, user, max_tokens, temperature)


def _fallback_message(first_name: str, products=None, show_prices: bool = True,
                      opening_mode: str = "ai", opening_line: str | None = None) -> str:
    """Template used when every AI provider fails. Greeting honors opening_mode;
    the opt-out line is added afterwards by _apply_opt_out (not here)."""
    name = (first_name or "").strip() or "دوست عزیز"
    lines = []
    if opening_mode in ("fixed", "random") and opening_line:
        lines.append(opening_line.strip())
    elif opening_mode != "none":
        lines.append(f"سلام {name} جان! 🌟")
    lines.append("از افراکالا با پیشنهادهای ویژه در خدمت شما هستیم.")
    if products:
        lines.append("")
        for prod in products[:3]:
            if show_prices:
                price = f"{prod['price']:,} تومان" if prod.get("price") else "تماس بگیرید"
                lines.append(f"• {prod['name']}: {price}")
            else:
                lines.append(f"• {prod['name']}")
    return "\n".join(lines)


EMOJI_INSTRUCTION = {
    "none": "هیچ ایموجی استفاده نکن",
    "low": "حداکثر ۱-۲ ایموجی استفاده کن",
    "medium": "از ۳-۵ ایموجی مناسب استفاده کن",
    "high": "از ایموجی‌های متنوع و زیاد استفاده کن (۵-۱۰ ایموجی)",
}


async def generate_message(first_name: str, last_name: str, gpt_prompt: str,
                           products: list[dict] = None, emoji_level: str = "medium",
                           show_prices: bool = True, opening_mode: str = "ai",
                           opening_line: str | None = None, include_opt_out: bool = True,
                           opt_out_text: str | None = None, use_rich_formatting: bool = False) -> str:
    products_text = ""
    if products:
        products_text = "\n\nمحصولات امروز افراکالا:\n"
        for p in products[:3]:
            if show_prices:
                price = f"{p['price']:,} تومان" if p.get("price") else "تماس بگیرید"
                products_text += f"• {p['name']}: {price}\n"
            else:
                products_text += f"• {p['name']}\n"
        if not show_prices:
            products_text += "(قیمت‌ها را در پیام درج نکن)\n"

    user_msg = f"اسم مشتری: {first_name} {last_name}\n{gpt_prompt}{products_text}\nپیام واتس‌اپ فارسی بنویس:"

    # Build dynamic rules for opening line + opt-out (Phases 2 & 5).
    extra_rules = []
    if opening_mode in ("fixed", "random") and opening_line:
        extra_rules.append(f"- پیام را دقیقاً با این عبارت شروع کن: «{opening_line.strip()}»")
    elif opening_mode == "none":
        extra_rules.append("- پیام را بدون هیچ سلام و احوال‌پرسی شروع کن و مستقیم به پیشنهاد برو")
    opt_text = (opt_out_text or DEFAULT_OPT_OUT).strip()
    if include_opt_out:
        extra_rules.append(f"- در پایان پیام دقیقاً این عبارت را قرار بده: «{opt_text}»")
    else:
        extra_rules.append("- هیچ عبارت لغو، انصراف یا لغو اشتراک در انتهای پیام نگذار")
    # V13.5 — WhatsApp rich formatting: bold with *, italic with _, etc.
    if use_rich_formatting:
        extra_rules.append(
            "- از قالب‌بندی واتساپ استفاده کن: نام محصولات و قیمت‌ها را با *ستاره* پررنگ کن، "
            "نکات مهم را برجسته کن (مثلاً _کج_). فقط از نشانه‌های *، _، ~ استفاده کن."
        )

    emoji_rule = EMOJI_INSTRUCTION.get(emoji_level, EMOJI_INSTRUCTION["medium"])
    system_prompt = SYSTEM_PROMPT + "".join(f"\n{r}" for r in extra_rules) + f"\n- درباره ایموجی: {emoji_rule}"

    text = await _chat(system_prompt, user_msg, max_tokens=500, temperature=0.85)
    if not text:
        text = _fallback_message(first_name, products, show_prices, opening_mode, opening_line)
    # Deterministic post-processing so the settings hold even if the model drifts
    # or the template fallback was used.
    text = _apply_opening(text, opening_mode, opening_line)
    text = _apply_opt_out(text, include_opt_out, opt_text)
    return text


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
