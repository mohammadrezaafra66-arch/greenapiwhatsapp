import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from app.database import get_db
from app.models.contact_group import ContactGroup, ContactGroupMember
from app.models.contact import Contact

router = APIRouter(prefix="/contact-groups", tags=["contact-groups"])


class GroupBody(BaseModel):
    name: str
    description: str | None = None
    color: str = "#25D366"


class MembersBody(BaseModel):
    contact_ids: list[str]


@router.get("/")
async def list_groups(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ContactGroup).order_by(ContactGroup.created_at.desc()))
    groups = result.scalars().all()
    # member counts
    counts = dict((await db.execute(
        select(ContactGroupMember.group_id, func.count()).group_by(ContactGroupMember.group_id)
    )).all())
    return [
        {
            "id": str(g.id),
            "name": g.name,
            "description": g.description,
            "color": g.color,
            "member_count": counts.get(g.id, 0),
            "created_at": str(g.created_at),
        }
        for g in groups
    ]


@router.post("/")
async def create_group(body: GroupBody, db: AsyncSession = Depends(get_db)):
    g = ContactGroup(name=body.name, description=body.description, color=body.color)
    db.add(g)
    await db.commit()
    await db.refresh(g)
    return {"id": str(g.id), "name": g.name}


@router.put("/{group_id}")
async def update_group(group_id: str, body: GroupBody, db: AsyncSession = Depends(get_db)):
    g = await db.get(ContactGroup, uuid.UUID(group_id))
    if not g:
        raise HTTPException(404, "Group not found")
    g.name = body.name
    g.description = body.description
    g.color = body.color
    await db.commit()
    return {"id": group_id, "updated": True}


@router.delete("/{group_id}")
async def delete_group(group_id: str, db: AsyncSession = Depends(get_db)):
    g = await db.get(ContactGroup, uuid.UUID(group_id))
    if not g:
        raise HTTPException(404, "Group not found")
    await db.execute(delete(ContactGroupMember).where(ContactGroupMember.group_id == g.id))
    await db.delete(g)
    await db.commit()
    return {"deleted": True}


@router.post("/{group_id}/members")
async def add_members(group_id: str, body: MembersBody, db: AsyncSession = Depends(get_db)):
    g = await db.get(ContactGroup, uuid.UUID(group_id))
    if not g:
        raise HTTPException(404, "Group not found")
    added = 0
    for cid in body.contact_ids:
        try:
            cid_uuid = uuid.UUID(cid)
        except ValueError:
            continue
        exists = await db.execute(
            select(ContactGroupMember).where(
                ContactGroupMember.group_id == g.id,
                ContactGroupMember.contact_id == cid_uuid,
            )
        )
        if exists.scalar_one_or_none():
            continue
        db.add(ContactGroupMember(group_id=g.id, contact_id=cid_uuid))
        added += 1
    await db.commit()
    return {"added": added}


@router.delete("/{group_id}/members/{contact_id}")
async def remove_member(group_id: str, contact_id: str, db: AsyncSession = Depends(get_db)):
    await db.execute(
        delete(ContactGroupMember).where(
            ContactGroupMember.group_id == uuid.UUID(group_id),
            ContactGroupMember.contact_id == uuid.UUID(contact_id),
        )
    )
    await db.commit()
    return {"removed": True}


@router.get("/{group_id}/contacts")
async def group_contacts(group_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Contact)
        .join(ContactGroupMember, ContactGroupMember.contact_id == Contact.id)
        .where(ContactGroupMember.group_id == uuid.UUID(group_id))
    )
    contacts = result.scalars().all()
    return [
        {"id": str(c.id), "phone": c.phone, "name": c.full_name, "has_whatsapp": c.has_whatsapp}
        for c in contacts
    ]
