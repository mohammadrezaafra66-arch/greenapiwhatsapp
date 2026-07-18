"""V26 PART 3 — Persian-aware keyword detection + auto-reply decision logic (pure).

Everything here is pure and unit-testable (no DB/network/time-of-day side effects). The
async orchestration in group_monitor_engine composes these functions.

Matching is Persian-aware: Arabic vs Persian letter variants (ي/ی, ك/ک), Arabic-Indic and
Persian digits, tatweel and tashkeel are all normalized, so «قيمت» and «قیمت» compare equal.
"""
from __future__ import annotations
import random
import re

# Arabic → Persian letter unification + tatweel removal.
_LETTER_MAP = {
    "ي": "ی", "ك": "ک", "ى": "ی", "ﻯ": "ی", "ﻼ": "لا",
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ﺇ": "ا",
    "ؤ": "و", "ئ": "ی", "ة": "ه", "ﻩ": "ه",
}
_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
# Arabic tashkeel/diacritics + tatweel to strip.
_DIACRITICS = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭـ]")


def normalize_fa(text: str | None) -> str:
    """Normalize Persian/Arabic text for robust matching: unify letter variants, strip
    diacritics/tatweel, map all digit scripts to ASCII, lowercase, collapse whitespace."""
    if not text:
        return ""
    t = text.translate(_DIGIT_MAP)
    t = "".join(_LETTER_MAP.get(ch, ch) for ch in t)
    t = _DIACRITICS.sub("", t)
    t = t.lower()
    return " ".join(t.split())


def detect(text: str | None, keywords) -> tuple[list[str], list[str]]:
    """Return (matched_trigger_words, matched_forbidden_words) for `text`.

    `keywords` is an iterable of objects with .word, .kind ('trigger'|'forbidden'), .active.
    Matching is substring-based on the normalized text (a customer rarely types a trigger
    as a standalone word). Each distinct keyword is reported at most once, in input order.
    """
    from app.models.group_monitor import KEYWORD_KIND_FORBIDDEN, KEYWORD_KIND_TRIGGER

    norm = normalize_fa(text)
    triggers: list[str] = []
    forbidden: list[str] = []
    if not norm:
        return triggers, forbidden
    for kw in keywords:
        if not getattr(kw, "active", True):
            continue
        w = normalize_fa(getattr(kw, "word", ""))
        if not w or w not in norm:
            continue
        if getattr(kw, "kind", KEYWORD_KIND_TRIGGER) == KEYWORD_KIND_FORBIDDEN:
            if kw.word not in forbidden:
                forbidden.append(kw.word)
        else:
            if kw.word not in triggers:
                triggers.append(kw.word)
    return triggers, forbidden


def select_predefined_reply(matched_triggers, replies, keyword_id_by_word):
    """Pick the predefined reply text for a message.

    `replies` is an iterable of objects with .keyword_id (uuid|None), .reply_text, .active.
    Preference: a reply whose keyword_id matches one of the matched trigger words; otherwise
    a default reply (keyword_id is None). Returns the reply_text, or None if none applies.
    """
    active = [r for r in replies if getattr(r, "active", True)]
    matched_ids = {keyword_id_by_word.get(w) for w in matched_triggers}
    matched_ids.discard(None)
    for r in active:
        if r.keyword_id is not None and r.keyword_id in matched_ids:
            return r.reply_text
    for r in active:
        if r.keyword_id is None:
            return r.reply_text
    return None


# ── per-group auto-reply rate limit (pure) ───────────────────────────────────
DEFAULT_REPLIES_PER_HOUR = 4


def within_rate_limit(recent_reply_count: int, cap: int = DEFAULT_REPLIES_PER_HOUR,
                      rng: random.Random | None = None) -> bool:
    """True if another auto-reply is allowed this hour for a group that has already sent
    `recent_reply_count` auto-replies in the trailing hour. The cap is jittered ±1 so the
    group's reply cadence isn't a constant fingerprint (never below 1)."""
    r = rng or random
    jittered = max(1, cap + r.randint(-1, 1))
    return recent_reply_count < jittered


def should_auto_reply(*, auto_reply_enabled: bool, conversation_mode: str,
                      has_trigger: bool, in_waking_hours: bool,
                      within_rate: bool) -> bool:
    """The single gate for sending an auto-reply. Default OFF: every condition must hold.
    conversation_mode 'off' (or auto_reply disabled) → never send."""
    from app.models.group_monitor import CONVERSATION_MODE_OFF
    if not auto_reply_enabled:
        return False
    if conversation_mode == CONVERSATION_MODE_OFF or not conversation_mode:
        return False
    if not has_trigger:
        return False
    if not in_waking_hours:
        return False
    return bool(within_rate)
