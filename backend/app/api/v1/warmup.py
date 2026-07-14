"""V16 PART 5 — warm-up dashboard, phrase-pool CRUD, and batch start/stop."""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.account import Account, AccountStatus
from app.models.warmup import WarmupPhrase
from app.services.warmup_auto import (
    warmup_day, warmup_daily_limit, warmup_sent_today, WARMUP_TOTAL_DAYS,
)

router = APIRouter(prefix="/warmup", tags=["warmup"])


@router.get("/dashboard")
async def warmup_dashboard(db: AsyncSession = Depends(get_db)):
    """Every account currently in warm-up: stage/day, progress, replies today vs cap, ready."""
    accounts = (await db.execute(
        select(Account).where(Account.auto_warmup.is_(True))
    )).scalars().all()
    items = []
    for a in accounts:
        day = warmup_day(a)
        cap = warmup_daily_limit(day)
        sent = await warmup_sent_today(str(a.id)) if cap else 0
        phase = ("دریافت‌فقط" if cap == 0 and not a.warmup_completed else
                 "آماده" if a.warmup_completed else f"ارسال ≤{cap}/روز")
        items.append({
            "account_id": str(a.id),
            "name": a.name,
            "status": a.status.value if hasattr(a.status, "value") else a.status,
            "day": day,
            "total_days": WARMUP_TOTAL_DAYS,
            "daily_cap": cap,
            "sent_today": sent,
            "phase": phase,
            "completed": a.warmup_completed,
        })
    return {"accounts": items, "total_days": WARMUP_TOTAL_DAYS}


# ── batch controls ──────────────────────────────────────────────────────────
@router.post("/start-all")
async def start_all(db: AsyncSession = Depends(get_db)):
    """Turn warm-up ON for every account that isn't already completed (for newly-added numbers)."""
    accounts = (await db.execute(
        select(Account).where(Account.status != AccountStatus.deleted, Account.warmup_completed.is_(False))
    )).scalars().all()
    n = 0
    for a in accounts:
        if not a.auto_warmup:
            a.auto_warmup = True
            if not a.warmup_started_at:
                a.warmup_started_at = datetime.utcnow()
            n += 1
    await db.commit()
    return {"started": n}


@router.post("/stop-all")
async def stop_all(db: AsyncSession = Depends(get_db)):
    accounts = (await db.execute(select(Account).where(Account.auto_warmup.is_(True)))).scalars().all()
    for a in accounts:
        a.auto_warmup = False
    await db.commit()
    return {"stopped": len(accounts)}


# ── phrase-pool CRUD ────────────────────────────────────────────────────────
class PhraseBody(BaseModel):
    text: str
    is_active: bool = True


@router.get("/phrases")
async def list_phrases(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(WarmupPhrase).order_by(WarmupPhrase.created_at))).scalars().all()
    return [{"id": str(p.id), "text": p.text, "is_active": p.is_active} for p in rows]


@router.post("/phrases")
async def create_phrase(body: PhraseBody, db: AsyncSession = Depends(get_db)):
    if not body.text.strip():
        raise HTTPException(400, "متن عبارت لازم است")
    p = WarmupPhrase(text=body.text.strip(), is_active=body.is_active)
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return {"id": str(p.id), "text": p.text, "is_active": p.is_active}


@router.put("/phrases/{phrase_id}")
async def update_phrase(phrase_id: str, body: PhraseBody, db: AsyncSession = Depends(get_db)):
    p = await db.get(WarmupPhrase, uuid.UUID(phrase_id))
    if not p:
        raise HTTPException(404, "عبارت یافت نشد")
    p.text = body.text.strip()
    p.is_active = body.is_active
    await db.commit()
    return {"ok": True}


@router.delete("/phrases/{phrase_id}")
async def delete_phrase(phrase_id: str, db: AsyncSession = Depends(get_db)):
    p = await db.get(WarmupPhrase, uuid.UUID(phrase_id))
    if p:
        await db.delete(p)
        await db.commit()
    return {"ok": True}
