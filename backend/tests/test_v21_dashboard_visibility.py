"""V21 PART 4 — dashboard ratio + capacity + peer-load + breaker visibility.

Asserts the mesh-dashboard payload carries everything the UI renders: per-warm-peer capacity
(n/cap), each cold number's assigned peer (or capacity-full waiting state), the not-connected
notice for pending numbers, and the breaker state with the distinct offending numbers.
"""
import uuid
import random
from datetime import datetime
from types import SimpleNamespace
import pytest

from app.models.account import Account, AccountStatus
from app.models.warmup_mesh import WarmupMeshEdge
from app.services.warmup_dashboard import build_dashboard
from app.services import warmup_mesh_service as svc


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


def _acc(iid, is_warm_peer=False):
    a = Account(name=f"name-{iid}", instance_id=iid, api_token="t")
    a.id = uuid.uuid4(); a.status = AccountStatus.active; a.is_warm_peer = is_warm_peer
    return a


def _edge(cold, peer):
    return WarmupMeshEdge(new_instance_id=cold, peer_instance_id=peer,
                          direction="bidirectional", handshake_state="active")


def _enr(iid, state="RECEIVING"):
    return SimpleNamespace(instance_id=iid, phone=f"98{iid}", state=state, is_enabled=True,
                           sent_today=0, received_today=0, reply_ratio=0.0, next_action_at=None,
                           rest_until=None, authorized_at=datetime(2026, 4, 25),
                           started_at=datetime(2026, 4, 25), id=uuid.uuid4())


# ── snapshot feeds the dashboard: peer load n/cap + assignments ─────────────
@pytest.mark.asyncio
async def test_snapshot_reports_load_and_assignments():
    p1 = _acc("P1", is_warm_peer=True)
    c1, c2 = _acc("C1"), _acc("C2")
    edges = [_edge("C1", "P1")]                          # P1 warms C1 (1/2)
    db = FakeSession(results=[
        FakeResult(scalars=[p1, c1, c2]),               # active accounts
        FakeResult(scalars=edges),                       # all edges
        FakeResult(rows=[("C1", "RECEIVING", True), ("C2", "COOLDOWN", True)]),  # enrollment states
    ])
    snap = await svc.mesh_capacity_snapshot(db)
    row = snap["peer_load"][0]
    assert row["instance_id"] == "P1" and row["cold_count"] == 1 and row["cap"] == 2 and row["full"] is False
    assert snap["assignments"] == {"C1": "P1"}
    assert snap["capacity_full_instances"] == set()      # P1 still has a slot → C2 not blocked


# ── full dashboard payload carries all PART 4 fields together ────────────────
def test_dashboard_payload_has_all_visibility_fields():
    e1 = _enr("C1", state="RECEIVING")
    e2 = _enr("C2", state="COOLDOWN")
    dash = build_dashboard(
        [e1, e2], {"C1": [SimpleNamespace(new_instance_id="C1", peer_instance_id="P1",
                                          saved_as_contact_new=True, saved_as_contact_peer=True,
                                          handshake_state="active", msg_count=1, last_msg_at=None,
                                          id=uuid.uuid4())],
                   "C2": []},
        now=datetime(2026, 5, 1, 12, 0, 0), breaker_tripped=True,
        peer_load=[{"instance_id": "P1", "name": "name-P1", "cold_count": 1, "cap": 2, "full": False}],
        capacity_full_instances={"C2"},
        breaker_offenders=[{"instance_id": "Z", "kind": "yellowCard", "at": None}],
    )
    # peer-load roster + cap value
    assert dash["max_cold_per_warm_peer"] == 2
    assert dash["peer_load"][0]["cold_count"] == 1
    # per-cold assignment + capacity-full waiting state
    c1 = next(c for c in dash["numbers"] if c["instance_id"] == "C1")
    c2 = next(c for c in dash["numbers"] if c["instance_id"] == "C2")
    assert c1["assigned_peer"] == "P1"
    assert c2["capacity_full"] is True and c2["banner"]["type"] == "capacity_full"
    # breaker state + offenders
    assert dash["breaker_tripped"] is True
    assert dash["global_banner"]["offenders"][0]["instance_id"] == "Z"
