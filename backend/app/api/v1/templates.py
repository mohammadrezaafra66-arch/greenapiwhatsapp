import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.template import MessageTemplate

router = APIRouter(prefix="/templates", tags=["templates"])


class TemplateBody(BaseModel):
    name: str
    content: str
    category: str | None = None
    campaign_type: str = "text"


@router.get("/")
async def list_templates(category: str = None, db: AsyncSession = Depends(get_db)):
    query = select(MessageTemplate).order_by(MessageTemplate.created_at.desc())
    if category:
        query = query.where(MessageTemplate.category == category)
    result = await db.execute(query)
    rows = result.scalars().all()
    return [
        {
            "id": str(t.id),
            "name": t.name,
            "category": t.category,
            "content": t.content,
            "campaign_type": t.campaign_type,
            "use_count": t.use_count,
        }
        for t in rows
    ]


@router.post("/")
async def create_template(body: TemplateBody, db: AsyncSession = Depends(get_db)):
    t = MessageTemplate(
        name=body.name,
        content=body.content,
        category=body.category,
        campaign_type=body.campaign_type,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return {"id": str(t.id), "name": t.name}


@router.post("/{template_id}/use")
async def use_template(template_id: str, db: AsyncSession = Depends(get_db)):
    t = await db.get(MessageTemplate, uuid.UUID(template_id))
    if not t:
        raise HTTPException(404, "Template not found")
    t.use_count += 1
    await db.commit()
    return {"id": str(t.id), "content": t.content, "use_count": t.use_count}


@router.delete("/{template_id}")
async def delete_template(template_id: str, db: AsyncSession = Depends(get_db)):
    t = await db.get(MessageTemplate, uuid.UUID(template_id))
    if not t:
        raise HTTPException(404, "Template not found")
    await db.delete(t)
    await db.commit()
    return {"success": True}
