"""V14 PART C — message-control tests (edit window, delete/read payloads)."""
import asyncio
from datetime import datetime, timedelta
import pytest
from app.services.msgcontrol import edit_window_ok, edit_seconds_left, EDIT_WINDOW_SECONDS
from app.services.green_api import GreenAPIClient


# ── FEATURE 9 — 15-minute edit window ───────────────────────────────────────
def test_edit_window_within():
    assert edit_window_ok(datetime.utcnow() - timedelta(minutes=5)) is True


def test_edit_window_expired():
    assert edit_window_ok(datetime.utcnow() - timedelta(minutes=16)) is False


def test_edit_window_unknown_sent_at_is_false():
    # Unknown sent_at → reject (can't prove it's editable → avoid a silent failure).
    assert edit_window_ok(None) is False


def test_edit_seconds_left_counts_down():
    left = edit_seconds_left(datetime.utcnow() - timedelta(minutes=5))
    assert 0 < left <= EDIT_WINDOW_SECONDS
    assert edit_seconds_left(datetime.utcnow() - timedelta(minutes=20)) == 0


# ── client payload shapes ───────────────────────────────────────────────────
def _capture(client):
    calls = {}

    async def fake_post(endpoint, data=None, timeout=30):
        calls["endpoint"] = endpoint
        calls["data"] = data
        return {"idMessage": "X"}

    client._post = fake_post
    return calls


def test_delete_only_sender_flag():
    c = GreenAPIClient("111", "tok")
    calls = _capture(c)
    asyncio.run(c.delete_message_raw("9891@c.us", "M1", only_sender=True))
    assert calls["endpoint"] == "deleteMessage"
    assert calls["data"]["onlySenderDelete"] is True

    calls2 = _capture(c)
    asyncio.run(c.delete_message_raw("9891@c.us", "M1", only_sender=False))
    assert "onlySenderDelete" not in calls2["data"]     # omitted → delete for everyone


def test_read_chat_optional_message_id():
    c = GreenAPIClient("111", "tok")
    calls = _capture(c)
    asyncio.run(c.read_chat("9891@c.us"))
    assert calls["endpoint"] == "readChat"
    assert "idMessage" not in calls["data"]

    calls2 = _capture(c)
    asyncio.run(c.read_chat("9891@c.us", "M1"))
    assert calls2["data"]["idMessage"] == "M1"


def test_edit_message_shape():
    c = GreenAPIClient("111", "tok")
    calls = _capture(c)
    asyncio.run(c.edit_message_raw("9891@c.us", "M1", "new"))
    assert calls["endpoint"] == "editMessage"
    assert calls["data"]["idMessage"] == "M1" and calls["data"]["message"] == "new"


def test_as_chat_id_passthrough_and_normalize():
    c = GreenAPIClient("111", "tok")
    assert c._as_chat_id("120363000@g.us") == "120363000@g.us"   # full chatId kept
    assert c._as_chat_id("09123456789").endswith("@c.us")        # bare phone normalized
