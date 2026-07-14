"""V14 PART E — statuses & groups tests (Features 19, 22)."""
import asyncio
import pytest
from app.services.green_api import GreenAPIClient
from app.services.group_add import cap_ok, MAX_PER_MINUTE, MAX_PER_HOUR, GROUP_SIZE_LIMIT


# ── FEATURE 22 — rate cap predicate (5/min, 30/hr) ──────────────────────────
def test_cap_ok_under_limits():
    ok, _ = cap_ok(0, 0)
    assert ok is True
    ok, _ = cap_ok(MAX_PER_MINUTE - 1, MAX_PER_HOUR - 1)
    assert ok is True


def test_cap_blocks_at_minute_limit():
    ok, reason = cap_ok(MAX_PER_MINUTE, 0)
    assert ok is False
    assert "دقیقه" in reason


def test_cap_blocks_at_hour_limit():
    ok, reason = cap_ok(0, MAX_PER_HOUR)
    assert ok is False
    assert "ساعت" in reason


def test_cap_constants():
    assert (MAX_PER_MINUTE, MAX_PER_HOUR, GROUP_SIZE_LIMIT) == (5, 30, 1024)


# ── FEATURE 22 — checkWhatsapp gate blocks a non-WhatsApp number ─────────────
def test_checkwhatsapp_gate_blocks_non_whatsapp(monkeypatch):
    """Simulate the pipeline's first guard: existsWhatsapp=False → never add."""
    c = GreenAPIClient("111", "tok")
    added = []

    async def fake_check(phone):
        return False   # not on WhatsApp

    async def fake_add(group_id, phone):
        added.append(phone)
        return {"ok": True}

    c.check_whatsapp = fake_check
    c.add_group_participant = fake_add

    async def gate(phone):
        if not await c.check_whatsapp(phone):
            return "no_whatsapp"
        await c.add_group_participant("g@g.us", phone)
        return "added"

    assert asyncio.run(gate("989000000000")) == "no_whatsapp"
    assert added == []    # the add was never attempted


# ── FEATURE 19 — participants reach the status payload ──────────────────────
def _capture(client):
    calls = {}

    async def fake_post(endpoint, data=None, timeout=30):
        calls["endpoint"] = endpoint
        calls["data"] = data
        return {"idMessage": "S1"}

    client._post = fake_post
    return calls


def test_text_status_participants_included():
    c = GreenAPIClient("111", "tok")
    calls = _capture(c)
    asyncio.run(c.send_text_status_full("hi", participants=["989120000001", "120@c.us"]))
    assert calls["endpoint"] == "sendTextStatus"
    assert calls["data"]["participants"][0].endswith("@c.us")   # normalized
    assert "120@c.us" in calls["data"]["participants"]


def test_public_status_omits_participants():
    c = GreenAPIClient("111", "tok")
    calls = _capture(c)
    asyncio.run(c.send_text_status_full("hi", participants=None))
    assert "participants" not in calls["data"]     # omitted ⇒ public


def test_voice_status_schema():
    c = GreenAPIClient("111", "tok")
    calls = _capture(c)
    asyncio.run(c.send_voice_status_full("https://x/a.mp3", participants=["989120000001"]))
    assert calls["endpoint"] == "sendVoiceStatus"
    assert calls["data"]["urlFile"] == "https://x/a.mp3"
    assert "backgroundColor" in calls["data"]
    assert calls["data"]["participants"] == ["989120000001@c.us"]


def test_update_group_settings_payload():
    c = GreenAPIClient("111", "tok")
    calls = _capture(c)
    asyncio.run(c.update_group_settings("120@g.us", allow_send=False))
    assert calls["endpoint"] == "updateGroupSettings"
    assert calls["data"]["groupId"] == "120@g.us"
    assert calls["data"]["allowParticipantsSendMessages"] is False
    assert "allowParticipantsEditGroupSettings" not in calls["data"]   # omitted when None
