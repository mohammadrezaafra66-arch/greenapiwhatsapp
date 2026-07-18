"""TG PART 5 — contacts & groups management for Telegram.

Proves:
  • the existence check is platform-aware (WhatsApp checkWhatsapp / Telegram checkAccount);
  • admin-group detection parses GetGroupData participants/isAdmin (same shape both platforms);
  • the manual link vault never attempts auto-join on either platform.
"""
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services import contacts_groups as cg
from app.services.green_api import GreenAPIClient


# ── platform-aware existence check ───────────────────────────────────────────
@pytest.mark.asyncio
async def test_contact_exists_whatsapp_uses_checkwhatsapp(monkeypatch):
    c = GreenAPIClient("7105", "tok")            # whatsapp
    c.check_whatsapp = AsyncMock(return_value=True)
    c.check_account = AsyncMock()
    assert await c.contact_exists("989123456789") is True
    c.check_whatsapp.assert_awaited_once()
    c.check_account.assert_not_awaited()


@pytest.mark.asyncio
async def test_contact_exists_telegram_uses_checkaccount(monkeypatch):
    c = GreenAPIClient("4100", "tok", platform="telegram")
    c.check_account = AsyncMock(return_value={"exist": True, "chatId": "10000000"})
    c.check_whatsapp = AsyncMock()
    assert await c.contact_exists("989123456789") is True
    c.check_account.assert_awaited_once()
    c.check_whatsapp.assert_not_awaited()


@pytest.mark.asyncio
async def test_contact_exists_telegram_false(monkeypatch):
    c = GreenAPIClient("4100", "tok", platform="telegram")
    c.check_account = AsyncMock(return_value={"exist": False})
    assert await c.contact_exists("989123456789") is False


# ── admin-group detection (shared shape) ─────────────────────────────────────
GROUP_DATA = {
    "size": 3,
    "participants": [
        {"id": "10000000@c.us", "isAdmin": True, "isSuperAdmin": False},
        {"id": "10000001@c.us", "isAdmin": False},
        {"id": "10000002", "isAdmin": False},
    ],
}


def test_parse_participants_and_size():
    assert len(cg.parse_participants(GROUP_DATA)) == 3
    assert cg.group_size(GROUP_DATA) == 3
    assert cg.group_size({"participants": [{"id": "a"}, {"id": "b"}]}) == 2


def test_is_account_admin_true_for_admin():
    assert cg.is_account_admin(GROUP_DATA, "10000000") is True
    assert cg.is_account_admin(GROUP_DATA, "10000000@c.us") is True   # suffix-insensitive


def test_is_account_admin_false_for_non_admin():
    assert cg.is_account_admin(GROUP_DATA, "10000001") is False
    assert cg.is_account_admin(GROUP_DATA, "99999999") is False


def test_is_account_admin_owner_field():
    data = {"participants": [], "owner": "10000005@c.us"}
    assert cg.is_account_admin(data, "10000005") is True


def test_telegram_group_data_shape_assumed_identical_to_whatsapp():
    # Telegram negative-number group with the SAME participants shape.
    tg_data = {"size": 2, "participants": [
        {"id": "10000000", "isSuperAdmin": True},
        {"id": "10000009", "isAdmin": False},
    ]}
    assert cg.is_account_admin(tg_data, "10000000") is True
    assert cg.group_size(tg_data) == 2


# ── link vault: never auto-join ──────────────────────────────────────────────
def test_no_auto_join_on_either_platform():
    assert cg.is_auto_join_supported("whatsapp") is False
    assert cg.is_auto_join_supported("telegram") is False
