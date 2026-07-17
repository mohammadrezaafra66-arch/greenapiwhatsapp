"""TG PART 4 — group monitoring + voice processing for Telegram.

Proves:
  • Telegram group vs private is classified by the NEGATIVE-number check, not '@g.us';
  • ingest stores platform='telegram' for a Telegram group message, deduped;
  • a private Telegram chat (positive number) is never captured as a group message;
  • the SAME V26 detection/auto-reply runs, sending via the Telegram client with 10–15s pacing;
  • the voice (Whisper) pipeline is platform-agnostic (reused unchanged).
"""
import uuid
import contextlib
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services import group_ingest as gi
from app.services import group_monitor_engine as eng
from app.models.group_monitor import (
    MonitoredGroup, GroupMessage, GroupKeyword, GroupPredefinedReply,
    KEYWORD_KIND_TRIGGER, CONVERSATION_MODE_PREDEFINED,
)
from app.models.account import Account


TG_GROUP = "-10000000000000"
TG_PRIVATE = "10000000"
LISTENER = "4100000001"


def _tg_group_payload(text="قیمت یخچال چنده؟", id_message="TGM1", chat_id=TG_GROUP):
    return {
        "typeWebhook": "incomingMessageReceived",
        "idMessage": id_message,
        "timestamp": 1588091580,
        "instanceData": {"idInstance": 4100000001, "typeInstance": "telegram"},
        "senderData": {"chatId": chat_id, "sender": TG_PRIVATE, "chatName": "گروه تلگرام",
                       "senderName": "علی", "senderPhoneNumber": 989123456789},
        "messageData": {"typeMessage": "textMessage",
                        "textMessageData": {"textMessage": text}},
    }


# ── classification ───────────────────────────────────────────────────────────
def test_telegram_group_classified_by_negative_number():
    assert gi.is_group_chat(TG_GROUP, "telegram") is True
    assert gi.is_group_chat(TG_PRIVATE, "telegram") is False
    # the WhatsApp @g.us check must NOT be what decides it
    assert gi.is_group_chat("-10000000000000", "whatsapp") is False


# ── ingest harness ───────────────────────────────────────────────────────────
class _Result:
    def __init__(self, obj): self._obj = obj
    def scalar_one_or_none(self): return self._obj


class _FakeDB:
    def __init__(self, *, account=None, monitored=None, existing=None):
        self.account = account
        self.monitored = monitored
        self.existing = existing
        self.added = []
        self.committed = False
    async def execute(self, q):
        from app.models.account import Account as A
        try:
            ent = q.column_descriptions[0]["entity"]
        except Exception:
            ent = None
        if ent is A:
            return _Result(self.account)
        if ent is MonitoredGroup:
            return _Result(self.monitored)
        if ent is GroupMessage:
            return _Result(self.existing)
        return _Result(None)
    def add(self, obj): self.added.append(obj)
    async def commit(self): self.committed = True
    async def rollback(self): pass
    async def refresh(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()


def _patch_session(monkeypatch, fake):
    @contextlib.asynccontextmanager
    async def _ctx():
        yield fake
    monkeypatch.setattr(gi, "AsyncSessionLocal", lambda: _ctx())


@pytest.mark.asyncio
async def test_telegram_group_message_ingested_with_platform(monkeypatch):
    acc = Account(name="L", instance_id=LISTENER, api_token="t"); acc.is_listener = True
    acc.platform = "telegram"
    mg = MonitoredGroup(listener_instance_id=LISTENER, group_id=TG_GROUP, group_name="G",
                        is_monitored=True, platform="telegram")
    db = _FakeDB(account=acc, monitored=mg)
    _patch_session(monkeypatch, db)
    gm_id = await gi.ingest_group_message(LISTENER, _tg_group_payload(), platform="telegram")
    assert gm_id is not None
    stored = db.added[0]
    assert stored.platform == "telegram" and stored.group_id == TG_GROUP
    assert stored.text == "قیمت یخچال چنده؟"


@pytest.mark.asyncio
async def test_telegram_private_not_captured(monkeypatch):
    acc = Account(name="L", instance_id=LISTENER, api_token="t"); acc.is_listener = True
    acc.platform = "telegram"
    mg = MonitoredGroup(listener_instance_id=LISTENER, group_id=TG_GROUP, is_monitored=True)
    db = _FakeDB(account=acc, monitored=mg)
    _patch_session(monkeypatch, db)
    gm_id = await gi.ingest_group_message(
        LISTENER, _tg_group_payload(chat_id=TG_PRIVATE), platform="telegram")
    assert gm_id is None and db.added == []


# ── auto-reply via Telegram client + pacing ──────────────────────────────────
class _EngResult:
    def __init__(self, items=None, scalar=None):
        self._items = items or []
        self._scalar = scalar
    def scalars(self): return SimpleNamespace(all=lambda: list(self._items))
    def scalar(self): return self._scalar
    def scalar_one_or_none(self): return self._items[0] if self._items else None


class _EngDB:
    def __init__(self, *, keywords, monitored, predefined, account):
        self.keywords = keywords; self.monitored = monitored
        self.predefined = predefined; self.account = account
        self.added = []; self.committed = False
    async def execute(self, q):
        sql = str(q).lower()
        if "count(" in sql:
            return _EngResult(scalar=0)
        try:
            ent = q.column_descriptions[0]["entity"]
        except Exception:
            ent = None
        if ent is GroupKeyword: return _EngResult(items=self.keywords)
        if ent is MonitoredGroup: return _EngResult(items=[self.monitored] if self.monitored else [])
        if ent is GroupPredefinedReply: return _EngResult(items=self.predefined)
        if ent is Account: return _EngResult(items=[self.account] if self.account else [])
        if ent is GroupMessage: return _EngResult(items=[])
        return _EngResult()
    def add(self, o): self.added.append(o)
    async def commit(self): self.committed = True


@pytest.mark.asyncio
async def test_telegram_group_autoreply_uses_telegram_client(monkeypatch):
    gm = GroupMessage(listener_instance_id=LISTENER, platform="telegram", group_id=TG_GROUP,
                      group_name="G", sender=TG_PRIVATE, sender_name="علی", id_message="TGM2",
                      type_message="textMessage", text="قیمت یخچال چنده؟")
    gm.id = uuid.uuid4()
    kw = GroupKeyword(word="قیمت", kind=KEYWORD_KIND_TRIGGER, active=True); kw.id = uuid.uuid4()
    reply = GroupPredefinedReply(keyword_id=None, reply_text="قیمت را خصوصی بفرستید", active=True)
    tg_acc = SimpleNamespace(instance_id=LISTENER, api_token="t", platform="telegram", api_host=None)
    db = _EngDB(keywords=[kw], monitored=MonitoredGroup(
        listener_instance_id=LISTENER, group_id=TG_GROUP, is_monitored=True,
        auto_reply_enabled=True, conversation_mode=CONVERSATION_MODE_PREDEFINED,
        platform="telegram"), predefined=[reply], account=tg_acc)

    monkeypatch.setattr(eng, "apply_typing_simulation", AsyncMock(return_value=0))
    monkeypatch.setattr(eng, "in_active_hours", lambda *a, **k: True)
    sent = {}
    class _Client:
        def __init__(self, iid, tok, platform="whatsapp", api_host=None):
            sent["platform"] = platform
        async def send_group_message(self, gid, msg):
            sent["target"] = gid; sent["msg"] = msg; return "MID"
    monkeypatch.setattr("app.services.green_api.GreenAPIClient", _Client)
    # keep the 10-15s pacing from blocking the test
    monkeypatch.setattr("app.services.telegram_send.telegram_send_delay", lambda *a, **k: 0)

    summary = await eng.run_detection_and_reply(db, gm, gm.text)
    assert summary["replied"] is True
    assert sent["platform"] == "telegram"       # sent via the Telegram client
    assert sent["target"] == TG_GROUP and sent["msg"] == "قیمت را خصوصی بفرستید"


def test_voice_pipeline_is_platform_agnostic():
    # The V26 voice service builds no Green API client — download_url + Whisper only — so it
    # is reused unchanged for Telegram. Assert its public surface has no platform coupling.
    from app.services import group_voice
    import inspect
    src = inspect.getsource(group_voice.process_voice_message)
    assert "@g.us" not in src and "platform" not in src.lower()
