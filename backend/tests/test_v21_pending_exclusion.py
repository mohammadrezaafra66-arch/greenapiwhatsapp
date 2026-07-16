"""V21 PART 2 — exclude pending / never-connected numbers from the mesh.

A number that isn't `authorized` on Green API must never enter the mesh: no enrollment, no
edges, no send, and it consumes no warm-peer ratio slot. It shows a connect-first notice until
it authorizes; once authorized it proceeds normally.
"""
import uuid
import random
from datetime import datetime
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.models.account import Account, AccountStatus
from app.models.warmup_mesh import WarmupEnrollment, WarmupMeshEdge
from app.services import warmup_mesh_service as svc
from app.services.warmup_mesh_service import (
    instance_is_authorized, enroll_and_preflight, NOT_CONNECTED_NOTICE,
)
from app.services.warmup_engine import run_warmup_tick
from app.services.warmup_state import WarmupState


class FakeScalars:
    def __init__(self, items): self._items = list(items)
    def all(self): return list(self._items)


class FakeResult:
    def __init__(self, rows=None, scalars=None):
        self._rows = rows or []
        self._scalars = scalars if scalars is not None else []
    def all(self): return list(self._rows)
    def scalars(self): return FakeScalars(self._scalars)
    def scalar_one_or_none(self): return self._scalars[0] if self._scalars else None


class FakeSession:
    def __init__(self, results=None):
        self._results = list(results or [])
        self.added = []; self.commits = 0
    async def execute(self, q): return self._results.pop(0) if self._results else FakeResult()
    def add(self, o): self.added.append(o)
    async def commit(self): self.commits += 1
    async def flush(self): pass


def _acc(iid, status=AccountStatus.active, is_warm_peer=False):
    a = Account(name=f"acc-{iid}", instance_id=iid, api_token="t")
    a.id = uuid.uuid4(); a.status = status; a.is_warm_peer = is_warm_peer
    a.phone = f"98904824{iid[-4:]}"
    return a


def _client(state):
    c = MagicMock()
    c.instance_id = "X"
    c.get_state = AsyncMock(return_value=state)
    c.set_warming_instance_settings = AsyncMock(return_value=True)
    c.show_messages_queue = AsyncMock(return_value=[])
    c.clear_messages_queue = AsyncMock(return_value=True)
    c.add_contact = AsyncMock(return_value=True)
    c.send_message = AsyncMock(return_value="MID")
    return c


# ── instance_is_authorized (fail-safe) ──────────────────────────────────────
@pytest.mark.asyncio
async def test_is_authorized_true_only_for_authorized():
    assert await instance_is_authorized(_client("authorized")) is True
    assert await instance_is_authorized(_client("notAuthorized")) is False
    assert await instance_is_authorized(_client("pending")) is False


@pytest.mark.asyncio
async def test_is_authorized_false_on_error():
    c = MagicMock(); c.instance_id = "X"
    c.get_state = AsyncMock(side_effect=RuntimeError("network"))
    assert await instance_is_authorized(c) is False


# ── enroll gate: pending instance → no enrollment, no edges, connect notice ──
@pytest.mark.asyncio
async def test_enroll_pending_creates_nothing_and_notices():
    acc = _acc("C1")
    db = FakeSession()
    res = await enroll_and_preflight(db, acc, client_factory=lambda *a: _client("notAuthorized"))
    assert res["not_connected"] is True
    assert res["notice"] == NOT_CONNECTED_NOTICE
    assert res["state"] is None
    # NO enrollment / edge created, no state applied
    assert [x for x in db.added if isinstance(x, WarmupEnrollment)] == []
    assert [x for x in db.added if isinstance(x, WarmupMeshEdge)] == []
    assert res["settings_applied"] is False and res["peers"] == []


@pytest.mark.asyncio
async def test_enroll_authorized_proceeds():
    acc = _acc("C1")
    db = FakeSession(results=[
        FakeResult(scalars=[]),          # existing enrollment (none)
        FakeResult(scalars=[]),          # existing edges
        FakeResult(scalars=[]),          # eligible: active accounts (no peers)
        FakeResult(scalars=[]),          # eligible: graduated
    ])
    res = await enroll_and_preflight(db, acc, client_factory=lambda *a: _client("authorized"),
                                     now=datetime(2026, 5, 1, 9, 0, 0))
    assert res.get("not_connected") is None
    assert res["state"] == WarmupState.COOLDOWN.value          # enrolled + held in cooldown
    assert [x for x in db.added if isinstance(x, WarmupEnrollment)]  # enrollment created


# ── tick gate: a pending enrolled number is skipped (no edges, no send) ──────
@pytest.mark.asyncio
async def test_tick_skips_pending_number():
    enr = WarmupEnrollment(instance_id="C1", phone="989048240001",
                           state=WarmupState.COOLDOWN.value, is_enabled=True)
    enr.id = uuid.uuid4()
    enr.authorized_at = datetime(2026, 5, 1, 9, 0, 0)
    enr.started_at = datetime(2026, 5, 1, 9, 0, 0)
    enr.next_action_at = None; enr.rest_until = None
    enr.sent_today = 0; enr.received_today = 0; enr.counters_date = None
    acc = _acc("C1")
    rec = {"get_state": 0, "add_contact": 0, "send": 0}

    def factory(iid, tok):
        c = MagicMock(); c.instance_id = iid
        async def _gs(): rec.__setitem__("get_state", rec["get_state"] + 1); return "notAuthorized"
        async def _add(*a, **k): rec.__setitem__("add_contact", rec["add_contact"] + 1); return True
        async def _send(*a, **k): rec.__setitem__("send", rec["send"] + 1); return "MID"
        c.get_state = AsyncMock(side_effect=_gs)
        c.add_contact = AsyncMock(side_effect=_add)
        c.send_message = AsyncMock(side_effect=_send)
        return c

    db = FakeSession(results=[
        FakeResult(scalars=[]),          # is_breaker_tripped: kill events (none → not tripped)
        FakeResult(scalars=[enr]),       # enabled enrollments
        FakeResult(scalars=[acc]),       # account lookup for the enrollment
    ])
    out = await run_warmup_tick(db, now=datetime(2026, 5, 1, 10, 0, 0), client_factory=factory,
                                rng=random.Random(0))
    # the pending number was checked and skipped — no edges built, nothing sent
    assert rec["get_state"] == 1                 # connection was verified
    assert rec["add_contact"] == 0 and rec["send"] == 0
    assert [x for x in db.added if isinstance(x, WarmupMeshEdge)] == []
    assert out["idle"] == 1 and out["acted"] == 0
