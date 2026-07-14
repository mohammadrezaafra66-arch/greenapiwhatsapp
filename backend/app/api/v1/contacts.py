import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
from app.database import get_db
from app.models.contact import Contact
from app.models.account import Account, AccountStatus
from app.models.inbox import Blacklist
from app.services.excel_service import parse_contacts_excel, normalize_phone
from app.services.green_api import GreenAPIClient

router = APIRouter(prefix="/contacts", tags=["contacts"])


class ContactCreate(BaseModel):
    phone: str
    first_name: str | None = None
    last_name: str | None = None
    province: str | None = None
    city: str | None = None


@router.get("/count")
async def count_contacts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(func.count()).select_from(Contact).where(Contact.blacklisted == False))
    return {"total": result.scalar() or 0}


@router.get("/export")
async def export_contacts(
    search: str = None,
    has_whatsapp: bool = None,
    province: str = None,
    blacklisted: bool = None,
    db: AsyncSession = Depends(get_db),
):
    """D2 — CSV export of contacts honoring the same filters as the list.
    UTF-8 BOM so Excel renders Persian correctly."""
    import csv, io
    from fastapi.responses import Response

    base = select(Contact)
    if not blacklisted:
        base = base.where(Contact.blacklisted == False)
    if search:
        base = base.where(or_(
            Contact.phone.contains(search),
            Contact.first_name.ilike(f"%{search}%"),
            Contact.last_name.ilike(f"%{search}%"),
        ))
    if has_whatsapp is not None:
        base = base.where(Contact.has_whatsapp == has_whatsapp)
    if province:
        base = base.where(Contact.province == province)

    contacts = (await db.execute(base.order_by(Contact.created_at.desc()))).scalars().all()

    buf = io.StringIO()
    buf.write("﻿")  # BOM
    w = csv.writer(buf)
    w.writerow(["phone", "first_name", "last_name", "province", "city", "has_whatsapp", "source", "group_source", "created_at"])
    for c in contacts:
        w.writerow([
            c.phone, c.first_name or "", c.last_name or "", c.province or "", c.city or "",
            "" if c.has_whatsapp is None else ("yes" if c.has_whatsapp else "no"),
            c.source or "", c.group_source or "", str(c.created_at),
        ])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=contacts.csv"},
    )


@router.post("/dedupe")
async def dedupe_contacts(db: AsyncSession = Depends(get_db)):
    """D4 — merge duplicate phone numbers, keeping the oldest row (names/source
    merged in). NOTE: contacts.phone has a UNIQUE index, so duplicates normally
    cannot accrue — this cleans up any legacy rows and is safe to run anytime."""
    dup_phones = (await db.execute(
        select(Contact.phone).group_by(Contact.phone).having(func.count() > 1)
    )).scalars().all()
    merged = 0
    for phone in dup_phones:
        rows = (await db.execute(
            select(Contact).where(Contact.phone == phone).order_by(Contact.created_at.asc())
        )).scalars().all()
        keep = rows[0]
        for extra in rows[1:]:
            if not keep.first_name and extra.first_name:
                keep.first_name = extra.first_name
            if not keep.last_name and extra.last_name:
                keep.last_name = extra.last_name
            if not keep.source and extra.source:
                keep.source = extra.source
            await db.delete(extra)
            merged += 1
    if merged:
        await db.commit()
    return {"merged": merged, "duplicate_phones": len(dup_phones)}


@router.get("/")
async def list_contacts(
    search: str = None,
    has_whatsapp: bool = None,
    province: str = None,
    blacklisted: bool = None,
    skip: int = 0,
    limit: int = 1000,  # default 1000, scale-friendly
    db: AsyncSession = Depends(get_db)
):
    skip = max(0, skip)
    # Default 1000/page; clamp to [1, 20000] as an OOM safety ceiling.
    limit = max(1, min(limit, 20000))

    base = select(Contact)
    # By default hide blacklisted; pass blacklisted=true to include everyone.
    if not blacklisted:
        base = base.where(Contact.blacklisted == False)
    if search:
        base = base.where(
            or_(
                Contact.phone.contains(search),
                Contact.first_name.ilike(f"%{search}%"),
                Contact.last_name.ilike(f"%{search}%")
            )
        )
    if has_whatsapp is not None:
        base = base.where(Contact.has_whatsapp == has_whatsapp)
    if province:
        base = base.where(Contact.province == province)

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0
    result = await db.execute(
        base.order_by(Contact.created_at.desc()).offset(skip).limit(limit)
    )
    contacts = result.scalars().all()
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "contacts": [
            {
                "id": str(c.id),
                "phone": c.phone,
                "name": c.full_name,
                "first_name": c.first_name,
                "last_name": c.last_name,
                "has_whatsapp": c.has_whatsapp,
                "province": c.province,
                "city": c.city,
                "segment": c.segment,
                "source": c.source,
                "group_source": c.group_source,
                "blacklisted": c.blacklisted,
                "created_at": str(c.created_at),
            }
            for c in contacts
        ],
    }


@router.post("/")
async def create_contact(body: ContactCreate, db: AsyncSession = Depends(get_db)):
    """Manually create a single contact. Phone is normalized (same as excel import)."""
    phone = normalize_phone(body.phone)
    if not phone:
        raise HTTPException(400, "شماره موبایل نامعتبر است")

    existing = await db.execute(select(Contact).where(Contact.phone == phone))
    if existing.scalar_one_or_none():
        raise HTTPException(409, "این شماره قبلاً ثبت شده است")

    contact = Contact(
        phone=phone,
        first_name=body.first_name or None,
        last_name=body.last_name or None,
        province=body.province or None,
        city=body.city or None,
        source="manual",
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return {
        "id": str(contact.id),
        "phone": contact.phone,
        "name": contact.full_name,
        "first_name": contact.first_name,
        "last_name": contact.last_name,
        "province": contact.province,
        "city": contact.city,
    }


@router.post("/import")
async def import_from_excel(
    file: UploadFile = File(...),
    source: str = "excel_import",
    db: AsyncSession = Depends(get_db)
):
    content = await file.read()
    contacts_data = parse_contacts_excel(content)

    added = 0
    skipped = 0
    for data in contacts_data:
        existing = await db.execute(select(Contact).where(Contact.phone == data["phone"]))
        if existing.scalar_one_or_none():
            skipped += 1
            continue
        contact = Contact(**data, source=source)
        db.add(contact)
        added += 1

    await db.commit()
    return {"added": added, "skipped": skipped, "total_in_file": len(contacts_data)}


@router.post("/check-bulk")
async def check_bulk(contact_ids: list[str], db: AsyncSession = Depends(get_db)):
    """Batch checkWhatsapp using the first active account."""
    acc_result = await db.execute(select(Account).where(Account.status == AccountStatus.active))
    account = acc_result.scalars().first()
    if not account:
        raise HTTPException(400, "No active account available")

    client = GreenAPIClient(account.instance_id, account.api_token)
    results = []
    for cid in contact_ids:
        contact = await db.get(Contact, uuid.UUID(cid))
        if not contact:
            continue
        try:
            has_wa = await client.check_whatsapp(contact.phone)
            contact.has_whatsapp = has_wa
            contact.whatsapp_checked_at = datetime.utcnow()
            results.append({"id": cid, "phone": contact.phone, "has_whatsapp": has_wa})
        except Exception as e:
            results.append({"id": cid, "phone": contact.phone, "error": str(e)})
    await db.commit()
    return {"checked": len(results), "results": results}


@router.get("/{contact_id}/history")
async def contact_history(contact_id: str, count: int = 50, db: AsyncSession = Depends(get_db)):
    """Fetch WhatsApp chat history for a contact via the first active account."""
    contact = await db.get(Contact, uuid.UUID(contact_id))
    if not contact:
        raise HTTPException(404, "Contact not found")
    acc_result = await db.execute(select(Account).where(Account.status == AccountStatus.active))
    account = acc_result.scalars().first()
    if not account:
        raise HTTPException(400, "No active account available")
    client = GreenAPIClient(account.instance_id, account.api_token)
    history = await client.get_chat_history(contact.phone, count)
    return {"phone": contact.phone, "history": history}


@router.post("/{contact_id}/send-file")
async def send_file_to_contact(
    contact_id: str,
    file: UploadFile = File(...),
    caption: str = Form(""),
    db: AsyncSession = Depends(get_db)
):
    """Send an arbitrary file directly to a contact via multipart upload (no URL hosting needed)."""
    contact = await db.get(Contact, uuid.UUID(contact_id))
    if not contact:
        raise HTTPException(404, "Contact not found")
    acc_result = await db.execute(select(Account).where(Account.status == AccountStatus.active))
    account = acc_result.scalars().first()
    if not account:
        raise HTTPException(400, "No active account available")

    client = GreenAPIClient(account.instance_id, account.api_token)
    content = await file.read()
    msg_id = await client.send_file_upload(contact.phone, content, file.filename, caption)
    return {"sent": bool(msg_id), "message_id": msg_id, "via": account.name}


@router.post("/{contact_id}/archive")
async def archive_contact_chat(contact_id: str, db: AsyncSession = Depends(get_db)):
    contact = await db.get(Contact, uuid.UUID(contact_id))
    if not contact:
        raise HTTPException(404, "Contact not found")
    acc_result = await db.execute(select(Account).where(Account.status == AccountStatus.active))
    account = acc_result.scalars().first()
    if not account:
        raise HTTPException(400, "No active account available")
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.archive_chat(contact.phone)
    return {"archived": ok}


@router.post("/{contact_id}/unarchive")
async def unarchive_contact_chat(contact_id: str, db: AsyncSession = Depends(get_db)):
    contact = await db.get(Contact, uuid.UUID(contact_id))
    if not contact:
        raise HTTPException(404, "Contact not found")
    acc_result = await db.execute(select(Account).where(Account.status == AccountStatus.active))
    account = acc_result.scalars().first()
    if not account:
        raise HTTPException(400, "No active account available")
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.unarchive_chat(contact.phone)
    return {"unarchived": ok}


@router.post("/{contact_id}/blacklist")
async def blacklist_contact(contact_id: str, reason: str = None, db: AsyncSession = Depends(get_db)):
    contact = await db.get(Contact, uuid.UUID(contact_id))
    if not contact:
        raise HTTPException(404, "Contact not found")
    contact.blacklisted = True
    contact.blacklist_reason = reason
    existing = await db.execute(select(Blacklist).where(Blacklist.phone == contact.phone))
    if not existing.scalar_one_or_none():
        db.add(Blacklist(phone=contact.phone, reason=reason))
    await db.commit()
    return {"status": "blacklisted", "phone": contact.phone}


@router.post("/{contact_id}/disappearing")
async def set_disappearing_messages(contact_id: str, ephemeral: int = 0, db: AsyncSession = Depends(get_db)):
    """Set disappearing messages timer for a contact's chat.
    ephemeral: 0=off, 86400=24h, 604800=7days, 7776000=90days"""
    contact = await db.get(Contact, uuid.UUID(contact_id))
    if not contact:
        raise HTTPException(404, "Contact not found")
    acc_result = await db.execute(select(Account).where(Account.status == AccountStatus.active))
    account = acc_result.scalars().first()
    if not account:
        raise HTTPException(400, "No active account")

    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.set_disappearing_chat(contact.phone, ephemeral)

    if ok:
        from app.models.wa_extras import DisappearingChatSetting
        existing = await db.execute(
            select(DisappearingChatSetting).where(
                DisappearingChatSetting.account_id == account.id,
                DisappearingChatSetting.chat_id == contact.chat_id,
            )
        )
        setting = existing.scalar_one_or_none()
        if setting:
            setting.ephemeral = ephemeral
        else:
            db.add(DisappearingChatSetting(account_id=account.id, chat_id=contact.chat_id, ephemeral=ephemeral))
        await db.commit()

    labels = {0: "خاموش", 86400: "۲۴ ساعت", 604800: "۷ روز", 7776000: "۹۰ روز"}
    return {"set": ok, "ephemeral": ephemeral, "label": labels.get(ephemeral, str(ephemeral))}


@router.post("/{contact_id}/add-to-phonebook")
async def add_contact_to_phonebook(contact_id: str, db: AsyncSession = Depends(get_db)):
    """Add a contact to the WhatsApp phonebook of the first active account."""
    contact = await db.get(Contact, uuid.UUID(contact_id))
    if not contact:
        raise HTTPException(404, "Contact not found")
    acc_result = await db.execute(select(Account).where(Account.status == AccountStatus.active))
    account = acc_result.scalars().first()
    if not account:
        raise HTTPException(400, "No active account")
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.add_contact(contact.phone, contact.first_name or "", contact.last_name or "")
    return {"added": ok, "phone": contact.phone, "name": contact.full_name}


@router.put("/{contact_id}/phonebook")
async def edit_contact_in_phonebook(contact_id: str, first_name: str, last_name: str = "", db: AsyncSession = Depends(get_db)):
    """Edit a contact in the WhatsApp phonebook (and mirror the change locally)."""
    contact = await db.get(Contact, uuid.UUID(contact_id))
    if not contact:
        raise HTTPException(404, "Contact not found")
    acc_result = await db.execute(select(Account).where(Account.status == AccountStatus.active))
    account = acc_result.scalars().first()
    if not account:
        raise HTTPException(400, "No active account")
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.edit_contact(contact.phone, first_name, last_name)
    if ok:
        contact.first_name = first_name
        contact.last_name = last_name
        await db.commit()
    return {"updated": ok, "phone": contact.phone}


# ── V14 F18 — full contact info (getContactInfo, cached 24h) ────────────────
@router.get("/{phone}/info")
async def contact_info(phone: str, refresh: bool = False, db: AsyncSession = Depends(get_db)):
    """Rich contact profile for lead qualification (avatar/name/isBusiness/products…).
    Served from a 24h cache; getContactInfo is only 1/sec so we never hammer it."""
    from datetime import timedelta
    from app.models.messaging import ContactInfoCache
    norm = normalize_phone(phone)
    chat_id = f"{norm}@c.us"
    cached = await db.get(ContactInfoCache, chat_id)
    fresh = cached and cached.fetched_at and (datetime.utcnow() - cached.fetched_at) < timedelta(hours=24)
    if cached and fresh and not refresh:
        return {"chat_id": chat_id, "cached": True, "info": cached.payload}

    acc = (await db.execute(
        select(Account).where(Account.is_default.is_(True), Account.status == AccountStatus.active)
    )).scalars().first()
    if not acc:
        acc = (await db.execute(
            select(Account).where(Account.status == AccountStatus.active)
        )).scalars().first()
    if not acc:
        if cached:
            return {"chat_id": chat_id, "cached": True, "info": cached.payload}
        raise HTTPException(400, "هیچ حساب متصلی برای دریافت اطلاعات نیست")

    try:
        info = await GreenAPIClient(acc.instance_id, acc.api_token).get_contact_info_raw(chat_id)
    except Exception:
        if cached:  # serve stale on error
            return {"chat_id": chat_id, "cached": True, "info": cached.payload}
        raise HTTPException(502, "دریافت اطلاعات مخاطب ناموفق بود")

    if cached:
        cached.payload = info
        cached.fetched_at = datetime.utcnow()
    else:
        db.add(ContactInfoCache(chat_id=chat_id, payload=info, fetched_at=datetime.utcnow()))
    await db.commit()
    return {"chat_id": chat_id, "cached": False, "info": info}


@router.delete("/{contact_id}")
async def delete_contact(contact_id: str, db: AsyncSession = Depends(get_db)):
    contact = await db.get(Contact, uuid.UUID(contact_id))
    if not contact:
        raise HTTPException(404, "Contact not found")
    await db.delete(contact)
    await db.commit()
    return {"success": True}
