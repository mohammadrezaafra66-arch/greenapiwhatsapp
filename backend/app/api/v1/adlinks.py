"""V16 PART 3 — advertising links CRUD."""
import re
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.advertising import AdvertisingLink
from app.services.adlinks import VALID_TYPES

router = APIRouter(prefix="/advertising-links", tags=["advertising-links"])

_URL_RE = re.compile(r"^https?://.+", re.IGNORECASE)


class LinkBody(BaseModel):
    url: str
    title: str
    link_type: str = "other"
    weight: int = 5
    is_active: bool = True


def _validate(body: LinkBody):
    if not _URL_RE.match((body.url or "").strip()):
        raise HTTPException(400, "آدرس نامعتبر است — باید با http:// یا https:// شروع شود")
    if not (body.title or "").strip():
        raise HTTPException(400, "عنوان لازم است")
    if not (1 <= int(body.weight) <= 10):
        raise HTTPException(400, "وزن باید بین ۱ تا ۱۰ باشد")
    if body.link_type not in VALID_TYPES:
        raise HTTPException(400, "نوع لینک نامعتبر است")


def _serialize(r: AdvertisingLink) -> dict:
    return {"id": str(r.id), "url": r.url, "title": r.title, "link_type": r.link_type,
            "weight": r.weight, "is_active": r.is_active}


@router.get("/")
async def list_links(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(AdvertisingLink).order_by(AdvertisingLink.created_at.desc()))).scalars().all()
    return [_serialize(r) for r in rows]


@router.post("/")
async def create_link(body: LinkBody, db: AsyncSession = Depends(get_db)):
    _validate(body)
    link = AdvertisingLink(url=body.url.strip(), title=body.title.strip(),
                           link_type=body.link_type, weight=int(body.weight), is_active=body.is_active)
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return _serialize(link)


@router.put("/{link_id}")
async def update_link(link_id: str, body: LinkBody, db: AsyncSession = Depends(get_db)):
    _validate(body)
    link = await db.get(AdvertisingLink, uuid.UUID(link_id))
    if not link:
        raise HTTPException(404, "لینک یافت نشد")
    link.url = body.url.strip()
    link.title = body.title.strip()
    link.link_type = body.link_type
    link.weight = int(body.weight)
    link.is_active = body.is_active
    await db.commit()
    return _serialize(link)


@router.post("/{link_id}/toggle")
async def toggle_link(link_id: str, db: AsyncSession = Depends(get_db)):
    link = await db.get(AdvertisingLink, uuid.UUID(link_id))
    if not link:
        raise HTTPException(404, "لینک یافت نشد")
    link.is_active = not link.is_active
    await db.commit()
    return {"id": link_id, "is_active": link.is_active}


@router.delete("/{link_id}")
async def delete_link(link_id: str, db: AsyncSession = Depends(get_db)):
    link = await db.get(AdvertisingLink, uuid.UUID(link_id))
    if link:
        await db.delete(link)
        await db.commit()
    return {"ok": True}
