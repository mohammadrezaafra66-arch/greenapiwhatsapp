"""TG PART 2 — connect + authorize a Telegram instance.

NOTE: no LIVE Telegram account is available in this environment, so these exercise the code
paths against mocked Green API responses using the verified shapes. Live authorization +
a real send/receive round-trip is the #1 blocker flagged in the final report.

Proves:
  • create stores platform='telegram' with the Telegram partner host, never the WhatsApp key;
  • QR flow returns a qr; code+password flow reaches authorized (mocked);
  • apply_state maps states correctly and stamps authorized_at on first authorize;
  • the QR-screen notice is the Telegram-specific wording.
"""
import uuid
import pytest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.api.v1 import telegram as tgapi
from app.services import telegram_service as tg
from app.models.account import Account, AccountStatus


# ── pure state mapping ───────────────────────────────────────────────────────
def test_map_state_to_status():
    assert tg.map_state_to_status("authorized") == AccountStatus.active
    assert tg.map_state_to_status("blocked") == AccountStatus.banned
    assert tg.map_state_to_status("suspended") == AccountStatus.suspended
    assert tg.map_state_to_status("notAuthorized") == AccountStatus.disconnected
    assert tg.map_state_to_status("starting") is None      # transient → ignored


def test_apply_state_stamps_authorized_at_once():
    acc = Account(name="t", instance_id="4100", api_token="k")
    acc.platform = "telegram"
    now = datetime(2026, 7, 17, 12, 0)
    tg.apply_state(acc, "authorized", now)
    assert acc.status == AccountStatus.active and acc.authorized_at == now
    # a later authorize must NOT move the anchor
    tg.apply_state(acc, "authorized", datetime(2026, 7, 20, 12, 0))
    assert acc.authorized_at == now


def test_apply_state_suspended_and_blocked():
    acc = Account(name="t", instance_id="4100", api_token="k")
    assert tg.apply_state(acc, "suspended") == AccountStatus.suspended
    assert tg.apply_state(acc, "blocked") == AccountStatus.banned


def test_qr_notice_is_telegram_specific():
    joined = " ".join(tg.TELEGRAM_QR_NOTICE)
    assert "۴۸ ساعت" in joined and "۱۰ تا ۱۵ ثانیه" in joined
    assert "تلگرام" in joined


# ── endpoint harness ─────────────────────────────────────────────────────────
class _Result:
    def __init__(self, obj): self._obj = obj
    def scalar_one_or_none(self): return self._obj


class _DB:
    def __init__(self, existing=None, get_obj=None):
        self.existing = existing
        self.get_obj = get_obj
        self.added = []
        self.committed = 0
    async def execute(self, q): return _Result(self.existing)
    async def get(self, model, pk): return self.get_obj
    def add(self, obj):
        self.added.append(obj)
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
    async def commit(self): self.committed += 1
    async def refresh(self, obj): pass


@pytest.mark.asyncio
async def test_create_telegram_account_stores_platform(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "green_partner_api_url_telegram", "https://4500.api.green-api.com")
    fake_client = SimpleNamespace(set_webhook=AsyncMock(return_value=True))
    monkeypatch.setattr(tgapi, "GreenAPIClient", lambda *a, **k: fake_client)
    monkeypatch.setattr(tgapi, "_tg_client", lambda acc: fake_client)

    db = _DB(existing=None)
    body = tgapi.TelegramCreate(name="اکانت تلگرام", instance_id="4100", api_token="tok")
    out = await tgapi.create_telegram_account(body, db=db)
    assert out["platform"] == "telegram"
    acc = db.added[0]
    assert acc.platform == "telegram"
    assert acc.api_host == "https://4500.api.green-api.com"
    assert acc.api_token == "tok"      # its OWN token, not the WhatsApp partner key


@pytest.mark.asyncio
async def test_qr_flow_returns_code(monkeypatch):
    acc = Account(name="t", instance_id="4100", api_token="k"); acc.platform = "telegram"
    acc.id = uuid.uuid4()
    db = _DB(get_obj=acc)
    fake = SimpleNamespace(get_qr_info=AsyncMock(return_value={"type": "qrCode", "message": "BASE64PNG"}))
    monkeypatch.setattr(tgapi, "_tg_client", lambda a: fake)
    out = await tgapi.telegram_qr(str(acc.id), db=db)
    assert out["type"] == "qrCode" and out["qr"] == "BASE64PNG"


@pytest.mark.asyncio
async def test_code_auth_flow_reaches_authorized(monkeypatch):
    acc = Account(name="t", instance_id="4100", api_token="k"); acc.platform = "telegram"
    acc.id = uuid.uuid4()
    db = _DB(get_obj=acc)
    fake = SimpleNamespace(
        start_authorization=AsyncMock(return_value={"status": "waitingForCode"}),
        send_authorization_code=AsyncMock(return_value={"status": "waitingForPassword"}),
        send_authorization_password=AsyncMock(return_value={"status": "success"}),
        get_state=AsyncMock(return_value="authorized"),
    )
    monkeypatch.setattr(tgapi, "_tg_client", lambda a: fake)

    r1 = await tgapi.telegram_auth_start(str(acc.id), tgapi.AuthStart(phone="989123456789"), db=db)
    assert r1["status"] == "waitingForCode"
    r2 = await tgapi.telegram_auth_code(str(acc.id), tgapi.AuthCode(code="12345"), db=db)
    assert r2["status"] == "waitingForPassword"
    r3 = await tgapi.telegram_auth_password(str(acc.id), tgapi.AuthPassword(password="pw"), db=db)
    assert r3["status"] == "success"
    st = await tgapi.telegram_state(str(acc.id), db=db)
    assert st["state"] == "authorized" and st["status"] == AccountStatus.active
    assert acc.authorized_at is not None      # 48h-gate anchor stamped


@pytest.mark.asyncio
async def test_non_telegram_account_rejected(monkeypatch):
    acc = Account(name="w", instance_id="7105", api_token="k"); acc.platform = "whatsapp"
    acc.id = uuid.uuid4()
    db = _DB(get_obj=acc)
    with pytest.raises(Exception):
        await tgapi.telegram_qr(str(acc.id), db=db)


@pytest.mark.asyncio
async def test_send_test_uses_telegram_client(monkeypatch):
    acc = Account(name="t", instance_id="4100", api_token="k"); acc.platform = "telegram"
    acc.id = uuid.uuid4()
    db = _DB(get_obj=acc)
    fake = SimpleNamespace(
        get_account_settings=AsyncMock(return_value={"wid": "10000000@c.us"}),
        send_message=AsyncMock(return_value="MSGID"),
    )
    monkeypatch.setattr(tgapi, "_tg_client", lambda a: fake)
    out = await tgapi.telegram_send_test(str(acc.id), tgapi.SelfTest(), db=db)
    assert out["sent"] and out["id_message"] == "MSGID" and out["target"] == "10000000"
