"""TG PART 1 — platform abstraction + Telegram credentials.

Proves:
  • chatId helpers classify BOTH WhatsApp (@g.us/@c.us) and Telegram (negative/positive
    number) ids correctly;
  • the Telegram partner key is stored + selected SEPARATELY from the WhatsApp key and never
    conflated;
  • the platform discriminator + api_host columns exist on accounts and default to whatsapp;
  • GreenAPIClient is platform/host aware.
"""
import pytest
from app.services import platforms as pf
from app.services.green_api import GreenAPIClient
from app.models.account import Account


# ── chat-id classification ───────────────────────────────────────────────────
def test_whatsapp_group_and_private():
    assert pf.is_group_chat_id("79876543210-1581234048@g.us", pf.PLATFORM_WHATSAPP)
    assert not pf.is_group_chat_id("79001234567@c.us", pf.PLATFORM_WHATSAPP)
    assert pf.is_private_chat_id("79001234567@c.us", pf.PLATFORM_WHATSAPP)
    assert not pf.is_private_chat_id("...@g.us", pf.PLATFORM_WHATSAPP)


def test_telegram_group_is_negative_number():
    assert pf.is_group_chat_id("-10000000000000", pf.PLATFORM_TELEGRAM)
    assert not pf.is_group_chat_id("10000000", pf.PLATFORM_TELEGRAM)      # positive = private
    assert not pf.is_group_chat_id("-10000000000000", pf.PLATFORM_WHATSAPP)  # wrong for WA


def test_telegram_private_is_positive_number_or_cus():
    assert pf.is_private_chat_id("10000000", pf.PLATFORM_TELEGRAM)
    assert pf.is_private_chat_id("79876543210@c.us", pf.PLATFORM_TELEGRAM)  # backward-compat
    assert not pf.is_private_chat_id("-10000000000000", pf.PLATFORM_TELEGRAM)  # group, not private


def test_group_and_private_are_mutually_exclusive_telegram():
    for cid in ("10000000", "-10000000000000"):
        assert pf.is_group_chat_id(cid, "telegram") != pf.is_private_chat_id(cid, "telegram")


def test_empty_and_none_are_neither():
    for p in (pf.PLATFORM_WHATSAPP, pf.PLATFORM_TELEGRAM):
        assert not pf.is_group_chat_id("", p) and not pf.is_private_chat_id(None, p)


def test_normalize_platform_defaults_whatsapp():
    assert pf.normalize_platform("telegram") == "telegram"
    assert pf.normalize_platform("TELEGRAM") == "telegram"
    assert pf.normalize_platform("bogus") == "whatsapp"
    assert pf.normalize_platform(None) == "whatsapp"


def test_platform_from_type_instance():
    assert pf.platform_from_type_instance("telegram") == "telegram"
    assert pf.platform_from_type_instance("whatsapp") == "whatsapp"
    assert pf.platform_from_type_instance(None) == "whatsapp"


# ── partner credentials never conflated ──────────────────────────────────────
def test_partner_credentials_are_distinct(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "green_partner_token", "WA-KEY")
    monkeypatch.setattr(settings, "green_partner_api_url", "https://wa.example")
    monkeypatch.setattr(settings, "green_partner_token_telegram", "TG-KEY")
    monkeypatch.setattr(settings, "green_partner_api_url_telegram", "https://tg.example")

    wa_token, wa_url = pf.partner_credentials("whatsapp")
    tg_token, tg_url = pf.partner_credentials("telegram")
    assert wa_token == "WA-KEY" and wa_url == "https://wa.example"
    assert tg_token == "TG-KEY" and tg_url == "https://tg.example"
    assert wa_token != tg_token and wa_url != tg_url


def test_green_partner_uses_platform_specific_key(monkeypatch):
    from app.config import settings
    from app.services import green_partner as gp
    monkeypatch.setattr(settings, "green_partner_token", "")
    monkeypatch.setattr(settings, "green_partner_token_telegram", "TG-ONLY")
    # WhatsApp not configured, Telegram configured — must not fall back to the other.
    assert gp.is_configured("whatsapp") is False
    assert gp.is_configured("telegram") is True
    with pytest.raises(gp.PartnerNotConfigured):
        gp._require_creds("whatsapp")
    token, _ = gp._require_creds("telegram")
    assert token == "TG-ONLY"


def test_telegram_delay_is_separate_from_whatsapp():
    lo, hi = pf.telegram_delay_seconds()
    assert (lo, hi) == (10, 15)
    from app.config import settings
    # WhatsApp default delay is a different (much larger) constant.
    assert settings.default_min_delay != lo and settings.default_max_delay != hi


# ── schema + client ──────────────────────────────────────────────────────────
def test_account_has_platform_columns():
    cols = Account.__table__.columns.keys()
    assert "platform" in cols and "api_host" in cols and "authorized_at" in cols
    assert Account.__table__.c.platform.default.arg == "whatsapp"


def test_client_is_platform_and_host_aware():
    c = GreenAPIClient("4100", "tok", platform="telegram", api_host="https://4500.api.green-api.com")
    assert c.platform == "telegram"
    assert c.base_url == "https://4500.api.green-api.com/waInstance4100"
    # default WhatsApp host preserved
    w = GreenAPIClient("7105", "tok")
    assert w.base_url == "https://api.green-api.com/waInstance7105"


def test_client_for_account_reads_platform():
    a = Account(name="TG", instance_id="4100", api_token="tok")
    a.platform = "telegram"
    a.api_host = "https://4500.api.green-api.com"
    c = GreenAPIClient.for_account(a)
    assert c.platform == "telegram" and "4500.api.green-api.com" in c.base_url


def test_telegram_chat_id_passthrough_for_resolved_ids():
    c = GreenAPIClient("4100", "tok", platform="telegram")
    assert c._chat_id("-10000000000000") == "-10000000000000"   # group id untouched
    assert c._chat_id("10000000") == "10000000"                 # resolved private chatId
    # WhatsApp client still appends @c.us
    w = GreenAPIClient("7105", "tok")
    assert w._chat_id("09123456789").endswith("@c.us")
