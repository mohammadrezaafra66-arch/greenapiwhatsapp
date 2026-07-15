"""V17 PART 3 — enrollment, pre-flight, and the mutual-contact mesh handshake.

Green API is mocked (injected client factory) and the DB is the repo's FakeSession
double, so the whole flow runs with no network/DB. Asserts: toggle ON creates the
enrollment + applies warming settings; queue cleared; 24h cooldown enforced; the
mutual-contact handshake completes before any edge is messageable; and the
insufficient-peers path surfaces the Persian notice and builds no edges.
"""
import uuid
import random
from datetime import datetime, timedelta
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.models.account import Account, AccountStatus
from app.models.warmup_mesh import WarmupEnrollment, WarmupMeshEdge, WarmupEventLog
from app.services import warmup_mesh_service as svc
from app.services.warmup_mesh_service import (
    select_peers, cooldown_remaining_hours, cooldown_elapsed, edge_is_messageable,
    eligible_peer_accounts, INSUFFICIENT_PEERS_NOTICE,
)
from app.services.warmup_state import WarmupState, HandshakeState, DEFAULT_WARMUP_CONFIG


# ── FakeSession (repo pattern) with flush() ──────────────────────────────────
class FakeScalars:
    def __init__(self, items): self._items = list(items)
    def all(self): return list(self._items)
    def first(self): return self._items[0] if self._items else None


class FakeResult:
    def __init__(self, rows=None, scalars=None):
        self._rows = rows or []
        self._scalars = scalars if scalars is not None else []
    def all(self): return list(self._rows)
    def scalars(self): return FakeScalars(self._scalars)
    def scalar_one_or_none(self): return self._scalars[0] if self._scalars else None


class FakeSession:
    def __init__(self, results=None, gets=None):
        self._results = list(results or [])
        self._gets = dict(gets or {})
        self.added = []
        self.commits = 0
    async def get(self, model, pk): return self._gets.get(model.__name__)
    async def execute(self, query):
        return self._results.pop(0) if self._results else FakeResult()
    def add(self, obj): self.added.append(obj)
    async def flush(self): pass
    async def commit(self): self.commits += 1
    async def refresh(self, obj): pass


def _account(instance_id, phone, **over):
    a = Account(name=f"acc-{instance_id}", instance_id=instance_id, api_token="tok")
    a.id = uuid.uuid4()
    a.status = AccountStatus.active
    a.phone = phone
    a.is_warm_peer = False
    for k, v in over.items():
        setattr(a, k, v)
    return a


def _mock_factory(recorder):
    """Return a client factory whose clients record calls into `recorder` keyed by instance."""
    def factory(instance_id, api_token):
        c = MagicMock()
        c.set_warming_instance_settings = AsyncMock(return_value=True)
        c.show_messages_queue = AsyncMock(return_value=[])
        c.clear_messages_queue = AsyncMock(return_value=True)
        async def _add_contact(phone, name, *a, **k):
            recorder.setdefault(instance_id, []).append(("add_contact", phone, name))
            return True
        c.add_contact = AsyncMock(side_effect=_add_contact)
        recorder.setdefault(instance_id, [])
        return c
    return factory


# ── select_peers (pure) ──────────────────────────────────────────────────────
def test_select_peers_respects_min_max():
    peers = [f"p{i}" for i in range(10)]
    for seed in range(20):
        sel = select_peers(peers, DEFAULT_WARMUP_CONFIG, rng=random.Random(seed))
        assert 3 <= len(sel) <= 6              # peers_per_new_number_min/max
        assert len(set(sel)) == len(sel)        # no duplicates


def test_select_peers_capped_by_availability():
    assert select_peers([], DEFAULT_WARMUP_CONFIG) == []
    two = select_peers(["a", "b"], DEFAULT_WARMUP_CONFIG, rng=random.Random(1))
    assert len(two) == 2                          # fewer than min → use what exists


# ── cooldown (pure) ──────────────────────────────────────────────────────────
def test_cooldown_unknown_auth_is_full():
    e = WarmupEnrollment(instance_id="x"); e.authorized_at = None
    assert cooldown_remaining_hours(e) == 24.0
    assert cooldown_elapsed(e) is False


def test_cooldown_elapsed_after_24h():
    now = datetime(2026, 5, 1, 12, 0, 0)
    e = WarmupEnrollment(instance_id="x"); e.authorized_at = now - timedelta(hours=25)
    assert cooldown_remaining_hours(e, now=now) == 0.0
    assert cooldown_elapsed(e, now=now) is True


def test_cooldown_not_elapsed_before_24h():
    now = datetime(2026, 5, 1, 12, 0, 0)
    e = WarmupEnrollment(instance_id="x"); e.authorized_at = now - timedelta(hours=10)
    assert cooldown_remaining_hours(e, now=now) == pytest.approx(14.0)
    assert cooldown_elapsed(e, now=now) is False


# ── edge messageable only after mutual handshake ─────────────────────────────
def test_edge_messageable_requires_both_flags_and_active():
    e = WarmupMeshEdge(new_instance_id="a", peer_instance_id="b")
    e.saved_as_contact_new = e.saved_as_contact_peer = False
    e.handshake_state = HandshakeState.NONE.value
    assert edge_is_messageable(e) is False
    e.saved_as_contact_new = True
    e.handshake_state = HandshakeState.CONTACT_SAVED.value
    assert edge_is_messageable(e) is False      # one side only → NOT messageable
    e.saved_as_contact_peer = True
    e.handshake_state = HandshakeState.ACTIVE.value
    assert edge_is_messageable(e) is True        # both sides saved → messageable


# ── full enroll + pre-flight with 3 warm peers ───────────────────────────────
@pytest.mark.asyncio
async def test_enroll_preflight_full_handshake():
    new = _account("NEW1", "989120000001")
    peers = [_account(f"PEER{i}", f"98912000010{i}", is_warm_peer=True) for i in range(3)]
    fake = FakeSession(results=[
        FakeResult(scalars=[]),          # 1) no existing enrollment
        FakeResult(scalars=peers),       # 2) active accounts (eligible pool)
        FakeResult(scalars=[]),          # 3) graduated instance ids (none)
        FakeResult(scalars=[]),          # 4) edge lookup peer 0 (new)
        FakeResult(scalars=[]),          # 5) edge lookup peer 1 (new)
        FakeResult(scalars=[]),          # 6) edge lookup peer 2 (new)
    ])
    rec = {}
    res = await svc.enroll_and_preflight(
        fake, new, client_factory=_mock_factory(rec),
        now=datetime(2026, 5, 1, 9, 0, 0), rng=random.Random(0),
    )

    # enrollment created + enabled, held in COOLDOWN with a full 24h remaining
    enr = [x for x in fake.added if isinstance(x, WarmupEnrollment)]
    assert len(enr) == 1 and enr[0].is_enabled is True
    assert res["state"] == WarmupState.COOLDOWN.value
    assert res["cooldown_hours"] == 24.0
    assert res["settings_applied"] is True
    assert res["queue_cleared"] is True
    assert res["notice"] is None

    # 3 edges built, every one messageable (mutual contact saved on BOTH sides)
    edges = [x for x in fake.added if isinstance(x, WarmupMeshEdge)]
    assert len(edges) == 3
    assert all(edge_is_messageable(e) for e in edges)
    assert len(res["peers"]) == 3 and all(p["messageable"] for p in res["peers"])

    # AddContact called on BOTH sides for each pair: new saved 3 peers; each peer saved new
    assert len(rec["NEW1"]) == 3
    for i in range(3):
        assert len(rec[f"PEER{i}"]) == 1
    assert fake.commits == 1


# ── insufficient peers: notice + no edges + nothing sent ─────────────────────
@pytest.mark.asyncio
async def test_enroll_preflight_insufficient_peers():
    new = _account("NEW2", "989120000002")
    fake = FakeSession(results=[
        FakeResult(scalars=[]),   # no existing enrollment
        FakeResult(scalars=[]),   # NO active peer accounts
        FakeResult(scalars=[]),   # no graduated
    ])
    rec = {}
    res = await svc.enroll_and_preflight(
        fake, new, client_factory=_mock_factory(rec),
        now=datetime(2026, 5, 1, 9, 0, 0),
    )
    # still enrolled + held in cooldown, but with the clear Persian notice
    assert res["state"] == WarmupState.COOLDOWN.value
    assert res["notice"] == INSUFFICIENT_PEERS_NOTICE
    # no edges built, and NO contact/message activity to any stranger
    assert [x for x in fake.added if isinstance(x, WarmupMeshEdge)] == []
    assert res["peers"] == []
    # settings still applied + queue still cleared (pre-flight always runs)
    assert res["settings_applied"] is True and res["queue_cleared"] is True


# ── disable: pauses immediately ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_disable_pauses_immediately():
    new = _account("NEW3", "989120000003")
    existing = WarmupEnrollment(instance_id="NEW3", state=WarmupState.RECEIVING.value)
    existing.id = uuid.uuid4(); existing.is_enabled = True
    fake = FakeSession(results=[FakeResult(scalars=[existing])])
    res = await svc.disable_warmup(fake, new)
    assert existing.is_enabled is False
    assert res["state"] == WarmupState.PAUSED.value
    assert fake.commits == 1


# ── eligibility: strangers never qualify ─────────────────────────────────────
@pytest.mark.asyncio
async def test_eligibility_only_warm_or_graduated():
    warm = _account("W", "9891", is_warm_peer=True)
    grad = _account("G", "9892")
    cold = _account("C", "9893")           # neither warm nor graduated → excluded
    fake = FakeSession(results=[
        FakeResult(scalars=[warm, grad, cold]),
        FakeResult(scalars=["G"]),          # G is graduated
    ])
    out = await eligible_peer_accounts(fake, exclude_instance_id="NEW")
    ids = {a.instance_id for a in out}
    assert ids == {"W", "G"}                # cold stranger excluded
