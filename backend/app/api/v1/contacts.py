from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from app.database import get_db
from app.models.contact import Contact
from app.services.excel_service import parse_contacts_excel
from app.services.green_api import GreenAPIClient
from app.models.inbox import Blacklist
from datetime import datetime

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("/")
async def list_contacts(
    search: str = None,
    has_whatsapp: bool = None,
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

    result = await db.execute(query.limit(200))
    contacts = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "phone": c.phone,
            "name": c.full_name,
            "has_whatsapp": c.has_whatsapp,
            "province": c.province,
        }
        for c in contacts
    ]


@router.post("/import")
async def import_from_excel(
    file: UploadFile = File(...),
    source: str = "excel_import",
    db: AsyncSession = Depends(get_db)
):
    """Import contacts from Excel file."""
    content = await file.read()
    contacts_data = parse_contacts_excel(content)

    added = 0
    skipped = 0
    for data in contacts_data:
        # Check if exists
        existing = await db.execute(
            select(Contact).where(Contact.phone == data["phone"])
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        contact = Contact(**data, source=source)
        db.add(contact)
        added += 1

    await db.commit()
    return {"added": added, "skipped": skipped, "total_in_file": len(contacts_data)}


@router.post("/{contact_id}/check-whatsapp")
async def check_whatsapp(
    contact_id: str,
    instance_id: str,
    api_token: str,
    db: AsyncSession = Depends(get_db)
):
    """Check if a contact has WhatsApp using a given account."""
    import uuid
    contact = await db.get(Contact, uuid.UUID(contact_id))
    if not contact:
        raise HTTPException(404, "Contact not found")

    client = GreenAPIClient(instance_id, api_token)
    has_wa = await client.check_whatsapp(contact.phone)

    contact.has_whatsapp = has_wa
    contact.whatsapp_checked_at = datetime.utcnow()
    await db.commit()

    return {"phone": contact.phone, "has_whatsapp": has_wa}


@router.post("/blacklist")
async def add_to_blacklist(phone: str, reason: str = None, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Blacklist).where(Blacklist.phone == phone))
    if existing.scalar_one_or_none():
        return {"status": "already_blacklisted"}

    bl = Blacklist(phone=phone, reason=reason)
    db.add(bl)

    # Also mark contact as blacklisted
    contact = await db.execute(select(Contact).where(Contact.phone == phone))
    c = contact.scalar_one_or_none()
    if c:
        c.blacklisted = True
        c.blacklist_reason = reason

    await db.commit()
    return {"status": "blacklisted", "phone": phone}
