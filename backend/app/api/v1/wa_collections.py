import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from app.database import get_db
from app.models.contact_group import WaGroupCollection, WaGroupCollectionMember
from app.models.group import WhatsAppGroup

router = APIRouter(prefix="/wa-collections", tags=["wa-collections"])


@router.get("/available-groups/{account_id}")
async def get_available_groups(account_id: str, db: AsyncSession = Depends(get_db)):
    """Get all WhatsApp groups synced from this account — for use in WA collections."""
    result = await db.execute(
        select(WhatsAppGroup)
        .where(WhatsAppGroup.account_id == uuid.UUID(account_id))
        .order_by(WhatsAppGroup.name)
    )
    groups = result.scalars().all()
    return [
        {
            "id": str(g.id),
            "group_chat_id": g.green_group_id,
            "name": g.name,
            "member_count": g.member_count,
        }
        for g in groups
    ]


class CollectionBody(BaseModel):
    name: str
    description: str | None = None


class GroupBody(BaseModel):
    group_chat_id: str
    group_name: str | None = None


@router.get("/")
async def list_collections(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WaGroupCollection).order_by(WaGroupCollection.created_at.desc()))
    collections = result.scalars().all()
    counts = dict((await db.execute(
        select(WaGroupCollectionMember.collection_id, func.count()).group_by(WaGroupCollectionMember.collection_id)
    )).all())
    return [
        {
            "id": str(c.id),
            "name": c.name,
            "description": c.description,
            "group_count": counts.get(c.id, 0),
            "created_at": str(c.created_at),
        }
        for c in collections
    ]


@router.post("/")
async def create_collection(body: CollectionBody, db: AsyncSession = Depends(get_db)):
    c = WaGroupCollection(name=body.name, description=body.description)
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return {"id": str(c.id), "name": c.name}


@router.put("/{collection_id}")
async def update_collection(collection_id: str, body: CollectionBody, db: AsyncSession = Depends(get_db)):
    c = await db.get(WaGroupCollection, uuid.UUID(collection_id))
    if not c:
        raise HTTPException(404, "Collection not found")
    c.name = body.name
    c.description = body.description
    await db.commit()
    return {"id": collection_id, "updated": True}


@router.delete("/{collection_id}")
async def delete_collection(collection_id: str, db: AsyncSession = Depends(get_db)):
    c = await db.get(WaGroupCollection, uuid.UUID(collection_id))
    if not c:
        raise HTTPException(404, "Collection not found")
    await db.execute(delete(WaGroupCollectionMember).where(WaGroupCollectionMember.collection_id == c.id))
    await db.delete(c)
    await db.commit()
    return {"deleted": True}


@router.post("/{collection_id}/groups")
async def add_group(collection_id: str, body: GroupBody, db: AsyncSession = Depends(get_db)):
    c = await db.get(WaGroupCollection, uuid.UUID(collection_id))
    if not c:
        raise HTTPException(404, "Collection not found")
    exists = await db.execute(
        select(WaGroupCollectionMember).where(
            WaGroupCollectionMember.collection_id == c.id,
            WaGroupCollectionMember.group_chat_id == body.group_chat_id,
        )
    )
    if exists.scalar_one_or_none():
        return {"added": False, "reason": "already in collection"}
    db.add(WaGroupCollectionMember(
        collection_id=c.id, group_chat_id=body.group_chat_id, group_name=body.group_name
    ))
    await db.commit()
    return {"added": True}


@router.delete("/{collection_id}/groups/{group_chat_id:path}")
async def remove_group(collection_id: str, group_chat_id: str, db: AsyncSession = Depends(get_db)):
    await db.execute(
        delete(WaGroupCollectionMember).where(
            WaGroupCollectionMember.collection_id == uuid.UUID(collection_id),
            WaGroupCollectionMember.group_chat_id == group_chat_id,
        )
    )
    await db.commit()
    return {"removed": True}


@router.get("/{collection_id}/groups")
async def collection_groups(collection_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(WaGroupCollectionMember).where(
            WaGroupCollectionMember.collection_id == uuid.UUID(collection_id)
        )
    )
    members = result.scalars().all()
    return [
        {"id": str(m.id), "group_chat_id": m.group_chat_id, "group_name": m.group_name}
        for m in members
    ]


@router.post("/{collection_id}/import-all-members")
async def import_all_members(collection_id: str, db: AsyncSession = Depends(get_db)):
    """Extract members from every group in the collection, merge + dedupe phone
    numbers, and bulk-insert them into contacts (tagged with the collection)."""
    col = await db.get(WaGroupCollection, uuid.UUID(collection_id))
    if not col:
        raise HTTPException(404, "Collection not found")

    members = (await db.execute(
        select(WaGroupCollectionMember).where(WaGroupCollectionMember.collection_id == col.id)
    )).scalars().all()
    if not members:
        raise HTTPException(400, "این مجموعه هیچ گروهی ندارد")

    from app.models.account import Account
    from app.models.contact import Contact
    from app.services.green_api import GreenAPIClient
    from app.services.excel_service import normalize_phone

    all_phones = set()
    groups_ok = 0
    groups_failed = 0
    account_cache = {}

    for m in members:
        grp = (await db.execute(
            select(WhatsAppGroup).where(WhatsAppGroup.green_group_id == m.group_chat_id)
        )).scalar_one_or_none()
        if not grp:
            groups_failed += 1
            continue
        if grp.account_id not in account_cache:
            account_cache[grp.account_id] = await db.get(Account, grp.account_id)
        account = account_cache[grp.account_id]
        if not account:
            groups_failed += 1
            continue
        try:
            client = GreenAPIClient(account.instance_id, account.api_token)
            data = await client.get_group_data(grp.green_group_id)
            for p in (data.get("participants", []) or []):
                phone = str(p.get("id", "")).split("@")[0]  # strip @c.us
                if phone and phone.isdigit():
                    all_phones.add(phone)
            groups_ok += 1
        except Exception as e:
            groups_failed += 1
            print(f"[CollectionImport] group {m.group_chat_id} error: {e}")

    # Bulk-insert merged phones into contacts (dedupe against existing + invalid).
    source = f"collection_import_{col.name}"[:200]
    added = 0
    skipped = 0
    invalid = 0
    added_set = set()
    for raw in all_phones:
        phone = normalize_phone(raw)
        if not phone:
            invalid += 1
            continue
        if phone in added_set:
            continue
        existing = (await db.execute(select(Contact).where(Contact.phone == phone))).scalar_one_or_none()
        if existing:
            skipped += 1
            continue
        db.add(Contact(phone=phone, source=source))
        added_set.add(phone)
        added += 1
    await db.commit()

    return {
        "collection": col.name,
        "groups_total": len(members),
        "groups_ok": groups_ok,
        "groups_failed": groups_failed,
        "unique_phones": len(all_phones),
        "added": added,
        "skipped": skipped,
        "invalid": invalid,
        "source": source,
    }
