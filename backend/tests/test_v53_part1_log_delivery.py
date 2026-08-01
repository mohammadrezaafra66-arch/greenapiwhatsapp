"""V53 PART 1 — the «همکاری تیمی» log must record DELIVERY, not intent.

The bug this pins: on 2026-08-01 a thank-you to a real contact was blocked one millisecond before
the log row was written —

    10:06:48,972  TC send blocked: sender 7105325764 fails eligibility (in_mesh_recovery)
    10:06:48,973  INSERT warmup_helper_log (event_type='thank_you', message_sent='هدیه جان، ...')

— and the row was indistinguishable from a delivered message. `warmup_helper_log` had no idMessage
and no success flag, so every historical `ask`/`thank_you` row overstated what real people received.

Proves:
  • `record()` defaults both new fields to None (unknown) — a caller that does not know must never
    imply delivery;
  • a genuine send stores Green API's idMessage and delivery_ok=True;
  • a gate-blocked send stores delivery_ok=False and NO idMessage;
  • the thank-you tick and the 10-day ask tick both propagate the real send result.
"""
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services import warmup_helper_log as tclog
from app.services import warmup_thankyou as ty
from app.services import warmup_team_schedule as ts

NOW = datetime(2026, 5, 4, 11, 0)


class _FakeDB:
    """Minimal session that only has to capture what record() adds."""

    def __init__(self):
        self.added = []

    def add(self, row):
        self.added.append(row)


# ── record(): the honest default ─────────────────────────────────────────────
def test_record_defaults_to_unknown_not_delivered():
    db = _FakeDB()
    row = tclog.record(db, event_type=tclog.EVENT_ASK, message_sent="سلام")
    assert row is not None
    # NULL == "we don't know", which is what every pre-V53 row must remain.
    assert row.delivery_ok is None
    assert row.id_message is None


def test_record_stores_a_real_send():
    db = _FakeDB()
    row = tclog.record(db, event_type=tclog.EVENT_ASK, message_sent="سلام",
                       id_message="AC7FF138FC1D6D314141A9FFF58E71C0", delivery_ok=True)
    assert row.delivery_ok is True
    assert row.id_message == "AC7FF138FC1D6D314141A9FFF58E71C0"


def test_record_stores_a_blocked_send_without_an_id():
    db = _FakeDB()
    row = tclog.record(db, event_type=tclog.EVENT_THANK_YOU, message_sent="ممنون",
                       id_message=None, delivery_ok=False)
    assert row.delivery_ok is False
    assert row.id_message is None


def test_blocked_and_delivered_rows_are_distinguishable():
    """The whole point: the two cases must not look identical any more."""
    db = _FakeDB()
    sent = tclog.record(db, event_type=tclog.EVENT_ASK, message_sent="متن یکسان",
                        id_message="ABC123", delivery_ok=True)
    blocked = tclog.record(db, event_type=tclog.EVENT_ASK, message_sent="متن یکسان",
                           delivery_ok=False)
    assert sent.message_sent == blocked.message_sent      # same text ...
    assert sent.delivery_ok != blocked.delivery_ok        # ... different truth
    assert bool(sent.id_message) and not blocked.id_message


# ── the thank-you tick propagates the real result ────────────────────────────
def _thread(**kw):
    return SimpleNamespace(
        id=uuid.uuid4(), helper_id=uuid.uuid4(), cold_instance_id="770022683809",
        topic_summary=None, step_count=1, status="active", last_step_at=None,
        awaiting_reply=False, pending_reply_at=None,
        awaiting_thankyou=True, pending_thankyou_at=NOW - timedelta(minutes=5), **kw)


@pytest.mark.asyncio
async def test_thankyou_tick_marks_blocked_send_as_not_delivered(monkeypatch):
    thread = _thread()
    helper = SimpleNamespace(id=thread.helper_id, name="هدیه طاهری", phone="989910728131",
                             sender_instance_id="7105325764", is_active=True,
                             job_title=None, years_experience=None, personal_benefit_note=None)
    sender = SimpleNamespace(instance_id="7105325764", name="main", api_token="t")
    captured = {}

    async def fake_send(*_a, **_k):
        return None                       # gate-blocked, exactly like the live incident

    def fake_record(db, **kw):
        captured.update(kw)
        return SimpleNamespace(**kw)

    monkeypatch.setattr(ty, "_send_as_sender", fake_send)
    monkeypatch.setattr(tclog, "record", fake_record)
    await _run_thankyou(monkeypatch, thread, helper, sender)

    assert captured["delivery_ok"] is False
    assert captured["id_message"] is None


@pytest.mark.asyncio
async def test_thankyou_tick_marks_real_send_as_delivered(monkeypatch):
    thread = _thread()
    helper = SimpleNamespace(id=thread.helper_id, name="هدیه طاهری", phone="989910728131",
                             sender_instance_id="7105325764", is_active=True,
                             job_title=None, years_experience=None, personal_benefit_note=None)
    sender = SimpleNamespace(instance_id="7105325764", name="main", api_token="t")
    captured = {}

    async def fake_send(*_a, **_k):
        return "IDMSG-REAL-1"

    def fake_record(db, **kw):
        captured.update(kw)
        return SimpleNamespace(**kw)

    monkeypatch.setattr(ty, "_send_as_sender", fake_send)
    monkeypatch.setattr(tclog, "record", fake_record)
    await _run_thankyou(monkeypatch, thread, helper, sender)

    assert captured["delivery_ok"] is True
    assert captured["id_message"] == "IDMSG-REAL-1"


async def _run_thankyou(monkeypatch, thread, helper, sender):
    """Drive run_thankyou_tick with everything around the send stubbed out."""
    class _Res:
        def __init__(self, items): self._items = items
        def scalars(self): return self
        def all(self): return self._items

    class _DB:
        async def execute(self, *_a, **_k):
            # first call: due threads; later: active accounts
            return _Res([thread]) if not getattr(self, "_used", False) else _Res([sender])
        async def get(self, *_a, **_k): return helper
        async def commit(self): pass
        def add(self, *_a, **_k): pass

    db = _DB()

    async def _execute(*_a, **_k):
        if not hasattr(db, "_used"):
            db._used = True
            return _Res([thread])
        return _Res([sender])

    db.execute = _execute
    monkeypatch.setattr(ty, "resolve_task_sender", lambda *a, **k: sender, raising=False)
    monkeypatch.setattr("app.services.warmup_helper_engine.resolve_task_sender",
                        lambda *a, **k: sender, raising=False)
    monkeypatch.setattr(ty.peer_pacer, "thankyou_ready", lambda *a, **k: True)
    monkeypatch.setattr(ty.peer_pacer, "record_thankyou", lambda *a, **k: None)

    async def fake_generate(**_k):
        return "هدیه جان، ممنونم! 🌟", "fallback"

    monkeypatch.setattr(ty, "generate_thank_you", fake_generate)
    return await ty.run_thankyou_tick(db, NOW)


# ── the ask tick uses the same contract ──────────────────────────────────────
def test_ask_tick_passes_send_result_to_the_log():
    """Guard the wiring itself: run_team_schedule_tick must forward id_message/delivery_ok."""
    import inspect
    src = inspect.getsource(ts.run_team_schedule_tick)
    assert "id_message=mid" in src
    assert "delivery_ok=bool(mid)" in src


def test_thankyou_tick_passes_send_result_to_the_log():
    import inspect
    src = inspect.getsource(ty.run_thankyou_tick)
    assert "id_message=mid" in src
    assert "delivery_ok=bool(mid)" in src
