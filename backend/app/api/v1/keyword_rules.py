import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.keyword_rule import KeywordRule

router = APIRouter(prefix="/keyword-rules", tags=["keyword-rules"])


class RuleCreate(BaseModel):
    keyword: str
    reply_message: str
    match_type: str = "contains"   # exact | contains
    scope: str = "both"            # pv | group | both
    account_id: str | None = None  # None = applies to all accounts
    is_active: bool = True


@router.get("/")
async def list_rules(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(KeywordRule).order_by(KeywordRule.created_at))
    rules = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "keyword": r.keyword,
            "reply_message": r.reply_message,
            "match_type": r.match_type,
            "scope": r.scope,
            "account_id": str(r.account_id) if r.account_id else None,
            "is_active": r.is_active,
            "use_count": r.use_count,
        }
        for r in rules
    ]


@router.post("/")
async def create_rule(body: RuleCreate, db: AsyncSession = Depends(get_db)):
    rule = KeywordRule(
        keyword=body.keyword,
        reply_message=body.reply_message,
        match_type=body.match_type,
        scope=body.scope,
        account_id=uuid.UUID(body.account_id) if body.account_id else None,
        is_active=body.is_active,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return {"id": str(rule.id), "keyword": rule.keyword}


@router.put("/{rule_id}")
async def update_rule(rule_id: str, body: RuleCreate, db: AsyncSession = Depends(get_db)):
    rule = await db.get(KeywordRule, uuid.UUID(rule_id))
    if not rule:
        raise HTTPException(404, "Rule not found")
    rule.keyword = body.keyword
    rule.reply_message = body.reply_message
    rule.match_type = body.match_type
    rule.scope = body.scope
    rule.is_active = body.is_active
    rule.account_id = uuid.UUID(body.account_id) if body.account_id else None
    await db.commit()
    return {"id": rule_id, "updated": True}


@router.delete("/{rule_id}")
async def delete_rule(rule_id: str, db: AsyncSession = Depends(get_db)):
    rule = await db.get(KeywordRule, uuid.UUID(rule_id))
    if not rule:
        raise HTTPException(404, "Rule not found")
    await db.delete(rule)
    await db.commit()
    return {"deleted": True}
