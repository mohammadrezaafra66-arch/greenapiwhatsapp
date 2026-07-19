"""V28 PART 3 — AI-personalized outreach messages from a one-line brief.

For each of a sender's contacts we generate a DISTINCT, natural Persian message that:
  • incorporates the user's short brief (e.g. «به شماره‌های جدید ما سلام بده»),
  • MUST include that contact's REAL saved name (validate → regenerate once → safe templated
    fallback that still inserts the name; never send without the name),
  • MUST NOT leak any account number / instance id / system label — reuse V24's hard filter
    (`message_is_safe`) on the BODY (the wa.me link legitimately contains the cold number's
    digits, so the link is appended AFTER body validation),
  • carries the click-to-chat wa.me link for the specific cold number, and
  • varies across contacts (reuse the V24 anti-repeat `is_near_duplicate` / `content_hash`).

NOTE: unlike the mesh generator, we DO NOT coerce the name to a curated pool — the contact's
real, user-entered name must appear verbatim. We only reject a name that itself looks like an
identifier (a real first name never does).
"""
from __future__ import annotations
import logging
import random

from app.services.warmup_content import (
    message_is_safe, is_near_duplicate, content_hash, looks_like_identifier,
)
from app.services.warmup_helper_service import wa_me_link, wa_me_digits, SUGGESTED_TEXT

logger = logging.getLogger("afrakala.outreach")


# ── name validation (real name, NOT restricted to a pool) ────────────────────
def message_includes_name(text: str, name: str) -> bool:
    """True if the contact's real name appears verbatim in the message body."""
    if not name or not name.strip():
        return False
    return name.strip() in (text or "")


def name_is_usable(name: str | None) -> bool:
    """A contact name may be used in a message only if it exists and does not itself look
    like a phone/instance id (a real first name never does)."""
    return bool(name and name.strip()) and not looks_like_identifier(name)


# ── AI prompts ───────────────────────────────────────────────────────────────
def _system_prompt() -> str:
    return (
        "تو یک دستیار فارسی‌زبان هستی که پیام‌های کوتاه، دوستانه و کاملاً طبیعی می‌نویسی. "
        "پیام باید شخصی و انسانی به‌نظر برسد، نه تبلیغاتی و نه رباتیک. "
        "هرگز شماره تلفن، عدد بلند، شناسه یا لینک ننویس — فقط یک پیام کوتاه محاوره‌ای فارسی. "
        "همیشه مخاطب را با نامش صدا بزن."
    )


def _user_prompt(brief: str, name: str) -> str:
    brief = (brief or "").strip() or "به این فرد سلام کن و ازش یک لطف کوچک بخواه"
    return (
        f"برای «{name}» یک پیام کوتاه و صمیمی فارسی بنویس که:\n"
        f"- حتماً با نام «{name}» شروع شود یا نامش داخل پیام باشد،\n"
        f"- این منظور را طبیعی برساند: {brief}\n"
        f"- کوتاه (یک تا دو جمله)، بدون هیچ عدد یا لینک یا شماره.\n"
        f"فقط متن پیام را بده."
    )


def build_outreach_ai_fn(chat_fn=None):
    """Return async `ai_fn(*, brief, name) -> str | None` backed by the shared multi-provider
    AI key pool (`gpt_service._chat`), or an injected `chat_fn` for tests."""
    async def _ai(*, brief: str, name: str):
        fn = chat_fn
        if fn is None:
            from app.services.gpt_service import _chat
            fn = _chat
        try:
            return await fn(_system_prompt(), _user_prompt(brief, name), 80, 0.9)
        except Exception as e:  # pragma: no cover
            logger.debug("outreach AI chat failed, will fall back: %s", e)
            return None
    return _ai


# ── templated fallback (ALWAYS contains the real name) ───────────────────────
_FALLBACK_TEMPLATES = [
    "سلام {name} جان، خوبی؟ یه لطف کوچیک ازت داشتم 🙏",
    "{name} عزیز سلام، وقتت بخیر — یه زحمت کوچیک برات دارم 🌹",
    "سلام {name}، امیدوارم حالت خوب باشه؛ یه کمک کوچیک ازت می‌خواستم 🙏",
    "{name} جان سلام، ببخشید مزاحمت شدم — یه کار کوچیک بود 👍",
    "سلام {name}، دمت گرم؛ یه لطف کوچیک ازت می‌خواستم اگه میشه 🌹",
]


def build_outreach_fallback(name: str, rng: random.Random | None = None) -> str:
    """A safe, name-slotted templated message used when AI is unavailable or keeps failing.
    ALWAYS includes the real name so we never send a nameless message."""
    r = rng or random
    return r.choice(_FALLBACK_TEMPLATES).replace("{name}", (name or "").strip())


# ── one message ──────────────────────────────────────────────────────────────
async def generate_outreach_message(*, brief: str, contact_name: str,
                                    cold_phone_digits: str | None,
                                    ai_fn=None, recent: list[str] | None = None,
                                    forbidden=(), rng: random.Random | None = None,
                                    suggested: str = SUGGESTED_TEXT,
                                    include_suggestion: bool = True,
                                    max_ai_tries: int = 2) -> tuple[str, str]:
    """Generate ONE personalized outreach message. Returns (full_message, source) where
    source ∈ {"ai","fallback"}. The wa.me link + optional copy/paste suggestion are appended
    AFTER body validation (the link legitimately contains the cold number's digits)."""
    recent = recent or []
    r = rng or random
    name = (contact_name or "").strip()
    if not name_is_usable(name):
        # A name that itself looks like an identifier can never be used — caller must fix it.
        raise ValueError("نام مخاطب معتبر نیست (نباید عدد/شناسه باشد)")

    body, source = None, "fallback"
    if ai_fn is not None:
        for _ in range(max_ai_tries):        # one attempt + one regeneration
            try:
                text = await ai_fn(brief=brief, name=name)
            except Exception:
                break
            text = (text or "").strip()
            if not text:
                continue
            if not message_is_safe(text, forbidden):         # V24 identifier-leak filter
                continue
            if not message_includes_name(text, name):        # MUST include the real name
                continue
            if is_near_duplicate(text, recent):              # anti-repeat across the batch
                continue
            body, source = text, "ai"
            break

    if body is None:
        # Safe templated fallback — still includes the name. Vary if a near-dup slips in.
        for _ in range(len(_FALLBACK_TEMPLATES) + 1):
            cand = build_outreach_fallback(name, r)
            if not is_near_duplicate(cand, recent):
                body = cand
                break
        if body is None:
            body = build_outreach_fallback(name, r)
        source = "fallback"

    link = wa_me_link(cold_phone_digits)
    lines = [body]
    if link:
        lines.append(f"لینک مستقیم (یک لمس): {link}")
    if include_suggestion:
        lines.append(f"می‌تونی همین رو بفرستی: «{suggested}»")
    return "\n".join(lines), source


# ── whole batch (per-contact, anti-repeat accumulation) ──────────────────────
async def generate_outreach_batch(*, brief: str, contacts: list[dict],
                                  cold_phone_digits: str | None,
                                  ai_fn=None, forbidden=(), rng: random.Random | None = None,
                                  include_suggestion: bool = True) -> list[dict]:
    """Generate a distinct message for each contact in a batch. `contacts` is a list of
    {"name","phone",...}. Accumulates prior BODIES so no two contacts of the same sender get
    near-identical text. Returns [{contact, message, source}]."""
    r = rng or random
    recent_bodies: list[str] = []
    out = []
    for c in contacts:
        msg, source = await generate_outreach_message(
            brief=brief, contact_name=c.get("name", ""), cold_phone_digits=cold_phone_digits,
            ai_fn=ai_fn, recent=recent_bodies, forbidden=forbidden, rng=r,
            include_suggestion=include_suggestion,
        )
        # track the BODY (first line) for anti-repeat, not the link/suggestion boilerplate
        recent_bodies.append(msg.split("\n", 1)[0])
        out.append({"contact": c, "message": msg, "source": source})
    return out
