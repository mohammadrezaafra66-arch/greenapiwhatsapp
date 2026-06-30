import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from app.database import get_db
from app.models.contact import Contact
from app.models.account import Account, AccountStatus
from app.models.inbox import Blacklist
from app.services.excel_service import parse_contacts_excel
from app.services.green_api import GreenAPIClient

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("/")
async def list_contacts(
    search: str = None,
    has_whatsapp: bool = None,
    province: str = None,
    db: AsyncSession = Depends(get_db)
):
    query = select(Contact).where(Contact.blacklisted == False)
    if search:
        query = query.where(
            or_(
                Contact.phone.contains(search),
                Contact.first_name.ilike(f"%{search}%"),
                Contact.last_name.ilike(f"%{search}%")
            )
        )
    if has_whatsapp is not None:
        query = query.where(Contact.has_whatsapp == has_whatsapp)
    if province:
        query = query.where(Contact.province == province)

    result = await db.execute(query.limit(500))
    contacts = result.scalars().all()
    return [
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
        }
        for c in contacts
    ]


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


@router.delete("/{contact_id}")
async def delete_contact(contact_id: str, db: AsyncSession = Depends(get_db)):
    contact = await db.get(Contact, uuid.UUID(contact_id))
    if not contact:
        raise HTTPException(404, "Contact not found")
    await db.delete(contact)
    await db.commit()
    return {"success": True}
