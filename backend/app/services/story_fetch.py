"""V50 PART 1 — multi-account incoming-story fetch.

Historically stories were fetched from exactly ONE account: the manual `/statuses/incoming`
endpoint resolves to whichever account is `is_default = true`, because the frontend calls it
with no account argument. If that single account is ever offline (as during its mesh-recovery
period) story fetching stops entirely, with zero fallback — even though other accounts are
connected and could see their own contacts' stories.

This module fixes that WITHOUT duplicating any fetch logic:

  • `fetch_stories_for_account` reuses the EXACT path the manual endpoint uses —
    `GreenAPIClient.get_incoming_statuses()` followed by the endpoint's own `_persist_incoming`
    (media download + active-contact harvest + row-id annotation). It just parameterizes the
    account, so it can run for ANY account, not only the default one.

  • `fetch_stories_for_all_eligible_accounts` lists every currently-eligible connected account
    and calls the per-account fetch for each, merging into `received_statuses` (already keyed by
    `instance_id` per row — no schema change). One account's failure is logged and skipped; it
    never aborts the others.

Eligibility (guardrail 3) reuses the project's ONE shared pre-send health gate
(`send_gate.gate_check`: status==active + 24h connect-cooldown + yellowCard-cooldown + throttle +
live Green API state) PLUS the V41 mesh-recovery pause (`sender_eligibility.in_mesh_recovery`). A
recovering or unhealthy account is skipped even though `getIncomingStatuses` is a read-only call —
staying consistent with this project's established caution that a recovering account gets zero
extra activity beyond its scripted recovery sequence.

This is READ-ONLY Green API activity (`getIncomingStatuses`, the same documented on-demand method
the manual page already uses). It does NOT enable or touch webhook/polling for messages or any
other feature — the webhook-only guarantee is untouched (guardrail 2).
"""
from __future__ import annotations
import logging
from datetime import datetime

from sqlalchemy import select

from app.models.account import Account, AccountStatus
from app.services.send_gate import gate_check
from app.services.sender_eligibility import in_mesh_recovery

logger = logging.getLogger("afrakala.story_fetch")


async def account_story_eligibility(db, account, now: datetime | None = None) -> tuple[bool, str]:
    """(eligible, reason_slug) for using `account` to fetch incoming stories right now.

    Reuses the ONE shared send-health gate (status/connect-cooldown/yellowCard-cooldown/throttle/
    live-state) and the V41 mesh-recovery pause — never a new, weaker check. reason ∈ the gate's
    slugs (not_active | connect_cooldown | cooldown | throttled | live_state:<s>) or
    'in_mesh_recovery' or 'ok'."""
    allowed, reason = gate_check(account, now)
    if not allowed:
        return False, reason
    if await in_mesh_recovery(db, getattr(account, "instance_id", None)):
        return False, "in_mesh_recovery"
    return True, "ok"


async def fetch_stories_for_account(db, account) -> int:
    """Fetch + persist ONE account's incoming stories, reusing the EXACT path the manual
    `/statuses/incoming` endpoint uses: `GreenAPIClient.get_incoming_statuses()` then the
    endpoint's own `_persist_incoming` (which downloads media, harvests active contacts, and
    annotates row-ids). No fetch/persist logic is duplicated here. Returns the number of statuses
    fetched from Green API for this account."""
    # Imported lazily to avoid an import cycle (the API module imports services at load time) and
    # to guarantee we call the SAME persistence helper the live endpoint uses — not a copy.
    from app.api.v1.statuses import _persist_incoming
    from app.services.green_api import GreenAPIClient

    client = GreenAPIClient(account.instance_id, account.api_token)
    statuses = await client.get_incoming_statuses()
    await _persist_incoming(db, account.instance_id, statuses)
    return len(statuses or [])


async def eligible_candidate_accounts(db) -> list:
    """Every active WhatsApp account, deterministically ordered with the default account first
    (it is the historical contributor), then the rest by instance_id. Telegram instances are
    excluded — `getIncomingStatuses` is a WhatsApp-status method. Per-account health/mesh-recovery
    is applied later by `account_story_eligibility`; this is only the candidate set."""
    rows = (await db.execute(
        select(Account).where(
            Account.status == AccountStatus.active,
            Account.platform == "whatsapp",
        )
    )).scalars().all()
    return sorted(rows, key=lambda a: (not bool(getattr(a, "is_default", False)),
                                       getattr(a, "instance_id", "") or ""))


async def fetch_stories_for_all_eligible_accounts(db, *, accounts: list | None = None,
                                                  fetch_fn=None,
                                                  now: datetime | None = None) -> dict:
    """V50 PART 1 — loop over EVERY currently-eligible connected account and fetch each one's
    incoming stories, merging results into `received_statuses` (already keyed per-row by
    `instance_id`, so no schema change and no cross-account collision).

    Skips any unhealthy / mesh-recovery account (guardrail 3), recording why. A single account's
    fetch raising is logged and skipped — it NEVER aborts fetching for the remaining accounts.

    `accounts` / `fetch_fn` are injection points for tests; production passes neither.
    Returns a summary: {eligible, fetched, failed, skipped, total_statuses, results, skipped_detail}.
    """
    now = now or datetime.utcnow()
    fetch_fn = fetch_fn or fetch_stories_for_account
    if accounts is None:
        accounts = await eligible_candidate_accounts(db)

    summary: dict = {
        "eligible": 0, "fetched": 0, "failed": 0, "skipped": 0,
        "total_statuses": 0, "results": [], "skipped_detail": [],
    }

    for account in accounts:
        instance_id = getattr(account, "instance_id", None)
        eligible, reason = await account_story_eligibility(db, account, now)
        if not eligible:
            summary["skipped"] += 1
            summary["skipped_detail"].append({"instance_id": instance_id, "reason": reason})
            logger.info("story-fetch skip %s: %s", instance_id, reason)
            continue
        summary["eligible"] += 1
        try:
            count = await fetch_fn(db, account)
            summary["fetched"] += 1
            summary["total_statuses"] += int(count or 0)
            summary["results"].append({"instance_id": instance_id, "count": int(count or 0)})
        except Exception as e:
            # Guardrail: one account's problem must not abort the others — log and continue.
            summary["failed"] += 1
            summary["results"].append({"instance_id": instance_id, "error": str(e)})
            logger.warning("story-fetch failed for %s: %s — continuing with next account",
                           instance_id, e)

    logger.info("story-fetch cycle: eligible=%s fetched=%s failed=%s skipped=%s statuses=%s",
                summary["eligible"], summary["fetched"], summary["failed"],
                summary["skipped"], summary["total_statuses"])
    return summary
