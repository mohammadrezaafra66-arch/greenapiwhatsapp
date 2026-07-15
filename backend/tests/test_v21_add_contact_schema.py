"""V21 — Green API add_contact schema + idempotency.

Green API's addContact takes chatId/firstName/lastName. The old phoneContact/company payload
returned 400 ("'chatId' is required" / "'company' is not allowed"), silently breaking the mesh
handshake. And a re-save returns 400 "Contact ... already exists" — which is a SUCCESS for the
handshake (the contact IS saved). These tests lock both behaviours in.
"""
import httpx
import pytest
from unittest.mock import AsyncMock

from app.services.green_api import GreenAPIClient


@pytest.mark.asyncio
async def test_add_contact_uses_chatid_schema(monkeypatch):
    c = GreenAPIClient("INST", "TOK")
    captured = {}
    async def fake_post(endpoint, data=None, timeout=30):
        captured["endpoint"] = endpoint; captured["data"] = data
        return {"addContact": True}
    monkeypatch.setattr(c, "_post", fake_post)
    ok = await c.add_contact("989122270261", "محمدرضا", "")
    assert ok is True
    assert captured["endpoint"] == "addContact"
    # correct schema: chatId (NOT phoneContact), no company field
    assert captured["data"]["chatId"] == "989122270261@c.us"
    assert "phoneContact" not in captured["data"]
    assert "company" not in captured["data"]
    assert captured["data"]["firstName"] == "محمدرضا"


@pytest.mark.asyncio
async def test_add_contact_treats_already_exists_as_success(monkeypatch):
    c = GreenAPIClient("INST", "TOK")
    resp = httpx.Response(400, json={"message": "Contact 989122270261@c.us already exists"},
                          request=httpx.Request("POST", "http://x/addContact"))
    async def fake_post(endpoint, data=None, timeout=30):
        raise httpx.HTTPStatusError("400", request=resp.request, response=resp)
    monkeypatch.setattr(c, "_post", fake_post)
    # "already exists" → the contact IS in the book → handshake success
    assert await c.add_contact("989122270261", "Peer") is True


@pytest.mark.asyncio
async def test_add_contact_reraises_other_400(monkeypatch):
    c = GreenAPIClient("INST", "TOK")
    resp = httpx.Response(400, json={"message": "Validation failed"},
                          request=httpx.Request("POST", "http://x/addContact"))
    async def fake_post(endpoint, data=None, timeout=30):
        raise httpx.HTTPStatusError("400", request=resp.request, response=resp)
    monkeypatch.setattr(c, "_post", fake_post)
    with pytest.raises(httpx.HTTPStatusError):
        await c.add_contact("989122270261", "Peer")
