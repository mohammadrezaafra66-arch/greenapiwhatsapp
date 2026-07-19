"""V25 PART 1 / V28 — API for the outreach assistant «دستیار ارتباط شخصی‌سازی‌شده».

V28 generalizes V25: any account can be an outreach SENDER, each with its OWN contact list
(name + phone, name mandatory), no hard count cap (a non-blocking soft-warning banner instead),
plus a per-cold-number task-status view. All UI strings Persian."""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.account import Account, AccountStatus
from app.models.warmup_helpers import WarmupHelperTask, WarmupHelper, OutreachBrief
from app.services import warmup_helper_service as hs

router = APIRouter(prefix="/warmup-helpers", tags=["warmup-helpers"])


class HelperBody(BaseModel):
    name: str
    phone: str
    is_active: bool = True
    sender_instance_id: str | None = None   # V28 — which of the user's accounts owns this contact


class HelperUpdateBody(BaseModel):
    name: str | None = None
    phone: str | None = None
    is_active: bool | None = None
    sender_instance_id: str | None = None


class ToggleBody(BaseModel):
    enabled: bool


class ThresholdBody(BaseModel):
    threshold: int


def _helper_dict(h) -> dict:
    return {
        "id": str(h.id), "name": h.name, "phone": h.phone,
        "sender_instance_id": h.sender_instance_id,
        "is_active": h.is_active,
        "created_at": h.created_at.isoformat() if h.created_at else None,
    }


@router.get("/senders")
async def list_senders(db: AsyncSession = Depends(get_db)):
    """V28 — every account the user can pick as an outreach sender (ANY account, not just warm
    peers), each with its current contact count. The sender role is INDEPENDENT of mesh
    warm-peer status (an account can be both, or either)."""
    accts = (await db.execute(
        select(Account).where(Account.status == AccountStatus.active).order_by(Account.created_at)
    )).scalars().all()
    counts = dict((await db.execute(
        select(WarmupHelper.sender_instance_id, func.count())
        .group_by(WarmupHelper.sender_instance_id)
    )).all())
    return {"senders": [{
        "instance_id": a.instance_id, "name": a.name, "phone": a.phone,
        "platform": getattr(a, "platform", "whatsapp") or "whatsapp",
        "is_warm_peer": bool(getattr(a, "is_warm_peer", False)),
        "contact_count": int(counts.get(a.instance_id, 0) or 0),
    } for a in accts]}


@router.get("/")
async def list_helpers(sender_instance_id: str | None = None, db: AsyncSession = Depends(get_db)):
    """One sender's OWN contact list (via ?sender_instance_id=), or all contacts when omitted.
    Includes the live count, the soft-warning threshold, and the non-blocking banner text when
    the sender's list is large (V28 — never a hard cap)."""
    if sender_instance_id:
        helpers = await hs.list_helpers_for_sender(db, sender_instance_id)
    else:
        helpers = await hs.list_helpers(db)
    active = sum(1 for h in helpers if h.is_active)
    conf = await hs.get_config(db)
    threshold = int(getattr(conf, "soft_warning_threshold", None) or hs.DEFAULT_SOFT_WARNING_THRESHOLD)
    await db.commit()   # persist a lazily-created config row
    return {
        "enabled": conf.is_enabled,
        "sender_instance_id": sender_instance_id,
        "active_count": active,
        "count": len(helpers),
        "soft_warning_threshold": threshold,
        "soft_warning": hs.soft_warning_notice(active, threshold),   # None or Persian banner
        "helpers": [_helper_dict(h) for h in helpers],
    }


@router.post("/")
async def create_helper(body: HelperBody, db: AsyncSession = Depends(get_db)):
    """Add one contact to a sender's list. name is MANDATORY; there is NO hard count cap.
    Returns the created contact plus a non-blocking soft-warning banner when the sender's list
    is now over the threshold (the client shows it and still proceeds)."""
    sender = body.sender_instance_id or await hs.resolve_main_sender_instance_id(db)
    try:
        h = await hs.add_helper(db, body.name, body.phone, body.is_active, sender_instance_id=sender)
    except ValueError as e:
        raise HTTPException(400, str(e))
    banner = None
    if sender:
        count = await hs.count_helpers_for_sender(db, sender)
        banner = hs.soft_warning_notice(count, await hs.get_soft_warning_threshold(db))
    return {**_helper_dict(h), "soft_warning": banner}


@router.post("/threshold")
async def set_threshold(body: ThresholdBody, db: AsyncSession = Depends(get_db)):
    """Set the soft-warning threshold (banner-only; never blocks)."""
    conf = await hs.set_soft_warning_threshold(db, body.threshold)
    return {"soft_warning_threshold": conf.soft_warning_threshold}


class BriefBody(BaseModel):
    sender_instance_id: str
    brief_text: str
    cold_instance_id: str        # the cold number the contacts are asked to greet
    include_suggestion: bool = True


@router.post("/generate-preview")
async def generate_preview(body: BriefBody, db: AsyncSession = Depends(get_db)):
    """V28 PART 3 — save the one-line brief and PREVIEW an AI-personalized message per contact
    of the sender (does NOT send — PART 4's engine handles slow, gated sending). Each message
    includes the contact's real name, leaks no identifier, and carries the wa.me link for the
    cold number."""
    from app.services.outreach_message import generate_outreach_batch, build_outreach_ai_fn
    from app.services.warmup_helper_engine import _resolve_cold_phone, _default_client_factory

    db.add(OutreachBrief(sender_instance_id=body.sender_instance_id, brief_text=body.brief_text))
    contacts = [{"id": str(h.id), "name": h.name, "phone": h.phone}
                for h in await hs.list_helpers_for_sender(db, body.sender_instance_id)
                if h.is_active]

    phone_digits, cold_acc = await _resolve_cold_phone(db, body.cold_instance_id, _default_client_factory)
    sender_acc = (await db.execute(
        select(Account).where(Account.instance_id == body.sender_instance_id))).scalar_one_or_none()
    forbidden = tuple(v for v in (
        body.sender_instance_id, getattr(sender_acc, "name", None),
        body.cold_instance_id, getattr(cold_acc, "name", None),
    ) if v)

    results = await generate_outreach_batch(
        brief=body.brief_text, contacts=contacts, cold_phone_digits=phone_digits,
        ai_fn=build_outreach_ai_fn(), forbidden=forbidden,
        include_suggestion=body.include_suggestion,
    )
    await db.commit()
    return {"sender_instance_id": body.sender_instance_id, "cold_instance_id": body.cold_instance_id,
            "count": len(results),
            "previews": [{"contact_id": r["contact"]["id"], "name": r["contact"]["name"],
                          "message": r["message"], "source": r["source"]} for r in results]}


@router.put("/{helper_id}")
async def edit_helper(helper_id: str, body: HelperUpdateBody, db: AsyncSession = Depends(get_db)):
    try:
        h = await hs.update_helper(db, uuid.UUID(helper_id), name=body.name,
                                   phone=body.phone, is_active=body.is_active,
                                   sender_instance_id=body.sender_instance_id)
    except ValueError as e:
        raise HTTPException(404 if "یافت نشد" in str(e) else 400, str(e))
    return _helper_dict(h)


@router.delete("/{helper_id}")
async def remove_helper(helper_id: str, db: AsyncSession = Depends(get_db)):
    ok = await hs.delete_helper(db, uuid.UUID(helper_id))
    return {"deleted": ok}


@router.post("/toggle")
async def toggle(body: ToggleBody, db: AsyncSession = Depends(get_db)):
    """Flip «کمک‌گیری از افراد واقعی برای گرم‌سازی» on/off (default OFF)."""
    conf = await hs.set_enabled(db, body.enabled)
    return {"enabled": conf.is_enabled}


@router.get("/dashboard")
async def outreach_dashboard(db: AsyncSession = Depends(get_db)):
    """V28 PART 5 — per-sender outreach dashboard: each sender's contact count (+ soft-warning
    banner when large), a per-status task summary, and every contact with its task statuses per
    cold number. Each sender is labeled so its outreach-sender role is not confused with mesh
    warm-peer status."""
    return await hs.build_outreach_dashboard(db)


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
