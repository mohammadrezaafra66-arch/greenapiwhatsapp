"""V56 — every «همکاری تیمی» send path records delivery, closing the V53 PART 1 gap.

V53 PART 1 gave warmup_helper_log an id_message/delivery_ok contract but only wired the two ticks
named at the time (run_team_schedule_tick, run_thankyou_tick). Three send paths kept writing NULL:
the ask/reminder and inline thank-you in warmup_helper_engine, and the cold auto-reply in
warmup_cold_reply. Those are not rare paths — every ask that actually fired on 2026-08-01 came
through the engine one, so the live log could not answer "did this reach the person?" for any of
them.

Proves:
  • all five outbound sites forward id_message=mid / delivery_ok=bool(mid);
  • the non-send events (incoming, safety_flag, eligibility_override) deliberately do NOT claim a
    delivery — they are inbound/administrative and must stay NULL;
  • the contract still holds at the record() layer for each event type used by those sites.
"""
import inspect

import pytest

from app.services import warmup_helper_log as tclog
from app.services import warmup_helper_engine as engine
from app.services import warmup_cold_reply as cr
from app.services import warmup_team_schedule as ts
from app.services import warmup_thankyou as ty


def _wired(fn) -> bool:
    src = inspect.getsource(fn)
    return "id_message=mid" in src and "delivery_ok=bool(mid)" in src


# ── every outbound path carries the send result ─────────────────────────────
def test_team_schedule_tick_wired():
    assert _wired(ts.run_team_schedule_tick)


def test_thankyou_tick_wired():
    assert _wired(ty.run_thankyou_tick)


def test_cold_reply_tick_wired():
    assert _wired(cr.run_cold_reply_tick)


def test_engine_ask_and_reminder_wired():
    src = inspect.getsource(engine)
    ask_call = src[src.index("tclog.EVENT_REMINDER if kind =="):]
    assert "id_message=mid" in ask_call[:600]
    assert "delivery_ok=bool(mid)" in ask_call[:600]


def test_engine_inline_thankyou_wired():
    src = inspect.getsource(engine.handle_helper_incoming)
    ty_call = src[src.index("tclog.EVENT_THANK_YOU"):]
    assert "id_message=mid" in ty_call[:500]
    assert "delivery_ok=bool(mid)" in ty_call[:500]


def test_no_outbound_site_is_left_unwired():
    """Count the outbound record() calls and require each to carry the result."""
    src = inspect.getsource(engine)
    outbound_markers = ["tclog.EVENT_REMINDER if kind ==", "tclog.EVENT_THANK_YOU"]
    for marker in outbound_markers:
        assert marker in src, f"expected an outbound log call for {marker}"
        seg = src[src.index(marker): src.index(marker) + 600]
        assert "delivery_ok=bool(mid)" in seg, f"{marker} does not record delivery"


# ── inbound / administrative events must NOT claim delivery ────────────────
def test_incoming_event_does_not_claim_delivery():
    src = inspect.getsource(engine.handle_helper_incoming)
    seg = src[src.index("tclog.EVENT_INCOMING"): src.index("tclog.EVENT_INCOMING") + 400]
    assert "delivery_ok" not in seg, "an inbound message has no delivery status of ours"


def test_safety_event_does_not_claim_delivery():
    src = inspect.getsource(engine.handle_helper_incoming)
    seg = src[src.index("tclog.EVENT_SAFETY"): src.index("tclog.EVENT_SAFETY") + 400]
    assert "delivery_ok" not in seg


# ── the record() contract itself, for the newly-wired event types ──────────
class _FakeDB:
    def __init__(self):
        self.added = []

    def add(self, row):
        self.added.append(row)


@pytest.mark.parametrize("event", [
    tclog.EVENT_ASK, tclog.EVENT_REMINDER, tclog.EVENT_THANK_YOU, tclog.EVENT_COLD_REPLY,
])
def test_blocked_and_delivered_stay_distinguishable(event):
    db = _FakeDB()
    sent = tclog.record(db, event_type=event, message_sent="x",
                        id_message="ID-1", delivery_ok=True)
    blocked = tclog.record(db, event_type=event, message_sent="x", delivery_ok=False)
    unknown = tclog.record(db, event_type=event, message_sent="x")
    assert (sent.delivery_ok, bool(sent.id_message)) == (True, True)
    assert (blocked.delivery_ok, blocked.id_message) == (False, None)
    assert (unknown.delivery_ok, unknown.id_message) == (None, None)
