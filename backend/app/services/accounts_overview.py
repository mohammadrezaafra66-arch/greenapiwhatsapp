"""V48 — unified "all accounts at a glance" aggregation.

PURE AGGREGATION ONLY. This module introduces NO new scoring / eligibility / incident math.
For every account it assembles one row by calling the EXACT existing, already-confirmed-correct
sources that the four separate pages use today:

  • connection state + activity  → the accounts source (Account row: status, sent/received today)
  • warmth score/level, days-connected, recent-incident count → warmup_warmth.warmth_for_account
    (the shared V27/V29 evaluator — called directly, never recomputed)
  • sender-eligibility + override → sender_eligibility.check_sender_eligibility + has_valid_override
  • health + throttle/cooldown + 7d rates → account_health.protection_snapshot (the SAME row the
    /protection page renders)
  • incident summary (last type/date, total count) → AccountIncident (the SAME table the
    /incidents timeline reads)
  • mesh role → warmup_exclusion.mesh_role_for (the SAME logic the mesh dashboard uses)
  • TC sender role + contact count + on/off → WarmupHelper counts + enabled_sender_ids
  • cold/recipient (TC) role → WarmupTeamEnrollment

Scope: every non-deleted account (soft-deleted rows are hidden on the accounts and protection
pages already, so the overview matches them).
"""
from __future__ import annotations
from datetime import datetime

from sqlalchemy import select, func

from app.models.account import Account, AccountStatus
from app.models.incident import AccountIncident
from app.models.warmup_helpers import WarmupHelper, WarmupTeamEnrollment
from app.services.warmup_warmth import warmth_for_account
from app.services import sender_eligibility as se
from app.services import warmup_helper_service as hs
from app.services.warmup_exclusion import enrollment_states_by_instance, mesh_role_for
from app.services.account_health import protection_snapshot


def _iso(dt):
    return dt.isoformat() if isinstance(dt, datetime) else None


async def _incident_summary_by_account(db) -> tuple[dict, dict]:
    """{account_id(str): most-recent AccountIncident} and {account_id(str): total count}, read
    from the SAME AccountIncident table the incident timeline uses. Newest-first scan so the
    first row seen per account is its most recent."""
    rows = (await db.execute(
        select(AccountIncident).order_by(AccountIncident.created_at.desc())
    )).scalars().all()
    latest: dict = {}
    counts: dict = {}
    for i in rows:
        key = str(i.account_id) if i.account_id else None
        if key is None:
            continue
        counts[key] = counts.get(key, 0) + 1
        latest.setdefault(key, i)
    return latest, counts


async def build_overview(db, now: datetime | None = None) -> list[dict]:
    """One aggregated row per non-deleted account. Every field is sourced from the existing
    services above; nothing is recomputed here."""
    now = now or datetime.utcnow()
    accounts = (await db.execute(
        select(Account).where(Account.status != AccountStatus.deleted).order_by(Account.created_at.desc())
    )).scalars().all()

    # Pre-aggregate the small lookup tables once (avoid per-account N+1 on these).
    enr_map = await enrollment_states_by_instance(db)                 # {instance_id: (state, is_enabled)}
    disabled_ids = await hs.enabled_sender_ids(db)                    # set of DISABLED sender instance_ids
    recovery_ids = await se.in_mesh_recovery_ids(db)                  # senders paused for mesh recovery
    contact_counts = dict((await db.execute(
        select(WarmupHelper.sender_instance_id, func.count()).group_by(WarmupHelper.sender_instance_id)
    )).all())
    team_cold = {e.cold_instance_id: bool(e.is_enabled)
                 for e in (await db.execute(select(WarmupTeamEnrollment))).scalars().all()}
    latest_incident, incident_totals = await _incident_summary_by_account(db)

    rows = []
    for a in accounts:
        iid = a.instance_id
        # ── warmth (shared evaluator) ──
        w = await warmth_for_account(db, a, now)
        # ── sender eligibility + override (exact /sender-eligibility functions) ──
        elig, ereason, emsg, eage = await se.check_sender_eligibility(db, iid, now)
        override = await se.has_valid_override(db, iid)
        # ── health / protection row (shared with /protection) ──
        snap = await protection_snapshot(a, db)
        # ── mesh role (shared with the mesh dashboard) ──
        mesh_role = mesh_role_for(enr_map.get(iid), bool(a.is_warm_peer))
        contact_count = int(contact_counts.get(iid, 0) or 0)
        tc_sender = contact_count > 0
        tc_cold = bool(team_cold.get(iid, False))
        # A "no role" account: not warmed/peer/graduated in the mesh, not a TC sender, not a TC cold.
        has_role = mesh_role != "none" or tc_sender or tc_cold
        # ── incident summary (same AccountIncident source as the timeline) ──
        li = latest_incident.get(str(a.id))
        status_val = a.status.value if hasattr(a.status, "value") else a.status

        rows.append({
            "account_id": str(a.id),
            "instance_id": iid,
            "name": a.name,
            "phone": a.phone,
            "platform": getattr(a, "platform", "whatsapp") or "whatsapp",
            "status": status_val,
            "green_api_deleted": snap["green_api_deleted"],
            # ── connection / activity (accounts source) ──
            "sent_today": a.sent_today,
            "received_today": a.received_today,
            "daily_cap": snap["effective_cap"],
            # ── warmth (shared evaluator — not recomputed) ──
            "warmth_score": w["score"],
            "warmth_level": w["level"],
            "warmth_components": w["components"],
            "days_connected": w["age_days"],
            "recent_incidents_14d": w["recent_incidents"],
            "incident_free_14d": int(w["recent_incidents"] or 0) == 0,
            # ── sender eligibility (exact TC functions) ──
            "eligible": bool(elig),
            "eligibility_reason": ereason,
            "eligibility_message": emsg,
            "eligibility_override": bool(override),
            # ── health / protection (shared row) ──
            "health_score": snap["health_score"],
            "yellow_card_rate_7d": snap["yellow_card_rate_7d"],
            "reply_rate_7d": snap["reply_rate_7d"],
            "in_cooldown": snap["in_cooldown"],
            "cooldown_until": snap["cooldown_until"],
            "throttle_factor": snap["throttle_factor"],
            "incident_count_7d": snap["incident_count_7d"],
            # ── incident summary (AccountIncident source) ──
            "last_incident_type": (li.incident_type if li else None),
            "last_incident_at": _iso(li.created_at) if li else None,
            "incident_total": int(incident_totals.get(str(a.id), 0)),
            # ── role ──
            "role": {
                "mesh": mesh_role,                                   # being_warmed|peer_sender|graduated_peer|none
                "mesh_state": (enr_map.get(iid) or (None, None))[0],
                "is_mesh_peer": mesh_role in ("peer_sender", "graduated_peer"),
                "tc_sender": tc_sender,
                "tc_contact_count": contact_count,
                "tc_team_enabled": iid not in disabled_ids,
                "tc_cold": tc_cold,
                "in_mesh_recovery": iid in recovery_ids,
                "none": not has_role,
            },
        })
    return rows
