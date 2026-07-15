"""V19 PART 3 — group warm-up UI data + manual link vault (endpoint layer).

DB via FakeSession. Asserts: warm-account dropdown flags warm/graduated; selecting a group
persists a target (upsert); listing targets; the link-vault CRUD + the manual-join Persian
notice.
"""
import uuid
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.api.v1 import warmup as W
from app.models.account import Account, AccountStatus
from app.models.warmup_mesh import WarmupGroupTarget, WarmupLinkVault
from app.services.warmup_state import WarmupState


class FakeScalars:
    def __init__(self, items): self._items = list(items)
    def all(self): return list(self._items)


class FakeResult:
    def __init__(self, scalars=None, rows=None):
        self._scalars = scalars if scalars is not None else []
        self._rows = rows or []
    def scalars(self): return FakeScalars(self._scalars)
    def scalar_one_or_none(self): return self._scalars[0] if self._scalars else None
    def all(self): return list(self._rows)


class FakeSession:
    def __init__(self, results=None, gets=None):
        self._results = list(results or [])
        self._gets = dict(gets or {})
        self.added = []; self.commits = 0; self.deleted = []
    async def get(self, model, pk): return self._gets.get(model.__name__)
    async def execute(self, q): return self._results.pop(0) if self._results else FakeResult()
    def add(self, o): self.added.append(o)
    async def commit(self): self.commits += 1
    async def refresh(self, o):
        if getattr(o, "id", None) is None: o.id = uuid.uuid4()
    async def delete(self, o): self.deleted.append(o)


def _acc(instance_id="WARM", is_warm_peer=False):
    a = Account(name=f"acc-{instance_id}", instance_id=instance_id, api_token="t")
    a.id = uuid.uuid4(); a.status = AccountStatus.active; a.is_warm_peer = is_warm_peer
    return a


# ── warm-accounts dropdown ───────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_warm_accounts_flags_warm_and_graduated():
    warm = _acc("W", is_warm_peer=True)
    grad = _acc("G")
    cold = _acc("C")
    db = FakeSession(results=[
        FakeResult(scalars=[cold, grad, warm]),          # active accounts
        FakeResult(rows=[("G", WarmupState.GRADUATED.value, True)]),  # enrollment map (G graduated)
    ])
    res = await W.warm_accounts(db)
    by = {a["instance_id"]: a for a in res["accounts"]}
    assert by["W"]["is_warm"] is True        # marked warm peer
    assert by["G"]["is_warm"] is True        # graduated
    assert by["C"]["is_warm"] is False       # cold
    # warm ones sort first
    assert res["accounts"][0]["is_warm"] is True


# ── group-target selection (upsert) ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_set_group_target_creates_then_updates():
    acc = _acc("WARM")
    # create (no existing)
    db = FakeSession(gets={"Account": acc}, results=[FakeResult(scalars=[])])
    body = W.GroupTargetBody(group_id="120@g.us", group_subject="گروه فروش", is_selected=True)
    res = await W.set_group_target(str(acc.id), body, db)
    assert res["ok"] is True and res["is_selected"] is True
    created = [x for x in db.added if isinstance(x, WarmupGroupTarget)]
    assert len(created) == 1 and created[0].group_id == "120@g.us" and created[0].warm_instance_id == "WARM"

    # update (existing row → toggle off)
    existing = WarmupGroupTarget(warm_instance_id="WARM", group_id="120@g.us",
                                 group_subject="گروه فروش", is_selected=True)
    db2 = FakeSession(gets={"Account": acc}, results=[FakeResult(scalars=[existing])])
    await W.set_group_target(str(acc.id), W.GroupTargetBody(group_id="120@g.us", is_selected=False), db2)
    assert existing.is_selected is False


@pytest.mark.asyncio
async def test_list_group_targets():
    acc = _acc("WARM")
    t1 = WarmupGroupTarget(warm_instance_id="WARM", group_id="120@g.us", group_subject="گ۱", is_selected=True)
    db = FakeSession(gets={"Account": acc}, results=[FakeResult(scalars=[t1])])
    res = await W.list_group_targets(str(acc.id), db)
    assert res["targets"][0]["group_id"] == "120@g.us" and res["targets"][0]["is_selected"] is True


# ── link vault CRUD + manual notice ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_link_vault_add_and_list_carry_manual_notice():
    db = FakeSession()
    body = W.LinkVaultBody(group_name="گروه عمومی", invite_link="https://chat.whatsapp.com/AbC", notes="n")
    created = await W.add_link_vault(body, db)
    assert created["invite_link"] == "https://chat.whatsapp.com/AbC"
    assert any(isinstance(x, WarmupLinkVault) for x in db.added)

    row = WarmupLinkVault(group_name="گروه عمومی", invite_link="https://chat.whatsapp.com/AbC")
    row.id = uuid.uuid4()
    db2 = FakeSession(results=[FakeResult(scalars=[row])])
    listed = await W.list_link_vault(db2)
    assert "Green API" in listed["notice"] and "دستی" in listed["notice"]     # manual-join notice
    assert listed["links"][0]["invite_link"] == "https://chat.whatsapp.com/AbC"


@pytest.mark.asyncio
async def test_link_vault_add_requires_link():
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        await W.add_link_vault(W.LinkVaultBody(invite_link="   "), FakeSession())


@pytest.mark.asyncio
async def test_link_vault_delete():
    row = WarmupLinkVault(group_name="g", invite_link="https://chat.whatsapp.com/x"); row.id = uuid.uuid4()
    db = FakeSession(gets={"WarmupLinkVault": row})
    res = await W.delete_link_vault(str(row.id), db)
    assert res["ok"] is True and row in db.deleted
