"""V35 PART 4 — API for the guided onboarding wizard «راه‌اندازی».

Endpoints:
  POST   /onboarding                       — step 1: record SIM insertion (starts Gate A)
  GET    /onboarding                       — list all in-progress onboardings + derived state
  GET    /onboarding/{id}                  — one onboarding + derived state
  POST   /onboarding/{id}/confirm-whatsapp — step 2: confirm WhatsApp is up (starts Gate B)
  POST   /onboarding/{id}/confirm-green-api— step 4: confirm Green API connected (done)
  DELETE /onboarding/{id}                  — remove an onboarding record

The locked/unlocked state is always DERIVED (onboarding_service.derive_state); the two confirm
endpoints refuse to run before their gate has elapsed, so no gate can be skipped from the API.
All datetimes are entered/shown in Shamsi (Tehran) via app.utils.shamsi.
"""
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.account_onboarding import AccountOnboarding
from app.services import onboarding_service as ob
from app.utils.shamsi import to_shamsi, from_shamsi

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class CreateBody(BaseModel):
    phone_number: str
    phone_make_model: str | None = None
    sim_inserted_shamsi: str            # "YYYY/MM/DD HH:MM" (Tehran) from the Shamsi picker


def _row_dict(o: AccountOnboarding, now: datetime | None = None) -> dict:
    now = now or datetime.utcnow()
    st = ob.derive_state(
        sim_inserted_at=o.sim_inserted_at, whatsapp_activated_at=o.whatsapp_activated_at,
        green_api_connected_at=o.green_api_connected_at, now=now)
    return {
        "id": str(o.id),
        "phone_number": o.phone_number,
        "phone_make_model": o.phone_make_model,
        "sim_inserted_at": o.sim_inserted_at.isoformat() if o.sim_inserted_at else None,
        "sim_inserted_shamsi": to_shamsi(o.sim_inserted_at),
        "whatsapp_activated_at": o.whatsapp_activated_at.isoformat() if o.whatsapp_activated_at else None,
        "whatsapp_activated_shamsi": to_shamsi(o.whatsapp_activated_at),
        "green_api_connected_at": o.green_api_connected_at.isoformat() if o.green_api_connected_at else None,
        "green_api_connected_shamsi": to_shamsi(o.green_api_connected_at),
        "current_step": o.current_step,
        # derived, authoritative state
        "phase": st["phase"],
        "step": st["step"],
        "locked": st["locked"],
        "done": st["done"],
        "next_unlock_at": st["next_unlock_at"].isoformat() if st["next_unlock_at"] else None,
        "next_unlock_shamsi": to_shamsi(st["next_unlock_at"]) if st["next_unlock_at"] else None,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }


@router.post("")
@router.post("/")
async def create_onboarding(body: CreateBody, db: AsyncSession = Depends(get_db)):
    """Step 1 — record the SIM insertion. Starts Gate A (24h). Phone number is mandatory."""
    phone = (body.phone_number or "").strip()
    if not phone:
        raise HTTPException(400, "شماره تلفن لازم است")
    sim_dt = from_shamsi(body.sim_inserted_shamsi)
    if sim_dt is None:
        raise HTTPException(400, "تاریخ و زمان واردکردن سیم‌کارت نامعتبر است")
    o = AccountOnboarding(
        phone_number=phone, phone_make_model=(body.phone_make_model or None) and body.phone_make_model.strip() or None,
        sim_inserted_at=sim_dt, current_step=1)
    db.add(o)
    await db.commit()
    await db.refresh(o)
    return _row_dict(o)


@router.get("")
@router.get("/")
async def list_onboardings(db: AsyncSession = Depends(get_db)):
    """List every onboarding-in-progress with its current step + next-unlock time (Shamsi)."""
    rows = (await db.execute(
        select(AccountOnboarding).order_by(AccountOnboarding.created_at.desc()))).scalars().all()
    now = datetime.utcnow()
    return {"onboardings": [_row_dict(o, now) for o in rows]}


@router.get("/{onboarding_id}")
async def get_onboarding(onboarding_id: str, db: AsyncSession = Depends(get_db)):
    o = await db.get(AccountOnboarding, uuid.UUID(onboarding_id))
    if o is None:
        raise HTTPException(404, "مورد یافت نشد")
    return _row_dict(o)


@router.post("/{onboarding_id}/confirm-whatsapp")
async def confirm_whatsapp(onboarding_id: str, db: AsyncSession = Depends(get_db)):
    """Step 2 — user confirms WhatsApp is up on this number. Allowed only once Gate A elapsed."""
    o = await db.get(AccountOnboarding, uuid.UUID(onboarding_id))
    if o is None:
        raise HTTPException(404, "مورد یافت نشد")
    now = datetime.utcnow()
    if not ob.can_confirm_whatsapp(
            sim_inserted_at=o.sim_inserted_at, whatsapp_activated_at=o.whatsapp_activated_at,
            green_api_connected_at=o.green_api_connected_at, now=now):
        raise HTTPException(400, "هنوز زود است — تا پایان دورهٔ ۲۴ ساعتهٔ اول صبر کنید")
    o.whatsapp_activated_at = now
    o.current_step = 3
    await db.commit()
    await db.refresh(o)
    return _row_dict(o)


@router.post("/{onboarding_id}/confirm-green-api")
async def confirm_green_api(onboarding_id: str, db: AsyncSession = Depends(get_db)):
    """Step 4 — user confirms the number is connected to Green API. Allowed only once Gate B elapsed."""
    o = await db.get(AccountOnboarding, uuid.UUID(onboarding_id))
    if o is None:
        raise HTTPException(404, "مورد یافت نشد")
    now = datetime.utcnow()
    if not ob.can_confirm_green_api(
            sim_inserted_at=o.sim_inserted_at, whatsapp_activated_at=o.whatsapp_activated_at,
            green_api_connected_at=o.green_api_connected_at, now=now):
        raise HTTPException(400, "هنوز زود است — تا پایان دورهٔ ۲۴ ساعتهٔ دوم صبر کنید")
    if o.green_api_login_prompted_at is None:
        o.green_api_login_prompted_at = now
    o.green_api_connected_at = now
    o.current_step = 4
    await db.commit()
    await db.refresh(o)
    return _row_dict(o)


@router.delete("/{onboarding_id}")
async def delete_onboarding(onboarding_id: str, db: AsyncSession = Depends(get_db)):
    o = await db.get(AccountOnboarding, uuid.UUID(onboarding_id))
    if o is None:
        raise HTTPException(404, "مورد یافت نشد")
    await db.delete(o)
    await db.commit()
    return {"deleted": True}
