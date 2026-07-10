import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.join_links import GroupJoinLink, AccountJoinStatus
from app.models.account import Account

router = APIRouter(prefix="/join-links", tags=["join-links"])


class BulkLink(BaseModel):
    name: str | None = ""
    invite_link: str
    link_type: str | None = "group"


@router.get("/")
async def list_links(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GroupJoinLink).where(GroupJoinLink.is_active == True).order_by(GroupJoinLink.created_at.desc()))
    return [
        {"id": str(l.id), "name": l.name, "invite_link": l.invite_link, "link_type": l.link_type, "created_at": str(l.created_at)}
        for l in result.scalars().all()
    ]


@router.post("/")
async def add_link(name: str, invite_link: str, link_type: str = "group", db: AsyncSession = Depends(get_db)):
    link = GroupJoinLink(name=name, invite_link=invite_link, link_type=link_type)
    db.add(link)
    await db.commit()
    return {"id": str(link.id)}


@router.post("/bulk")
async def add_links_bulk(links: list[BulkLink], db: AsyncSession = Depends(get_db)):
    """Add multiple links at once. Each: {name, invite_link, link_type}."""
    added = 0
    for l in links:
        if l.invite_link and l.invite_link.strip():
            db.add(GroupJoinLink(name=l.name or "", invite_link=l.invite_link.strip(), link_type=l.link_type or "group"))
            added += 1
    await db.commit()
    return {"added": added}


@router.delete("/{link_id}")
async def delete_link(link_id: str, db: AsyncSession = Depends(get_db)):
    link = await db.get(GroupJoinLink, uuid.UUID(link_id))
    if link:
        await db.delete(link)
        await db.commit()
    return {"deleted": True}


@router.get("/status")
async def join_status(db: AsyncSession = Depends(get_db)):
    """Per-account × per-link join status matrix."""
    rows = (await db.execute(select(AccountJoinStatus))).scalars().all()
    accs = {a.id: a.name for a in (await db.execute(select(Account))).scalars().all()}
    links = {l.id: l.name or l.invite_link for l in (await db.execute(select(GroupJoinLink))).scalars().all()}
    return [
        {
            "account_id": str(r.account_id), "account": accs.get(r.account_id, "?"),
            "link_id": str(r.link_id), "link": links.get(r.link_id, "?"),
            "status": r.status, "error": r.error,
            "joined_at": str(r.joined_at) if r.joined_at else None,
        }
        for r in rows
    ]


@router.post("/join-all/{account_id}")
async def join_all_links(account_id: str, db: AsyncSession = Depends(get_db)):
    """Attempt to join all registered links with this account (background task)."""
    from app.workers.tasks import task_join_all_links
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    result = await db.execute(select(GroupJoinLink).where(GroupJoinLink.is_active == True))
    links = [(str(l.id), l.invite_link, l.name or "") for l in result.scalars().all()]
    task = task_join_all_links.delay(str(account.id), account.instance_id, account.api_token, links)
    return {"task_id": task.id, "links_to_join": len(links)}
