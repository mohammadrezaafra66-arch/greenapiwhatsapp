"""V41 PART 5 — dashboard visibility + end-to-end recovery simulation.

Proves the mesh dashboard clearly surfaces a recovery re-warm — recovery-mode status, day-index,
assigned peer, and the restart-on-disruption reset counter — and ties the pieces together end to
end: the recovery timeline reaches GRADUATED only at the expected day; a mid-cycle disruption resets
it to Day 1 and the dashboard reflects the reset; the TC sender pause holds throughout; and no other
enrollment is ever flagged/touched.
"""
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.warmup_dashboard import (
    build_number_card, build_dashboard, GRADUATE_DAY, RECOVERY_BADGE_FA, RECOVERY_RESET_LABEL_FA,
)
from app.services.warmup_scheduler import target_state_for_day, RECOVERY_GRADUATE_DAY
from app.services.warmup_state import WarmupState
from app.services.warmup_killswitch import recovery_disruption_reset
from app.services.sender_eligibility import enrollment_in_mesh_recovery

NOW = datetime(2026, 7, 23, 12, 0, 0)


class _FakeDB:
    """Minimal session: recovery_disruption_reset + _alert only ever call db.add."""
    def __init__(self):
        self.added = []
    def add(self, obj):
        self.added.append(obj)


def _enr(day=0, recovery=False, **kw):
    # Anchor so day_index(enr, NOW) == `day` (>=1); day<=0 → no anchor → computed 0.
    anchor = None if day <= 0 else NOW - timedelta(days=day - 1)
    base = dict(instance_id="7105325764", phone="989122270261",
                state=kw.pop("state", WarmupState.COOLDOWN.value),
                day_index=day, sent_today=0, received_today=0, reply_ratio=0.0,
                is_enabled=recovery, next_action_at=None, rest_until=None,
                authorized_at=anchor, started_at=anchor,
                recovery_mode=recovery, recovery_reset_count=0,
                recovery_last_reset_at=None, recovery_last_reset_reason=None)
    base.update(kw)
    e = SimpleNamespace(**base)
    e.id = uuid.uuid4()
    return e


# ── 5.1 dashboard visibility ────────────────────────────────────────────────────────────────────
def test_recovery_card_surfaces_recovery_fields():
    e = _enr(day=6, recovery=True, state=WarmupState.RAMPING.value, recovery_reset_count=2,
             recovery_last_reset_at=NOW - timedelta(days=1), recovery_last_reset_reason="yellowCard")
    card = build_number_card(e, [], NOW)
    assert card["recovery_mode"] is True
    assert card["recovery_badge"] == RECOVERY_BADGE_FA
    assert card["recovery_reset_count"] == 2                       # "reset X times due to disruption"
    assert card["recovery_reset_label"] == RECOVERY_RESET_LABEL_FA
    assert card["recovery_last_reset_reason"] == "yellowCard"
    assert card["recovery_last_reset_at"] is not None
    assert card["day_index"] == 6                                  # current day-index shown
    assert card["graduate_day"] == RECOVERY_GRADUATE_DAY           # recovery horizon, not 25
    assert card["progress_pct"] == 50                             # 6 / 12


def test_assigned_peer_is_shown_on_the_card():
    e = _enr(day=3, recovery=True, state=WarmupState.RECEIVING.value)
    edge = SimpleNamespace(new_instance_id="7105325764", peer_instance_id="770022690011",
                           msg_count=2, last_msg_at=NOW, handshake_state="active",
                           saved_as_contact_new=True, saved_as_contact_peer=True, id=uuid.uuid4())
    card = build_number_card(e, [edge], NOW)
    assert card["assigned_peer"] == "770022690011"


def test_non_recovery_card_is_unchanged():
    e = _enr(day=6, recovery=False, state=WarmupState.RAMPING.value)
    card = build_number_card(e, [], NOW)
    assert card["recovery_mode"] is False
    assert card["recovery_badge"] is None
    assert card["recovery_reset_count"] == 0
    assert card["graduate_day"] == GRADUATE_DAY                    # 25 — general onboarding horizon
    assert card["progress_pct"] == 24                             # 6 / 25, unchanged


# ── 5.2 end-to-end simulation ─────────────────────────────────────────────────────────────────
def test_recovery_timeline_reaches_graduated_only_at_day_12():
    seq = {d: target_state_for_day(d, WarmupState.COOLDOWN.value, recovery=True) for d in range(0, 14)}
    assert seq[0] == seq[1] == WarmupState.COOLDOWN.value          # GA day1 no-link / day2 authorize-only
    assert seq[2] == seq[3] == seq[4] == WarmupState.RECEIVING.value   # GA days 3–5 receiving
    assert seq[5] == WarmupState.REPLYING.value                    # GA day6 replies begin
    assert all(seq[d] == WarmupState.RAMPING.value for d in (6, 7, 8, 9, 10, 11))  # 12→100 ramp
    assert seq[12] == seq[13] == WarmupState.GRADUATED.value
    # never graduates early
    assert all(seq[d] != WarmupState.GRADUATED.value for d in range(0, RECOVERY_GRADUATE_DAY))


@pytest.mark.asyncio
async def test_mid_cycle_disruption_resets_to_day1_and_dashboard_shows_it():
    e = _enr(day=5, recovery=True, state=WarmupState.RECEIVING.value)
    db = _FakeDB()
    res = await recovery_disruption_reset(db, e, "yellowCard", NOW)

    assert res["day_index"] == 0 and res["reset_count"] == 1
    assert e.state == WarmupState.COOLDOWN.value                   # hard restart to Day 1
    assert e.recovery_reset_count == 1
    # the reset is logged as a durable event (reset event + Persian alert)
    assert any(getattr(o, "event_type", None) == "recovery_reset" for o in db.added)

    card = build_number_card(e, [], NOW)                           # re-anchored to NOW → computed day 1
    assert card["day_index"] == 1
    assert card["state"] == WarmupState.COOLDOWN.value
    assert card["recovery_reset_count"] == 1                       # counter now visible on the card
    assert card["recovery_last_reset_reason"] == "yellowCard"


def test_tc_sender_pause_holds_through_recovery_then_clears_on_graduation():
    mid = _enr(day=3, recovery=True, state=WarmupState.RECEIVING.value)
    assert enrollment_in_mesh_recovery(mid) is True               # paused as TC sender while recovering
    graduated = _enr(day=12, recovery=True, state=WarmupState.GRADUATED.value)
    assert enrollment_in_mesh_recovery(graduated) is False        # done recovering → no longer paused


def test_only_the_recovery_number_is_flagged_no_other_enrollment_touched():
    rec = _enr(day=3, recovery=True, state=WarmupState.RECEIVING.value, instance_id="7105325764")
    other1 = _enr(day=0, recovery=False, state=WarmupState.PAUSED.value, instance_id="770022683809")
    other2 = _enr(day=0, recovery=False, state=WarmupState.BLOCKED_RESET.value, instance_id="770022682882")
    dash = build_dashboard([rec, other1, other2], {}, now=NOW)
    cards = {c["instance_id"]: c for c in dash["numbers"]}
    assert cards["7105325764"]["recovery_mode"] is True
    assert cards["770022683809"]["recovery_mode"] is False
    assert cards["770022682882"]["recovery_mode"] is False
    assert sum(1 for c in dash["numbers"] if c["recovery_mode"]) == 1   # exactly one recovery card
