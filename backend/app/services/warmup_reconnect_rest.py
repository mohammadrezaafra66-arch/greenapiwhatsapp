"""V38 — mandatory post-RECONNECT rest. **V39 PART 1 GENERALIZED this into a UNIVERSAL check.**

Originally (V38) this was a Team-Collaboration-ONLY rest, checked separately inside
`_send_from_main` and deliberately NOT touching the shared V27 send-gate. V39 PART 1 supersedes
that narrower scoping: the 24h connect/reconnect cooldown is now folded into the ONE shared gate
(`send_gate.can_send_now`, reason slug `connect_cooldown`) so it applies UNIVERSALLY — every send
path (mesh warm-up, campaigns, Team Collaboration) and every account (first-ever connection AND
reconnection).

To keep exactly ONE source of truth, the functions below are now THIN WRAPPERS delegating to
`send_gate.connect_cooldown_active` / `hours_until_connect_cooldown_over`. They are retained for
backward compatibility with existing callers/tests; the real logic lives in `send_gate`. The
canonical anchor is `Account.connected_at` (falling back to the legacy `reconnected_at`).
"""
from __future__ import annotations
from datetime import datetime

from app.services import send_gate

# The mandatory rest window after a (re)connect, in hours — the single value lives in send_gate;
# re-exported here so legacy imports of RECONNECT_REST_HOURS keep working.
RECONNECT_REST_HOURS = send_gate.CONNECT_COOLDOWN_HOURS


def reconnect_rest_active(account, now: datetime | None = None,
                          hours: int = RECONNECT_REST_HOURS) -> bool:
    """Thin wrapper over the shared universal connect-cooldown (V39 PART 1). True when `account`
    (re)connected within the last `hours` and must NOT send yet. NULL anchor → no rest owed."""
    return send_gate.connect_cooldown_active(account, now, hours)


def hours_until_rest_over(account, now: datetime | None = None,
                          hours: int = RECONNECT_REST_HOURS) -> float:
    """Thin wrapper: hours remaining in the connect-cooldown (0.0 when none owed / elapsed)."""
    return send_gate.hours_until_connect_cooldown_over(account, now, hours)
