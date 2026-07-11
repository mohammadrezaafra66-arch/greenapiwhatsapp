import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.ai_key import AIKey

router = APIRouter(prefix="/ai-keys", tags=["ai-keys"])

VALID_PROVIDERS = ("openai", "deepseek", "gemini")


def _mask(key: str) -> str:
    if not key or len(key) <= 8:
        return "****"
    return key[:6] + "..." + key[-4:]


def _serialize(k: AIKey) -> dict:
    return {
        "id": str(k.id),
        "provider": k.provider,
        "api_key_masked": _mask(k.api_key),
        "label": k.label,
        "is_active": k.is_active,
        "status": k.status,
        "last_checked_at": str(k.last_checked_at) if k.last_checked_at else None,
        "last_error": k.last_error,
        "success_count": k.success_count,
        "fail_count": k.fail_count,
        "rate_limited_until": str(k.rate_limited_until) if k.rate_limited_until else None,
    }


class AIKeyCreate(BaseModel):
    provider: str
    api_key: str
    label: str | None = None


class AIKeyUpdate(BaseModel):
    api_key: str | None = None
    label: str | None = None
    is_active: bool | None = None


@router.get("/")
async def list_keys(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AIKey).order_by(AIKey.created_at.desc()))
    return [_serialize(k) for k in result.scalars().all()]


@router.post("/")
async def create_key(body: AIKeyCreate, db: AsyncSession = Depends(get_db)):
    if body.provider not in VALID_PROVIDERS:
        raise HTTPException(400, "provider must be openai, deepseek, or gemini")
    if not body.api_key.strip():
        raise HTTPException(400, "api_key is required")
    key = AIKey(provider=body.provider, api_key=body.api_key.strip(), label=body.label)
    db.add(key)
    await db.commit()
    return {"id": str(key.id), "status": "added"}


@router.post("/bulk")
async def create_keys_bulk(keys: list[AIKeyCreate], db: AsyncSession = Depends(get_db)):
    added = 0
    for body in keys:
        if body.provider in VALID_PROVIDERS and body.api_key.strip():
            db.add(AIKey(provider=body.provider, api_key=body.api_key.strip(), label=body.label))
            added += 1
    await db.commit()
    return {"added": added}


@router.put("/{key_id}")
async def update_key(key_id: str, body: AIKeyUpdate, db: AsyncSession = Depends(get_db)):
    k = await db.get(AIKey, uuid.UUID(key_id))
    if not k:
        raise HTTPException(404, "Key not found")
    if body.api_key is not None and body.api_key.strip():
        k.api_key = body.api_key.strip()
        k.status = "unknown"  # reset status on key change
        k.last_error = None
        k.rate_limited_until = None
    if body.label is not None:
        k.label = body.label
    if body.is_active is not None:
        k.is_active = body.is_active
    await db.commit()
    return {"status": "updated"}


@router.delete("/{key_id}")
async def delete_key(key_id: str, db: AsyncSession = Depends(get_db)):
    k = await db.get(AIKey, uuid.UUID(key_id))
    if k:
        await db.delete(k)
        await db.commit()
    return {"status": "deleted"}


@router.post("/{key_id}/test")
async def test_key(key_id: str, db: AsyncSession = Depends(get_db)):
    """Live-test one key with a tiny prompt. Updates its status."""
    from app.services.gpt_service import _call_provider
    from app.services.ai_key_pool import mark_success, mark_failure
    k = await db.get(AIKey, uuid.UUID(key_id))
    if not k:
        raise HTTPException(404, "Key not found")
    try:
        text, *_ = await _call_provider(k.provider, k.api_key, "بگو سلام", max_tokens=10)
        await mark_success(k.id)
        return {"status": "working", "response": (text or "")[:100]}
    except Exception as e:
        msg = str(e)
        is_rl = "429" in msg or "rate" in msg.lower() or "quota" in msg.lower()
        is_inv = "401" in msg or "invalid" in msg.lower() or "unauthorized" in msg.lower()
        await mark_failure(k.id, msg, is_rate_limit=is_rl, is_invalid=is_inv)
        return {"status": "rate_limited" if is_rl else "invalid" if is_inv else "failed", "error": msg[:200]}


@router.post("/test-all")
async def test_all_keys(db: AsyncSession = Depends(get_db)):
    """Test every active key, return summary."""
    result = await db.execute(select(AIKey).where(AIKey.is_active == True))
    keys = result.scalars().all()
    from app.services.gpt_service import _call_provider
    from app.services.ai_key_pool import mark_success, mark_failure
    summary = {"working": 0, "failed": 0, "rate_limited": 0, "invalid": 0}
    for k in keys:
        try:
            await _call_provider(k.provider, k.api_key, "test", max_tokens=5)
            await mark_success(k.id)
            summary["working"] += 1
        except Exception as e:
            msg = str(e)
            is_rl = "429" in msg or "rate" in msg.lower() or "quota" in msg.lower()
            is_inv = "401" in msg or "invalid" in msg.lower() or "unauthorized" in msg.lower()
            await mark_failure(k.id, msg, is_rate_limit=is_rl, is_invalid=is_inv)
            if is_rl:
                summary["rate_limited"] += 1
            elif is_inv:
                summary["invalid"] += 1
            else:
                summary["failed"] += 1
    return summary


@router.get("/pool-status")
async def pool_status(db: AsyncSession = Depends(get_db)):
    """Summary of the key pool by provider and status."""
    result = await db.execute(select(AIKey))
    keys = result.scalars().all()
    by_provider: dict = {}
    for k in keys:
        p = k.provider
        if p not in by_provider:
            by_provider[p] = {"total": 0, "active": 0, "working": 0}
        by_provider[p]["total"] += 1
        if k.is_active:
            by_provider[p]["active"] += 1
        if k.status == "working":
            by_provider[p]["working"] += 1
    return {"by_provider": by_provider, "total_keys": len(keys)}
