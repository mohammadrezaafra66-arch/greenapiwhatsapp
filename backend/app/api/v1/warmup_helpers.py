"""V25 PART 1 — API for the "human helpers" warm-up assist.

CRUD over the capped (≤25) helper list, the single global toggle (default OFF), and a
read-only view of the per-cold-number ask tasks + their status. All UI strings Persian."""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.account import Account
from app.models.warmup_helpers import WarmupHelperTask
from app.services import warmup_helper_service as hs

router = APIRouter(prefix="/warmup-helpers", tags=["warmup-helpers"])


class HelperBody(BaseModel):
    name: str
    phone: str
    is_active: bool = True


class HelperUpdateBody(BaseModel):
    name: str | None = None
    phone: str | None = None
    is_active: bool | None = None


class ToggleBody(BaseModel):
    enabled: bool


@router.get("/")
async def list_helpers(db: AsyncSession = Depends(get_db)):
    """The helper list + the active count («۱۸ از ۲۵») + the global toggle state."""
    helpers = await hs.list_helpers(db)
    active = sum(1 for h in helpers if h.is_active)
    conf = await hs.get_config(db)
    await db.commit()   # persist a lazily-created config row
    return {
        "enabled": conf.is_enabled,
        "active_count": active,
        "max_active": hs.MAX_ACTIVE_HELPERS,
        "helpers": [{
            "id": str(h.id), "name": h.name, "phone": h.phone,
            "is_active": h.is_active, "created_at": h.created_at.isoformat() if h.created_at else None,
        } for h in helpers],
    }


@router.post("/")
async def create_helper(body: HelperBody, db: AsyncSession = Depends(get_db)):
    try:
        h = await hs.add_helper(db, body.name, body.phone, body.is_active)
    except hs.HelperCapError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"id": str(h.id), "name": h.name, "phone": h.phone, "is_active": h.is_active}


@router.put("/{helper_id}")
async def edit_helper(helper_id: str, body: HelperUpdateBody, db: AsyncSession = Depends(get_db)):
    try:
        h = await hs.update_helper(db, uuid.UUID(helper_id), name=body.name,
                                   phone=body.phone, is_active=body.is_active)
    except hs.HelperCapError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        raise HTTPException(404 if "یافت نشد" in str(e) else 400, str(e))
    return {"id": str(h.id), "name": h.name, "phone": h.phone, "is_active": h.is_active}


@router.delete("/{helper_id}")
async def remove_helper(helper_id: str, db: AsyncSession = Depends(get_db)):
    ok = await hs.delete_helper(db, uuid.UUID(helper_id))
    return {"deleted": ok}


@router.post("/toggle")
async def toggle(body: ToggleBody, db: AsyncSession = Depends(get_db)):
    """Flip «کمک‌گیری از افراد واقعی برای گرم‌سازی» on/off (default OFF)."""
    conf = await hs.set_enabled(db, body.enabled)
    return {"enabled": conf.is_enabled}


@router.get("/tasks")
async def list_tasks(cold_instance_id: str | None = None, limit: int = 200,
                     db: AsyncSession = Depends(get_db)):
    """The helper tasks (per cold number) and their status, so the user can see who greeted
    each new number. Optionally filter to one cold number via ?cold_instance_id=."""
    helpers = {str(h.id): h for h in await hs.list_helpers(db)}
    accounts = (await db.execute(select(Account))).scalars().all()
    name_by_instance = {a.instance_id: a.name for a in accounts}

    q = select(WarmupHelperTask)
    if cold_instance_id:
        q = q.where(WarmupHelperTask.cold_instance_id == cold_instance_id)
    q = q.order_by(WarmupHelperTask.created_at.desc()).limit(min(limit, 500))
    rows = (await db.execute(q)).scalars().all()

    return {"tasks": [{
        "id": str(t.id),
        "helper_id": str(t.helper_id),
        "helper_name": (helpers.get(str(t.helper_id)).name if helpers.get(str(t.helper_id)) else None),
        "cold_instance_id": t.cold_instance_id,
        "cold_name": name_by_instance.get(t.cold_instance_id, t.cold_instance_id),
        "status": t.status,
        "asked_at": t.asked_at.isoformat() if t.asked_at else None,
        "reminded_at": t.reminded_at.isoformat() if t.reminded_at else None,
        "done_at": t.done_at.isoformat() if t.done_at else None,
        "attempts": t.attempts,
    } for t in rows]}
