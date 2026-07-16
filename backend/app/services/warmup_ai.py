"""V23 — wire the multi-provider AI key pool into mesh warm-up content generation.

`build_warmup_ai_fn()` returns the `ai_fn` that `warmup_content.generate_mesh_message`
calls FIRST for every mesh message. It routes through `gpt_service._chat`, which is
pool-first (OpenAI → DeepSeek → Gemini, auto-skipping rate-limited/invalid keys) and
falls back to env-var keys — so warm-up messages are AI-generated whenever any key is
usable. On any failure (no key, over budget, timeout, empty), the chat layer returns
None and `generate_mesh_message` degrades to the curated Persian phrase pool.

Each number gets a STABLE persona (deterministic from its instance_id) and the short
per-edge running history is fed in, so exchanges read as varied, natural, multi-turn
Persian small-talk between two people in the home-appliance trade — never templated.

Pure/​injectable: `build_warmup_ai_fn(chat_fn=...)` lets tests inject a fake chat layer,
so "AI first, fallback only on failure" is verifiable without the network.
"""
from __future__ import annotations
import logging

logger = logging.getLogger("afrakala.warmup.ai")

# Stable persona bank — each number consistently "sounds like" one of these so a
# conversation has two distinct, coherent voices. Home-appliance wholesale/retail milieu.
PERSONAS: list[str] = [
    "یک فروشندهٔ لوازم خانگی که خونگرم و صمیمیه و کوتاه و خودمونی پیام می‌ده",
    "یک همکار عمده‌فروش که رک و سریع پیام می‌ده و زیاد تعارف نمی‌کنه",
    "یک مغازه‌دار باتجربه که آروم و محترمانه و با کمی شوخی حرف می‌زنه",
    "یک بازاری جوان و پرانرژی که با ایموجی و خیلی خلاصه پیام می‌ده",
    "یک خانمِ فروشنده که مودب و گرم و کمی رسمی پیام می‌ده",
    "یک تاجر لوازم خانگی که اهل احوال‌پرسی و بازارگرمیه",
    "یک همکار قدیمی که مثل رفیق صمیمی و بی‌تکلف پیام می‌ده",
    "یک فروشندهٔ دقیق که بیشتر دنبال قیمت و موجودی و کاره تا خوش‌وبش",
]


def persona_for_instance(instance_id: str | None) -> str:
    """A stable persona for a number (same instance_id → same voice every time)."""
    if not instance_id:
        return PERSONAS[0]
    idx = sum(ord(c) for c in str(instance_id)) % len(PERSONAS)
    return PERSONAS[idx]


def _system_prompt(persona: str | None) -> str:
    persona = persona or PERSONAS[0]
    return (
        "تو در نقش «" + persona + "» هستی و در واتساپ با یک آشنای کاری در حوزهٔ لوازم "
        "خانگی گپ می‌زنی. فقط و فقط «یک» پیام کوتاه فارسی و طبیعی بنویس، مثل چت واقعی "
        "بین دو نفر. قوانین: خیلی کوتاه (حداکثر یک جمله)، بدون امضا و بدون معرفی خودت، "
        "هر بار جمله را متفاوت بگو و تکراری نشو، گاهی می‌تونی یک ایموجی بذاری، گفتگو را "
        "با توجه به پیام‌های قبلی به‌شکل طبیعی ادامه بده. فقط متن همان یک پیام را خروجی بده."
    )


def _user_prompt(history: list[str] | None, name: str | None, product: str | None) -> str:
    lines: list[str] = []
    if name:
        lines.append(f"طرف مقابل: {name}")
    if product:
        lines.append(f"موضوع احتمالی: {product}")
    hist = [h for h in (history or []) if h and h.strip()][-6:]
    if hist:
        lines.append("چند پیام آخر این گفتگو (قدیمی→جدید):")
        lines.extend(f"- {h.strip()}" for h in hist)
        lines.append("حالا پیام بعدی و طبیعی این گفتگو را بنویس.")
    else:
        lines.append("این اولین پیام گفتگوست؛ یک پیام کوتاه و طبیعی برای شروع بنویس.")
    return "\n".join(lines)


def _clean(text: str) -> str | None:
    """Keep the AI output short and message-like: first line only, strip wrapping
    quotes, collapse whitespace, cap length. Returns None if nothing usable remains."""
    if not text:
        return None
    t = " ".join(str(text).strip().splitlines()[0].split())
    # Strip common wrapping quotes the model sometimes adds.
    for a, b in (('"', '"'), ("«", "»"), ("'", "'"), ("“", "”")):
        if t.startswith(a) and t.endswith(b) and len(t) > 2:
            t = t[1:-1].strip()
    if len(t) > 160:
        t = t[:160].rstrip()
    return t or None


def build_warmup_ai_fn(chat_fn=None):
    """Return the async `ai_fn(persona, history, name, product) -> str | None` that
    `generate_mesh_message` calls first. `chat_fn` (injectable) defaults to the real
    multi-provider pool (`gpt_service._chat`). Returns None on any failure so the
    generator falls back to the curated phrase pool."""
    async def _ai(*, persona=None, history=None, name=None, product=None):
        fn = chat_fn
        if fn is None:
            from app.services.gpt_service import _chat  # lazy: avoid import cycle
            fn = _chat
        try:
            text = await fn(_system_prompt(persona), _user_prompt(history, name, product),
                            60, 0.9)
        except Exception as e:
            logger.debug("warmup AI chat failed, will fall back: %s", e)
            return None
        return _clean(text)
    return _ai
