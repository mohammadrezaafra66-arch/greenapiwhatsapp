"""V27 PART 4 — real-time instance-state monitoring (Green API's own recommendation).

Green API's docs recommend BOTH polling getStateInstance ~every minute AND subscribing to
the state-change webhook, acting immediately on blocked/notAuthorized. This module is the
single place that turns an observed state (from either source) into:
  • a refreshed live-state cache that PART 1's send-gate reads, and
  • an immediate per-instance kill-switch trip on a danger state.

The Celery poll task (tasks.poll_instance_states, ~60s, staggered) and the webhook handler
both call `apply_state`, so a card is caught within ~a minute by the poll and within a
round-trip by the webhook — never left to send 19 more messages like the incident.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta

from app.services import send_gate, governors

logger = logging.getLogger("afrakala.state_monitor")

# Live states that must immediately quarantine the instance.
DANGER_STATES = {"yellowcard", "blocked", "notauthorized", "notauthorised", "logout"}


async def apply_state(db, account, state: str, source: str,
                      now: datetime | None = None) -> dict:
    """Record `state` for `account` in the live-state cache/table and act on danger states.
    Returns {instance_id, state, acted}. `source` is "poll" or "webhook"."""
    now = now or datetime.utcnow()
    s = (state or "unknown").strip().lower()
    await send_gate.persist_live_state(db, account.instance_id, s, source, now)
    result = {"instance_id": account.instance_id, "state": s, "acted": None}
    if s not in DANGER_STATES:
        return result
    if s == "yellowcard":
        # Reuse the full V14 automatic incident response (send-stop + cooldown + throttle);
        # it is idempotent per unresolved incident, so repeated polls don't double-handle.
        from app.services.incident_handler import handle_yellow_card
        try:
            await handle_yellow_card(account, source, db)
            result["acted"] = "yellowCard"
        except Exception as e:  # pragma: no cover - network best-effort
            logger.warning("handle_yellow_card failed for %s: %s", account.instance_id, e)
    else:
        # blocked / notAuthorized / logout → hard per-instance kill-switch so can_send_now
        # refuses it right away (in addition to the status change the webhook applies).
        account.throttle_factor = governors.YELLOW_THROTTLE_FACTOR
        account.throttle_until = now + timedelta(days=7)
        account.cooldown_until = now + timedelta(days=1)
        account.last_incident_at = now
        result["acted"] = s
    return result
