"""V27 PART 5 — lazy cached WhatsApp-existence validation.

Proves:
  • a number checked within the cache window is NOT re-checked (no duplicate CheckWhatsapp);
  • a nonexistent number is excluded with a logged reason;
  • cache expiry after the window triggers a fresh single check;
  • the validator is fail-open when the client can't check.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest

from app.services import number_validation as nv
from app.services.number_validation import (
    validate_number, filter_numbers, cache_is_fresh, NUMBER_CHECK_TTL_DAYS,
    NONEXISTENT_REASON_FA,
)

NOW = datetime(2026, 7, 18, 12, 0, 0)


class _Row:
    def __init__(self, phone, exists, checked_at):
        self.phone, self.exists, self.checked_at, self.reason = phone, exists, checked_at, None


class _Result:
    def __init__(self, row): self._row = row
    def scalar_one_or_none(self): return self._row


class _DB:
    """Fake DB backed by a dict of phone->row; counts nothing but stores added rows."""
    def __init__(self, rows=None):
        self.rows = {r.phone: r for r in (rows or [])}
        self.added = []
    async def execute(self, *a, **k):
        # crude: return the row whose phone appears in the compiled query params isn't available,
        # so we stash the "current phone" via _lookup set by validate_number's caller pattern.
        return _Result(self.rows.get(self._current))
    def add(self, obj):
        self.added.append(obj); self.rows[obj.phone] = obj
    async def commit(self): pass


class _CountingClient:
    def __init__(self, exists=True):
        self.exists, self.calls = exists, 0
    async def check_whatsapp(self, phone):
        self.calls += 1
        return self.exists


# helper: patch _get_cached to use our dict keyed lookup deterministically
@pytest.fixture
def db_and_patch(monkeypatch):
    store = {}
    added = []

    async def _get_cached(db, phone):
        return store.get(str(phone))

    class _FakeDB:
        def add(self, obj):
            added.append(obj); store[obj.phone] = obj
        async def commit(self): pass

    monkeypatch.setattr(nv, "_get_cached", _get_cached)
    return _FakeDB(), store, added


# ── pure freshness ───────────────────────────────────────────────────────────
def test_cache_is_fresh():
    assert cache_is_fresh(_Row("p", True, NOW), NOW) is True
    assert cache_is_fresh(_Row("p", True, NOW - timedelta(days=NUMBER_CHECK_TTL_DAYS + 1)), NOW) is False
    assert cache_is_fresh(None, NOW) is False


# ── caching behaviour ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_fresh_cache_is_not_rechecked(db_and_patch):
    db, store, _ = db_and_patch
    store["98901"] = _Row("98901", True, NOW - timedelta(days=1))   # checked yesterday
    client = _CountingClient(exists=True)
    res = await validate_number(db, "98901", client, NOW)
    assert res == {"exists": True, "from_cache": True, "checked": False}
    assert client.calls == 0                                        # NO duplicate check


@pytest.mark.asyncio
async def test_nonexistent_number_excluded_and_cached(db_and_patch):
    db, store, added = db_and_patch
    client = _CountingClient(exists=False)
    res = await validate_number(db, "98902", client, NOW)
    assert res["exists"] is False and res["checked"] is True and client.calls == 1
    assert store["98902"].exists is False and store["98902"].reason == NONEXISTENT_REASON_FA


@pytest.mark.asyncio
async def test_expired_cache_triggers_one_fresh_check(db_and_patch):
    db, store, _ = db_and_patch
    store["98903"] = _Row("98903", True, NOW - timedelta(days=NUMBER_CHECK_TTL_DAYS + 2))
    client = _CountingClient(exists=True)
    res = await validate_number(db, "98903", client, NOW)
    assert res["from_cache"] is False and res["checked"] is True and client.calls == 1


@pytest.mark.asyncio
async def test_fail_open_when_client_cannot_check(db_and_patch):
    db, _, _ = db_and_patch

    class _Broken:
        async def check_whatsapp(self, phone): raise RuntimeError("no method")
    res = await validate_number(db, "98904", _Broken(), NOW)
    assert res["exists"] is True and res["checked"] is False       # fail-open


@pytest.mark.asyncio
async def test_filter_numbers_splits_valid_and_excluded(db_and_patch):
    db, store, _ = db_and_patch

    class _SelectiveClient:
        async def check_whatsapp(self, phone): return phone != "BAD"
    out = await filter_numbers(db, ["G1", "BAD", "G2"], _SelectiveClient(), NOW)
    assert out["valid"] == ["G1", "G2"]
    assert out["excluded"] == [{"phone": "BAD", "reason": NONEXISTENT_REASON_FA}]
