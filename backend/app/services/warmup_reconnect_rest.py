"""V38 — mandatory post-RECONNECT rest for the Team-Collaboration send path.

The project already enforces a 24h post-AUTHORIZATION cooldown on cold accounts (see
`warmup_cold_reply.post_auth_cooldown_elapsed`). This module extends the SAME principle to a
RECONNECT event: when any account drops (notAuthorized / logout / block) and is later brought
back with a QR rescan, it must rest for 24h before it sends ANY Team-Collaboration traffic —
instead of being instantly send-eligible with zero rest the moment `status` flips back to
`active` (which contradicts every other anti-ban rule in the system).

The reconnect instant is stamped on `Account.reconnected_at` in BOTH reconnect paths
(the state-change webhook and the `sync_account_states` poll). These functions are PURE (no DB,
no framework) so the behavior can be unit-pinned, and are consulted ONLY inside `_send_from_main`
(the single choke point for every TC send). They NEVER touch the shared V27 send-gate
(`send_gate.can_send_now`) that campaigns and the warm-up mesh rely on — so this rest applies to
TC sends only and changes nothing for other accounts' gates.
"""
from __future__ import annotations
from datetime import datetime, timedelta

# The mandatory rest window after a reconnect, in hours — matches the project's established 24h
# post-authorization cooldown so the anti-ban rules stay consistent.
RECONNECT_REST_HOURS = 24


def reconnect_rest_active(account, now: datetime | None = None,
                          hours: int = RECONNECT_REST_HOURS) -> bool:
    """True when `account` reconnected within the last `hours` and must NOT send TC traffic yet.

    `reconnected_at` is a UTC-naive instant (stamped with datetime.utcnow() on reconnect). A
    None value (never reconnected since the feature shipped, or a long-connected account) means
    NO rest is owed — so already-connected accounts are unaffected until they actually reconnect.
    """
    ra = getattr(account, "reconnected_at", None)
    if not isinstance(ra, datetime):   # None, or a light test double that doesn't model it → no rest
        return False
    now = now or datetime.utcnow()
    return now < ra + timedelta(hours=hours)


def hours_until_rest_over(account, now: datetime | None = None,
                          hours: int = RECONNECT_REST_HOURS) -> float:
    """Hours remaining in the post-reconnect rest (0.0 when no rest is owed / already elapsed)."""
    ra = getattr(account, "reconnected_at", None)
    if not isinstance(ra, datetime):
        return 0.0
    now = now or datetime.utcnow()
    remaining = (ra + timedelta(hours=hours) - now).total_seconds() / 3600.0
    return max(0.0, remaining)
