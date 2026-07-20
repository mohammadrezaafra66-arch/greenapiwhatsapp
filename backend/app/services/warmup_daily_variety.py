"""V36 PART 2 — guaranteed daily VARIETY for «همکاری تیمی» ask-requests.

Requirement: each day, a sender should ask up to 10 DIFFERENT contacts (never the same few
repeatedly), chosen least-recently-asked-first so the rotation is fair. If a sender has fewer than
10 eligible contacts, it asks however many are eligible (each at most once that day).

This module is the PURE selection core (no DB, no framework) so `node`-style unit tests can pin the
behavior exactly. The engine (`warmup_helper_engine.run_helper_tick`) reduces its already-loaded
task rows into the small dicts these functions expect, then asks the ONE contact this returns.

Definitions (all datetimes are Tehran-naive, matching the tick's `now` and `asked_at`):
  • "asked today"      — a contact whose sender emitted an ask for it on `now`'s calendar day.
  • "least-recently-asked" — ordered by the contact's most-recent ask time across ALL history,
                             with never-asked contacts first (they have the strongest claim).

The cap is per-SENDER and counts DISTINCT contacts (a contact assigned to 2 cold accounts still
counts once toward the sender's 10), so a sender never floods one person and never exceeds 10
different people per day.
"""
from __future__ import annotations
from datetime import datetime

# Max DISTINCT contacts a single sender may ask per day. Fewer eligible → ask only those.
DAILY_DISTINCT_CONTACT_CAP = 10

_MIN = datetime.min  # sort key for "never asked" → first (highest priority)


def same_tehran_day(a: datetime | None, b: datetime | None) -> bool:
    """True when two Tehran-naive datetimes fall on the same calendar day. None → False."""
    if a is None or b is None:
        return False
    return a.date() == b.date()


def distinct_asked_today_by_sender(ask_rows, now: datetime) -> dict[str, set]:
    """Reduce ask history into {sender_instance_id: {helper_id, …}} for asks emitted TODAY.

    `ask_rows` is an iterable of (helper_id, sender_instance_id, asked_at) tuples (asked_at may be
    None for never-asked rows — those are ignored here). helper_id is stringified for stable keys."""
    out: dict[str, set] = {}
    for helper_id, sender_id, asked_at in ask_rows:
        if asked_at is None or sender_id is None:
            continue
        if same_tehran_day(asked_at, now):
            out.setdefault(sender_id, set()).add(str(helper_id))
    return out


def last_ask_by_helper(ask_rows) -> dict[str, datetime]:
    """Reduce ask history into {helper_id: most-recent asked_at}. Never-asked helpers are absent."""
    out: dict[str, datetime] = {}
    for helper_id, _sender_id, asked_at in ask_rows:
        if asked_at is None:
            continue
        k = str(helper_id)
        prev = out.get(k)
        if prev is None or asked_at > prev:
            out[k] = asked_at
    return out


def eligible_pending_ordered(pending, *, helper_sender: dict, last_ask: dict,
                             asked_today_by_sender: dict,
                             cap: int = DAILY_DISTINCT_CONTACT_CAP) -> list:
    """Order the pending (never-asked) tasks so the NEXT ask maximizes daily variety.

    A pending task is DROPPED when, for its contact's sender:
      • the sender already asked `cap` distinct contacts today (daily ceiling reached), OR
      • this same contact was already asked today (give a different contact a turn first).
    The survivors are ordered least-recently-asked contact first (never-asked → first), tie-broken
    by task creation time, so repeatedly taking `[0]` across ticks rotates through contacts fairly.

    `pending`            — task-like objects exposing `.helper_id` and `.created_at`.
    `helper_sender`      — {helper_id(str): sender_instance_id}.
    `last_ask`           — {helper_id(str): most-recent asked_at} (from last_ask_by_helper()).
    `asked_today_by_sender` — {sender_instance_id: {helper_id(str), …}} asked today.
    """
    survivors = []
    for t in pending:
        hid = str(t.helper_id)
        sid = helper_sender.get(hid)
        asked = asked_today_by_sender.get(sid, set())
        if len(asked) >= cap:      # this sender hit its 10-distinct daily ceiling
            continue
        if hid in asked:           # this contact already got its ask today → rotate to another
            continue
        survivors.append(t)
    survivors.sort(key=lambda t: (last_ask.get(str(t.helper_id)) or _MIN, t.created_at or _MIN))
    return survivors
