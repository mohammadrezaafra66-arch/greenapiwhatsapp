"""V27 PART 9 — minimum-2-distinct-peers requirement + staggered cold-number starts.

Proves:
  • a growing cohort (>2 active cold numbers) with only 1 healthy peer is refused with the
    capacity-full notice instead of concentrating risk on one peer;
  • 2+ healthy peers allow the cohort to grow;
  • only-active-but-throttled/cooled peers don't count as healthy;
  • two cold numbers under the SAME peer get staggered (offset) start times;
  • the first cold number under a peer is not offset.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest

from app.services import warmup_mesh_service as svc
from app.services.warmup_mesh_service import (
    requires_more_peers, stagger_offset_days, is_peer_healthy,
    MIN_DISTINCT_HEALTHY_PEERS, SMALL_COHORT, STAGGER_DAYS_PER_COLD,
)

NOW = datetime(2026, 7, 18, 12, 0, 0)


def _peer(status="active", cooldown_until=None, throttle_until=None, throttle_factor=1.0):
    return SimpleNamespace(status=SimpleNamespace(value=status), cooldown_until=cooldown_until,
                           throttle_until=throttle_until, throttle_factor=throttle_factor)


# ── min-2-peers rule ─────────────────────────────────────────────────────────
def test_third_cold_number_with_one_peer_is_blocked():
    # 2 already assigned, adding the 3rd, only 1 healthy peer → require more peers
    assert requires_more_peers(active_assigned_cold=2, healthy_peer_count=1) is True


def test_third_cold_number_with_two_peers_is_allowed():
    assert requires_more_peers(active_assigned_cold=2, healthy_peer_count=2) is False


def test_first_and_second_cold_numbers_always_allowed():
    assert requires_more_peers(0, 1) is False
    assert requires_more_peers(1, 1) is False      # 2nd number, single peer → still fine


def test_healthy_peer_definition():
    assert is_peer_healthy(_peer(), NOW) is True
    assert is_peer_healthy(_peer(status="banned"), NOW) is False
    assert is_peer_healthy(_peer(cooldown_until=NOW + timedelta(days=1)), NOW) is False
    assert is_peer_healthy(_peer(throttle_until=NOW + timedelta(days=1),
                                 throttle_factor=0.5), NOW) is False


def test_throttled_peer_does_not_count_toward_min():
    peers = [_peer(), _peer(throttle_until=NOW + timedelta(days=1), throttle_factor=0.5)]
    healthy = sum(1 for p in peers if is_peer_healthy(p, NOW))
    assert healthy == 1
    # 3rd cold number but only 1 of the 2 peers is healthy → blocked
    assert requires_more_peers(2, healthy) is True


# ── stagger ──────────────────────────────────────────────────────────────────
def test_stagger_offsets_by_peer_load():
    assert stagger_offset_days(0) == 0                    # first cold under the peer
    assert stagger_offset_days(1) == STAGGER_DAYS_PER_COLD    # second → +1 day
    assert stagger_offset_days(2) == 2 * STAGGER_DAYS_PER_COLD


# ── integration: enroll_and_preflight applies the stagger + min-peers notice ──
class _FakeScalars:
    def __init__(self, items): self._items = list(items)
    def all(self): return list(self._items)
    def first(self): return self._items[0] if self._items else None


class _FakeResult:
    def __init__(self, rows=None, scalars=None):
        self._rows = rows or []
        self._scalars = scalars if scalars is not None else []
    def all(self): return list(self._rows)
    def scalars(self): return _FakeScalars(self._scalars)
    def scalar_one_or_none(self): return self._scalars[0] if self._scalars else None


class _FakeSession:
    def __init__(self, results):
        self._results = list(results)
        self.added = []
    async def execute(self, *a, **k):
        return self._results.pop(0) if self._results else _FakeResult()
    def add(self, obj): self.added.append(obj)
    async def flush(self): pass
    async def commit(self): pass


def _account(iid, phone, is_warm_peer=False):
    return SimpleNamespace(id=iid, instance_id=iid, api_token="t", phone=phone, name=iid,
                           is_warm_peer=is_warm_peer, status=SimpleNamespace(value="active"),
                           cooldown_until=None, throttle_until=None, throttle_factor=1.0)


def _authorized_client(*a, **k):
    from unittest.mock import AsyncMock, MagicMock
    c = MagicMock()
    c.get_state = AsyncMock(return_value="authorized")
    c.set_warming_instance_settings = AsyncMock(return_value=True)
    c.show_messages_queue = AsyncMock(return_value=[])
    c.clear_messages_queue = AsyncMock(return_value=True)
    c.add_contact = AsyncMock(return_value=True)
    c.get_contacts = AsyncMock(return_value=[])
    return c


@pytest.mark.asyncio
async def test_enroll_blocks_third_cold_number_with_single_peer():
    """Only 1 healthy peer already serving 2 cold numbers → the 3rd gets capacity-full, no peer."""
    new = _account("NEW3", "989120000003")
    peers = [_account("PEER1", "989120000010", is_warm_peer=True)]
    # load query returns edges that put 2 cold numbers on PEER1 (its slots full / cohort=2)
    edge_a = SimpleNamespace(new_instance_id="COLDA", peer_instance_id="PEER1")
    edge_b = SimpleNamespace(new_instance_id="COLDB", peer_instance_id="PEER1")
    db = _FakeSession(results=[
        _FakeResult(scalars=[]),           # existing enrollment (none)
        _FakeResult(scalars=[]),           # existing edges for NEW3 (none)
        _FakeResult(scalars=peers),        # eligible: active accounts
        _FakeResult(scalars=[]),           # graduated ids
        _FakeResult(scalars=[edge_a, edge_b]),   # peer_cold_load: edges
        _FakeResult(rows=[("COLDA", "RECEIVING", True), ("COLDB", "RECEIVING", True)]),  # enr states
    ])
    res = await svc.enroll_and_preflight(db, new, client_factory=_authorized_client,
                                         now=NOW, rng=__import__("random").Random(0))
    assert res["notice"] == svc.CAPACITY_FULL_NOTICE
    assert res["peers"] == []              # no peer assigned — risk not concentrated
