"""V21 PART 1 — warm:cold ratio cap (1 warm peer : MAX_COLD_PER_WARM_PEER cold).

A single warm peer may warm AT MOST MAX_COLD_PER_WARM_PEER (=2) cold numbers at a time. Cold
numbers are distributed across peers to balance load; a peer is never overloaded past the cap.
When every eligible peer is at capacity, the cold number waits (no edge) and the dashboard
surfaces the capacity-full notice.
"""
import uuid
import random
from datetime import datetime
from types import SimpleNamespace
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.models.account import Account, AccountStatus
from app.models.warmup_mesh import WarmupMeshEdge
from app.services import warmup_mesh_service as svc
from app.services.warmup_mesh_service import (
    MAX_COLD_PER_WARM_PEER, CAPACITY_FULL_NOTICE, compute_peer_load,
    select_least_loaded_peer, ensure_mesh_edges, edge_is_messageable,
)
from app.services.warmup_state import WarmupState, HandshakeState


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


def _peer(iid):
    a = Account(name=f"peer-{iid}", instance_id=iid, api_token="t")
    a.id = uuid.uuid4(); a.status = AccountStatus.active; a.is_warm_peer = True
    a.phone = f"98912227{iid[-4:]}"
    return a


def _cold(iid):
    a = Account(name=f"cold-{iid}", instance_id=iid, api_token="t")
    a.id = uuid.uuid4(); a.status = AccountStatus.active; a.is_warm_peer = False
    a.phone = f"98904824{iid[-4:]}"
    return a


def _edge(cold, peer):
    return WarmupMeshEdge(new_instance_id=cold, peer_instance_id=peer,
                          direction="bidirectional", handshake_state=HandshakeState.NONE.value)


def _mock_factory(rec):
    def factory(iid, tok):
        c = MagicMock()
        async def _add(phone, name, *a, **k):
            rec.setdefault(iid, []).append(phone); return True
        c.add_contact = AsyncMock(side_effect=_add)
        rec.setdefault(iid, [])
        return c
    return factory


# ── pure: compute_peer_load counts only ACTIVE cold numbers ─────────────────
def test_compute_peer_load_counts_active_only():
    edges = [_edge("C1", "P1"), _edge("C2", "P1"), _edge("C3", "P2"), _edge("C4", "P1")]
    enr = {
        "C1": (WarmupState.COOLDOWN.value, True),      # counts
        "C2": (WarmupState.RECEIVING.value, True),     # counts
        "C3": (WarmupState.PAUSED.value, True),        # PAUSED → frees slot
        "C4": (WarmupState.GRADUATED.value, True),     # GRADUATED → frees slot
    }
    load = compute_peer_load(edges, enr)
    assert load == {"P1": 2}          # P1: C1+C2 (C4 graduated freed); P2: C3 paused → 0/absent


def test_compute_peer_load_disabled_frees_slot():
    edges = [_edge("C1", "P1")]
    assert compute_peer_load(edges, {"C1": (WarmupState.RECEIVING.value, False)}) == {}


# ── pure: select_least_loaded_peer balances + respects cap ──────────────────
def test_select_least_loaded_prefers_emptiest():
    peers = [_peer("P1"), _peer("P2")]
    chosen = select_least_loaded_peer(peers, {"P1": 1, "P2": 0}, cap=2, rng=random.Random(0))
    assert chosen.instance_id == "P2"


def test_select_least_loaded_none_when_all_full():
    peers = [_peer("P1"), _peer("P2")]
    assert select_least_loaded_peer(peers, {"P1": 2, "P2": 2}, cap=2) is None


def test_select_least_loaded_skips_full_picks_available():
    peers = [_peer("P1"), _peer("P2")]
    chosen = select_least_loaded_peer(peers, {"P1": 2, "P2": 1}, cap=2, rng=random.Random(0))
    assert chosen.instance_id == "P2"


# ── distribution simulation: 4 cold across 2 peers → 2 each, none over cap ──
def test_distribute_four_cold_two_peers_balanced():
    peers = [_peer("P1"), _peer("P2")]
    load = {}
    rng = random.Random(0)
    assigned = {}
    for cold in ["C1", "C2", "C3", "C4"]:
        peer = select_least_loaded_peer(peers, load, MAX_COLD_PER_WARM_PEER, rng)
        assert peer is not None                                   # all 4 get a peer
        load[peer.instance_id] = load.get(peer.instance_id, 0) + 1
        assigned[cold] = peer.instance_id
    assert load == {"P1": 2, "P2": 2}                             # balanced, exactly 2 each
    assert all(v <= MAX_COLD_PER_WARM_PEER for v in load.values())  # none over cap


# ── one peer + 3 cold → only 2 get an edge, 3rd waits (capacity full) ───────
def test_one_peer_three_cold_third_waits():
    peers = [_peer("P1")]
    load = {}
    rng = random.Random(1)
    outcomes = []
    for cold in ["C1", "C2", "C3"]:
        peer = select_least_loaded_peer(peers, load, MAX_COLD_PER_WARM_PEER, rng)
        if peer is None:
            outcomes.append(None)
        else:
            load[peer.instance_id] = load.get(peer.instance_id, 0) + 1
            outcomes.append(peer.instance_id)
    assert outcomes == ["P1", "P1", None]        # 3rd cold gets no peer
    assert load == {"P1": 2}                       # peer never exceeds the cap


# ── ensure_mesh_edges: builds ONE capped edge to the least-loaded peer ───────
@pytest.mark.asyncio
async def test_ensure_mesh_edges_assigns_one_capped_peer():
    cold = _cold("C1")
    p1, p2 = _peer("P1"), _peer("P2")
    rec = {}
    db = FakeSession(results=[
        FakeResult(scalars=[]),          # existing edges for C1 (none)
        FakeResult(scalars=[p1, p2]),    # eligible_peer_accounts: active accounts
        FakeResult(scalars=[]),          # eligible_peer_accounts: graduated ids
        FakeResult(scalars=[]),          # peer_cold_load: all edges (none → both load 0)
        FakeResult(rows=[]),             # peer_cold_load: enrollment states
        FakeResult(scalars=[]),          # _handshake_edge: edge pair lookup
    ])
    built = await ensure_mesh_edges(db, cold, client_factory=_mock_factory(rec),
                                    now=datetime(2026, 5, 1), rng=random.Random(0))
    assert built == 1
    edges = [x for x in db.added if isinstance(x, WarmupMeshEdge)]
    assert len(edges) == 1 and edge_is_messageable(edges[0])
    assert edges[0].peer_instance_id in ("P1", "P2")


# ── ensure_mesh_edges: peer at cap → no edge built (cold waits) ──────────────
@pytest.mark.asyncio
async def test_ensure_mesh_edges_no_edge_when_peer_full():
    cold = _cold("C3")
    p1 = _peer("P1")
    rec = {}
    # P1 already warms C1 + C2 (both active) → at cap 2. C3 must get nothing.
    all_edges = [_edge("C1", "P1"), _edge("C2", "P1")]
    db = FakeSession(results=[
        FakeResult(scalars=[]),            # existing edges for C3 (none)
        FakeResult(scalars=[p1]),          # eligible: active accounts (only P1)
        FakeResult(scalars=[]),            # eligible: graduated ids
        FakeResult(scalars=all_edges),     # peer_cold_load: all edges
        FakeResult(rows=[("C1", WarmupState.RECEIVING.value, True),
                         ("C2", WarmupState.RECEIVING.value, True)]),  # enrollment states
    ])
    built = await ensure_mesh_edges(db, cold, client_factory=_mock_factory(rec),
                                    now=datetime(2026, 5, 1), rng=random.Random(0))
    assert built == 0
    assert [x for x in db.added if isinstance(x, WarmupMeshEdge)] == []
    assert rec == {}                        # no addContact to anyone — C3 simply waits


# ── ensure_mesh_edges: already linked to eligible peer → no 2nd peer added ───
@pytest.mark.asyncio
async def test_ensure_mesh_edges_already_linked_no_second_peer():
    cold = _cold("C1")
    p1, p2 = _peer("P1"), _peer("P2")
    existing = [WarmupMeshEdge(new_instance_id="C1", peer_instance_id="P1",
                               direction="bidirectional", handshake_state=HandshakeState.ACTIVE.value)]
    existing[0].saved_as_contact_new = existing[0].saved_as_contact_peer = True
    db = FakeSession(results=[
        FakeResult(scalars=existing),      # existing edges for C1 → active edge to P1
        FakeResult(scalars=[p1, p2]),      # eligible: active accounts
        FakeResult(scalars=[]),            # eligible: graduated
    ])
    built = await ensure_mesh_edges(db, cold, client_factory=_mock_factory({}),
                                    now=datetime(2026, 5, 1), rng=random.Random(0))
    assert built == 0                       # already has its one eligible peer → no new peer
    assert [x for x in db.added if isinstance(x, WarmupMeshEdge)] == []


# ── mesh_capacity_snapshot: peer roster + capacity-full detection ────────────
@pytest.mark.asyncio
async def test_mesh_capacity_snapshot_peer_full_and_waiting_cold():
    p1 = _peer("P1")
    c1, c2, c3 = _cold("C1"), _cold("C2"), _cold("C3")
    all_edges = [_edge("C1", "P1"), _edge("C2", "P1")]   # P1 warms C1+C2 → full (2/2)
    db = FakeSession(results=[
        FakeResult(scalars=[p1, c1, c2, c3]),            # active accounts
        FakeResult(scalars=all_edges),                   # all edges
        FakeResult(rows=[("C1", WarmupState.RECEIVING.value, True),
                         ("C2", WarmupState.RECEIVING.value, True),
                         ("C3", WarmupState.COOLDOWN.value, True)]),   # enrollment states
    ])
    snap = await svc.mesh_capacity_snapshot(db)
    # peer roster shows P1 at 2/2 and full
    assert len(snap["peer_load"]) == 1
    row = snap["peer_load"][0]
    assert row["instance_id"] == "P1" and row["cold_count"] == 2 and row["cap"] == 2 and row["full"] is True
    # C3 is being warmed, has no peer edge, and every peer is full → waiting on capacity
    assert snap["capacity_full_instances"] == {"C3"}
    # C1/C2 are assigned to P1
    assert snap["assignments"] == {"C1": "P1", "C2": "P1"}


@pytest.mark.asyncio
async def test_mesh_capacity_snapshot_not_full_when_slot_free():
    p1, p2 = _peer("P1"), _peer("P2")
    c1, c3 = _cold("C1"), _cold("C3")
    all_edges = [_edge("C1", "P1")]                       # P1: 1/2, P2: 0/2 → capacity remains
    db = FakeSession(results=[
        FakeResult(scalars=[p1, p2, c1, c3]),
        FakeResult(scalars=all_edges),
        FakeResult(rows=[("C1", WarmupState.RECEIVING.value, True),
                         ("C3", WarmupState.COOLDOWN.value, True)]),
    ])
    snap = await svc.mesh_capacity_snapshot(db)
    # a slot is free (P2 empty) → C3 is NOT capacity-blocked (it will be assigned next tick)
    assert snap["capacity_full_instances"] == set()
