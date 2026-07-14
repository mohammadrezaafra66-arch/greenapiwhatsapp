"""V16 PART 1 — Supabase connectivity diagnostic (reachable+data / +empty / unreachable)."""
import asyncio
import pytest
from app.services import supabase_health


class _Resp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload if payload is not None else []

    def json(self):
        return self._payload


class _Client:
    """Fake httpx.AsyncClient; routes by URL suffix."""
    def __init__(self, health=200, products=(200, [{"id": "1"}])):
        self._health = health
        self._products = products

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None, headers=None):
        if "/auth/v1/health" in url:
            return _Resp(self._health)
        if "/rest/v1/" in url:
            code, rows = self._products
            return _Resp(code, rows)
        return _Resp(404)


def _patch(monkeypatch, tcp_ok, health=200, products=(200, [{"id": "1"}])):
    async def fake_tcp(timeout=3.0):
        return tcp_ok
    monkeypatch.setattr(supabase_health, "_tcp_ok", fake_tcp)
    monkeypatch.setattr(supabase_health.httpx, "AsyncClient", lambda *a, **k: _Client(health, products))


def test_reachable_with_data_is_connected(monkeypatch):
    _patch(monkeypatch, True, 200, (200, [{"id": "1"}]))
    r = asyncio.run(supabase_health.check_supabase())
    assert r["status"] == "connected"
    assert r["reachable"] is True
    assert r["rest_products"]["count"] == 1


def test_reachable_but_empty_is_empty(monkeypatch):
    _patch(monkeypatch, True, 200, (200, []))
    r = asyncio.run(supabase_health.check_supabase())
    assert r["status"] == "empty"
    assert r["reachable"] is True
    assert r["rest_products"]["count"] == 0


def test_tcp_down_is_disconnected(monkeypatch):
    _patch(monkeypatch, False)
    r = asyncio.run(supabase_health.check_supabase())
    assert r["status"] == "disconnected"
    assert r["reachable"] is False
    assert r["tcp"]["ok"] is False


def test_reachable_but_401_is_disconnected(monkeypatch):
    _patch(monkeypatch, True, 200, (401, {"code": "42501"}))
    r = asyncio.run(supabase_health.check_supabase())
    assert r["status"] == "disconnected"
    assert r["reachable"] is False
    assert r["rest_products"]["http"] == 401
