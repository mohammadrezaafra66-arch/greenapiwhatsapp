"""V14 PART A — Green API Partner client tests.

MANDATORY: the partner token must never appear in a raised error (rule 9).
"""
import asyncio
import pytest
from app.services import green_partner
from app.services.green_partner import PartnerNotConfigured


FAKE_TOKEN = "gac.SECRETsecretSECRET1234567890"


class _FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    """Async-context-manager stand-in for httpx.AsyncClient."""
    def __init__(self, status_code, payload):
        self._status = status_code
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None):
        # remember what URL would have been hit (it contains the token)
        _FakeClient.last_url = url
        return _FakeResp(self._status, self._payload)


def _patch_httpx(monkeypatch, status_code, payload=None):
    monkeypatch.setattr(
        green_partner.httpx, "AsyncClient",
        lambda *a, **k: _FakeClient(status_code, payload or {}),
    )


def test_require_token_raises_when_unconfigured(monkeypatch):
    monkeypatch.setattr(green_partner.settings, "green_partner_token", "")
    assert green_partner.is_configured() is False
    with pytest.raises(PartnerNotConfigured):
        green_partner._require_token()


def test_is_configured_true_with_token(monkeypatch):
    monkeypatch.setattr(green_partner.settings, "green_partner_token", FAKE_TOKEN)
    assert green_partner.is_configured() is True


def test_error_never_leaks_token(monkeypatch):
    """A failed partner call must raise an error containing neither the token nor 'gac.'."""
    monkeypatch.setattr(green_partner.settings, "green_partner_token", FAKE_TOKEN)
    _patch_httpx(monkeypatch, 403, {"error": "forbidden"})
    with pytest.raises(RuntimeError) as ei:
        asyncio.run(green_partner._partner_post("createInstance", {"name": "x"}))
    msg = str(ei.value)
    assert FAKE_TOKEN not in msg
    assert "gac." not in msg
    assert "403" in msg  # status code is fine to surface


def test_success_returns_json(monkeypatch):
    monkeypatch.setattr(green_partner.settings, "green_partner_token", FAKE_TOKEN)
    _patch_httpx(monkeypatch, 200, {"idInstance": 1101, "apiTokenInstance": "tok"})
    out = asyncio.run(green_partner.create_instance({"name": "x"}))
    assert out["idInstance"] == 1101


def test_delete_instance_account_sends_int(monkeypatch):
    monkeypatch.setattr(green_partner.settings, "green_partner_token", FAKE_TOKEN)
    _patch_httpx(monkeypatch, 200, {"deleteInstanceAccount": True})
    out = asyncio.run(green_partner.delete_instance_account("7105325764"))
    assert out["deleteInstanceAccount"] is True


def test_sync_auto_name_guard():
    """Auto-generated names may be overwritten from Green API; user names must not."""
    from app.services.partner_sync import _is_auto_name
    assert _is_auto_name("شماره 1101", "1101") is True     # auto prefix
    assert _is_auto_name("1101", "1101") is True            # equals id
    assert _is_auto_name(None, "1101") is True              # empty
    assert _is_auto_name("فروش تهران", "1101") is False     # user-chosen
