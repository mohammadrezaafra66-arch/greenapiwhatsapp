"""V26 PART 2 — ingest monitored-group messages via the existing webhook.

Proves (against the verified Green API webhook shapes):
  • group text on a monitored group is captured & deduped;
  • a group message on a NON-monitored group, or from a NON-listener instance, is ignored;
  • a private (@c.us) message is never captured as a group message;
  • an audio message is stored with is_voice + audio_url + transcription_status='pending';
  • field extraction handles textMessage / extendedTextMessage / audioMessage / media caption.
"""
import uuid
import pytest
from types import SimpleNamespace

from app.services import group_ingest as gi
from app.models.group_monitor import (
    MonitoredGroup, GroupMessage, TRANSCRIPTION_PENDING, TRANSCRIPTION_NONE,
)
from app.models.account import Account


GROUP_ID = "79876543210-1581234048@g.us"
LISTENER = "7105000001"


def _group_text_payload(text="قیمت یخچال چنده؟", id_message="MSG1", type_message="textMessage"):
    return {
        "typeWebhook": "incomingMessageReceived",
        "idMessage": id_message,
        "timestamp": 1588091580,
        "senderData": {
            "chatId": GROUP_ID, "sender": "79001234567@c.us",
            "chatName": "گروه افراکالا", "senderName": "علی", "senderContactName": "علی رضایی",
        },
        "messageData": {"typeMessage": type_message,
                        "textMessageData": {"textMessage": text}},
    }


def _group_audio_payload(id_message="AUD1"):
    return {
        "typeWebhook": "incomingMessageReceived",
        "idMessage": id_message,
        "timestamp": 1588091590,
        "senderData": {"chatId": GROUP_ID, "sender": "79001234567@c.us",
                       "chatName": "گروه افراکالا", "senderName": "مریم"},
        "messageData": {
            "typeMessage": "audioMessage",
            "fileMessageData": {"downloadUrl": "https://green/a.ogg",
                                "mimeType": "audio/ogg", "fileName": "voice.ogg"},
        },
    }


def _private_payload(id_message="PVT1"):
    p = _group_text_payload(id_message=id_message)
    p["senderData"]["chatId"] = "79001234567@c.us"   # private chat
    return p


# ── pure extraction ──────────────────────────────────────────────────────────
def test_is_group_chat():
    assert gi.is_group_chat(GROUP_ID)
    assert not gi.is_group_chat("79001234567@c.us")
    assert not gi.is_group_chat(None)


def test_extract_text_message():
    f = gi.extract_group_message_fields(_group_text_payload(text="سلام"))
    assert f["text"] == "سلام" and not f["is_voice"]
    assert f["type_message"] == "textMessage"
    assert f["sender"] == "79001234567@c.us" and f["sender_name"] == "علی"
    assert f["transcription_status"] == TRANSCRIPTION_NONE


def test_extract_extended_text_message():
    p = {"idMessage": "E1", "timestamp": 1,
         "senderData": {"chatId": GROUP_ID, "sender": "x@c.us", "chatName": "G",
                        "senderName": "n"},
         "messageData": {"typeMessage": "extendedTextMessage",
                         "extendedTextMessageData": {"text": "موجودی داری؟"}}}
    f = gi.extract_group_message_fields(p)
    assert f["text"] == "موجودی داری؟" and f["type_message"] == "extendedTextMessage"


def test_extract_audio_message_sets_voice_and_pending():
    f = gi.extract_group_message_fields(_group_audio_payload())
    assert f["is_voice"] is True
    assert f["audio_url"] == "https://green/a.ogg"
    assert f["transcription_status"] == TRANSCRIPTION_PENDING
    assert f["text"] is None


def test_extract_media_caption():
    p = {"idMessage": "I1", "timestamp": 1,
         "senderData": {"chatId": GROUP_ID, "sender": "x@c.us", "chatName": "G",
                        "senderName": "n"},
         "messageData": {"typeMessage": "imageMessage",
                         "fileMessageData": {"caption": "این محصول موجوده؟"}}}
    f = gi.extract_group_message_fields(p)
    assert f["text"] == "این محصول موجوده؟" and not f["is_voice"]
    assert f["type_message"] == "imageMessage"


def test_senderContactName_fallback_for_name():
    p = _group_text_payload()
    del p["senderData"]["senderName"]
    f = gi.extract_group_message_fields(p)
    assert f["sender_name"] == "علی رضایی"


# ── ingest against a fake DB ──────────────────────────────────────────────────
class _Result:
    def __init__(self, obj): self._obj = obj
    def scalar_one_or_none(self): return self._obj


class _FakeDB:
    """Serves the three queries ingest_group_message runs (account, monitored_group,
    existing group_message dedupe) and records added rows + commits."""
    def __init__(self, *, account=None, monitored=None, existing=None):
        self.account = account
        self.monitored = monitored
        self.existing = existing
        self.added = []
        self.committed = False

    async def execute(self, q):
        target = _target_entity(q)
        if target is Account:
            return _Result(self.account)
        if target is MonitoredGroup:
            return _Result(self.monitored)
        if target is GroupMessage:
            return _Result(self.existing)
        return _Result(None)

    def add(self, obj): self.added.append(obj)
    async def commit(self): self.committed = True
    async def rollback(self): pass
    async def refresh(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()


def _target_entity(q):
    """Best-effort: identify which mapped class a select() targets."""
    try:
        desc = q.column_descriptions
        return desc[0]["entity"]
    except Exception:
        return None


def _patch_session(monkeypatch, fake):
    import contextlib

    @contextlib.asynccontextmanager
    async def _fake_ctx():
        yield fake
    monkeypatch.setattr(gi, "AsyncSessionLocal", lambda: _fake_ctx())


@pytest.mark.asyncio
async def test_group_text_on_monitored_group_is_stored(monkeypatch):
    acc = Account(name="L", instance_id=LISTENER, api_token="t")
    acc.is_listener = True
    mg = MonitoredGroup(listener_instance_id=LISTENER, group_id=GROUP_ID, group_name="G",
                        is_monitored=True)
    db = _FakeDB(account=acc, monitored=mg, existing=None)
    _patch_session(monkeypatch, db)

    gm_id = await gi.ingest_group_message(LISTENER, _group_text_payload())
    assert gm_id is not None and db.committed
    assert len(db.added) == 1
    stored = db.added[0]
    assert stored.text == "قیمت یخچال چنده؟"
    assert stored.group_id == GROUP_ID and stored.sender_name == "علی"


@pytest.mark.asyncio
async def test_audio_stored_with_voice_and_pending(monkeypatch):
    acc = Account(name="L", instance_id=LISTENER, api_token="t"); acc.is_listener = True
    mg = MonitoredGroup(listener_instance_id=LISTENER, group_id=GROUP_ID, is_monitored=True)
    db = _FakeDB(account=acc, monitored=mg)
    _patch_session(monkeypatch, db)

    gm_id = await gi.ingest_group_message(LISTENER, _group_audio_payload())
    assert gm_id is not None
    stored = db.added[0]
    assert stored.is_voice is True
    assert stored.audio_url == "https://green/a.ogg"
    assert stored.transcription_status == TRANSCRIPTION_PENDING


@pytest.mark.asyncio
async def test_duplicate_id_message_is_deduped(monkeypatch):
    acc = Account(name="L", instance_id=LISTENER, api_token="t"); acc.is_listener = True
    mg = MonitoredGroup(listener_instance_id=LISTENER, group_id=GROUP_ID, is_monitored=True)
    existing = GroupMessage(listener_instance_id=LISTENER, group_id=GROUP_ID, id_message="MSG1")
    db = _FakeDB(account=acc, monitored=mg, existing=existing)
    _patch_session(monkeypatch, db)

    gm_id = await gi.ingest_group_message(LISTENER, _group_text_payload(id_message="MSG1"))
    assert gm_id is None and db.added == []


@pytest.mark.asyncio
async def test_non_listener_instance_is_ignored(monkeypatch):
    acc = Account(name="C", instance_id=LISTENER, api_token="t"); acc.is_listener = False
    mg = MonitoredGroup(listener_instance_id=LISTENER, group_id=GROUP_ID, is_monitored=True)
    db = _FakeDB(account=acc, monitored=mg)
    _patch_session(monkeypatch, db)

    gm_id = await gi.ingest_group_message(LISTENER, _group_text_payload())
    assert gm_id is None and db.added == []


@pytest.mark.asyncio
async def test_non_monitored_group_is_ignored(monkeypatch):
    acc = Account(name="L", instance_id=LISTENER, api_token="t"); acc.is_listener = True
    db = _FakeDB(account=acc, monitored=None)   # no monitored_group row
    _patch_session(monkeypatch, db)

    gm_id = await gi.ingest_group_message(LISTENER, _group_text_payload())
    assert gm_id is None and db.added == []


@pytest.mark.asyncio
async def test_private_message_never_captured_as_group(monkeypatch):
    acc = Account(name="L", instance_id=LISTENER, api_token="t"); acc.is_listener = True
    mg = MonitoredGroup(listener_instance_id=LISTENER, group_id=GROUP_ID, is_monitored=True)
    db = _FakeDB(account=acc, monitored=mg)
    _patch_session(monkeypatch, db)

    gm_id = await gi.ingest_group_message(LISTENER, _private_payload())
    assert gm_id is None and db.added == []
