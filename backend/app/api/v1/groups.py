import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.group import WhatsAppGroup
from app.models.account import Account, AccountStatus
from app.services.green_api import GreenAPIClient

router = APIRouter(prefix="/groups", tags=["groups"])


class GroupCreateBody(BaseModel):
    account_id: str
    name: str
    description: str | None = None
    phones: list[str] = []


class MembersBody(BaseModel):
    phones: list[str]


class GroupSendBody(BaseModel):
    message: str


async def _client_for_group(group: WhatsAppGroup, db: AsyncSession) -> GreenAPIClient:
    account = await db.get(Account, group.account_id)
    if not account:
        raise HTTPException(400, "Owning account not found")
    return GreenAPIClient(account.instance_id, account.api_token)


@router.get("/")
async def list_groups(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WhatsAppGroup).order_by(WhatsAppGroup.created_at.desc()))
    groups = result.scalars().all()
    return [
        {
            "id": str(g.id),
            "green_group_id": g.green_group_id,
            "account_id": str(g.account_id),
            "name": g.name,
            "description": g.description,
            "member_count": g.member_count,
        }
        for g in groups
    ]


@router.post("/")
async def create_group(body: GroupCreateBody, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, uuid.UUID(body.account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    client = GreenAPIClient(account.instance_id, account.api_token)

    green_group_id = None
    if body.phones:
        try:
            result = await client.create_group(body.name, body.phones)
            green_group_id = result.get("chatId") or result.get("groupId")
        except Exception as e:
            raise HTTPException(502, f"Green API create_group failed: {e}")

    group = WhatsAppGroup(
        green_group_id=green_group_id,
        account_id=account.id,
        name=body.name,
        description=body.description,
        member_count=len(body.phones),
    )
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return {"id": str(group.id), "green_group_id": group.green_group_id, "name": group.name}


@router.post("/{group_id}/members")
async def add_members(group_id: str, body: MembersBody, db: AsyncSession = Depends(get_db)):
    group = await db.get(WhatsAppGroup, uuid.UUID(group_id))
    if not group:
        raise HTTPException(404, "Group not found")
    if not group.green_group_id:
        raise HTTPException(400, "Group has no Green API group id")
    client = await _client_for_group(group, db)
    added = 0
    for phone in body.phones:
        try:
            await client.add_group_participant(group.green_group_id, phone)
            added += 1
        except Exception:
            pass
    group.member_count += added
    await db.commit()
    return {"added": added}


@router.delete("/{group_id}/members/{phone}")
async def remove_member(group_id: str, phone: str, db: AsyncSession = Depends(get_db)):
    group = await db.get(WhatsAppGroup, uuid.UUID(group_id))
    if not group:
        raise HTTPException(404, "Group not found")
    if not group.green_group_id:
        raise HTTPException(400, "Group has no Green API group id")
    client = await _client_for_group(group, db)
    await client.remove_group_participant(group.green_group_id, phone)
    if group.member_count > 0:
        group.member_count -= 1
    await db.commit()
    return {"success": True}


@router.post("/{group_id}/send")
async def send_to_group(group_id: str, body: GroupSendBody, db: AsyncSession = Depends(get_db)):
    group = await db.get(WhatsAppGroup, uuid.UUID(group_id))
    if not group:
        raise HTTPException(404, "Group not found")
    if not group.green_group_id:
        raise HTTPException(400, "Group has no Green API group id")
    client = await _client_for_group(group, db)
    msg_id = await client.send_group_message(group.green_group_id, body.message)
    return {"sent": bool(msg_id), "message_id": msg_id}


@router.put("/{group_id}/name")
async def update_group_name(group_id: str, name: str, account_id: str, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.update_group_name(group_id, name)
    return {"updated": ok}


@router.post("/{group_id}/admin/{phone}")
async def set_group_admin(group_id: str, phone: str, account_id: str, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.set_group_admin(group_id, phone)
    return {"set_admin": ok}


@router.delete("/{group_id}/admin/{phone}")
async def remove_group_admin(group_id: str, phone: str, account_id: str, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.remove_group_admin(group_id, phone)
    return {"removed_admin": ok}


@router.post("/{group_id}/leave")
async def leave_group(group_id: str, account_id: str, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    client = GreenAPIClient(account.instance_id, account.api_token)
    ok = await client.leave_group(group_id)
    return {"left": ok}


@router.post("/sync/{account_id}")
async def sync_groups_from_wa(account_id: str, db: AsyncSession = Depends(get_db)):
    """Fetch all WhatsApp groups this account is member of and save to DB."""
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")

    client = GreenAPIClient(account.instance_id, account.api_token)
    try:
        chats = await client.get_chats()
    except Exception as e:
        raise HTTPException(502, f"Green API error: {e}")

    saved = 0
    for chat in chats:
        chat_id = chat.get("id", "")
        if "@g.us" not in chat_id:
            continue  # skip PV chats

        existing = await db.execute(
            select(WhatsAppGroup).where(WhatsAppGroup.green_group_id == chat_id)
        )
        if not existing.scalar_one_or_none():
            grp = WhatsAppGroup(
                green_group_id=chat_id,
                account_id=uuid.UUID(account_id),
                name=chat.get("name", chat_id),
                member_count=chat.get("participantsCount", 0)
            )
            db.add(grp)
            saved += 1

    await db.commit()
    return {"synced": saved, "total_chats": len(chats)}


@router.get("/{group_id}/info")
async def group_info(group_id: str, db: AsyncSession = Depends(get_db)):
    group = await db.get(WhatsAppGroup, uuid.UUID(group_id))
    if not group:
        raise HTTPException(404, "Group not found")
    if not group.green_group_id:
        raise HTTPException(400, "Group has no Green API group id")
    client = await _client_for_group(group, db)
    data = await client.get_group_data(group.green_group_id)
    return data
