"""V16 PART 5 — warm-up dashboard, phrase-pool CRUD, and batch start/stop.
V17 — mesh warm-up enrollment: the one toggle + pre-flight + warm-peer marking."""
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


# ── V17 — the one toggle: enroll / disable a number for automatic mesh warm-up ──
@router.post("/enroll/{account_id}")
async def enroll_account(account_id: str, db: AsyncSession = Depends(get_db)):
    """Flip warm-up ON for an account: create the enrollment and run pre-flight
    (apply warming settings, clear queue, 24h cooldown, mutual-contact mesh handshake)."""
    acc = await db.get(Account, uuid.UUID(account_id))
    if not acc:
        raise HTTPException(404, "اکانت یافت نشد")
    from app.services.warmup_mesh_service import enroll_and_preflight
    return await enroll_and_preflight(db, acc)


@router.post("/disable/{account_id}")
async def disable_account(account_id: str, db: AsyncSession = Depends(get_db)):
    """Flip warm-up OFF: pause everything for this number immediately."""
    acc = await db.get(Account, uuid.UUID(account_id))
    if not acc:
        raise HTTPException(404, "اکانت یافت نشد")
    from app.services.warmup_mesh_service import disable_warmup
    return await disable_warmup(db, acc)


class WarmPeerBody(BaseModel):
    is_warm_peer: bool = True


@router.post("/warm-peer/{account_id}")
async def set_warm_peer(account_id: str, body: WarmPeerBody, db: AsyncSession = Depends(get_db)):
    """Manually mark a known-good number (e.g. 989122270261) as an eligible warm mesh peer."""
    acc = await db.get(Account, uuid.UUID(account_id))
    if not acc:
        raise HTTPException(404, "اکانت یافت نشد")
    acc.is_warm_peer = body.is_warm_peer
    await db.commit()
    return {"account_id": account_id, "is_warm_peer": acc.is_warm_peer}


# ── V17 PART 6 — mesh warm-up dashboard + per-number controls ────────────────
@router.get("/mesh-dashboard")
async def mesh_dashboard(db: AsyncSession = Depends(get_db)):
    """Full mesh warm-up dashboard: one card per enrolled number (state/day/progress,
    counts vs target, reply ratio, peers + per-edge activity, next action, banners)."""
    from app.models.warmup_mesh import WarmupEnrollment, WarmupMeshEdge
    from app.services.warmup_dashboard import build_dashboard
    from app.services.warmup_killswitch import is_breaker_tripped
    enrollments = (await db.execute(select(WarmupEnrollment))).scalars().all()
    edges = (await db.execute(select(WarmupMeshEdge))).scalars().all()
    edges_by_instance: dict = {}
    for e in edges:
        edges_by_instance.setdefault(e.new_instance_id, []).append(e)
    tripped = await is_breaker_tripped(db)
    return build_dashboard(enrollments, edges_by_instance, breaker_tripped=tripped)


async def _account_or_404(account_id: str, db) -> Account:
    acc = await db.get(Account, uuid.UUID(account_id))
    if not acc:
        raise HTTPException(404, "اکانت یافت نشد")
    return acc


@router.post("/pause/{account_id}")
async def pause_number(account_id: str, db: AsyncSession = Depends(get_db)):
    from app.services.warmup_mesh_service import disable_warmup
    return await disable_warmup(db, await _account_or_404(account_id, db))


@router.post("/resume/{account_id}")
async def resume_number(account_id: str, db: AsyncSession = Depends(get_db)):
    from app.services.warmup_mesh_service import resume_warmup
    return await resume_warmup(db, await _account_or_404(account_id, db))


@router.post("/restart/{account_id}")
async def restart_number(account_id: str, db: AsyncSession = Depends(get_db)):
    from app.services.warmup_mesh_service import force_restart
    return await force_restart(db, await _account_or_404(account_id, db))


@router.get("/events/{account_id}")
async def number_events(account_id: str, limit: int = 50, db: AsyncSession = Depends(get_db)):
    """Recent warmup_event_log rows for a number (audit trail shown in the dashboard)."""
    from app.models.warmup_mesh import WarmupEnrollment, WarmupEventLog
    acc = await _account_or_404(account_id, db)
    enr = (await db.execute(
        select(WarmupEnrollment).where(WarmupEnrollment.instance_id == acc.instance_id)
    )).scalar_one_or_none()
    if not enr:
        return {"events": []}
    rows = (await db.execute(
        select(WarmupEventLog).where(WarmupEventLog.enrollment_id == enr.id)
        .order_by(WarmupEventLog.created_at.desc()).limit(limit)
    )).scalars().all()
    return {"events": [{
        "event_type": r.event_type, "delivery_status": r.delivery_status,
        "payload": r.payload_json, "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]}


@router.post("/mesh-start-all")
async def mesh_start_all(db: AsyncSession = Depends(get_db)):
    """Batch «شروع گرم‌سازی همه» — enroll every active account not already enrolled."""
    from app.models.warmup_mesh import WarmupEnrollment
    from app.services.warmup_mesh_service import enroll_and_preflight
    accounts = (await db.execute(
        select(Account).where(Account.status == AccountStatus.active)
    )).scalars().all()
    enrolled_ids = set((await db.execute(select(WarmupEnrollment.instance_id))).scalars().all())
    started = 0
    for a in accounts:
        if a.instance_id in enrolled_ids:
            continue
        try:
            await enroll_and_preflight(db, a)
            started += 1
        except Exception:
            pass
    return {"started": started}


@router.post("/mesh-stop-all")
async def mesh_stop_all(db: AsyncSession = Depends(get_db)):
    """Global stop: pause every enrolled number immediately."""
    from app.models.warmup_mesh import WarmupEnrollment
    from app.services.warmup_state import WarmupState
    rows = (await db.execute(
        select(WarmupEnrollment).where(WarmupEnrollment.is_enabled.is_(True))
    )).scalars().all()
    for enr in rows:
        enr.is_enabled = False
        if enr.state not in (WarmupState.BLOCKED_RESET.value,):
            enr.state = WarmupState.PAUSED.value
    await db.commit()
    return {"stopped": len(rows)}


# ── V19 PART 1 — read a warm account's ADMIN-owned groups (add targets) ──────
@router.get("/admin-groups/{account_id}")
async def admin_groups(account_id: str, refresh: bool = False, db: AsyncSession = Depends(get_db)):
    """List the groups where this (warm) account is admin/superadmin — the only groups it
    can place cold numbers into. Cached/throttled to protect getGroupData."""
    acc = await db.get(Account, uuid.UUID(account_id))
    if not acc:
        raise HTTPException(404, "اکانت یافت نشد")
    if acc.status != AccountStatus.active:
        raise HTTPException(400, "این اکانت متصل/فعال نیست")
    from app.services.green_api import GreenAPIClient
    from app.services.warmup_groups import list_admin_groups
    client = GreenAPIClient(acc.instance_id, acc.api_token)
    groups = await list_admin_groups(client, own_number=acc.phone, use_cache=not refresh)
    return {"account_id": account_id, "instance_id": acc.instance_id, "groups": groups}


@router.get("/breaker")
async def breaker_status(db: AsyncSession = Depends(get_db)):
    from app.services.warmup_killswitch import is_breaker_tripped
    return {"tripped": await is_breaker_tripped(db)}


@router.post("/breaker/reset")
async def breaker_reset(db: AsyncSession = Depends(get_db)):
    from app.services.warmup_killswitch import reset_breaker
    res = await reset_breaker(db)
    await db.commit()
    return res


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
