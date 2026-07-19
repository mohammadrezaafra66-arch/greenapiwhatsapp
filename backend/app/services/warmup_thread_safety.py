"""V29 «همکاری تیمی» PART 4 — thread-level safety flagging.

If a forbidden/sensitive word appears in EITHER direction of a thread (the contact's incoming
message, the sender's ask, or the cold account's auto-reply), we PAUSE only that thread
(status='paused') and raise an admin alert (a WarmupThreadAlert row — never an auto-message).
The rest of «همکاری تیمی» keeps running.

Forbidden words reuse V26's group-monitoring keyword concept (GroupKeyword kind='forbidden')
when present, unioned with a small built-in default list, so the admin's existing forbidden
list also protects threads.
"""
from __future__ import annotations
import logging
from sqlalchemy import select

from app.models.warmup_helpers import WarmupThreadAlert
from app.services import warmup_helper_thread as wt

logger = logging.getLogger("afrakala.warmup.safety")

# Direction tags for an alert.
DIR_OUTBOUND_ASK = "outbound_ask"
DIR_INBOUND = "inbound"
DIR_COLD_REPLY = "cold_reply"

# A small built-in list, always applied even with no admin-configured group keywords. Kept
# deliberately short + generic (financial-fraud / illicit terms) — extend via the group keyword
# list rather than hardcoding a large table here.
DEFAULT_FORBIDDEN_WORDS = (
    "کلاهبرداری", "فیشینگ", "رمز کارت", "رمز دوم", "cvv", "کلمه عبور", "پسورد",
    "شرط‌بندی", "قمار", "مواد مخدر", "تهدید",
)


def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def find_forbidden_word(text: str | None, words) -> str | None:
    """PURE. Return the first forbidden word found in `text` (case-insensitive substring), or
    None. `words` is any iterable of forbidden terms."""
    t = _norm(text)
    if not t:
        return None
    for w in words or ():
        wn = _norm(w)
        if wn and wn in t:
            return w
    return None


async def load_forbidden_words(db) -> list[str]:
    """The active forbidden-word list: the built-in defaults ∪ the admin's V26 group
    forbidden keywords. Best-effort — never fails the caller if the group table is absent."""
    words = list(DEFAULT_FORBIDDEN_WORDS)
    try:
        from app.models.group_monitor import GroupKeyword, KEYWORD_KIND_FORBIDDEN
        rows = (await db.execute(
            select(GroupKeyword.keyword).where(GroupKeyword.kind == KEYWORD_KIND_FORBIDDEN)
        )).all()
        for (kw,) in rows:
            if kw and kw.strip():
                words.append(kw.strip())
    except Exception as e:  # pragma: no cover - group monitoring optional
        logger.debug("forbidden-word load (group keywords) skipped: %s", e)
    # de-dup preserving order
    seen, out = set(), []
    for w in words:
        k = _norm(w)
        if k and k not in seen:
            seen.add(k)
            out.append(w)
    return out


async def scan_and_flag(db, thread, text: str, direction: str,
                        words=None) -> WarmupThreadAlert | None:
    """If `text` contains a forbidden word, PAUSE `thread` and create an admin alert. Returns the
    alert row (added, not committed — the caller's session commits) or None when clean. Loads the
    forbidden list itself unless `words` is supplied. Never raises for the caller's sake."""
    if thread is None or not text:
        return None
    try:
        wl = words if words is not None else await load_forbidden_words(db)
        hit = find_forbidden_word(text, wl)
        if not hit:
            return None
        wt.pause_thread(thread)
        alert = WarmupThreadAlert(
            thread_id=thread.id, helper_id=getattr(thread, "helper_id", None),
            cold_instance_id=getattr(thread, "cold_instance_id", None),
            keyword=str(hit)[:120], direction=direction, message_excerpt=str(text)[:500])
        db.add(alert)
        logger.info("thread %s paused: forbidden word %r (%s)", thread.id, hit, direction)
        return alert
    except Exception as e:  # pragma: no cover
        logger.warning("thread safety scan failed (non-fatal): %s", e)
        return None
