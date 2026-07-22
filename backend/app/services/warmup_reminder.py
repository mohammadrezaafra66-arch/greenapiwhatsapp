"""V38 — AI-generated, reminder-TONED «همکاری تیمی» reminder messages.

Until now the single/second reminder used a STATIC line (`warmup_helper_service.build_reminder_message`).
This makes the reminder AI-generated and clearly DISTINGUISHABLE in tone from the first ask:

  • it explicitly SIGNALS that it is a reminder — naturally weaving in «این پیام جهت یادآوری است» /
    «هنوز منتظر جوابتم» / «یادت نره» rather than reading like a fresh first request;
  • it naturally uses reminder/urgency emoji from a small curated set (⏰ ⏳ ⌛ 🏃 🔔 📌 📣) — varied,
    never forcing all of them into one message;
  • it reuses — UNCHANGED — the exact same anti-repeat (`is_near_duplicate`) and identifier-leak
    (`message_is_safe`) guards every other warm-up generator uses, so no phone/instance-id/label
    can ever leak and consecutive reminders are never near-duplicates.

This module ONLY changes reminder generation. The ask / thank-you / cold-reply generators are
untouched. Pure pieces (`has_reminder_signal`, `has_reminder_emoji`, `generate_reminder`) are
rng/ai-injectable so the tone + leak-safety guarantees are unit-tested without the network or a DB.
"""
from __future__ import annotations
import logging
import random

from app.services.warmup_content import message_is_safe, is_near_duplicate, has_emoji

logger = logging.getLogger("afrakala.warmup.reminder")

# ── Reminder tone markers ────────────────────────────────────────────────────
# A small curated set of reminder / urgency emoji. Generation naturally draws from these; a
# reminder that reaches the wire always carries at least one (a backstop appends one if the AI
# returned none), and NONE of them are used by the ask/thank-you generators — so tone is distinct.
REMINDER_EMOJI = ("⏰", "⏳", "⌛", "🏃", "🔔", "📌", "📣")

# Persian reminder-signaling stems: a genuine reminder contains at least one of these so it never
# reads like a fresh first ask. Matched as substrings (Persian has no casing to fold).
REMINDER_SIGNAL_MARKERS = (
    "یادآور",   # یادآوری / یادآور
    "یادت",     # یادت نره / یادت باشه
    "منتظر",    # هنوز منتظر جوابتم
    "هنوز",     # هنوز پیامی ازت ندیدم
    "فراموش",   # اگه فراموش نشده باشه
    "پیگیر",    # پیگیر همون درخواستم
)


def has_reminder_signal(text: str | None) -> bool:
    """PURE. True if `text` contains reminder-signaling language (so tone differs from a fresh ask)."""
    if not text:
        return False
    return any(m in text for m in REMINDER_SIGNAL_MARKERS)


def has_reminder_emoji(text: str | None) -> bool:
    """PURE. True if `text` contains at least one emoji from the curated reminder/urgency set."""
    if not text:
        return False
    return any(e in text for e in REMINDER_EMOJI)


def _ensure_reminder_emoji(text: str, rng: random.Random) -> str:
    """Backstop (mirrors the ask generator's emoji backstop): guarantee a reminder emoji is present
    without rejecting an otherwise-good, on-topic reminder that happened to carry only a generic one."""
    if has_reminder_emoji(text):
        return text
    return f"{text} {rng.choice(REMINDER_EMOJI)}"


# ── AI prompts ───────────────────────────────────────────────────────────────
def _system_prompt() -> str:
    return (
        "تو یک فروشندهٔ فارسی‌زبان صمیمی هستی که یک «پیام یادآوری» برای همکاری می‌فرستی که قبلاً یک "
        "درخواست کوچک برایش فرستاده‌ای و هنوز جواب نگرفته‌ای. "
        "پیام باید کاملاً واضح نشان بدهد که این یک یادآوری است (نه یک درخواست تازه) — مثلاً با لحن‌هایی "
        "مثل «این پیام فقط جهت یادآوریه»، «هنوز منتظر جوابتم» یا «یادت نره». "
        "لحن باید دوستانه اما کمی پیگیرانه/فوری‌تر از یک سلامِ اول باشد، نه طلبکارانه. "
        "یکی دو ایموجیِ متناسب با یادآوری/عجله به‌کار ببر مثل ⏰ ⏳ ⌛ 🏃 🔔 📌 📣 (طبیعی و کم، نه همه را باهم). "
        "هرگز شماره تلفن، عدد بلند، شناسه یا لینک ننویس — فقط متن کوتاه یادآوری فارسی."
    )


def _user_prompt(contact_name: str) -> str:
    who = (contact_name or "").strip()
    addressee = f"«{who}»" if who else "این همکار"
    return (
        f"برای {addressee} یک پیام کوتاهِ یادآوری بنویس که یادآوری کند همان پیام کوتاهی که قبلاً ازش "
        f"خواستی هنوز فرستاده نشده. "
        f"حتماً به‌شکل طبیعی برسان که این یادآوری است (مثل «فقط جهت یادآوری» یا «هنوز منتظرتم»)، "
        f"یکی دو ایموجیِ یادآوری/عجله داشته باشد، کوتاه (یک تا دو جمله) و بدون هیچ عدد یا لینک. "
        f"فقط متن پیام را بده."
    )


def build_reminder_ai_fn(chat_fn=None):
    """Return async `ai_fn(*, contact_name) -> str | None` backed by the shared multi-provider AI key
    pool (`gpt_service._chat`), or an injected `chat_fn` for tests."""
    async def _ai(*, contact_name: str):
        fn = chat_fn
        if fn is None:
            from app.services.gpt_service import _chat
            fn = _chat
        try:
            return await fn(_system_prompt(), _user_prompt(contact_name), 70, 0.9)
        except Exception as e:  # pragma: no cover
            logger.debug("reminder AI chat failed, will fall back: %s", e)
            return None
    return _ai


# ── templated fallback (ALWAYS reminder-signal + reminder emoji + name) ───────
_FALLBACK = [
    "سلام {name} جان، این پیام فقط جهت یادآوریه ⏰ اگه فرصت کردی همون پیام کوتاه رو بفرست، ممنون می‌شم",
    "{name} عزیز، یه یادآوری کوچیک 🔔 هنوز منتظر همون پیامتم، اگه بشه لطف می‌کنی",
    "سلام {name}، یادت نره اون پیام کوتاه رو بفرستی ⏳ ممنونم ازت",
    "{name} جان، فقط یه یادآوری ⏰ هنوز منتظر جوابتم 🏃 اگه یه لحظه وقت کردی",
    "سلام {name}، پیگیر همون درخواست کوچیکم 📌 اگه فراموش نشده، همون پیام کوتاه رو بزن لطفاً",
    "{name} جان، این پیام جهت یادآوریه 📣 فراموش نکن همون پیام کوتاه رو بفرستی، ممنون می‌شم",
]


def build_reminder_fallback(name: str | None, rng: random.Random | None = None) -> str:
    """A safe, name-slotted reminder used when AI is unavailable. ALWAYS carries a reminder-signal
    phrase AND a reminder emoji, so even the fallback is distinguishable from a fresh ask."""
    r = rng or random
    who = (name or "").strip()
    return r.choice(_FALLBACK).replace("{name}", who).replace("  ", " ").strip()


# ── one reminder ─────────────────────────────────────────────────────────────
async def generate_reminder(*, contact_name: str, ai_fn=None, forbidden=(),
                            recent: list[str] | None = None, rng: random.Random | None = None,
                            max_ai_tries: int = 2) -> tuple[str, str]:
    """Generate ONE reminder BODY. Returns (text, source ∈ {ai,fallback}).

    Every candidate passes the SAME (unchanged) V24 identifier-leak filter (`message_is_safe`) and
    the anti-repeat check (`is_near_duplicate`) used across the warm-up generators. AI candidates are
    additionally required to SIGNAL reminder tone (`has_reminder_signal`); a reminder emoji is
    guaranteed by a backstop that appends one only if none is present (never rejecting an otherwise
    good message). A safe, reminder-signaling, emoji-bearing fallback is always available."""
    recent = recent or []
    r = rng or random
    if ai_fn is not None:
        for _ in range(max_ai_tries):
            try:
                text = await ai_fn(contact_name=contact_name)
            except Exception:
                break
            text = (text or "").strip()
            if not text:
                continue
            if not message_is_safe(text, forbidden):     # UNCHANGED identifier-leak filter
                continue
            if is_near_duplicate(text, recent):           # UNCHANGED anti-repeat
                continue
            if not has_reminder_signal(text):             # must READ like a reminder, not a fresh ask
                continue
            return _ensure_reminder_emoji(text, r), "ai"
    for _ in range(len(_FALLBACK) + 1):
        cand = build_reminder_fallback(contact_name, r)
        if message_is_safe(cand, forbidden) and not is_near_duplicate(cand, recent):
            return _ensure_reminder_emoji(cand, r), "fallback"
    return _ensure_reminder_emoji(build_reminder_fallback(contact_name, r), r), "fallback"
