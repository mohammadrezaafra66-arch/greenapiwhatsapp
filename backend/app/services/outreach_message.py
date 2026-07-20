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
    message_is_safe, is_near_duplicate, content_hash, looks_like_identifier, has_emoji,
)
from app.services.warmup_helper_service import wa_me_link, wa_me_digits, SUGGESTED_TEXT

logger = logging.getLogger("afrakala.outreach")

# V29 «همکاری تیمی» — an ask-message references AT MOST 2 cold accounts (explicit ceiling).
MAX_REFERENCED_COLD_ACCOUNTS = 2

# V35 PART 3 — Persian labels for the contact-relationship categories (codes stored in the DB).
RELATIONSHIP_FA = {
    "friend": "دوست",
    "colleague": "همکار",
    "employee": "کارمند",
    "family": "فامیل",
}


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


# ── V29 «همکاری تیمی» PART 3 — thread-aware, profile-personalized generation ──
def _thread_system_prompt() -> str:
    return (
        "تو یک دستیار فارسی‌زبان هستی که پیام‌های کوتاه، دوستانه و کاملاً طبیعی و انسانی می‌نویسی. "
        "پیام باید مثل گفت‌وگوی واقعی بین دو همکار باشد، نه تبلیغاتی و نه رباتیک. "
        "هر بار جمله را متفاوت بگو و هرگز تکراری/نزدیک‌به‌قبلی ننویس. "
        "یکی دو ایموجی مناسب و طبیعی به‌کار ببر (نه زیاد و نه اسپم). "
        "هرگز شماره تلفن، عدد بلند، شناسه یا لینک ننویس — فقط متن کوتاه محاوره‌ای فارسی. "
        "همیشه مخاطب را با نام کاملش صدا بزن و اگر موضوع گفت‌وگو ادامه‌دار است، همان موضوع را دنبال کن."
    )


def _profile_line(*, job_title, years_experience, personal_benefit_note,
                  relationship=None, referral_note=None) -> str:
    """A short Persian hint the AI uses to make the ask personally relevant. Empty when no
    profile data is present. V35 PART 3 — also weaves in the relationship category (so the tone
    matches friend/colleague/employee/family) and, when present, the free-text referral note
    (e.g. «شماره شما را آقای X داده») so the generated message can reference it naturally."""
    bits = []
    if job_title:
        bits.append(f"سمت او: {str(job_title).strip()}")
    if years_experience:
        bits.append(f"سابقهٔ تخصصی: {years_experience} سال")
    if personal_benefit_note:
        bits.append(f"چرا کمک برای خودش هم مفید است: {str(personal_benefit_note).strip()}")
    rel_fa = RELATIONSHIP_FA.get(str(relationship or "").strip().lower())
    if rel_fa:
        bits.append(f"نسبت او با فرستنده: {rel_fa} (لحن پیام را متناسب با این نسبت تنظیم کن)")
    if referral_note:
        bits.append(f"چطور با او آشنا شدیم/چه کسی معرفی کرده: {str(referral_note).strip()} "
                    f"(اگر طبیعی بود، در پیام به‌شکل دوستانه به آن اشاره کن)")
    return "؛ ".join(bits)


def _thread_user_prompt(*, name, topic, step_count, brief, profile_line) -> str:
    cont = ("این ادامهٔ همان گفت‌وگوی قبلی است؛ موضوع را عوض نکن." if step_count > 0
            else "این اولین پیام این گفت‌وگوست؛ یک شروع طبیعی و مرتبط با موضوع بنویس.")
    lines = [
        f"برای «{name}» یک پیام کوتاه و صمیمی فارسی بنویس که:",
        f"- حتماً نام کامل «{name}» داخل پیام باشد،",
        f"- موضوع گفت‌وگو: {topic}",
        f"- {cont}",
    ]
    if profile_line:
        lines.append(f"- با توجه به این نکات، ربط شخصی کمک را طبیعی برسان: {profile_line}")
    if (brief or "").strip():
        lines.append(f"- منظور کلی فرستنده: {brief.strip()}")
    lines.append("- کوتاه (یک تا دو جمله)، بدون هیچ عدد یا لینک یا شماره. فقط متن پیام را بده.")
    return "\n".join(lines)


def build_thread_ai_fn(chat_fn=None):
    """Return async `ai_fn(*, name, topic, step_count, brief, profile_line) -> str | None`
    backed by the shared AI key pool (or an injected chat_fn for tests)."""
    async def _ai(*, name, topic, step_count, brief, profile_line):
        fn = chat_fn
        if fn is None:
            from app.services.gpt_service import _chat
            fn = _chat
        try:
            return await fn(_thread_system_prompt(),
                            _thread_user_prompt(name=name, topic=topic, step_count=step_count,
                                                brief=brief, profile_line=profile_line),
                            90, 0.9)
        except Exception as e:  # pragma: no cover
            logger.debug("thread AI chat failed, will fall back: %s", e)
            return None
    return _ai


def _thread_fallback(name: str, topic: str, step_count: int, rng: random.Random) -> str:
    """A safe, name-slotted templated ask that references the ongoing topic — used when AI is
    unavailable. ALWAYS includes the real full name and stays on-topic."""
    if step_count > 0:
        tmpls = [
            "سلام {name} جان، درمورد {topic} خواستم پیگیری کنم؛ اگه فرصت کردی یه پیام بده 🙏",
            "{name} عزیز، همون {topic} رو می‌گم؛ ممنون میشم یه سر بزنی 🌹",
            "سلام {name}، بازم درباره‌ی {topic} مزاحمت شدم، یه لطف کوچیک 👍",
        ]
    else:
        tmpls = [
            "سلام {name} جان، درباره‌ی {topic} یه زحمت کوچیک برات داشتم 🙏",
            "{name} عزیز سلام، وقتت بخیر — درمورد {topic} یه کمک کوچیک می‌خواستم 🌹",
            "سلام {name}، امیدوارم خوب باشی؛ راجع‌به {topic} یه لطف کوچیک ازت می‌خواستم 🙏",
        ]
    return rng.choice(tmpls).replace("{name}", (name or "").strip()).replace("{topic}", topic)


async def generate_thread_ask_message(*, brief: str | None, contact: dict, topic: str,
                                      step_count: int, cold_phone_digits: list[str],
                                      ai_fn=None, recent: list[str] | None = None,
                                      forbidden=(), rng: random.Random | None = None,
                                      suggested: str = SUGGESTED_TEXT,
                                      include_suggestion: bool = True,
                                      max_ai_tries: int = 2) -> tuple[str, str]:
    """Generate ONE thread-aware, profile-personalized ask-message. Returns (full_message, source).

    • uses the contact's real FULL name (validated; regenerate once; safe templated fallback);
    • references job_title/years_experience/personal_benefit_note where present;
    • continues `topic` when step_count > 0 (never restarts on an unrelated subject);
    • appends wa.me link(s) for the 1–2 assigned cold accounts (raw numbers never leak — the
      link legitimately carries the cold number's digits, so links are added AFTER body
      validation), capped at MAX_REFERENCED_COLD_ACCOUNTS;
    • body passes V24's identifier-leak filter + the anti-repeat check."""
    recent = recent or []
    r = rng or random
    name = (contact.get("name") or "").strip()
    if not name_is_usable(name):
        raise ValueError("نام مخاطب معتبر نیست (نباید عدد/شناسه باشد)")
    profile_line = _profile_line(
        job_title=contact.get("job_title"), years_experience=contact.get("years_experience"),
        personal_benefit_note=contact.get("personal_benefit_note"),
        relationship=contact.get("relationship"), referral_note=contact.get("referral_note"))

    body, source = None, "fallback"
    if ai_fn is not None:
        for _ in range(max_ai_tries):
            try:
                text = await ai_fn(name=name, topic=topic, step_count=step_count,
                                   brief=brief, profile_line=profile_line)
            except Exception:
                break
            text = (text or "").strip()
            if not text:
                continue
            if not message_is_safe(text, forbidden):
                continue
            if not message_includes_name(text, name):
                continue
            if is_near_duplicate(text, recent):
                continue
            body, source = text, "ai"
            break

    if body is None:
        for _ in range(6):
            cand = _thread_fallback(name, topic, step_count, r)
            if message_is_safe(cand, forbidden) and not is_near_duplicate(cand, recent):
                body = cand
                break
        if body is None:
            body = _thread_fallback(name, topic, step_count, r)
        source = "fallback"

    # V30 PART 5 — guarantee a natural emoji in every ask body (the AI prompt already requests one;
    # this backstops an emoji-less AI reply without rejecting an otherwise-good, on-topic message).
    if not has_emoji(body):
        body = f"{body} 🙏"

    # Append up to 2 wa.me links (explicit ceiling). Each cold number's link is added AFTER body
    # validation because the link legitimately contains that cold number's digits.
    lines = [body]
    digits_list = [d for d in (cold_phone_digits or []) if wa_me_digits(d)][:MAX_REFERENCED_COLD_ACCOUNTS]
    links = [wa_me_link(d) for d in digits_list]
    links = [ln for ln in links if ln]
    if len(links) == 1:
        lines.append(f"لینک مستقیم (یک لمس): {links[0]}")
    elif len(links) >= 2:
        lines.append("لینک‌های مستقیم (یک لمس):")
        for ln in links:
            lines.append(f"• {ln}")
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
