"""V36 PART 2 — slower ask spacing (20 → 55 min) + guaranteed daily variety.

Requirement: each day a sender asks up to 10 DIFFERENT contacts, least-recently-asked first
(round-robin), capped at 10 (or fewer if <10 eligible). Spacing between a sender's asks rises to
55 min so those 10 spread naturally across the 09:00–19:00 (600 min) window. Existing V27/V30
safety gates are unchanged — only the spacing value and the contact-selection rule move.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest

from app.services import warmup_daily_variety as variety
from app.services import warmup_ask_spacing as spacing


def _task(helper_id, created_day=1):
    return SimpleNamespace(helper_id=helper_id, created_at=datetime(2026, 5, created_day, 0, 0))


NOW = datetime(2026, 5, 4, 9, 0)   # Tehran-naive, inside the 09:00–19:00 window


# ── spacing bumped to 55 minutes ─────────────────────────────────────────────
def test_ask_spacing_is_55_minutes():
    assert spacing.ASK_MIN_SPACING_MINUTES == 55


def test_ask_spacing_gate_blocks_below_55_allows_at_55():
    assert spacing.ask_spacing_ok(NOW - timedelta(minutes=54), NOW) is False  # too soon → blocked
    assert spacing.ask_spacing_ok(NOW - timedelta(minutes=55), NOW) is True   # exactly 55 → allowed
    assert spacing.ask_spacing_ok(NOW - timedelta(minutes=90), NOW) is True
    assert spacing.ask_spacing_ok(None, NOW) is True                          # first ask ever


def test_ten_asks_fit_the_working_window_at_55min():
    # 09:00–19:00 = 600 min; 10 asks need 9 gaps × 55 = 495 min ≤ 600 → they fit comfortably.
    assert 9 * spacing.ASK_MIN_SPACING_MINUTES <= 600


# ── history reducers ─────────────────────────────────────────────────────────
def test_distinct_asked_today_by_sender():
    rows = [
        ("H1", "S1", datetime(2026, 5, 4, 9, 30)),   # today
        ("H2", "S1", datetime(2026, 5, 4, 11, 0)),   # today
        ("H1", "S1", datetime(2026, 5, 4, 15, 0)),   # today again, same contact → still 1
        ("H3", "S1", datetime(2026, 5, 3, 10, 0)),   # yesterday → excluded
        ("H4", "S2", datetime(2026, 5, 4, 9, 0)),    # today, other sender
        ("H5", "S1", None),                          # never asked → ignored
    ]
    got = variety.distinct_asked_today_by_sender(rows, NOW)
    assert got["S1"] == {"H1", "H2"}
    assert got["S2"] == {"H4"}


def test_last_ask_by_helper_takes_the_max():
    rows = [
        ("H1", "S1", datetime(2026, 5, 1, 9, 0)),
        ("H1", "S1", datetime(2026, 5, 3, 9, 0)),    # newer wins
        ("H2", "S1", None),                          # never asked → absent
    ]
    la = variety.last_ask_by_helper(rows)
    assert la["H1"] == datetime(2026, 5, 3, 9, 0)
    assert "H2" not in la


# ── selection: variety + least-recently-asked ────────────────────────────────
def test_never_asked_contacts_come_first():
    pending = [_task("A"), _task("B"), _task("C")]
    helper_sender = {"A": "S1", "B": "S1", "C": "S1"}
    last_ask = {"A": datetime(2026, 5, 3, 10, 0), "B": datetime(2026, 5, 2, 10, 0)}  # C never asked
    ordered = variety.eligible_pending_ordered(
        pending, helper_sender=helper_sender, last_ask=last_ask, asked_today_by_sender={})
    assert [str(t.helper_id) for t in ordered] == ["C", "B", "A"]  # never-asked, then oldest ask


def test_contact_already_asked_today_is_skipped():
    pending = [_task("A"), _task("B")]
    helper_sender = {"A": "S1", "B": "S1"}
    ordered = variety.eligible_pending_ordered(
        pending, helper_sender=helper_sender, last_ask={},
        asked_today_by_sender={"S1": {"A"}})
    assert [str(t.helper_id) for t in ordered] == ["B"]  # A already had its turn today


def test_daily_cap_blocks_all_when_reached():
    asked = {f"H{i}" for i in range(variety.DAILY_DISTINCT_CONTACT_CAP)}  # 10 distinct today
    pending = [_task("NEW")]
    ordered = variety.eligible_pending_ordered(
        pending, helper_sender={"NEW": "S1"}, last_ask={},
        asked_today_by_sender={"S1": asked})
    assert ordered == []  # sender hit its 10-distinct ceiling → no 11th contact


def _simulate_day(n_contacts):
    """Drive the pure selection like the engine would across a day: repeatedly take the top
    candidate, 'ask' it (mark asked today + remove from pending), until nothing is eligible."""
    sender = "S1"
    pending = [_task(f"H{i}", created_day=1) for i in range(n_contacts)]
    helper_sender = {f"H{i}": sender for i in range(n_contacts)}
    last_ask, asked_today = {}, {sender: set()}
    picked = []
    for _ in range(n_contacts + 15):   # plenty of ticks
        ordered = variety.eligible_pending_ordered(
            pending, helper_sender=helper_sender, last_ask=last_ask,
            asked_today_by_sender=asked_today)
        if not ordered:
            break
        t = ordered[0]
        hid = str(t.helper_id)
        picked.append(hid)
        asked_today[sender].add(hid)
        last_ask[hid] = NOW
        pending = [p for p in pending if p is not t]
    return picked


def test_exactly_ten_distinct_contacts_when_many_eligible():
    picked = _simulate_day(15)                 # 15 eligible contacts
    assert len(picked) == 10                    # capped at 10 asks
    assert len(set(picked)) == 10               # and all 10 are DIFFERENT contacts


def test_asks_all_when_fewer_than_ten_eligible():
    picked = _simulate_day(4)                    # only 4 eligible
    assert len(picked) == 4                       # sends to however many are eligible
    assert len(set(picked)) == 4                  # each exactly once


def test_multiple_senders_are_capped_independently():
    pending = ([SimpleNamespace(helper_id=f"A{i}", created_at=datetime(2026, 5, 1, 0, i)) for i in range(3)] +
               [SimpleNamespace(helper_id=f"B{i}", created_at=datetime(2026, 5, 1, 0, i)) for i in range(3)])
    helper_sender = {**{f"A{i}": "S1" for i in range(3)}, **{f"B{i}": "S2" for i in range(3)}}
    # S1 already asked its 10 today → all S1 pending blocked; S2 fresh → its pending survive.
    asked_today = {"S1": {f"x{i}" for i in range(10)}, "S2": set()}
    ordered = variety.eligible_pending_ordered(
        pending, helper_sender=helper_sender, last_ask={}, asked_today_by_sender=asked_today)
    senders = {helper_sender[str(t.helper_id)] for t in ordered}
    assert senders == {"S2"}   # only the un-capped sender's contacts remain eligible
