"""V20 PART 2 — warm-peer designation (sender role, separate from being warmed).

Asserts: is_warm_peer makes an instance an eligible mesh peer WITHOUT enrollment; a warm
peer is NEVER enrolled/warmed (enroll_and_preflight refuses; batch skips it); an enrolled
cold number builds edges to a marked peer (fixes the 0-edge case); GRADUATED stays
eligible; mesh cadence (plan_number_action) is unaffected.
"""
import uuid
import random
import inspect
from datetime import datetime
from types import SimpleNamespace
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.models.account import Account, AccountStatus
from app.models.warmup_mesh import WarmupEnrollment, WarmupMeshEdge
from app.services import warmup_mesh_service as svc
from app.services.warmup_mesh_service import (
    eligible_peer_accounts, enroll_and_preflight, ensure_mesh_edges, edge_is_messageable,
    WARM_PEER_NOT_WARMED_NOTICE,
)
from app.services.warmup_state import WarmupState


class FakeScalars:
    def __init__(self, items): self._items = list(items)
    def all(self): return list(self._items)


class FakeResult:
    def __init__(self, scalars=None):
        self._scalars = scalars if scalars is not None else []
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


def _acc(instance_id, phone=None, is_warm_peer=False, status=AccountStatus.active):
    a = Account(name=f"acc-{instance_id}", instance_id=instance_id, api_token="t")
    a.id = uuid.uuid4(); a.status = status; a.is_warm_peer = is_warm_peer
    a.phone = phone or f"9891200000{instance_id[-2:]}"
    return a


def _mock_factory(rec):
    def factory(iid, tok):
        c = MagicMock()
        async def _add(phone, name, *a, **k):
            rec.setdefault(iid, []).append(("add_contact", phone)); return True
        c.add_contact = AsyncMock(side_effect=_add)
        rec.setdefault(iid, [])
        return c
    return factory


# ── eligibility: is_warm_peer OR graduated ──────────────────────────────────
@pytest.mark.asyncio
async def test_warm_peer_is_eligible_without_enrollment():
    peer = _acc("WARM", is_warm_peer=True)
    grad = _acc("GRAD")
    cold = _acc("COLD")
    db = FakeSession(results=[
        FakeResult(scalars=[peer, grad, cold]),       # active accounts
        FakeResult(scalars=["GRAD"]),                  # graduated instance ids
    ])
    out = await eligible_peer_accounts(db, exclude_instance_id="NEW")
    ids = {a.instance_id for a in out}
    assert ids == {"WARM", "GRAD"}          # warm peer + graduated; cold excluded


# ── a warm peer is NEVER enrolled/warmed ────────────────────────────────────
@pytest.mark.asyncio
async def test_enroll_refuses_warm_peer():
    peer = _acc("WARM", is_warm_peer=True)
    db = FakeSession()
    res = await enroll_and_preflight(db, peer, client_factory=lambda *a: MagicMock())
    assert res["is_warm_peer"] is True
    assert res["notice"] == WARM_PEER_NOT_WARMED_NOTICE
    assert res["state"] is None
    # NO enrollment row created — a peer is never put on the being-warmed side
    assert [x for x in db.added if isinstance(x, WarmupEnrollment)] == []
    assert db.commits == 0


@pytest.mark.asyncio
async def test_batch_enroll_skips_warm_peers():
    from app.api.v1 import warmup as W
    peer = _acc("WARM", is_warm_peer=True)
    cold = _acc("COLD1")
    db = FakeSession(results=[
        FakeResult(scalars=[peer, cold]),   # active accounts
        FakeResult(scalars=[]),             # already-enrolled ids (none)
    ])
    called = []
    async def fake_enroll(db_, acc, **k):
        called.append(acc.instance_id); return {"state": "COOLDOWN"}
    import app.services.warmup_mesh_service as mesh
    orig = mesh.enroll_and_preflight
    mesh.enroll_and_preflight = fake_enroll
    try:
        res = await W.mesh_start_all(db)
    finally:
        mesh.enroll_and_preflight = orig
    assert "WARM" not in called          # peer skipped
    assert called == ["COLD1"]           # only the cold number enrolled
    assert res["started"] == 1


# ── ensure_mesh_edges: cold number builds an edge to a warm peer ────────────
@pytest.mark.asyncio
async def test_ensure_mesh_edges_builds_edge_to_peer():
    cold = _acc("COLD", phone="989120000001")
    peer = _acc("WARM", phone="989122270261", is_warm_peer=True)
    rec = {}
    db = FakeSession(results=[
        FakeResult(scalars=[]),               # existing edges for COLD → none
        FakeResult(scalars=[peer]),           # eligible_peer_accounts: active accounts
        FakeResult(scalars=[]),               # eligible_peer_accounts: graduated ids
        FakeResult(scalars=[]),               # _handshake_edge: edge pair lookup → none
    ])
    built = await ensure_mesh_edges(db, cold, client_factory=_mock_factory(rec),
                                    now=datetime(2026, 5, 1), rng=random.Random(0))
    assert built == 1
    edges = [x for x in db.added if isinstance(x, WarmupMeshEdge)]
    assert len(edges) == 1 and edges[0].peer_instance_id == "WARM"
    assert edge_is_messageable(edges[0])        # mutual contact saved on both sides
    # mutual AddContact happened on BOTH instances
    assert rec["COLD"] and rec["WARM"]
    assert db.commits == 1


@pytest.mark.asyncio
async def test_ensure_mesh_edges_noop_without_peers():
    cold = _acc("COLD", phone="989120000001")
    db = FakeSession(results=[
        FakeResult(scalars=[]),      # existing edges → none
        FakeResult(scalars=[cold]),  # active accounts (only itself, excluded)
        FakeResult(scalars=[]),      # graduated → none
    ])
    built = await ensure_mesh_edges(db, cold, client_factory=lambda *a: MagicMock(),
                                    now=datetime(2026, 5, 1))
    assert built == 0                # no eligible peer → nothing built (silent 0-peer)
    assert db.commits == 0


@pytest.mark.asyncio
async def test_ensure_mesh_edges_noop_when_slots_full():
    cold = _acc("COLD")
    # already has max peers → no new edges
    existing = [SimpleNamespace(peer_instance_id=f"P{i}") for i in range(6)]
    db = FakeSession(results=[FakeResult(scalars=existing)])
    built = await ensure_mesh_edges(db, cold, client_factory=lambda *a: MagicMock(),
                                    now=datetime(2026, 5, 1))
    assert built == 0


# ── mesh cadence unchanged (only eligibility broadened) ─────────────────────
def test_plan_number_action_signature_unchanged():
    """PART 2 only broadens peer eligibility — the send-cadence planner is untouched."""
    from app.services.warmup_engine import plan_number_action
    sig = inspect.signature(plan_number_action)
    assert list(sig.parameters)[:2] == ["enrollment", "edges"]   # same inputs, no group/peer args
