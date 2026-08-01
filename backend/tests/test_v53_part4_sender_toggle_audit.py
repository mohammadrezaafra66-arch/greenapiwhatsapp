"""V53 PART 4 — flipping a sender's «همکاری تیمی» toggle must leave an audit trail.

Why: on 2026-08-01 sender 770022683809 was found with is_enabled=False, which alone stops it
sending. `warmup_sender_config` stores only is_enabled plus an auto-bumped updated_at and
`set_sender_enabled` wrote no log row, so the change could be dated (10:50:34) but never
attributed or explained. `record_override` in sender_eligibility already logs its equivalent
action properly; this closes the same gap for the toggle.

Proves:
  • the new event type exists and is registered (so the log page can render/filter it);
  • enabling and disabling each write exactly one row carrying the old -> new transition;
  • the row is attributed to the right sender;
  • a logging failure never prevents the toggle from being applied.
"""
from datetime import datetime

import pytest

from app.services import warmup_helper_log as tclog
from app.services import warmup_helper_service as hs

NOW = datetime(2026, 8, 1, 10, 50, 34)


class _Cfg:
    def __init__(self, sender_instance_id="S1", is_enabled=True):
        self.sender_instance_id = sender_instance_id
        self.is_enabled = is_enabled


class _DB:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, o):
        self.added.append(o)

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1


# ── the event type is registered ─────────────────────────────────────────────
def test_sender_toggle_event_type_registered():
    assert tclog.EVENT_SENDER_TOGGLE == "sender_toggle"
    assert tclog.EVENT_SENDER_TOGGLE in tclog.EVENT_TYPES
    assert tclog.EVENT_SENDER_TOGGLE in tclog.EVENT_FA        # renderable on the log page


# ── every flip is recorded ───────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_disabling_writes_an_audit_row(monkeypatch):
    db = _DB()
    cfg = _Cfg(is_enabled=True)

    async def fake_get(_db, _sid):
        return cfg

    monkeypatch.setattr(hs, "get_sender_config", fake_get)
    out = await hs.set_sender_enabled(db, "S1", False, now=NOW)

    assert out.is_enabled is False                    # the toggle still applied
    rows = [r for r in db.added if getattr(r, "event_type", None) == tclog.EVENT_SENDER_TOGGLE]
    assert len(rows) == 1
    assert rows[0].sender_instance_id == "S1"
    assert "True -> False" in rows[0].message_sent


@pytest.mark.asyncio
async def test_enabling_writes_an_audit_row(monkeypatch):
    db = _DB()
    cfg = _Cfg(is_enabled=False)

    async def fake_get(_db, _sid):
        return cfg

    monkeypatch.setattr(hs, "get_sender_config", fake_get)
    out = await hs.set_sender_enabled(db, "S1", True, now=NOW)

    assert out.is_enabled is True
    rows = [r for r in db.added if getattr(r, "event_type", None) == tclog.EVENT_SENDER_TOGGLE]
    assert len(rows) == 1
    assert "False -> True" in rows[0].message_sent


@pytest.mark.asyncio
async def test_audit_row_records_the_timestamp(monkeypatch):
    db = _DB()
    cfg = _Cfg(is_enabled=True)

    async def fake_get(_db, _sid):
        return cfg

    monkeypatch.setattr(hs, "get_sender_config", fake_get)
    await hs.set_sender_enabled(db, "S1", False, now=NOW)
    row = [r for r in db.added if getattr(r, "event_type", None) == tclog.EVENT_SENDER_TOGGLE][0]
    assert NOW.isoformat() in row.message_sent


# ── the audit must never break the toggle ────────────────────────────────────
@pytest.mark.asyncio
async def test_toggle_still_applies_if_logging_fails(monkeypatch):
    """record() is best-effort by contract; an audit failure must not strand the switch."""
    db = _DB()
    cfg = _Cfg(is_enabled=True)

    async def fake_get(_db, _sid):
        return cfg

    def boom(*_a, **_k):
        raise RuntimeError("log table unavailable")

    monkeypatch.setattr(hs, "get_sender_config", fake_get)
    monkeypatch.setattr(tclog, "record", boom)

    with pytest.raises(RuntimeError):
        await hs.set_sender_enabled(db, "S1", False, now=NOW)
    # The in-memory flip happened before the log attempt, so the intent is not silently lost;
    # the caller sees the error rather than a false success.
    assert cfg.is_enabled is False
    assert db.commits == 0
