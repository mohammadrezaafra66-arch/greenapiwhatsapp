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
# V57 — `suspended` (Green API's spam restriction) added; it was previously recorded but acted on
# nowhere, so a restricted instance kept its throttle/cooldown untouched.
DANGER_STATES = {"yellowcard", "blocked", "notauthorized", "notauthorised", "logout", "suspended"}


def parse_suspended_until(wa_settings: dict) -> datetime | None:
    """PURE. V57 — read `suspendedUntil` (UNIX epoch, UTC) out of a getWaSettings payload.
    Green API returns it only while a spam restriction is in force; it is the single fact that
    separates a TEMPORARY restriction from a permanent block. Anything unusable → None."""
    raw = (wa_settings or {}).get("suspendedUntil")
    if raw in (None, "", 0, "0"):
        return None
    try:
        return datetime.utcfromtimestamp(int(raw))
    except (TypeError, ValueError, OSError, OverflowError):
        return None


async def refresh_suspended_until(db, account, client=None) -> datetime | None:
    """V57 — fetch and persist `accounts.suspended_until` for a suspended instance. Best-effort:
    a network/permission failure must never break the poll or webhook path that called us."""
    try:
        if client is None:
            from app.services.green_api import GreenAPIClient
            client = GreenAPIClient(account.instance_id, account.api_token)
        until = parse_suspended_until(await client.get_wa_settings())
    except Exception as e:  # pragma: no cover - network best-effort
        logger.warning("suspendedUntil lookup failed for %s: %s",
                       getattr(account, "instance_id", "?"), e)
        return None
    account.suspended_until = until
    return until


async def apply_state(db, account, state: str, source: str,
                      now: datetime | None = None) -> dict:
    """Record `state` for `account` in the live-state cache/table and act on danger states.
    Returns {instance_id, state, acted}. `source` is "poll" or "webhook"."""
    now = now or datetime.utcnow()
    s = (state or "unknown").strip().lower()
    await send_gate.persist_live_state(db, account.instance_id, s, source, now)
    result = {"instance_id": account.instance_id, "state": s, "acted": None}
    # V57 — keep `suspended_until` in step with the live state: fill it while suspended, clear it
    # the moment the instance reports anything else, so a stale date can never linger in the UI.
    if s == "suspended":
        # V67.1 Phase 1.1 — canonical suspension path only. Must NOT fall through into the
        # generic danger-state cooldown/throttle branch (webhook + record_suspension deliberately
        # omit cooldown so a recovered number is not sidelined after the restriction lifts).
        from app.models.account import AccountStatus
        if getattr(account, "status", None) != AccountStatus.suspended:
            account.status = AccountStatus.suspended
        result["suspended_until"] = await refresh_suspended_until(db, account)
        # V65 — record the suspension as an incident so health/warmth/eligibility stop calling a
        # restricted number healthy. Idempotent per open incident, so the 60s poll adds one row,
        # not one per tick. Fleet breaker is notified inside record_suspension.
        from app.services.incident_handler import record_suspension
        try:
            await record_suspension(account, source, db)
        except Exception as e:  # pragma: no cover - best-effort
            logger.warning("record_suspension failed for %s: %s", account.instance_id, e)
        result["acted"] = "suspended"
        return result

    if getattr(account, "suspended_until", None) is not None:
        account.suspended_until = None
    # V65 — the instance reports something other than suspended: close any open suspension
    # incident so a recovered number is not penalised for a restriction that has lifted.
    from app.services.incident_handler import resolve_suspension
    try:
        await resolve_suspension(account, db)
    except Exception as e:  # pragma: no cover - best-effort
        logger.warning("resolve_suspension failed for %s: %s", account.instance_id, e)

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
        # (suspended returns earlier — never reaches this branch.)
        account.throttle_factor = governors.YELLOW_THROTTLE_FACTOR
        account.throttle_until = now + timedelta(days=7)
        account.cooldown_until = now + timedelta(days=1)
        account.last_incident_at = now
        result["acted"] = s
    return result
