"""V20 PART 1 — fix the stuck warm-up toggle.

The bug: disabling a number with a legacy auto_warmup flag but NO enrollment didn't persist
(disable_warmup returned early without commit → get_db discarded auto_warmup=False → box
sprang back). Tests: disable now commits in the no-enrollment branch; the toggle endpoint
persists auto_warmup=False; and the idempotent reconcile clears only flags with no active
enrollment.
"""
import uuid
import pytest
from unittest.mock import AsyncMock, patch

from app.models.account import Account, AccountStatus
from app.models.warmup_mesh import WarmupEnrollment
from app.services.warmup_state import WarmupState
from app.services import warmup_mesh_service as svc
from app.services.warmup_exclusion import reconcile_stale_auto_warmup


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
        self.added = []; self.commits = 0
    async def get(self, model, pk): return self._gets.get(model.__name__)
    async def execute(self, q): return self._results.pop(0) if self._results else FakeResult()
    def add(self, o): self.added.append(o)
    async def commit(self): self.commits += 1
    async def refresh(self, o): pass
    async def flush(self): pass


def _acc(instance_id="7105325764", auto_warmup=True):
    a = Account(name="n", instance_id=instance_id, api_token="t"); a.id = uuid.uuid4()
    a.status = AccountStatus.active; a.auto_warmup = auto_warmup; a.is_warm_peer = False
    return a


# ── disable_warmup commits even with no enrollment ──────────────────────────
@pytest.mark.asyncio
async def test_disable_no_enrollment_commits():
    db = FakeSession(results=[FakeResult(scalars=[])])   # no enrollment
    res = await svc.disable_warmup(db, _acc())
    assert res["disabled"] is True and res["state"] is None
    assert db.commits == 1                                # THE FIX: commit happens now


@pytest.mark.asyncio
async def test_disable_with_enrollment_still_commits_and_pauses():
    enr = WarmupEnrollment(instance_id="COLD", state=WarmupState.RECEIVING.value)
    enr.id = uuid.uuid4(); enr.is_enabled = True
    db = FakeSession(results=[FakeResult(scalars=[enr])])
    res = await svc.disable_warmup(db, _acc(instance_id="COLD"))
    assert enr.is_enabled is False and res["state"] == WarmupState.PAUSED.value
    assert db.commits == 1


# ── the toggle endpoint persists auto_warmup=False on OFF (no enrollment) ────
@pytest.mark.asyncio
async def test_toggle_off_persists_auto_warmup_false():
    from app.api.v1 import accounts as accounts_api
    acc = _acc(auto_warmup=True)
    db = FakeSession(results=[FakeResult(scalars=[])], gets={"Account": acc})  # disable: no enrollment
    with patch.object(accounts_api, "_get_account", new=AsyncMock(return_value=acc)):
        res = await accounts_api.set_auto_warmup(str(acc.id), accounts_api.WarmupToggle(enabled=False), db)
    assert res["warmup_enrolled"] is False
    assert acc.auto_warmup is False        # cleared…
    assert db.commits >= 1                  # …AND committed (survives get_db close)


# ── idempotent reconcile of stale flags ─────────────────────────────────────
@pytest.mark.asyncio
async def test_reconcile_clears_only_flags_without_active_enrollment():
    stale1 = _acc("7105325764", auto_warmup=True)
    stale2 = _acc("770022683810", auto_warmup=True)
    enrolled = _acc("770022683837", auto_warmup=True)   # has an ACTIVE enrollment → keep
    db = FakeSession(results=[
        FakeResult(rows=[("770022683837", WarmupState.COOLDOWN.value, True)]),  # enrollment map
        FakeResult(scalars=[stale1, stale2, enrolled]),                          # auto_warmup=true accounts
    ])
    cleared = await reconcile_stale_auto_warmup(db)
    assert cleared == 2
    assert stale1.auto_warmup is False and stale2.auto_warmup is False
    assert enrolled.auto_warmup is True         # active enrollment → untouched
    assert db.commits == 1


@pytest.mark.asyncio
async def test_reconcile_idempotent_noop_when_nothing_stale():
    enrolled = _acc("770022683837", auto_warmup=True)
    db = FakeSession(results=[
        FakeResult(rows=[("770022683837", WarmupState.COOLDOWN.value, True)]),
        FakeResult(scalars=[enrolled]),
    ])
    cleared = await reconcile_stale_auto_warmup(db)
    assert cleared == 0 and db.commits == 0     # nothing to clear → no write


@pytest.mark.asyncio
async def test_reconcile_disabled_enrollment_counts_as_stale():
    # enrollment exists but is_enabled=False → the flag should still be cleared
    acc = _acc("X", auto_warmup=True)
    db = FakeSession(results=[
        FakeResult(rows=[("X", WarmupState.PAUSED.value, False)]),   # disabled enrollment
        FakeResult(scalars=[acc]),
    ])
    cleared = await reconcile_stale_auto_warmup(db)
    assert cleared == 1 and acc.auto_warmup is False
