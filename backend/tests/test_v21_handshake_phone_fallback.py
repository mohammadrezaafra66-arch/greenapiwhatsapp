"""V21 — mesh handshake blocker fix: getWaSettings phone fallback + retry of stuck edges.

The partner/QR flow leaves accounts.phone NULL (the number lives only in the account name),
which used to make _handshake_edge silently skip the mutual-contact step so edges stayed
handshake=none forever. These tests lock in the durable fix:
  • _resolve_account_phone fills accounts.phone from getWaSettings and persists it.
  • _handshake_edge completes the mutual-contact handshake even when both phones start NULL.
  • ensure_mesh_edges RETRIES an existing non-active edge (it no longer only builds new ones).
  • backfill_account_phones fills every null phone and skips already-filled / deleted rows.
"""
import uuid
import random
from datetime import datetime
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.models.account import Account, AccountStatus
from app.models.warmup_mesh import WarmupMeshEdge
from app.services.warmup_mesh_service import (
    _resolve_account_phone, _handshake_edge, ensure_mesh_edges, backfill_account_phones,
    edge_is_messageable,
)
from app.services.warmup_state import HandshakeState


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
    a.phone = phone
    return a


def _factory_with_wa(rec, wa_phones: dict):
    """Client factory where get_wa_settings returns the real MSISDN per instance and
    add_contact succeeds — models the partner/QR case (accounts.phone null, phone in WA)."""
    def factory(iid, tok):
        c = MagicMock()
        async def _add(phone, name, *a, **k):
            rec.setdefault(iid, []).append(("add_contact", phone)); return True
        async def _wa():
            return {"phone": wa_phones.get(iid, "")}
        c.add_contact = AsyncMock(side_effect=_add)
        c.get_wa_settings = AsyncMock(side_effect=_wa)
        rec.setdefault(iid, [])
        return c
    return factory


# ── _resolve_account_phone: getWaSettings fallback + persist ────────────────
@pytest.mark.asyncio
async def test_resolve_phone_prefers_existing():
    a = _acc("A", phone="989120000001")
    client = MagicMock()
    client.get_wa_settings = AsyncMock(side_effect=AssertionError("should not be called"))
    assert await _resolve_account_phone(a, client) == "989120000001"


@pytest.mark.asyncio
async def test_resolve_phone_falls_back_and_persists():
    a = _acc("A", phone=None)
    client = MagicMock()
    client.get_wa_settings = AsyncMock(return_value={"wid": "989122270261@c.us"})
    got = await _resolve_account_phone(a, client)
    assert got == "989122270261"
    assert a.phone == "989122270261"        # persisted onto the account


# ── _handshake_edge completes even when BOTH phones start NULL ───────────────
@pytest.mark.asyncio
async def test_handshake_completes_with_null_phones_via_wa_fallback():
    cold = _acc("COLD", phone=None)
    peer = _acc("WARM", phone=None, is_warm_peer=True)
    rec = {}
    factory = _factory_with_wa(rec, {"COLD": "989120000001", "WARM": "989122270261"})
    db = FakeSession(results=[FakeResult(scalars=[])])   # edge pair lookup → none
    edge = await _handshake_edge(db, cold, peer, factory)
    assert edge.handshake_state == HandshakeState.ACTIVE.value
    assert edge_is_messageable(edge)
    # phones were filled from getWaSettings and persisted
    assert cold.phone == "989120000001" and peer.phone == "989122270261"
    # mutual AddContact used the resolved phones on BOTH instances
    assert ("add_contact", "989122270261") in rec["COLD"]
    assert ("add_contact", "989120000001") in rec["WARM"]


# ── ensure_mesh_edges RETRIES a stuck handshake=none edge → active ──────────
@pytest.mark.asyncio
async def test_ensure_mesh_edges_retries_stuck_edge():
    cold = _acc("COLD", phone=None)
    peer = _acc("WARM", phone=None, is_warm_peer=True)
    stuck = WarmupMeshEdge(new_instance_id="COLD", peer_instance_id="WARM",
                           direction="bidirectional", handshake_state=HandshakeState.NONE.value)
    rec = {}
    factory = _factory_with_wa(rec, {"COLD": "989120000001", "WARM": "989122270261"})
    db = FakeSession(results=[
        FakeResult(scalars=[stuck]),   # existing edges for COLD
        FakeResult(scalars=[peer]),    # retry loop: peer_acc lookup
        FakeResult(scalars=[stuck]),   # _handshake_edge: edge pair lookup → the stuck edge
        FakeResult(scalars=[peer]),    # eligible: active accounts
        FakeResult(scalars=[]),        # eligible: graduated ids
    ])
    built = await ensure_mesh_edges(db, cold, client_factory=factory,
                                    now=datetime(2026, 5, 1), rng=random.Random(0))
    assert built == 0                          # peer already present → no NEW edge
    assert stuck.handshake_state == HandshakeState.ACTIVE.value   # but the stuck edge healed
    assert edge_is_messageable(stuck)
    assert db.commits == 1                     # retry committed


# ── backfill_account_phones: fill nulls, skip filled / deleted ──────────────
@pytest.mark.asyncio
async def test_backfill_fills_nulls_and_skips():
    null1 = _acc("N1", phone=None)
    null2 = _acc("N2", phone=None)
    have = _acc("H", phone="989120000009")
    gone = _acc("D", phone=None, status=AccountStatus.deleted)
    rec = {}
    factory = _factory_with_wa(rec, {"N1": "989120000001", "N2": "989122270261"})
    db = FakeSession(results=[FakeResult(scalars=[null1, null2, have, gone])])
    results = await backfill_account_phones(db, client_factory=factory)
    by_id = {r["instance_id"]: r for r in results}
    assert by_id["N1"]["action"] == "filled" and null1.phone == "989120000001"
    assert by_id["N2"]["action"] == "filled" and null2.phone == "989122270261"
    assert by_id["H"]["action"] == "kept"
    assert by_id["D"]["action"] == "skipped_deleted"
    assert db.commits == 1
