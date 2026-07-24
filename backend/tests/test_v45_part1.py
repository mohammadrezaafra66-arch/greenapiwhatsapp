"""V45 PART 1 — "our own numbers" exclusion list: normalization, CRUD, and pre-seed.

Hermetic (fake in-memory session, no live DB), matching the project's unit-test convention. Proves:
  • the match key reuses the EXISTING normalizer and collapses every equivalent phone format;
  • add/remove via the service AND the API endpoint work and are idempotent (no duplicate);
  • pre-seed populates from accounts that have a phone, without duplicating, and is re-runnable.
"""
import uuid
from types import SimpleNamespace

import pytest

from app.models.own_number import OwnNumberExclusion
from app.services import own_number_exclusion as own
from app.api.v1.own_numbers import add_own_number, remove_own_number, list_own_numbers, OwnNumberBody
from fastapi import HTTPException


# ── a fake AsyncSession that understands exactly the queries the service issues ────────────────
class _Result:
    def __init__(self, rows): self._rows = list(rows)
    def scalars(self): return self
    def all(self): return list(self._rows)
    def scalar_one_or_none(self): return self._rows[0] if self._rows else None


class FakeSession:
    def __init__(self, accounts=None):
        self.rows = []                      # OwnNumberExclusion rows
        self.accounts = list(accounts or [])  # SimpleNamespace(phone=..., name=...)

    async def execute(self, q):
        cds = q.column_descriptions
        if len(cds) == 2:                   # select(Account.phone, Account.name)
            return _Result([(a.phone, a.name) for a in self.accounts if a.phone is not None])
        name = cds[0].get("name")
        if name == "phone_core":            # select(OwnNumberExclusion.phone_core)
            return _Result([r.phone_core for r in self.rows])
        target = q.compile().params.get("phone_core_1")   # select(OwnNumberExclusion).where(...)
        if target is not None:
            return _Result([r for r in self.rows if r.phone_core == target])
        return _Result(list(self.rows))

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        self.rows.append(obj)

    async def get(self, model, pk):
        return next((r for r in self.rows if r.id == pk), None)

    async def delete(self, obj):
        self.rows = [r for r in self.rows if r is not obj]

    async def commit(self): pass
    async def refresh(self, obj): pass


# ── normalization: one key across every equivalent format (reuses the existing normalizer) ────
def test_normalize_collapses_equivalent_formats():
    forms = [
        "09121234567", "989121234567", "+989121234567", "98 912 123 4567",
        "989121234567@c.us", "۰۹۱۲۱۲۳۴۵۶۷",  # Persian digits
    ]
    keys = {own.normalize_own_number(f) for f in forms}
    assert keys == {"9121234567"}            # every form → the same national core


def test_normalize_distinguishes_different_numbers():
    assert own.normalize_own_number("09121234567") != own.normalize_own_number("09121234568")


def test_normalize_empty_is_blank():
    assert own.normalize_own_number("") == ""
    assert own.normalize_own_number(None) == ""


# ── add / idempotency / is_excluded ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_add_then_excluded_across_formats():
    db = FakeSession()
    row, created = await own.add_exclusion(db, "09121234567", label="my line")
    assert created is True and row.phone_core == "9121234567"
    assert len(db.rows) == 1
    # a DIFFERENT stored form of the SAME number is recognized as excluded
    assert await own.is_excluded(db, "989121234567@c.us") is True
    assert await own.is_excluded(db, "09120000000") is False


@pytest.mark.asyncio
async def test_add_duplicate_is_noop_no_second_row():
    db = FakeSession()
    _, c1 = await own.add_exclusion(db, "09121234567")
    _, c2 = await own.add_exclusion(db, "+989121234567")   # same number, other format
    assert c1 is True and c2 is False
    assert len(db.rows) == 1                                # never duplicated


@pytest.mark.asyncio
async def test_remove_deletes_row():
    db = FakeSession()
    row, _ = await own.add_exclusion(db, "09121234567")
    assert await own.remove_exclusion(db, row.id) is True
    assert db.rows == []
    assert await own.remove_exclusion(db, uuid.uuid4()) is False


# ── pre-seed from connected instances (accounts with a phone), deduped + re-runnable ──────────
@pytest.mark.asyncio
async def test_seed_from_accounts_populates_and_dedups():
    accounts = [
        SimpleNamespace(phone="989121111111", name="Acc1"),
        SimpleNamespace(phone="09122222222", name="Acc2"),
        SimpleNamespace(phone=None, name="NoPhone"),          # skipped (no number)
        SimpleNamespace(phone="989121111111", name="Dup"),    # same core as Acc1 → not duplicated
    ]
    db = FakeSession(accounts=accounts)
    added = await own.seed_from_accounts(db)
    assert added == 2
    cores = await own.get_excluded_cores(db)
    assert cores == {"9121111111", "9122222222"}
    # re-running seeds nothing new (idempotent)
    assert await own.seed_from_accounts(db) == 0
    assert len(db.rows) == 2


@pytest.mark.asyncio
async def test_seed_does_not_touch_manual_entry():
    db = FakeSession(accounts=[SimpleNamespace(phone="989121111111", name="Acc1")])
    await own.add_exclusion(db, "09129999999", label="manual", source="manual")
    await own.seed_from_accounts(db)
    by_core = {r.phone_core: r for r in db.rows}
    assert by_core["9129999999"].source == "manual"        # untouched
    assert by_core["9121111111"].source == "account"


# ── the API endpoints (thin wrappers) behave correctly ────────────────────────────────────────
@pytest.mark.asyncio
async def test_api_add_list_remove_roundtrip():
    db = FakeSession()
    res = await add_own_number(OwnNumberBody(phone="0912 123 4567", label="x"), db=db)
    assert res["created"] is True
    listed = await list_own_numbers(db=db)
    assert listed["count"] == 1 and listed["items"][0]["phone_core"] == "9121234567"
    # duplicate add via API → created False, still one row
    res2 = await add_own_number(OwnNumberBody(phone="989121234567"), db=db)
    assert res2["created"] is False
    assert (await list_own_numbers(db=db))["count"] == 1
    # remove
    rid = res["item"]["id"]
    await remove_own_number(rid, db=db)
    assert (await list_own_numbers(db=db))["count"] == 0


@pytest.mark.asyncio
async def test_api_add_rejects_invalid_number():
    db = FakeSession()
    with pytest.raises(HTTPException):
        await add_own_number(OwnNumberBody(phone="abc"), db=db)
