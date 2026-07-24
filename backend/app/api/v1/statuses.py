import os
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.account import Account, AccountStatus
from app.models.status_send import StatusSend
from app.services.green_api import GreenAPIClient

router = APIRouter(prefix="/statuses", tags=["statuses"])
logger = logging.getLogger("afrakala.statuses")


async def _persist_incoming(db: AsyncSession, instance_id: str, statuses: list[dict]) -> None:
    """V40 PART 1 — persist fetched incoming stories + download their media locally (best-effort).
    V40 PART 4 — then annotate each returned status with its persisted `row_id` (and `analyzed`
    flag) so the received-stories list can trigger per-story analysis. Never lets a persistence
    error break the live fetch the UI depends on."""
    try:
        from app.services.story_media import persist_incoming_statuses, normalize_status
        await persist_incoming_statuses(db, instance_id, statuses)
        await db.commit()
        await _annotate_row_ids(db, instance_id, statuses, normalize_status)
    except Exception as e:
        logger.warning("persist incoming statuses failed for %s: %s", instance_id, e)
    # V45 PART 3 — harvest each story's poster into the «مخاطبین فعال واتساپ» lead list (deduped;
    # own numbers excluded). Best-effort so it never breaks the live fetch the Stories tab depends on.
    try:
        from app.services.active_contact_harvest import harvest_status_senders
        await harvest_status_senders(db, statuses)
        await db.commit()
    except Exception as e:
        logger.warning("harvest status senders failed for %s: %s", instance_id, e)


async def _annotate_row_ids(db, instance_id, statuses, normalize_status) -> None:
    """Attach each live status's persisted row_id + analyzed flag (for the per-story analyze button)."""
    from app.models.received_status import ReceivedStatus
    from app.models.story_analysis import StoryProductAnalysis
    ids = [m for m in (normalize_status(s).get("status_message_id") for s in (statuses or [])) if m]
    if not ids:
        return
    rows = (await db.execute(
        select(ReceivedStatus.id, ReceivedStatus.status_message_id)
        .where(ReceivedStatus.instance_id == instance_id, ReceivedStatus.status_message_id.in_(ids))
    )).all()
    by_msg = {mid: rid for rid, mid in rows}
    analyzed = set((await db.execute(
        select(StoryProductAnalysis.story_id).where(StoryProductAnalysis.story_id.in_(by_msg.values()))
    )).scalars().all())
    for s in statuses:
        mid = normalize_status(s).get("status_message_id")
        rid = by_msg.get(mid)
        if rid is not None:
            s["row_id"] = str(rid)
            s["analyzed"] = rid in analyzed


class TextStatusBody(BaseModel):
    text: str
    bg_color: str = "#25D366"
    account_ids: list[str] | None = None  # None = all active accounts
    participants: list[str] | None = None  # V14 F19 — null/[] = public to all contacts


class ImageStatusBody(BaseModel):
    image_url: str
    caption: str = ""
    account_ids: list[str] | None = None
    participants: list[str] | None = None


class VoiceStatusBody(BaseModel):
    audio_url: str
    bg_color: str = "#228B22"
    account_ids: list[str] | None = None
    participants: list[str] | None = None


async def _target_accounts(account_ids, db: AsyncSession):
    if account_ids:
        accounts = []
        for aid in account_ids:
            import uuid as _uuid
            a = await db.get(Account, _uuid.UUID(aid))
            if a:
                accounts.append(a)
        return accounts
    result = await db.execute(select(Account).where(Account.status == AccountStatus.active))
    return result.scalars().all()


@router.post("/text")
async def send_text_status(body: TextStatusBody, db: AsyncSession = Depends(get_db)):
    accounts = await _target_accounts(body.account_ids, db)
    if not accounts:
        raise HTTPException(400, "No target accounts")
    results = []
    for account in accounts:
        client = GreenAPIClient(account.instance_id, account.api_token)
        try:
            msg_id = await client.send_text_status_full(body.text, body.bg_color, participants=body.participants)
            db.add(StatusSend(
                account_id=account.id, instance_id=account.instance_id,
                status_type="text", content=body.text, green_api_message_id=msg_id
            ))
            results.append({"account": account.name, "message_id": msg_id})
        except Exception as e:
            results.append({"account": account.name, "error": str(e)})
    await db.commit()
    return {"sent_to": len(results), "results": results}


@router.post("/image")
async def send_image_status(body: ImageStatusBody, db: AsyncSession = Depends(get_db)):
    accounts = await _target_accounts(body.account_ids, db)
    if not accounts:
        raise HTTPException(400, "No target accounts")
    results = []
    for account in accounts:
        client = GreenAPIClient(account.instance_id, account.api_token)
        try:
            msg_id = await client.send_media_status_full(body.image_url, caption=body.caption, participants=body.participants)
            db.add(StatusSend(
                account_id=account.id, instance_id=account.instance_id,
                status_type="image", content=body.caption, media_url=body.image_url,
                green_api_message_id=msg_id
            ))
            results.append({"account": account.name, "message_id": msg_id})
        except Exception as e:
            results.append({"account": account.name, "error": str(e)})
    await db.commit()
    return {"sent_to": len(results), "results": results}


@router.post("/voice")
async def send_voice_status(body: VoiceStatusBody, db: AsyncSession = Depends(get_db)):
    accounts = await _target_accounts(body.account_ids, db)
    if not accounts:
        raise HTTPException(400, "No target accounts")
    results = []
    for account in accounts:
        client = GreenAPIClient(account.instance_id, account.api_token)
        try:
            msg_id = await client.send_voice_status_full(body.audio_url, bg_color=body.bg_color, participants=body.participants)
            db.add(StatusSend(
                account_id=account.id, instance_id=account.instance_id,
                status_type="voice", content=body.audio_url, media_url=body.audio_url,
                green_api_message_id=msg_id
            ))
            results.append({"account": account.name, "message_id": msg_id})
        except Exception as e:
            results.append({"account": account.name, "error": str(e)})
    await db.commit()
    return {"sent_to": len(results), "results": results}


@router.delete("/{message_id}")
async def delete_status(message_id: str, account_id: str, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.delete_status(message_id)
    return {"deleted": ok}


@router.get("/history/{account_id}")
async def status_history(account_id: str, db: AsyncSession = Depends(get_db)):
    """Posted status history from Green API for this account (last 7 days)."""
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    client = GreenAPIClient(account.instance_id, account.api_token)
    try:
        statuses = await client.get_outgoing_statuses(10080)
    except Exception as e:
        msg = "دریافت تاریخچه استوری برای این حساب ممکن نیست"
        if "403" in str(e):
            msg = "این قابلیت در پلن Green API این حساب فعال نیست (خطای ۴۰۳)"
        return {"account": account.name, "statuses": [], "error": msg}
    return {"account": account.name, "statuses": statuses}


@router.get("/scheduled/{account_id}")
async def scheduled_statuses(account_id: str, db: AsyncSession = Depends(get_db)):
    """Future scheduled statuses for this account (from status_schedules)."""
    from app.models.status_schedule import StatusSchedule
    from app.utils.shamsi import to_shamsi
    result = await db.execute(
        select(StatusSchedule)
        .where(StatusSchedule.account_id == uuid.UUID(account_id))
        .where(StatusSchedule.is_active == True)
        .order_by(StatusSchedule.next_run_at.nullslast())
    )
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "status_type": s.status_type,
            "content_type": s.content_type,
            "intro_subtype": s.intro_subtype,
            "next_run_shamsi": to_shamsi(s.next_run_at),
            "days_of_week": s.days_of_week,
            "specific_dates": s.specific_dates,
            "times": s.times,
            "is_active": s.is_active,
        }
        for s in result.scalars().all()
    ]


@router.get("/incoming")
async def incoming_statuses(account_id: str | None = None, db: AsyncSession = Depends(get_db)):
    """Fetch incoming WhatsApp statuses (Green API getIncomingStatuses). Account is
    resolved from the query param, else the default account, else the first active."""
    account = None
    if account_id:
        account = await db.get(Account, uuid.UUID(account_id))
    if account is None:
        account = (await db.execute(
            select(Account).where(Account.is_default == True)
        )).scalars().first()
    if account is None:
        account = (await db.execute(
            select(Account).where(Account.status == AccountStatus.active)
        )).scalars().first()
    if account is None:
        raise HTTPException(400, "هیچ حساب فعالی برای دریافت استوری‌ها موجود نیست")
    client = GreenAPIClient(account.instance_id, account.api_token)
    try:
        statuses = await client.get_incoming_statuses()
    except Exception as e:
        # Green API returns 403 for this method on some plans/tiers — degrade
        # gracefully instead of a 500 so the UI can show a friendly message.
        msg = "دریافت استوری‌های ورودی برای این حساب ممکن نیست"
        if "403" in str(e):
            msg = "این قابلیت در پلن Green API این حساب فعال نیست (خطای ۴۰۳)"
        return {"account": account.name, "account_id": str(account.id),
                "count": 0, "statuses": [], "error": msg}
    # V40 PART 1 — persist fetched stories + download their media before the ~24h WhatsApp expiry.
    await _persist_incoming(db, account.instance_id, statuses)
    return {
        "account": account.name,
        "account_id": str(account.id),
        "count": len(statuses),
        "statuses": statuses,
    }


@router.get("/incoming/{account_id}")
async def get_incoming_statuses(account_id: str, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    client = GreenAPIClient(account.instance_id, account.api_token)
    statuses = await client.get_incoming_statuses()
    # V40 PART 1 — persist fetched stories + download their media locally.
    await _persist_incoming(db, account.instance_id, statuses)
    return {"count": len(statuses), "statuses": statuses}


@router.get("/media/{status_row_id}")
async def get_status_media(status_row_id: str, db: AsyncSession = Depends(get_db)):
    """V40 PART 1 — serve the locally-persisted story image (never the expiring WhatsApp URL)."""
    from app.models.received_status import ReceivedStatus
    row = await db.get(ReceivedStatus, uuid.UUID(status_row_id))
    if row is None or not row.local_media_path or not os.path.exists(row.local_media_path):
        raise HTTPException(404, "تصویر استوری در دسترس نیست")
    return FileResponse(row.local_media_path)


# ── V40 PART 3 — story product analysis (text via existing detector, image via vision) ──────────
def _analysis_payload(row, from_cache: bool) -> dict:
    return {
        "story_id": str(row.story_id),
        "analysis_type": row.analysis_type,
        "detected_product": row.detected_product_name,
        "matched_product_id": row.matched_product_id,
        "in_assistant": bool(row.in_assistant),
        "assistant_status": "در دستیار داریم" if row.in_assistant else "خارج از دستیار",
        "ai_confidence": row.ai_confidence,
        "raw_ai_note": row.raw_ai_note,
        "from_cache": from_cache,
    }


def _log_story_mention(db, story, analysis) -> None:
    """V40 PART 5 — a story that detected a product feeds the SAME product_mention_logs the report
    reads, tagged source='status'. Written ONCE (only on first analysis, never on a cache hit) so a
    re-run cannot inflate the mention count."""
    from app.models.reporting import ProductMentionLog
    db.add(ProductMentionLog(
        product_name=analysis.detected_product_name,
        product_id=analysis.matched_product_id,
        source="status",
        sender_phone=story.sender_phone,
        sender_name=story.sender_name or "",
        group_name=None,
        group_chat_id=None,
        instance_id=story.instance_id,
        message_text=(story.text_content or story.caption or "")[:500],
        mentioned_at=analysis.analyzed_at,
    ))


async def _analyze_story_rows(db, rows, *, vision_fn=None):
    """Analyze each persisted story once (cached), reusing ONE catalog fetch + analyzer. Returns
    the list of (row_analysis, from_cache). Shared by the per-story button and the daily bulk run.
    A newly-detected product also writes a source='status' ProductMentionLog into the existing
    report pipeline (PART 5) — only on the first analysis, so re-runs never double-count."""
    from app.services.price_service import get_products
    from app.services.story_analyzer import build_story_analyzer
    from app.services.story_analysis import analyze_story_once
    from app.services.catalog_spot_alert import get_our_phone_cores, maybe_raise_spot_alert
    from app.services.own_number_exclusion import get_excluded_cores, is_excluded_core
    products = await get_products(500)
    analyzer = build_story_analyzer(products, vision_fn=vision_fn)
    our_cores = await get_our_phone_cores(db)
    # V45 PART 2.2 — never run the (costly vision) analyzer on our OWN numbers. Defense in depth:
    # callers pre-filter, but skipping here too guarantees no own-number story can ever reach the AI
    # path or persist a story_product_analysis row, no matter how it was invoked.
    excluded_cores = await get_excluded_cores(db)
    out = []
    for story in rows:
        if is_excluded_core(getattr(story, "sender_phone", None), excluded_cores):
            continue
        analysis, from_cache = await analyze_story_once(db, story, analyzer=analyzer)
        if not from_cache and analysis.detected_product_name:
            _log_story_mention(db, story, analysis)
            # V40 PART 7 — a catalog product advertised by an outside contact → admin spot alert.
            await maybe_raise_spot_alert(
                db, contact_phone=story.sender_phone, contact_name=story.sender_name,
                product_name=analysis.detected_product_name, product_id=analysis.matched_product_id,
                source="status", instance_id=story.instance_id,
                message_text=story.text_content or story.caption, our_cores=our_cores)
        out.append((analysis, from_cache))
    return out


@router.post("/{status_row_id}/analyze")
async def analyze_story(status_row_id: str, db: AsyncSession = Depends(get_db)):
    """V40 PART 3.3 — analyze ONE persisted story (text or image) with AI, cached one-time."""
    from app.models.received_status import ReceivedStatus
    story = await db.get(ReceivedStatus, uuid.UUID(status_row_id))
    if story is None:
        raise HTTPException(404, "استوری یافت نشد")
    # V45 PART 2.2 — an own-number story is never analyzed (no vision/AI call, no persisted row).
    from app.services.own_number_exclusion import is_excluded as _is_own_excluded
    if await _is_own_excluded(db, getattr(story, "sender_phone", None)):
        return {
            "excluded": True,
            "detected_product": None,
            "assistant_status": "خارج از رصد (شمارهٔ خودی)",
            "from_cache": False,
        }
    (analysis, from_cache), = await _analyze_story_rows(db, [story])
    await db.commit()
    return _analysis_payload(analysis, from_cache)


def _analysis_row_payload(analysis, story) -> dict:
    """V40 PART 4 — one row for the «تحلیل محصولات استوری‌ها» tab. The thumbnail points at the
    LOCAL persisted image endpoint (never the expiring WhatsApp URL); None when no local media."""
    from app.utils.shamsi import to_shamsi
    has_local = bool(getattr(story, "local_media_path", None)) and bool(getattr(story, "media_downloaded", False))
    return {
        "id": str(analysis.id),
        "story_id": str(story.id),
        "contact_name": story.sender_name or story.sender_phone or "—",
        "phone": story.sender_phone,
        "status_text": story.text_content or story.caption or "",
        "thumbnail_url": f"/api/v1/statuses/media/{story.id}" if has_local else None,
        "analysis_type": analysis.analysis_type,
        "detected_product": analysis.detected_product_name,
        "in_assistant": bool(analysis.in_assistant),
        "assistant_status": "در دستیار داریم" if analysis.in_assistant else "خارج از دستیار",
        "ai_confidence": analysis.ai_confidence,
        "analyzed_shamsi": to_shamsi(analysis.analyzed_at),
    }


@router.get("/analysis")
async def story_analysis_list(account_id: str | None = None, limit: int = 200,
                              db: AsyncSession = Depends(get_db)):
    """V40 PART 4 — analyzed-story rows for the «تحلیل محصولات استوری‌ها» tab (joined story + result)."""
    from app.models.received_status import ReceivedStatus
    from app.models.story_analysis import StoryProductAnalysis
    q = (
        select(StoryProductAnalysis, ReceivedStatus)
        .join(ReceivedStatus, StoryProductAnalysis.story_id == ReceivedStatus.id)
        .order_by(StoryProductAnalysis.analyzed_at.desc())
        .limit(max(1, min(limit, 1000)))
    )
    if account_id:
        acc = await db.get(Account, uuid.UUID(account_id))
        if acc:
            q = q.where(ReceivedStatus.instance_id == acc.instance_id)
    rows = (await db.execute(q)).all()
    return {"count": len(rows),
            "items": [_analysis_row_payload(a, s) for a, s in rows]}


@router.post("/analyze-today")
async def analyze_today_statuses(account_id: str | None = None, db: AsyncSession = Depends(get_db)):
    """V40 PART 3.4 — analyze every NOT-yet-analyzed story stored today, reusing the same per-story
    analysis. Returns a short summary (analyzed, products found, outside-assistant count)."""
    from datetime import datetime as _dt
    from app.models.received_status import ReceivedStatus
    from app.models.story_analysis import StoryProductAnalysis
    start = _dt.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    q = (
        select(ReceivedStatus)
        .outerjoin(StoryProductAnalysis, StoryProductAnalysis.story_id == ReceivedStatus.id)
        .where(ReceivedStatus.created_at >= start, StoryProductAnalysis.id.is_(None))
    )
    if account_id:
        acc = await db.get(Account, uuid.UUID(account_id))
        if acc:
            q = q.where(ReceivedStatus.instance_id == acc.instance_id)
    rows = (await db.execute(q)).scalars().all()
    # V45 PART 2.2 — drop our OWN numbers before any AI/vision call. Partition here (not just inside
    # _analyze_story_rows) so the summary can report own-number exclusions honestly and separately.
    from app.services.own_number_exclusion import get_excluded_cores, is_excluded_core
    _excluded_cores = await get_excluded_cores(db)
    eligible = [r for r in rows if not is_excluded_core(getattr(r, "sender_phone", None), _excluded_cores)]
    excluded_own = len(rows) - len(eligible)
    results = await _analyze_story_rows(db, eligible)
    await db.commit()
    products_found = sum(1 for a, _ in results if a.detected_product_name)
    outside = sum(1 for a, _ in results if a.detected_product_name and not a.in_assistant)
    # Stories the AI could not be run on at all: nothing was stored for them and they stay eligible.
    # Reported separately so the summary never claims to have analyzed what it actually skipped.
    skipped = sum(1 for a, _ in results if getattr(a, "vision_failed", False))
    analyzed = len(results) - skipped
    message = (f"{analyzed} استوری تحلیل شد، {products_found} محصول شناسایی شد "
               f"({outside} خارج از دستیار).")
    if skipped:
        message += (f" ⚠️ {skipped} استوری به دلیل در دسترس نبودن سرویس هوش مصنوعی تحلیل نشد "
                    f"و برای تلاش مجدد باقی ماند.")
    if excluded_own:
        message += f" {excluded_own} استوری متعلق به شماره‌های خودی نادیده گرفته شد."
    return {
        "analyzed": analyzed,
        "products_found": products_found,
        "outside_assistant": outside,
        "skipped_ai_unavailable": skipped,
        "excluded_own_numbers": excluded_own,
        "message": message,
    }


@router.get("/{message_id}/stats")
async def status_statistics(message_id: str, db: AsyncSession = Depends(get_db)):
    """Fetch view statistics for a status by its Green API message id."""
    result = await db.execute(
        select(StatusSend).where(StatusSend.green_api_message_id == message_id)
    )
    record = result.scalars().first()
    if not record:
        raise HTTPException(404, "Status record not found")
    account = await db.get(Account, record.account_id)
    if not account:
        raise HTTPException(400, "Account not found")
    client = GreenAPIClient(account.instance_id, account.api_token)
    stats = await client.get_status_statistics(message_id)
    return stats
