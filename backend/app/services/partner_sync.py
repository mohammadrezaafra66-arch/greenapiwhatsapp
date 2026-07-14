"""V14 FEATURE 3 — reconcile local accounts with the Green API Partner account.

Shared by POST /api/v1/partner/sync and the Celery beat task
`sync_partner_instances` (every 6h). NEVER auto-deletes a local account — instances
missing from Green API are flagged is_orphaned=true for manual review.
"""
import logging
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.account import Account, AccountStatus
from app.models.partner import PartnerInstanceLog
from app.services import green_partner

logger = logging.getLogger("afrakala.partner")

# Prefix used for names we auto-generate when pulling in a console-created instance.
_AUTO_NAME_PREFIX = "شماره "


def _is_auto_name(name: str | None, id_instance) -> bool:
    """True if the local name is still an auto-generated default (safe to overwrite
    from Green API), false if the user renamed it (must be preserved)."""
    if not name:
        return True
    return name.startswith(_AUTO_NAME_PREFIX) or name == str(id_instance)


async def sync_partner_instances(db: AsyncSession) -> dict:
    """Pull the partner instance list and reconcile. Returns counts."""
    remote = await green_partner.get_instances()
    remote = remote if isinstance(remote, list) else []

    created = updated = orphaned = 0
    seen_ids: set[str] = set()

    for inst in remote:
        id_instance = inst.get("idInstance")
        if id_instance is None:
            continue
        id_str = str(id_instance)
        # Green API returns instances deleted in the last ~3 months flagged deleted=true.
        if inst.get("deleted") is True:
            continue
        seen_ids.add(id_str)
        tariff = inst.get("tariff") or inst.get("typeInstance")
        remote_name = inst.get("name")

        existing = (
            await db.execute(select(Account).where(Account.instance_id == id_str))
        ).scalar_one_or_none()

        if existing:
            if tariff:
                existing.tariff = tariff
            # Only overwrite the name if the local one is still auto-generated.
            if remote_name and _is_auto_name(existing.name, id_str):
                existing.name = remote_name
            existing.is_orphaned = False
            updated += 1
        else:
            # A console-created instance we didn't know about — pull it in.
            db.add(Account(
                name=remote_name or f"{_AUTO_NAME_PREFIX}{id_str}",
                instance_id=id_str,
                api_token=inst.get("apiTokenInstance") or "",
                status=AccountStatus.pending,
                created_via_partner=True,
                partner_created_at=datetime.utcnow(),
                tariff=tariff,
            ))
            created += 1

    # Flag local partner accounts that Green API no longer lists. NEVER auto-delete.
    locals_ = (await db.execute(select(Account))).scalars().all()
    for a in locals_:
        if a.instance_id not in seen_ids and a.status != AccountStatus.deleted \
                and (a.created_via_partner or False):
            if not a.is_orphaned:
                a.is_orphaned = True
                orphaned += 1

    detail = f"created={created} updated={updated} orphaned={orphaned}"
    db.add(PartnerInstanceLog(action="synced", detail=detail))
    await db.commit()
    logger.info("Partner sync: %s", detail)
    return {"created": created, "updated": updated, "orphaned": orphaned}
