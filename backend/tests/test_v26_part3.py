"""V26 PART 3 — keyword detection + auto-reply (predefined & AI) + forbidden flagging.

Proves:
  • Persian-aware normalization/matching («قيمت» ≡ «قیمت», digit scripts);
  • trigger → matched_keywords recorded; forbidden → flagged + admin alert, no auto-message;
  • predefined reply selection (keyword-specific wins, else default);
  • the auto-reply gate is default-OFF and honors mode/waking-hours/rate-limit;
  • AI reply path is invoked in ai mode and NEVER leaks an identifier (V24 safeguard);
  • the engine sends only when enabled and marks replied.
"""
import uuid
import random
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services import group_detection as gd
from app.services import group_ai_reply as gar
from app.services import group_monitor_engine as eng
from app.models.group_monitor import (
    GroupKeyword, GroupPredefinedReply, GroupMessage, MonitoredGroup,
    KEYWORD_KIND_TRIGGER, KEYWORD_KIND_FORBIDDEN,
    CONVERSATION_MODE_OFF, CONVERSATION_MODE_PREDEFINED, CONVERSATION_MODE_AI,
)


# ── Persian normalization ────────────────────────────────────────────────────
def test_normalize_unifies_arabic_and_persian():
    assert gd.normalize_fa("قيمت") == gd.normalize_fa("قیمت")     # ي vs ی
    assert gd.normalize_fa("كولر") == gd.normalize_fa("کولر")     # ك vs ک
    assert gd.normalize_fa("۱۲۳") == "123"                        # Persian digits
    assert gd.normalize_fa("٤٥٦") == "456"                        # Arabic-Indic digits
    assert gd.normalize_fa("  سلام   دنیا ") == "سلام دنیا"


def _kw(word, kind=KEYWORD_KIND_TRIGGER, active=True):
    return SimpleNamespace(word=word, kind=kind, active=active)


def test_detect_trigger_across_letter_variants():
    kws = [_kw("قیمت"), _kw("موجودی")]
    triggers, forbidden = gd.detect("سلام، قيمت این یخچال چنده؟", kws)
    assert triggers == ["قیمت"] and forbidden == []


def test_detect_forbidden():
    kws = [_kw("قیمت"), _kw("کلاهبرداری", KEYWORD_KIND_FORBIDDEN)]
    triggers, forbidden = gd.detect("این فروشگاه کلاهبرداری است", kws)
    assert forbidden == ["کلاهبرداری"] and triggers == []


def test_detect_ignores_inactive():
    kws = [_kw("قیمت", active=False)]
    assert gd.detect("قیمت چنده", kws) == ([], [])


def test_detect_empty_text():
    assert gd.detect("", [_kw("قیمت")]) == ([], [])


# ── predefined reply selection ───────────────────────────────────────────────
def test_predefined_keyword_specific_wins_over_default():
    kid = uuid.uuid4()
    replies = [
        SimpleNamespace(keyword_id=None, reply_text="پاسخ پیش‌فرض", active=True),
        SimpleNamespace(keyword_id=kid, reply_text="قیمت را خصوصی بپرسید", active=True),
    ]
    got = gd.select_predefined_reply(["قیمت"], replies, {"قیمت": kid})
    assert got == "قیمت را خصوصی بپرسید"


def test_predefined_falls_back_to_default():
    replies = [SimpleNamespace(keyword_id=None, reply_text="پاسخ پیش‌فرض", active=True)]
    got = gd.select_predefined_reply(["موجودی"], replies, {"موجودی": uuid.uuid4()})
    assert got == "پاسخ پیش‌فرض"


def test_predefined_none_when_no_reply():
    assert gd.select_predefined_reply(["x"], [], {}) is None


# ── rate limit + gate ────────────────────────────────────────────────────────
def test_within_rate_limit_bounds():
    rng = random.Random(0)
    # cap 4, jitter ±1 → allowed while count < (3..5); definitely allowed at 0, blocked at 10
    assert gd.within_rate_limit(0, 4, rng)
    assert not gd.within_rate_limit(10, 4, rng)


def test_gate_default_off():
    # auto_reply disabled
    assert not gd.should_auto_reply(auto_reply_enabled=False,
                                    conversation_mode=CONVERSATION_MODE_PREDEFINED,
                                    has_trigger=True, in_waking_hours=True, within_rate=True)
    # mode off
    assert not gd.should_auto_reply(auto_reply_enabled=True,
                                    conversation_mode=CONVERSATION_MODE_OFF,
                                    has_trigger=True, in_waking_hours=True, within_rate=True)


def test_gate_respects_hours_and_rate_and_trigger():
    base = dict(auto_reply_enabled=True, conversation_mode=CONVERSATION_MODE_AI,
                has_trigger=True, in_waking_hours=True, within_rate=True)
    assert gd.should_auto_reply(**base)
    assert not gd.should_auto_reply(**{**base, "in_waking_hours": False})
    assert not gd.should_auto_reply(**{**base, "within_rate": False})
    assert not gd.should_auto_reply(**{**base, "has_trigger": False})


# ── AI reply generation + V24 safeguard ──────────────────────────────────────
@pytest.mark.asyncio
async def test_ai_reply_returns_safe_text():
    async def fake_chat(system, user, max_tokens, temperature):
        assert "افراکالا" in system
        return "سلام، بله این یخچال موجوده، در خدمتیم 🙏"
    got = await gar.generate_ai_reply("قیمت یخچال چنده؟", chat_fn=fake_chat)
    assert got and "یخچال" in got


@pytest.mark.asyncio
async def test_ai_reply_rejects_identifier_leak():
    async def leaky(system, user, max_tokens, temperature):
        return "برای 9048249532 موجوده"     # long digit run = identifier leak
    got = await gar.generate_ai_reply("موجودی؟", forbidden=("9048249532",), chat_fn=leaky)
    assert got is None


@pytest.mark.asyncio
async def test_ai_reply_history_drops_identifier_lines():
    seen = {}
    async def cap(system, user, max_tokens, temperature):
        seen["user"] = user
        return "بله موجوده"
    await gar.generate_ai_reply("قیمت؟", history=["سلام 770022682898 گوشی", "یخچال دارید؟"],
                                chat_fn=cap)
    assert "یخچال دارید؟" in seen["user"] and "770022682898" not in seen["user"]


# ── engine: fake DB harness ──────────────────────────────────────────────────
class _Res:
    def __init__(self, items=None, scalar=None):
        self._items = items or []
        self._scalar = scalar
    def scalars(self): return SimpleNamespace(all=lambda: list(self._items))
    def scalar(self): return self._scalar
    def scalar_one_or_none(self): return self._items[0] if self._items else None


class _EngineDB:
    def __init__(self, *, keywords=None, monitored=None, predefined=None,
                 recent_count=0, account=None, recent_texts=None):
        self.keywords = keywords or []
        self.monitored = monitored
        self.predefined = predefined or []
        self.recent_count = recent_count
        self.account = account
        self.recent_texts = recent_texts or []
        self.added = []
        self.committed = False

    async def execute(self, q):
        sql = str(q).lower()
        if "count(" in sql:
            return _Res(scalar=self.recent_count)
        entity = None
        try:
            entity = q.column_descriptions[0]["entity"]
        except Exception:
            pass
        if entity is GroupKeyword:
            return _Res(items=self.keywords)
        if entity is MonitoredGroup:
            return _Res(items=[self.monitored] if self.monitored else [])
        if entity is GroupPredefinedReply:
            return _Res(items=self.predefined)
        if entity is GroupMessage:
            return _Res(items=self.recent_texts)
        from app.models.account import Account
        if entity is Account:
            return _Res(items=[self.account] if self.account else [])
        return _Res()

    def add(self, obj): self.added.append(obj)
    async def commit(self): self.committed = True


def _gm(text="قیمت یخچال چنده؟", group="g@g.us", listener="7105"):
    m = GroupMessage(listener_instance_id=listener, group_id=group, group_name="G",
                     sender="s@c.us", sender_name="علی", id_message="M1",
                     type_message="textMessage", text=text)
    m.id = uuid.uuid4()
    return m


def _mg(mode=CONVERSATION_MODE_OFF, enabled=False, group="g@g.us", listener="7105"):
    return MonitoredGroup(listener_instance_id=listener, group_id=group, group_name="G",
                          is_monitored=True, auto_reply_enabled=enabled, conversation_mode=mode)


class _FakeClient:
    def __init__(self, *a, **k): self.sent = []
    async def send_group_message(self, group_id, message):
        self.sent.append((group_id, message)); return "REPLYID"


@pytest.fixture(autouse=True)
def _patch_send(monkeypatch):
    # No real typing/network in engine tests.
    monkeypatch.setattr(eng, "apply_typing_simulation", AsyncMock(return_value=0))
    client = _FakeClient()
    monkeypatch.setattr("app.services.green_api.GreenAPIClient",
                        lambda *a, **k: client)
    # keep waking-hours deterministic ON unless a test overrides
    monkeypatch.setattr(eng, "in_active_hours", lambda *a, **k: True)
    return client


@pytest.mark.asyncio
async def test_trigger_records_matched_and_default_off_sends_nothing(_patch_send):
    gm = _gm()
    db = _EngineDB(keywords=[_kw("قیمت")], monitored=_mg(CONVERSATION_MODE_OFF, enabled=False),
                   account=SimpleNamespace(instance_id="7105", api_token="t"))
    summary = await eng.run_detection_and_reply(db, gm, gm.text)
    assert gm.matched_keywords == "قیمت"
    assert summary["replied"] is False and _patch_send.sent == []
    assert not gm.replied


@pytest.mark.asyncio
async def test_predefined_reply_sent_when_enabled(_patch_send):
    gm = _gm()
    kid = uuid.uuid4()
    kw = GroupKeyword(word="قیمت", kind=KEYWORD_KIND_TRIGGER, active=True); kw.id = kid
    replies = [GroupPredefinedReply(keyword_id=kid, reply_text="قیمت را خصوصی بفرستید", active=True)]
    db = _EngineDB(keywords=[kw],
                   monitored=_mg(CONVERSATION_MODE_PREDEFINED, enabled=True),
                   predefined=replies,
                   account=SimpleNamespace(instance_id="7105", api_token="t"))
    summary = await eng.run_detection_and_reply(db, gm, gm.text)
    assert summary["replied"] is True and gm.replied is True
    assert _patch_send.sent == [("g@g.us", "قیمت را خصوصی بفرستید")]


@pytest.mark.asyncio
async def test_ai_mode_invokes_ai(monkeypatch, _patch_send):
    gm = _gm()
    kw = GroupKeyword(word="قیمت", kind=KEYWORD_KIND_TRIGGER, active=True); kw.id = uuid.uuid4()
    ai_mock = AsyncMock(return_value="سلام، بله موجوده در خدمتیم")
    monkeypatch.setattr("app.services.group_ai_reply.generate_ai_reply", ai_mock)
    db = _EngineDB(keywords=[kw], monitored=_mg(CONVERSATION_MODE_AI, enabled=True),
                   account=SimpleNamespace(instance_id="7105", api_token="t"))
    summary = await eng.run_detection_and_reply(db, gm, gm.text)
    assert ai_mock.await_count == 1
    assert summary["replied"] is True
    assert _patch_send.sent == [("g@g.us", "سلام، بله موجوده در خدمتیم")]


@pytest.mark.asyncio
async def test_forbidden_flags_and_alerts_no_send(_patch_send):
    gm = _gm(text="این کلاهبرداری است")
    kws = [_kw("قیمت"), GroupKeyword(word="کلاهبرداری", kind=KEYWORD_KIND_FORBIDDEN, active=True)]
    db = _EngineDB(keywords=kws, monitored=_mg(CONVERSATION_MODE_PREDEFINED, enabled=True),
                   account=SimpleNamespace(instance_id="7105", api_token="t"))
    summary = await eng.run_detection_and_reply(db, gm, gm.text)
    assert gm.flagged_forbidden is True and summary["forbidden"] == ["کلاهبرداری"]
    from app.models.group_monitor import GroupForbiddenAlert
    alerts = [a for a in db.added if isinstance(a, GroupForbiddenAlert)]
    assert len(alerts) == 1 and alerts[0].word == "کلاهبرداری"
    assert _patch_send.sent == []          # forbidden never triggers an auto-message


@pytest.mark.asyncio
async def test_rate_limit_blocks_reply(_patch_send):
    gm = _gm()
    kw = GroupKeyword(word="قیمت", kind=KEYWORD_KIND_TRIGGER, active=True); kw.id = uuid.uuid4()
    db = _EngineDB(keywords=[kw], monitored=_mg(CONVERSATION_MODE_PREDEFINED, enabled=True),
                   predefined=[GroupPredefinedReply(keyword_id=None, reply_text="x", active=True)],
                   recent_count=99,   # way over the jittered cap
                   account=SimpleNamespace(instance_id="7105", api_token="t"))
    summary = await eng.run_detection_and_reply(db, gm, gm.text)
    assert summary["replied"] is False and _patch_send.sent == []


@pytest.mark.asyncio
async def test_outside_waking_hours_blocks_reply(monkeypatch, _patch_send):
    monkeypatch.setattr(eng, "in_active_hours", lambda *a, **k: False)
    gm = _gm()
    kw = GroupKeyword(word="قیمت", kind=KEYWORD_KIND_TRIGGER, active=True); kw.id = uuid.uuid4()
    db = _EngineDB(keywords=[kw], monitored=_mg(CONVERSATION_MODE_PREDEFINED, enabled=True),
                   predefined=[GroupPredefinedReply(keyword_id=None, reply_text="x", active=True)],
                   account=SimpleNamespace(instance_id="7105", api_token="t"))
    summary = await eng.run_detection_and_reply(db, gm, gm.text)
    assert summary["replied"] is False and _patch_send.sent == []
