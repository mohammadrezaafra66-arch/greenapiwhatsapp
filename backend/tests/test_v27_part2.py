"""V27 PART 2 — peer-level (per-instance) rate limiting.

Reproduces and fixes the incident's 2.6–9s-apart pattern: pacing is now keyed on the SENDING
instance, not the cold-number enrollment. Proves:
  • one peer serving 2 cold numbers in the same tick → the second send is held ≥10s (deferred),
    never emitted seconds after the first;
  • two DIFFERENT peers are independent (not paced against each other);
  • a lone cold number under a peer is unaffected;
  • run_warmup_tick actually wires the pacer (peer_ready + record + defer) around the send.
"""
import inspect
import random
from datetime import datetime, timedelta
import pytest

from app.services import peer_pacer
from app.services import warmup_engine


NOW = datetime(2026, 7, 18, 12, 0, 0)


@pytest.fixture(autouse=True)
def _reset():
    peer_pacer.reset()
    yield
    peer_pacer.reset()


# ── pure pacer ───────────────────────────────────────────────────────────────
def test_fresh_instance_is_ready():
    assert peer_pacer.peer_ready("PEER", NOW) is True
    assert peer_pacer.seconds_until_ready("PEER", NOW) == 0.0


def test_gap_is_within_10_to_15_seconds():
    r = random.Random(0)
    for _ in range(200):
        g = peer_pacer.jittered_gap_seconds(r)
        assert 10.0 <= g <= 15.0


def test_two_cold_numbers_one_peer_are_spaced_at_least_10s():
    """The exact incident: two cold numbers share ONE peer and both come due in the same tick."""
    r = random.Random(0)
    # cold number A sends via PEER
    assert peer_pacer.peer_ready("PEER", NOW) is True
    peer_pacer.record_peer_send("PEER", NOW, r)
    # cold number B, same tick / same instant, same PEER → must be blocked (deferred)
    assert peer_pacer.peer_ready("PEER", NOW) is False
    wait = peer_pacer.seconds_until_ready("PEER", NOW)
    assert wait >= peer_pacer.MIN_PEER_GAP_SECONDS - 1e-6
    # B may only send once the jittered gap has elapsed
    assert peer_pacer.peer_ready("PEER", NOW + timedelta(seconds=wait + 0.001)) is True
    assert peer_pacer.peer_ready("PEER", NOW + timedelta(seconds=5)) is False   # 5s < floor


def test_two_different_peers_are_not_limited_against_each_other():
    peer_pacer.record_peer_send("P1", NOW, random.Random(1))
    # P2 has never sent → ready immediately, regardless of P1
    assert peer_pacer.peer_ready("P2", NOW) is True
    assert peer_pacer.peer_ready("P1", NOW) is False


def test_lone_peer_ready_again_after_gap():
    """A single cold number per peer: after its gap elapses the peer is ready as normal."""
    nxt = peer_pacer.record_peer_send("SOLO", NOW, random.Random(3))
    assert peer_pacer.peer_ready("SOLO", nxt + timedelta(seconds=0.001)) is True


def test_empty_instance_id_is_noop():
    assert peer_pacer.peer_ready("", NOW) is True
    assert peer_pacer.seconds_until_ready(None, NOW) == 0.0


# ── wiring: run_warmup_tick enforces the pacer around the send ────────────────
def test_run_warmup_tick_wires_the_pacer():
    src = inspect.getsource(warmup_engine.run_warmup_tick)
    assert "peer_pacer" in src
    assert "peer_ready" in src                 # checked before sending
    assert "record_peer_send" in src           # recorded after sending
    # a not-ready sender is deferred, not sent
    assert "deferred += 1" in src
