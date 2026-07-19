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

# V29 «همکاری تیمی» sentinel so a PATCH can distinguish "omit" from "clear to null".
_UNSET = "__unset__"


class HelperBody(BaseModel):
    name: str
    phone: str
    is_active: bool = True
    sender_instance_id: str | None = None   # V28 — which of the user's accounts owns this contact
    # V29 «همکاری تیمی» — rich personnel profile (optional).
    job_title: str | None = None
    years_experience: int | None = None
    personal_benefit_note: str | None = None
    phone_secondary: str | None = None      # «شماره کاری»
    # V29 — the «همکاری تیمی» UI sends this true so NEW saves must carry a full name (first +
    # last). Default False keeps the V25/V28 API contract (single-token names) intact.
    require_full_name: bool = False


class HelperUpdateBody(BaseModel):
    name: str | None = None
    phone: str | None = None
    is_active: bool | None = None
    sender_instance_id: str | None = None
    # V29 — rich-profile patch fields (default sentinel → "leave unchanged").
    job_title: str | None = _UNSET
    years_experience: int | None = _UNSET
    personal_benefit_note: str | None = _UNSET
    phone_secondary: str | None = _UNSET
    require_full_name: bool = False


class ToggleBody(BaseModel):
    enabled: bool


class ThresholdBody(BaseModel):
    threshold: int


class SenderToggleBody(BaseModel):
    sender_instance_id: str
    enabled: bool


class ColdAssignBody(BaseModel):
    cold_instance_id: str


class CurrentBriefBody(BaseModel):
    sender_instance_id: str
    brief_text: str


def _helper_dict(h) -> dict:
    return {
        "id": str(h.id), "name": h.name, "phone": h.phone,
        "sender_instance_id": h.sender_instance_id,
        "is_active": h.is_active,
        # V29 rich profile
        "job_title": getattr(h, "job_title", None),
        "years_experience": getattr(h, "years_experience", None),
        "personal_benefit_note": getattr(h, "personal_benefit_note", None),
        "phone_secondary": getattr(h, "phone_secondary", None),
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
    disabled = await hs.enabled_sender_ids(db)   # V29 — set of explicitly-disabled senders
    return {"senders": [{
        "instance_id": a.instance_id, "name": a.name, "phone": a.phone,
        "platform": getattr(a, "platform", "whatsapp") or "whatsapp",
        "is_warm_peer": bool(getattr(a, "is_warm_peer", False)),
        "contact_count": int(counts.get(a.instance_id, 0) or 0),
        "team_enabled": a.instance_id not in disabled,   # V29 per-sender «همکاری تیمی» toggle
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
        h = await hs.add_helper(
            db, body.name, body.phone, body.is_active, sender_instance_id=sender,
            job_title=body.job_title, years_experience=body.years_experience,
            personal_benefit_note=body.personal_benefit_note, phone_secondary=body.phone_secondary,
            require_full_name=body.require_full_name,   # V29 «همکاری تیمی» UI sends true
        )
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
    # Translate the _UNSET sentinel back into the service's own _UNSET (omit → leave unchanged).
    patch = {}
    for f in ("job_title", "years_experience", "personal_benefit_note", "phone_secondary"):
        v = getattr(body, f)
        if v != _UNSET:
            patch[f] = v
    try:
        h = await hs.update_helper(db, uuid.UUID(helper_id), name=body.name,
                                   phone=body.phone, is_active=body.is_active,
                                   sender_instance_id=body.sender_instance_id,
                                   require_full_name=body.require_full_name, **patch)
    except ValueError as e:
        raise HTTPException(404 if "یافت نشد" in str(e) else 400, str(e))
    return _helper_dict(h)


# ── V29 «همکاری تیمی» — cold-account assignment (a contact's path; ceiling of 2) ──
@router.get("/{helper_id}/cold-accounts")
async def list_cold_accounts(helper_id: str, db: AsyncSession = Depends(get_db)):
    """The cold accounts a contact is assigned to (1 preferred, up to 2)."""
    cold_ids = await hs.list_cold_accounts_for_helper(db, uuid.UUID(helper_id))
    accounts = (await db.execute(select(Account))).scalars().all()
    name_by = {a.instance_id: a.name for a in accounts}
    return {"helper_id": helper_id, "max": hs.MAX_COLD_ACCOUNTS_PER_CONTACT,
            "hint": hs.COLD_ASSIGN_HINT_FA,
            "cold_accounts": [{"cold_instance_id": c, "name": name_by.get(c, c)} for c in cold_ids]}


@router.post("/{helper_id}/cold-accounts")
async def add_cold_account(helper_id: str, body: ColdAssignBody, db: AsyncSession = Depends(get_db)):
    """Assign a contact to a cold account. Rejected (400 + Persian) beyond the ceiling of 2."""
    try:
        task = await hs.assign_cold_account(db, uuid.UUID(helper_id), body.cold_instance_id)
    except ValueError as e:
        raise HTTPException(404 if "یافت نشد" in str(e) else 400, str(e))
    count = await hs.count_cold_accounts_for_helper(db, uuid.UUID(helper_id))
    return {"assigned": True, "task_id": str(task.id), "cold_instance_id": task.cold_instance_id,
            "count": count, "hint": hs.COLD_ASSIGN_HINT_FA}


@router.delete("/{helper_id}/cold-accounts/{cold_instance_id}")
async def remove_cold_account(helper_id: str, cold_instance_id: str,
                              db: AsyncSession = Depends(get_db)):
    removed = await hs.unassign_cold_account(db, uuid.UUID(helper_id), cold_instance_id)
    return {"removed": removed}


# ── V29 — per-sender «همکاری تیمی» toggle (finer than the global one) ──────────
@router.post("/sender-toggle")
async def sender_toggle(body: SenderToggleBody, db: AsyncSession = Depends(get_db)):
    """Enable/disable «همکاری تیمی» for ONE sender without touching the global master toggle."""
    cfg = await hs.set_sender_enabled(db, body.sender_instance_id, body.enabled)
    return {"sender_instance_id": cfg.sender_instance_id, "enabled": cfg.is_enabled}


@router.get("/sender-config")
async def sender_config(sender_instance_id: str, db: AsyncSession = Depends(get_db)):
    enabled = await hs.is_sender_enabled(db, sender_instance_id)
    await db.commit()
    return {"sender_instance_id": sender_instance_id, "enabled": enabled}


# ── V29 — current brief (exactly one active per sender) ───────────────────────
@router.post("/current-brief")
async def set_current_brief(body: CurrentBriefBody, db: AsyncSession = Depends(get_db)):
    """Set the sender's ACTIVE brief (append-only history + is_current flag)."""
    brief = await hs.set_current_brief(db, body.sender_instance_id, body.brief_text)
    return {"id": str(brief.id), "sender_instance_id": brief.sender_instance_id,
            "brief_text": brief.brief_text, "is_current": brief.is_current}


@router.get("/current-brief")
async def get_current_brief(sender_instance_id: str, db: AsyncSession = Depends(get_db)):
    brief = await hs.get_current_brief(db, sender_instance_id)
    if brief is None:
        return {"sender_instance_id": sender_instance_id, "brief_text": None, "is_current": None}
    return {"id": str(brief.id), "sender_instance_id": brief.sender_instance_id,
            "brief_text": brief.brief_text, "is_current": brief.is_current}


class ThreadPreviewBody(BaseModel):
    sender_instance_id: str
    cold_instance_id: str
    include_suggestion: bool = True


@router.post("/generate-thread-preview")
async def generate_thread_preview(body: ThreadPreviewBody, db: AsyncSession = Depends(get_db)):
    """V29 PART 3 — PREVIEW a thread-aware, profile-personalized ask per contact assigned to a
    cold account. Seeds from the sender's CURRENT brief, continues each thread's topic when it
    has prior steps, grounds step-0 topics in a REAL product from the live price feed, references
    the cold account only via its wa.me link, and never leaks identifiers. Does NOT send or
    advance threads (PART 7's engine does that)."""
    from app.services.outreach_message import generate_thread_ask_message, build_thread_ai_fn
    from app.services.warmup_helper_engine import _resolve_cold_phone, _default_client_factory
    from app.services import warmup_helper_thread as wt

    brief = await hs.get_current_brief(db, body.sender_instance_id)
    brief_text = brief.brief_text if brief else None
    product = await _pick_real_product()

    phone_digits, cold_acc = await _resolve_cold_phone(db, body.cold_instance_id, _default_client_factory)
    sender_acc = (await db.execute(
        select(Account).where(Account.instance_id == body.sender_instance_id))).scalar_one_or_none()
    forbidden = tuple(v for v in (
        body.sender_instance_id, getattr(sender_acc, "name", None),
        body.cold_instance_id, getattr(cold_acc, "name", None),
    ) if v)

    ai_fn = build_thread_ai_fn()
    recent: list[str] = []
    previews = []
    for h in await hs.list_helpers_for_sender(db, body.sender_instance_id):
        if not h.is_active:
            continue
        # only contacts actually assigned to this cold account
        cold_ids = await hs.list_cold_accounts_for_helper(db, h.id)
        if body.cold_instance_id not in cold_ids:
            continue
        thread = await wt.get_thread(db, h.id, body.cold_instance_id)
        step_count = int(getattr(thread, "step_count", 0) or 0)
        existing_topic = getattr(thread, "topic_summary", None)
        topic = wt.derive_topic(brief=brief_text, product=product,
                                existing_topic=existing_topic, step_count=step_count)
        # secondary work number lets ONE contact reach the SAME cold account from two numbers,
        # but this is still ONE cold account (the wa.me link is the cold number's).
        msg, source = await generate_thread_ask_message(
            brief=brief_text,
            contact={"name": h.name, "job_title": h.job_title,
                     "years_experience": h.years_experience,
                     "personal_benefit_note": h.personal_benefit_note},
            topic=topic, step_count=step_count, cold_phone_digits=[phone_digits],
            ai_fn=ai_fn, recent=recent, forbidden=forbidden,
            include_suggestion=body.include_suggestion)
        recent.append(msg.split("\n", 1)[0])
        previews.append({"contact_id": str(h.id), "name": h.name, "topic": topic,
                         "step_count": step_count, "message": msg, "source": source})
    await db.commit()
    return {"sender_instance_id": body.sender_instance_id,
            "cold_instance_id": body.cold_instance_id, "product": product,
            "count": len(previews), "previews": previews}


async def _pick_real_product() -> str | None:
    """One REAL current product name from the live Supabase price feed, for step-0 topic
    grounding. Best-effort — returns None if the feed is unavailable (topic falls back to brief)."""
    try:
        from app.services.price_service import get_products
        products = await get_products(50)
        for p in products or []:
            name = (p.get("name") if isinstance(p, dict) else None) or ""
            if name.strip():
                return name.strip()
    except Exception:
        return None
    return None


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


@router.get("/thread-alerts")
async def list_thread_alerts(only_open: bool = True, limit: int = 100,
                             db: AsyncSession = Depends(get_db)):
    """V29 PART 4 — admin alerts for safety-paused threads (forbidden/sensitive word). Read-only
    surfacing; acknowledging one does NOT auto-resume the thread (admin decides)."""
    from app.models.warmup_helpers import WarmupThreadAlert, WarmupHelper
    q = select(WarmupThreadAlert)
    if only_open:
        q = q.where(WarmupThreadAlert.acknowledged.is_(False))
    q = q.order_by(WarmupThreadAlert.created_at.desc()).limit(min(limit, 500))
    rows = (await db.execute(q)).scalars().all()
    helpers = {str(h.id): h for h in await hs.list_helpers(db)}
    return {"alerts": [{
        "id": str(a.id), "thread_id": str(a.thread_id),
        "helper_id": str(a.helper_id) if a.helper_id else None,
        "helper_name": (helpers.get(str(a.helper_id)).name if helpers.get(str(a.helper_id)) else None),
        "cold_instance_id": a.cold_instance_id, "keyword": a.keyword,
        "direction": a.direction, "message_excerpt": a.message_excerpt,
        "acknowledged": a.acknowledged,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    } for a in rows]}


@router.post("/thread-alerts/{alert_id}/ack")
async def ack_thread_alert(alert_id: str, db: AsyncSession = Depends(get_db)):
    from app.models.warmup_helpers import WarmupThreadAlert
    a = await db.get(WarmupThreadAlert, uuid.UUID(alert_id))
    if a is None:
        raise HTTPException(404, "هشدار یافت نشد")
    a.acknowledged = True
    await db.commit()
    return {"acknowledged": True}


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
