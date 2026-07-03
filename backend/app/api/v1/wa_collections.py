import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from app.database import get_db
from app.models.contact_group import WaGroupCollection, WaGroupCollectionMember

router = APIRouter(prefix="/wa-collections", tags=["wa-collections"])


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
