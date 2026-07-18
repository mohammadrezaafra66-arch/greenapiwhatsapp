"""V27 PART 2 — per-INSTANCE (peer-level) send pacer.

Fixes incident gap #2. Pacing used to be enforced per COLD-NUMBER enrollment only, so when
ONE warm peer served two cold numbers their combined send stream came out 2.6–9 s apart —
under the 10–15 s anti-ban floor — because each cold number scheduled independently with no
awareness of the shared sender.

This module keys the gap on the SENDING INSTANCE, full stop: after any send from an instance
(mesh OR campaign OR any other feature), the instance may not send again until a jittered
10–15 s gap has elapsed. If a second send from the same instance is due sooner, the caller
defers it. State is a small in-memory map — process-local by design (a peer's send cadence
is a real-time property; nothing to persist), and reset() keeps unit-tests isolated.
"""
from __future__ import annotations
import random
from datetime import datetime, timedelta

# The shared anti-ban floor between two sends FROM THE SAME INSTANCE (jittered per send).
MIN_PEER_GAP_SECONDS = 10
MAX_PEER_GAP_SECONDS = 15

# instance_id -> earliest datetime that instance may send again.
_peer_next_allowed: dict[str, datetime] = {}


def reset() -> None:
    """Test helper — clear all per-instance pacing state."""
    _peer_next_allowed.clear()


def jittered_gap_seconds(rng: random.Random | None = None,
                         min_gap: int = MIN_PEER_GAP_SECONDS,
                         max_gap: int = MAX_PEER_GAP_SECONDS) -> float:
    return (rng or random).uniform(min_gap, max_gap)


def peer_ready(instance_id, now: datetime | None = None) -> bool:
    """True if `instance_id` is allowed to send right now (its jittered gap has elapsed)."""
    if not instance_id:
        return True
    now = now or datetime.utcnow()
    nxt = _peer_next_allowed.get(str(instance_id))
    return nxt is None or now >= nxt


def seconds_until_ready(instance_id, now: datetime | None = None) -> float:
    """How many seconds until `instance_id` may send again (0.0 if ready now)."""
    if not instance_id:
        return 0.0
    now = now or datetime.utcnow()
    nxt = _peer_next_allowed.get(str(instance_id))
    if nxt is None or now >= nxt:
        return 0.0
    return (nxt - now).total_seconds()


def record_peer_send(instance_id, now: datetime | None = None,
                     rng: random.Random | None = None,
                     min_gap: int = MIN_PEER_GAP_SECONDS,
                     max_gap: int = MAX_PEER_GAP_SECONDS) -> datetime:
    """Mark that `instance_id` just sent: block its next send until now + a jittered gap.
    Returns the computed next-allowed time. Call after EVERY real send from the instance
    (mesh, campaign, group, helper) so the gap is enforced across all of them together."""
    now = now or datetime.utcnow()
    if not instance_id:
        return now
    nxt = now + timedelta(seconds=jittered_gap_seconds(rng, min_gap, max_gap))
    _peer_next_allowed[str(instance_id)] = nxt
    return nxt
