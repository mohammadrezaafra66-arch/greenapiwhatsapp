"""V53 PART 5 — one unusable pairing must not starve a cold account's healthy contacts.

The lock-up this pins. `run_team_schedule_tick` used to pick the single least-progressed thread
and only THEN check whether its contact was active, its sender toggled on, and its sender
resolvable — `continue`ing the WHOLE enrollment when any of those failed. Since
`select_thread_for_step` is deterministic (lowest step_count, then longest idle), the same dead
thread was re-picked on every tick forever.

Live effect: cold accounts 770022683809 and 770022683810 each had 31 assigned contacts, only 2
of them active. The selection always landed on a DEACTIVATED contact belonging to the
mesh-recovering sender 7105325764, so neither cold account could ever reach its two healthy
contacts. Enrolling them would have produced silence, not messages.

Proves:
  • with no restriction the old behaviour is preserved (backward compatible);
  • an unusable thread is skipped in favour of a usable one, even when the unusable one sorts first;
  • the ordering preference (least-progressed, then longest-idle) still holds among usable threads;
  • None is returned only when NO usable thread is due;
  • paused / already-stepped-today threads are still excluded;
  • the tick pre-filters on all three permanent conditions.
"""
import inspect
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.services import warmup_team_schedule as ts
from app.services import warmup_helper_thread as wt

NOW = datetime(2026, 8, 1, 12, 0)


def _thread(helper_id, step_count=0, last_step_at=None, status=wt.STATUS_ACTIVE):
    return SimpleNamespace(id=uuid.uuid4(), helper_id=helper_id, step_count=step_count,
                           last_step_at=last_step_at, status=status)


# ── backward compatibility ───────────────────────────────────────────────────
def test_no_restriction_keeps_old_behaviour():
    dead, alive = uuid.uuid4(), uuid.uuid4()
    threads = [_thread(dead, step_count=0), _thread(alive, step_count=5)]
    chosen = ts.select_thread_for_step(threads, NOW)
    assert chosen.helper_id == dead          # least-progressed wins, as before


# ── the fix ──────────────────────────────────────────────────────────────────
def test_unusable_thread_is_skipped_for_a_usable_one():
    """The exact live shape: the dead thread sorts FIRST but must not be chosen."""
    dead, alive = uuid.uuid4(), uuid.uuid4()
    threads = [_thread(dead, step_count=0), _thread(alive, step_count=5)]
    chosen = ts.select_thread_for_step(threads, NOW, usable_helper_ids={alive})
    assert chosen is not None
    assert chosen.helper_id == alive


def test_many_dead_contacts_do_not_hide_the_one_healthy_one():
    """31 assigned contacts, 1 usable — the live ratio."""
    dead = [uuid.uuid4() for _ in range(30)]
    alive = uuid.uuid4()
    threads = [_thread(d, step_count=0) for d in dead] + [_thread(alive, step_count=9)]
    chosen = ts.select_thread_for_step(threads, NOW, usable_helper_ids={alive})
    assert chosen.helper_id == alive


def test_ordering_still_applies_among_usable_threads():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    threads = [_thread(a, step_count=0),            # unusable
               _thread(b, step_count=3),            # usable, more progressed
               _thread(c, step_count=1)]            # usable, least progressed
    chosen = ts.select_thread_for_step(threads, NOW, usable_helper_ids={b, c})
    assert chosen.helper_id == c


def test_tie_breaks_on_longest_idle_among_usable():
    a, b = uuid.uuid4(), uuid.uuid4()
    threads = [_thread(a, step_count=2, last_step_at=NOW - timedelta(days=1)),
               _thread(b, step_count=2, last_step_at=NOW - timedelta(days=5))]
    chosen = ts.select_thread_for_step(threads, NOW, usable_helper_ids={a, b})
    assert chosen.helper_id == b              # idle longest


# ── nothing usable / other exclusions still hold ─────────────────────────────
def test_none_when_nothing_usable():
    dead = uuid.uuid4()
    threads = [_thread(dead)]
    assert ts.select_thread_for_step(threads, NOW, usable_helper_ids=set()) is None
    assert ts.select_thread_for_step(threads, NOW, usable_helper_ids={uuid.uuid4()}) is None


def test_paused_thread_still_excluded_even_if_usable():
    hid = uuid.uuid4()
    threads = [_thread(hid, status="paused")]
    assert ts.select_thread_for_step(threads, NOW, usable_helper_ids={hid}) is None


def test_already_stepped_today_still_excluded_even_if_usable():
    hid = uuid.uuid4()
    threads = [_thread(hid, last_step_at=NOW - timedelta(hours=2))]
    assert ts.select_thread_for_step(threads, NOW, usable_helper_ids={hid}) is None


def test_usable_thread_stepped_today_does_not_mask_a_fresh_one():
    stale, fresh = uuid.uuid4(), uuid.uuid4()
    threads = [_thread(stale, step_count=0, last_step_at=NOW - timedelta(hours=1)),
               _thread(fresh, step_count=4)]
    chosen = ts.select_thread_for_step(threads, NOW, usable_helper_ids={stale, fresh})
    assert chosen.helper_id == fresh


# ── the tick actually uses the filter ────────────────────────────────────────
def test_tick_prefilters_before_selecting():
    src = inspect.getsource(ts.run_team_schedule_tick)
    assert "usable_helper_ids" in src
    # the filter must be built BEFORE the selection call, not after
    assert src.index("usable_helper_ids = set()") < src.index("select_thread_for_step(")


def test_tick_filters_on_all_three_permanent_conditions():
    src = inspect.getsource(ts.run_team_schedule_tick)
    head = src[src.index("usable_helper_ids = set()"):src.index("select_thread_for_step(")]
    assert "is_active" in head                 # deactivated contact
    assert "is_sender_enabled" in head         # per-sender toggle
    assert "resolve_task_sender" in head       # sender account not active
