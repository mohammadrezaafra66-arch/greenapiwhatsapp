"""V26 PART 3 — AI smart-reply generation for monitored groups (conversation_mode = ai).

A short, natural Persian reply for a home-appliance-sales customer message, generated via
the existing multi-provider AI key pool. The output is passed through the V24 identifier-leak
safeguard (`message_is_safe`) so an internal account number / instance id / label can NEVER
leak into a group reply. Returns None on any failure/unsafe output → caller falls back to a
predefined/default reply or sends nothing.
"""
from __future__ import annotations
import logging

from app.services.warmup_content import message_is_safe, looks_like_identifier

logger = logging.getLogger("afrakala.group_ai")

_SYSTEM = (
    "تو دستیار فروش یک فروشگاه لوازم خانگی به نام افراکالا هستی. در گروه واتساپ به پیام "
    "مشتری کوتاه، مودبانه و طبیعی به فارسی پاسخ بده. فقط درباره لوازم خانگی و خرید صحبت کن. "
    "هیچ شماره حساب، شناسه، شماره تلفن داخلی یا برچسب داخلی را ننویس. پاسخ حداکثر دو جمله باشد."
)


def build_user_prompt(customer_text: str, history: list[str] | None = None) -> str:
    """Compose the user prompt from the customer's message plus a little recent context.
    History lines that look like they carry an identifier are dropped defensively."""
    lines = []
    safe_history = [h for h in (history or []) if h and not looks_like_identifier(h)]
    if safe_history:
        lines.append("چند پیام اخیر گروه:")
        lines.extend(f"- {h}" for h in safe_history[-4:])
        lines.append("")
    lines.append(f"پیام مشتری: {customer_text}")
    lines.append("یک پاسخ کوتاه و مفید بده.")
    return "\n".join(lines)


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    t = text.strip()
    for a, b in (('"', '"'), ("«", "»"), ("'", "'"), ("“", "”")):
        if t.startswith(a) and t.endswith(b) and len(t) > 2:
            t = t[1:-1].strip()
    if len(t) > 400:
        t = t[:400].rstrip()
    return t or None


async def generate_ai_reply(customer_text: str, *, history: list[str] | None = None,
                            forbidden=(), chat_fn=None, max_tries: int = 2) -> str | None:
    """Generate a safe Persian smart reply, or None. `chat_fn(system, user, max_tokens,
    temperature)` is injectable; defaults to the real multi-provider pool (gpt_service._chat).
    Every candidate is checked with `message_is_safe` so no identifier ever ships."""
    if not customer_text or not customer_text.strip():
        return None
    fn = chat_fn
    if fn is None:
        from app.services.gpt_service import _chat  # lazy: avoid import cycle
        fn = _chat
    user = build_user_prompt(customer_text, history)
    for _ in range(max_tries):
        try:
            raw = await fn(_SYSTEM, user, 120, 0.7)
        except Exception as e:
            logger.debug("group AI reply chat failed, will fall back: %s", e)
            return None
        text = _clean(raw)
        if not text:
            return None
        if message_is_safe(text, forbidden):
            return text
        logger.debug("group AI reply contained an identifier/label — rejecting")
    return None
