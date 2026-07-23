"""V41 Path B PART 2 — dashboard visibility for the pending auto-apply state.

Proves the mesh dashboard payload reflects the LAST recheck's findings while 7105325764 is not yet
enrolled in recovery mode, and that once enrolled the pending note gives way to the normal recovery
card (recovery_mode/day-index) from V41 PART 5.
"""
from datetime import datetime
from types import SimpleNamespace

from app.services.warmup_dashboard import build_recovery_pending, build_dashboard
from app.services.warmup_state import WarmupState

NOW = datetime(2026, 7, 29, 1, 30, 0)


# ── pending note mirrors the last recheck finding ────────────────────────────
def test_pending_note_blocked_breaker_and_no_peer():
    note = build_recovery_pending({"breaker_tripped": True, "peer_qualifies": False,
                                   "at": "2026-07-23T01:30:00"})
    assert note["waiting"] is True
    assert note["breaker_tripped"] is True and note["peer_qualifies"] is False
    assert "بریکر: فعال" in note["message"]                    # breaker active/tripped
    assert "یافت نشد" in note["message"]                       # peer not found
    assert note["last_checked_at"] == "2026-07-23T01:30:00"


def test_pending_note_clear_and_peer_found():
    note = build_recovery_pending({"breaker_tripped": False, "peer_qualifies": True,
                                   "at": "2026-07-29T01:30:00"})
    assert "بریکر: پاک شده" in note["message"]                 # breaker clear
    assert "یافت شد" in note["message"]                        # peer found
    assert note["breaker_tripped"] is False and note["peer_qualifies"] is True


def test_pending_note_when_no_recheck_yet():
    note = build_recovery_pending(None)
    assert note["waiting"] is True
    assert note["breaker_tripped"] is None and note["peer_qualifies"] is None
    assert "هنوز بررسی خودکار انجام نشده" in note["message"]


# ── dashboard payload carries the pending note (pending state) ───────────────
def test_dashboard_includes_pending_note():
    note = build_recovery_pending({"breaker_tripped": True, "peer_qualifies": False, "at": None})
    dash = build_dashboard([], {}, breaker_tripped=False, now=NOW, recovery_pending=note)
    assert dash["recovery_pending"] is note
    assert dash["recovery_pending"]["waiting"] is True


# ── once enrolled: pending note is absent, normal recovery card shows ─────────
def test_dashboard_switches_to_recovery_card_when_enrolled():
    enr = SimpleNamespace(instance_id="7105325764", phone="7105325764",
                          state=WarmupState.COOLDOWN.value, day_index=0, is_enabled=True,
                          recovery_mode=True, recovery_reset_count=0, sent_today=0, received_today=0,
                          reply_ratio=0.0, next_action_at=None, rest_until=None,
                          started_at=NOW, authorized_at=NOW)
    # The endpoint passes recovery_pending=None once the target is enrolled in recovery mode.
    dash = build_dashboard([enr], {}, breaker_tripped=False, now=NOW, recovery_pending=None)
    assert dash["recovery_pending"] is None
    card = dash["numbers"][0]
    assert card["recovery_mode"] is True
    assert card["recovery_badge"] is not None       # normal V41 PART 5 recovery view
    assert card["state"] == WarmupState.COOLDOWN.value
