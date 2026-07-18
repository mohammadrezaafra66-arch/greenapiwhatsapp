"""TG PART 3 — core sending & campaigns for Telegram.

Proves:
  • message splitting at Telegram's 4096-char cap (never truncates; splits on boundaries);
  • the 48h non-contact gate blocks strangers and allows contacts (mock time);
  • Telegram delay is the distinct 10–15s constant, never the WhatsApp delay;
  • chatId resolution via CheckAccount is cached (resolved once per instance+phone);
  • reporting summarizes by platform.
"""
import random
import pytest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services import telegram_send as ts
from app.services import platforms as pf
from app.services.delay_service import delay_for_platform


# ── message splitting ────────────────────────────────────────────────────────
def test_short_message_not_split():
    assert ts.split_message("سلام") == ["سلام"]
    assert ts.split_message("") == []


def test_long_message_split_under_cap():
    text = "\n".join(f"خط شماره {i} با کمی متن فارسی برای پر کردن" for i in range(600))
    chunks = ts.split_message(text, limit=4096)
    assert len(chunks) >= 2
    assert all(len(c) <= 4096 for c in chunks)
    # no content lost (ignoring whitespace at split boundaries)
    assert "".join(c.replace("\n", "").replace(" ", "") for c in chunks) == \
        text.replace("\n", "").replace(" ", "")


def test_split_prefers_boundaries():
    text = "بخش اول. " * 300 + "\n\n" + "بخش دوم. " * 300
    chunks = ts.split_message(text, limit=1200)
    assert all(len(c) <= 1200 for c in chunks) and len(chunks) >= 3


def test_hard_split_when_no_boundary():
    text = "ا" * 5000       # no spaces/newlines at all
    chunks = ts.split_message(text, limit=4096)
    assert len(chunks) == 2 and len(chunks[0]) == 4096


# ── 48h non-contact gate ─────────────────────────────────────────────────────
def test_gate_blocks_stranger_in_first_48h():
    now = datetime(2026, 7, 17, 12, 0)
    auth = now - timedelta(hours=10)
    assert ts.telegram_can_send_to(auth, is_existing_contact=False, now=now) is False


def test_gate_allows_contact_even_in_first_48h():
    now = datetime(2026, 7, 17, 12, 0)
    auth = now - timedelta(hours=1)
    assert ts.telegram_can_send_to(auth, is_existing_contact=True, now=now) is True


def test_gate_opens_after_48h():
    now = datetime(2026, 7, 17, 12, 0)
    auth = now - timedelta(hours=49)
    assert ts.telegram_can_send_to(auth, is_existing_contact=False, now=now) is True


def test_gate_blocks_when_authorized_at_unknown():
    assert ts.telegram_can_send_to(None, is_existing_contact=False) is False
    assert ts.telegram_can_send_to(None, is_existing_contact=True) is True


def test_hours_until_gate_open():
    now = datetime(2026, 7, 17, 12, 0)
    assert ts.hours_until_gate_open(now - timedelta(hours=18), now=now) == pytest.approx(30, abs=0.01)
    assert ts.hours_until_gate_open(now - timedelta(hours=50), now=now) == 0.0


# ── delay constants ──────────────────────────────────────────────────────────
def test_telegram_delay_distinct_from_whatsapp():
    wa = (45, 110)
    assert delay_for_platform("telegram", wa) == (10, 15)
    assert delay_for_platform("whatsapp", wa) == wa
    for _ in range(50):
        d = ts.telegram_send_delay(random.Random(0))
        assert 10 <= d <= 15


# ── chatId resolution + cache ────────────────────────────────────────────────
class _Res:
    def __init__(self, obj): self._obj = obj
    def scalar_one_or_none(self): return self._obj


class _DB:
    def __init__(self, cached=None):
        self.cached = cached
        self.added = []
        self.committed = 0
    async def execute(self, q): return _Res(self.cached)
    def add(self, obj): self.added.append(obj)
    async def commit(self): self.committed += 1
    async def rollback(self): pass


@pytest.mark.asyncio
async def test_resolve_chat_id_calls_checkaccount_and_caches():
    client = SimpleNamespace(instance_id="4100",
                             check_account=AsyncMock(return_value={"exist": True, "chatId": "10000000"}))
    db = _DB(cached=None)
    chat_id, exist = await ts.resolve_chat_id(db, client, "989123456789")
    assert chat_id == "10000000" and exist is True
    assert len(db.added) == 1 and db.added[0].chat_id == "10000000"
    client.check_account.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_chat_id_uses_cache():
    cached = SimpleNamespace(chat_id="10000000", exist=True)
    client = SimpleNamespace(instance_id="4100", check_account=AsyncMock())
    db = _DB(cached=cached)
    chat_id, exist = await ts.resolve_chat_id(db, client, "989123456789")
    assert chat_id == "10000000" and exist is True
    client.check_account.assert_not_awaited()      # cache hit → no API call


@pytest.mark.asyncio
async def test_resolve_chat_id_nonexistent():
    client = SimpleNamespace(instance_id="4100",
                             check_account=AsyncMock(return_value={"exist": False}))
    db = _DB(cached=None)
    chat_id, exist = await ts.resolve_chat_id(db, client, "989123456789")
    assert chat_id is None and exist is False


# ── reporting by platform ────────────────────────────────────────────────────
def test_summarize_by_platform():
    accts = [
        SimpleNamespace(platform="whatsapp", sent_today=5, received_today=2,
                        status=SimpleNamespace(value="active")),
        SimpleNamespace(platform="telegram", sent_today=3, received_today=1,
                        status=SimpleNamespace(value="active")),
        SimpleNamespace(platform="telegram", sent_today=0, received_today=0,
                        status=SimpleNamespace(value="pending")),
    ]
    out = pf.summarize_by_platform(accts)
    assert out["whatsapp"]["count"] == 1 and out["whatsapp"]["sent_today"] == 5
    assert out["telegram"]["count"] == 2 and out["telegram"]["sent_today"] == 3
    assert out["telegram"]["active"] == 1
