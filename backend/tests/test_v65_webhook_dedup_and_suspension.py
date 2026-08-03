"""V65 — two defects that together made a burnt account look healthy and delivered look 0%.

DEFECT 1 — the webhook dedup key was (instance_id, idMessage). One message legitimately emits
several webhooks carrying the SAME idMessage: the send notification, then a status webhook per
transition (sent → delivered → read). The send notification claimed the key first, so every
status that followed was dropped as a duplicate and `delivery_status` was never written. Live
proof: the first real campaign sent 30 messages, Green API reported 15 delivered, the dashboard
showed 0%.

DEFECT 2 — a Green API spam suspension changed `accounts.status` but wrote NO incident row.
Every health judgement counts incident rows, so on 2026-08-03 instance 770022683838 was
suspended for seven days and still reported warmth 80 «بالا» with incident_count_7d = 0 —
i.e. it stayed eligible to be chosen for the next campaign.
"""
import inspect

import pytest

from app.api.v1.webhook import _dedup_key
from app.services import incident_handler, state_monitor
from app.services.warmup_peer_eligibility import DISQUALIFYING_INCIDENT_TYPES
from app.services.warmup_warmth import compute_warmth

INST = "770022683838"
MID = "3EB01A3A175DD4731D3406"


def _code(fn) -> str:
    """Source with the docstring stripped, so an assertion about the CODE is not satisfied — or
    broken — by prose in the docstring that mentions the same identifier."""
    parts = inspect.getsource(fn).split('"""')
    return parts[0] + "".join(parts[2:]) if len(parts) >= 3 else parts[0]


def _wh(wtype, mid=MID, status=None):
    p = {"typeWebhook": wtype, "idMessage": mid}
    if status is not None:
        p["status"] = status
    return p


# ── DEFECT 1: the dedup key ─────────────────────────────────────────────────
def test_the_send_notification_no_longer_swallows_the_status_webhooks():
    """The exact live failure: one idMessage, four events, only the first survived."""
    keys = {
        _dedup_key(INST, _wh("outgoingAPIMessageWebhook")),
        _dedup_key(INST, _wh("outgoingMessageStatus", status="sent")),
        _dedup_key(INST, _wh("outgoingMessageStatus", status="delivered")),
        _dedup_key(INST, _wh("outgoingMessageStatus", status="read")),
    }
    assert len(keys) == 4, "each of the four events must have its own dedup identity"


def test_a_message_can_progress_sent_then_delivered_then_read():
    seen = set()
    survived = []
    for st in ("sent", "delivered", "read"):
        k = _dedup_key(INST, _wh("outgoingMessageStatus", status=st))
        if k not in seen:
            seen.add(k)
            survived.append(st)
    assert survived == ["sent", "delivered", "read"]


def test_the_genuine_duplicate_is_still_blocked():
    """Green API redelivering the EXACT same event must still be dropped — that is what the
    guard is for, and the fix must not weaken it."""
    a = _dedup_key(INST, _wh("outgoingMessageStatus", status="delivered"))
    b = _dedup_key(INST, _wh("outgoingMessageStatus", status="delivered"))
    assert a == b


def test_the_same_event_on_two_instances_stays_separate():
    assert _dedup_key("770022683809", _wh("outgoingMessageStatus", status="sent")) != \
           _dedup_key("770022683810", _wh("outgoingMessageStatus", status="sent"))


def test_different_messages_stay_separate():
    assert _dedup_key(INST, _wh("outgoingMessageStatus", "AAA", "sent")) != \
           _dedup_key(INST, _wh("outgoingMessageStatus", "BBB", "sent"))


def test_incoming_messages_still_dedupe_by_id():
    a = _dedup_key(INST, _wh("incomingMessageReceived", "XYZ"))
    b = _dedup_key(INST, _wh("incomingMessageReceived", "XYZ"))
    assert a == b
    assert a != _dedup_key(INST, _wh("incomingMessageReceived", "OTHER"))


def test_a_payload_missing_fields_does_not_crash():
    for p in ({}, {"idMessage": "x"}, {"typeWebhook": "y"}, {"status": "sent"}):
        assert isinstance(_dedup_key(INST, p), str)


def test_the_guard_receives_the_whole_payload_not_just_the_id():
    """A signature taking only `id_message` cannot see the type — the old shape must be gone."""
    sig = inspect.signature(__import__(
        "app.api.v1.webhook", fromlist=["_already_processed"])._already_processed)
    assert "payload" in sig.parameters
    assert "id_message" not in sig.parameters


# ── DEFECT 2: a suspension is an incident ───────────────────────────────────
def test_suspended_now_disqualifies_a_peer():
    assert "suspended" in DISQUALIFYING_INCIDENT_TYPES


def test_the_other_disqualifying_types_are_untouched():
    for t in ("yellowCard", "blocked", "notAuthorized", "logout"):
        assert t in DISQUALIFYING_INCIDENT_TYPES


def test_one_counted_incident_collapses_the_warmth_score():
    """The live row: 18.8 days old, no activity → 80 «بالا» while suspended. With the
    suspension counted, the incident component zeroes and it can no longer read as high."""
    healthy = compute_warmth(age_days=18.8, recent_incident_count=0, days_since_activity=None)
    burnt = compute_warmth(age_days=18.8, recent_incident_count=1,
                           days_since_activity=None, eligible=False)
    assert healthy["score"] == 80 and healthy["level"] == "بالا"
    assert burnt["score"] < healthy["score"]
    assert burnt["level"] != "بالا"


def test_recording_a_suspension_is_idempotent_per_open_incident():
    """The 60s poll must add one row, not one per tick."""
    src = _code(incident_handler.record_suspension)
    assert "resolved.is_(False)" in src
    assert "return None" in src


def test_a_suspension_bumps_the_counter_health_reads():
    src = _code(incident_handler.record_suspension)
    assert "incident_count_7d" in src
    assert "last_incident_at" in src


def test_a_suspension_does_not_invent_a_cooldown():
    """The suspension already blocks sending via the gate; an extra cooldown would outlive the
    restriction and sideline a recovered number."""
    assert "cooldown_until" not in _code(incident_handler.record_suspension)


def test_recovery_closes_the_incident():
    src = _code(incident_handler.resolve_suspension)
    assert "resolved = True" in src
    assert "resolved_at" in src


def test_both_detection_paths_record_the_suspension():
    """A suspension can be learned from the webhook OR the 60s poll — both must write it."""
    from app.api.v1 import webhook as wh
    assert "record_suspension" in inspect.getsource(wh.handle_state_change)
    assert "record_suspension" in inspect.getsource(state_monitor.apply_state)


def test_the_poll_path_also_resolves_on_recovery():
    assert "resolve_suspension" in inspect.getsource(state_monitor.apply_state)


def test_suspended_is_still_a_danger_state():
    assert "suspended" in state_monitor.DANGER_STATES


@pytest.mark.parametrize("state", ["yellowcard", "blocked", "notauthorized", "logout", "suspended"])
def test_every_danger_state_survives_the_change(state):
    assert state in state_monitor.DANGER_STATES
