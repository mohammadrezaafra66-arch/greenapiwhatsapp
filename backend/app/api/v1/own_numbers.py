"""V45 PART 1 — management API for the "our own numbers" exclusion list.

CRUD over own_number_exclusions plus a re-sync-from-instances action. Numbers are normalized to the
national core on the way in (reusing the existing normalizer), so equivalent formats collapse to one
entry and adding a duplicate is a no-op.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.own_number import OwnNumberExclusion
from app.services import own_number_exclusion as own_svc

router = APIRouter(prefix="/own-numbers", tags=["own-numbers"])


class OwnNumberBody(BaseModel):
    phone: str
    label: str | None = None


def _serialize(r: OwnNumberExclusion) -> dict:
    return {
        "id": str(r.id),
        "phone_core": r.phone_core,
        "phone_raw": r.phone_raw,
        "label": r.label,
        "source": r.source,
        "added_at": r.added_at.isoformat() if r.added_at else None,
    }


@router.get("/")
async def list_own_numbers(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(OwnNumberExclusion).order_by(OwnNumberExclusion.added_at.desc())
    )).scalars().all()
    return {"count": len(rows), "items": [_serialize(r) for r in rows]}


@router.post("/")
async def add_own_number(body: OwnNumberBody, db: AsyncSession = Depends(get_db)):
    core = own_svc.normalize_own_number(body.phone)
    if not core:
        raise HTTPException(400, "شماره معتبر نیست")
    row, created = await own_svc.add_exclusion(db, body.phone, label=body.label, source="manual")
    await db.commit()
    await db.refresh(row)
    return {"created": created, "item": _serialize(row)}


@router.delete("/{exclusion_id}")
async def remove_own_number(exclusion_id: str, db: AsyncSession = Depends(get_db)):
    try:
        eid = uuid.UUID(exclusion_id)
    except ValueError:
        raise HTTPException(400, "شناسه معتبر نیست")
    ok = await own_svc.remove_exclusion(db, eid)
    if not ok:
        raise HTTPException(404, "یافت نشد")
    await db.commit()
    return {"deleted": True}


@router.post("/reseed")
async def reseed_from_accounts(db: AsyncSession = Depends(get_db)):
    """Re-sync from our own Green API instances — adds any connected-instance numbers not already
    listed. Idempotent: never duplicates, never touches manual entries."""
    added = await own_svc.seed_from_accounts(db)
    await db.commit()
    return {"added": added}
