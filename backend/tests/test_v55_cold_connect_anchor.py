"""V55 — the cold account's 24h cooldown must be datable without a mesh enrollment.

The bug: `post_auth_cooldown_elapsed` reads the MESH enrollment only. A cold account that was
never enrolled in the mesh warm-up yields `None` -> False *forever*, not for 24 hours. Live effect
on 2026-08-01: all seven enrolled cold accounts (770022695748/9, 695751/2/3, 693145, 698646) had
no mesh row, so `run_team_schedule_tick` skipped every one of them on every tick — the 10-day
cycle could never fire — and `cold_account_ready` blocked every cold auto-reply for the same
reason, killing the reply half of the warm-up.

V39 PART 1 had already made `accounts.connected_at` the universal 24h connect anchor
("mesh, campaigns AND Team Collaboration"), on the same 24-hour clock, and it IS populated for
exactly those QR/partner numbers.

Proves:
  • an account with only connect_at is correctly gated: blocked inside 24h, allowed after;
  • an account with only a mesh enrollment behaves exactly as before (no regression);
  • when BOTH anchors exist the stricter one wins — this can never be looser than before;
  • an account with NO anchor at all still fails CLOSED;
  • the boundary is exactly 24h;
  • cold_account_ready propagates the fix and still applies the health gate afterwards;
  • the team tick calls the new gate, not the mesh-only one.
"""
import inspect
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.services import warmup_team_schedule as ts
from app.services.send_gate import CONNECT_COOLDOWN_HOURS, connect_anchor
from app.services.warmup_cold_reply import (
    cold_intake_cooldown_elapsed, cold_account_ready, post_auth_cooldown_elapsed,
)

NOW = datetime(2026, 8, 1, 14, 0)


def _acc(connected_at=None, reconnected_at=None, status="active"):
    return SimpleNamespace(instance_id="C1", status=status, phone="98900",
                           connected_at=connected_at, reconnected_at=reconnected_at)


def _enr(authorized_at=None):
    return SimpleNamespace(instance_id="C1", authorized_at=authorized_at)


# ── the anchor helper ────────────────────────────────────────────────────────
def test_connect_anchor_distinguishes_missing_from_elapsed():
    assert connect_anchor(_acc()) is None
    ts_val = NOW - timedelta(days=3)
    assert connect_anchor(_acc(connected_at=ts_val)) == ts_val


def test_connect_anchor_falls_back_to_legacy_reconnected_at():
    ts_val = NOW - timedelta(days=3)
    assert connect_anchor(_acc(reconnected_at=ts_val)) == ts_val


# ── the live case: connect anchor only, no mesh row ─────────────────────────
def test_no_mesh_row_but_connected_long_ago_is_allowed():
    """The exact live shape — 770022695748 connected 2026-07-29, no mesh enrollment."""
    acc = _acc(connected_at=datetime(2026, 7, 29, 7, 49))
    assert post_auth_cooldown_elapsed(None, NOW) is False        # the old check: blocked forever
    assert cold_intake_cooldown_elapsed(acc, None, NOW) is True  # the new one: correctly allowed


def test_no_mesh_row_and_freshly_connected_is_blocked():
    """770022698646 connected 2026-08-01 12:30 — must stay blocked for its first 24h."""
    acc = _acc(connected_at=datetime(2026, 8, 1, 12, 30))
    assert cold_intake_cooldown_elapsed(acc, None, NOW) is False


def test_connect_cooldown_boundary_is_exactly_24h():
    anchor = NOW - timedelta(hours=CONNECT_COOLDOWN_HOURS)
    assert cold_intake_cooldown_elapsed(_acc(connected_at=anchor), None, NOW) is True
    just_inside = NOW - timedelta(hours=CONNECT_COOLDOWN_HOURS) + timedelta(minutes=1)
    assert cold_intake_cooldown_elapsed(_acc(connected_at=just_inside), None, NOW) is False


# ── no regression for accounts that DO have a mesh row ──────────────────────
def test_mesh_row_only_behaves_exactly_as_before():
    old_enr = _enr(authorized_at=NOW - timedelta(days=5))
    fresh_enr = _enr(authorized_at=NOW - timedelta(hours=2))
    acc = _acc()                                   # no connect anchor
    assert cold_intake_cooldown_elapsed(acc, old_enr, NOW) is post_auth_cooldown_elapsed(old_enr, NOW)
    assert cold_intake_cooldown_elapsed(acc, fresh_enr, NOW) is post_auth_cooldown_elapsed(fresh_enr, NOW)


def test_both_anchors_present_the_stricter_one_wins():
    old_enr = _enr(authorized_at=NOW - timedelta(days=5))       # clear
    fresh_acc = _acc(connected_at=NOW - timedelta(hours=1))     # still cooling
    assert cold_intake_cooldown_elapsed(fresh_acc, old_enr, NOW) is False

    fresh_enr = _enr(authorized_at=NOW - timedelta(hours=1))    # still cooling
    old_acc = _acc(connected_at=NOW - timedelta(days=5))        # clear
    assert cold_intake_cooldown_elapsed(old_acc, fresh_enr, NOW) is False

    # both clear -> allowed
    assert cold_intake_cooldown_elapsed(old_acc, old_enr, NOW) is True


def test_never_looser_than_the_old_check_when_a_mesh_row_exists():
    """Property: for any account, adding the connect anchor can only ever REMOVE permission."""
    for enr_age_h in (0, 1, 23, 24, 48):
        enr = _enr(authorized_at=NOW - timedelta(hours=enr_age_h))
        for acc_age_h in (0, 1, 23, 24, 48):
            acc = _acc(connected_at=NOW - timedelta(hours=acc_age_h))
            old = post_auth_cooldown_elapsed(enr, NOW)
            new = cold_intake_cooldown_elapsed(acc, enr, NOW)
            assert not (new and not old), (
                f"new gate allowed what the old one blocked (enr={enr_age_h}h acc={acc_age_h}h)")


# ── fail closed ─────────────────────────────────────────────────────────────
def test_no_anchor_at_all_still_fails_closed():
    assert cold_intake_cooldown_elapsed(_acc(), None, NOW) is False


def test_mesh_row_without_authorized_at_is_not_treated_as_an_anchor():
    """A row that exists but carries no timestamp dates nothing — must not unlock the gate."""
    assert cold_intake_cooldown_elapsed(_acc(), _enr(authorized_at=None), NOW) is False


# ── cold_account_ready still layers the health gate on top ──────────────────
def test_cold_account_ready_allows_a_dated_healthy_account():
    acc = _acc(connected_at=NOW - timedelta(days=3))
    ready, reason = cold_account_ready(acc, None, NOW)
    assert ready is True and reason == "ok"


def test_cold_account_ready_blocks_on_cooldown_before_looking_at_health():
    acc = _acc(connected_at=NOW - timedelta(hours=1))
    ready, reason = cold_account_ready(acc, None, NOW)
    assert ready is False and reason == "cooldown_24h"


def test_cold_account_ready_still_blocks_an_inactive_account():
    acc = _acc(connected_at=NOW - timedelta(days=3), status="banned")
    ready, reason = cold_account_ready(acc, None, NOW)
    assert ready is False and reason == "not_active"


def test_cold_account_ready_utc_now_defaults_to_now():
    """Existing callers pass only `now` — behaviour must be unchanged for them."""
    acc = _acc(connected_at=NOW - timedelta(days=3))
    assert cold_account_ready(acc, None, NOW) == cold_account_ready(acc, None, NOW, utc_now=NOW)


# ── wiring ──────────────────────────────────────────────────────────────────
def test_team_tick_uses_the_new_gate():
    src = inspect.getsource(ts.run_team_schedule_tick)
    assert "cold_intake_cooldown_elapsed(cold, mesh_enr" in src
    assert "post_auth_cooldown_elapsed(mesh_enr" not in src   # the mesh-only check is gone
    assert "_to_utc_naive(now)" in src                        # compared on the UTC clock
