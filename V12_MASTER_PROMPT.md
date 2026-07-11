# CLAUDE CODE MASTER PROMPT — V12 (AI Key Pool Manager)
# Afrakala WhatsApp Sender
# Repo: https://github.com/mohammadrezaafra66-arch/greenapiwhatsapp
# Local: C:\Users\AFRA\Desktop\bots\claudegreenapi

## AUTONOMOUS EXECUTION CONTRACT
- Run every phase sequentially. NEVER ask for confirmation or present choices.
- At each decision point, pick the safest reasonable option, note it in the summary, continue.
- Verify → commit → push each logical unit (backend tests + browser-check frontend).
- Only hard-stop on irreversible data loss. Everything else: proceed.
- Use afrakala/whatsapp_sender for DB, real container/service names.
- Adapt all snippets to the app's real conventions. Keep changes additive. Preserve ALL existing features.

## DB / ENV FACTS
- DB container: claudegreenapi-db-1, user afrakala, db whatsapp_sender
- Backend :8002, Frontend :3002
- Services to restart after: backend worker-general worker-webhooks

## GOAL
Build a multi-key AI pool: user adds 10-12 API keys across providers (OpenAI/GPT, DeepSeek, Gemini).
System randomly picks a WORKING key each time. Failed/rate-limited keys are auto-skipped and auto-recover.
Full CRUD (add/edit/delete/toggle) from the frontend. System auto-detects which keys have credit/work.

---

## PHASE 1 — DB: ai_keys table

In main.py lifespan DDL:
```python
        ddl_v12 = [
            """CREATE TABLE IF NOT EXISTS ai_keys (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                provider varchar(30) NOT NULL,
                api_key text NOT NULL,
                label varchar(200),
                is_active boolean DEFAULT true,
                status varchar(30) DEFAULT 'unknown',
                last_checked_at timestamp,
                last_error text,
                success_count integer DEFAULT 0,
                fail_count integer DEFAULT 0,
                rate_limited_until timestamp,
                created_at timestamp DEFAULT now()
            )""",
            "CREATE INDEX IF NOT EXISTS idx_ai_keys_provider ON ai_keys(provider)",
            "CREATE INDEX IF NOT EXISTS idx_ai_keys_active ON ai_keys(is_active)",
        ]
        for stmt in ddl_v12:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V12] {e}")
```

provider values: openai | deepseek | gemini
status values: unknown | working | failed | rate_limited | invalid

Create `backend/app/models/ai_key.py`:
```python
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Integer, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class AIKey(Base):
    __tablename__ = "ai_keys"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(30))
    api_key: Mapped[str] = mapped_column(Text)
    label: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(30), default="unknown")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    rate_limited_until: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```
Import it in models/__init__.py.

---

## PHASE 2 — Backend: key pool service

Create `backend/app/services/ai_key_pool.py`:
```python
"""Manages a pool of AI API keys across providers with random working-key selection."""
import random
from datetime import datetime, timedelta
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.ai_key import AIKey

async def get_working_key(provider: str | None = None) -> AIKey | None:
    """
    Return a random active, non-rate-limited key.
    If provider given, restrict to it; otherwise any provider.
    Prefers keys with status 'working' or 'unknown', skips 'invalid'/'failed'/currently rate-limited.
    """
    async with AsyncSessionLocal() as db:
        query = select(AIKey).where(AIKey.is_active == True)
        if provider:
            query = query.where(AIKey.provider == provider)
        result = await db.execute(query)
        keys = list(result.scalars().all())

        now = datetime.utcnow()
        # Filter out invalid + currently rate-limited keys
        usable = [
            k for k in keys
            if k.status not in ("invalid",)
            and (k.rate_limited_until is None or k.rate_limited_until < now)
        ]
        if not usable:
            return None
        # Prefer known-working keys, but include unknown ones too
        working = [k for k in usable if k.status == "working"]
        pool = working if working else usable
        return random.choice(pool)

async def mark_success(key_id):
    async with AsyncSessionLocal() as db:
        k = await db.get(AIKey, key_id)
        if k:
            k.status = "working"
            k.success_count += 1
            k.last_checked_at = datetime.utcnow()
            k.last_error = None
            k.rate_limited_until = None
            await db.commit()

async def mark_failure(key_id, error: str, is_rate_limit: bool = False, is_invalid: bool = False):
    async with AsyncSessionLocal() as db:
        k = await db.get(AIKey, key_id)
        if k:
            k.fail_count += 1
            k.last_checked_at = datetime.utcnow()
            k.last_error = error[:500]
            if is_invalid:
                k.status = "invalid"
            elif is_rate_limit:
                k.status = "rate_limited"
                k.rate_limited_until = datetime.utcnow() + timedelta(minutes=15)
            else:
                k.status = "failed"
            await db.commit()
```

---

## PHASE 3 — Backend: rewrite gpt_service to use the pool

In `backend/app/services/gpt_service.py` (or wherever _chat/_call lives), replace the env-key logic with pool-based selection. The generation flow:
1. Try to get a working key (prefer OpenAI, then DeepSeek, then Gemini — but any works)
2. Call that provider's API with the selected key
3. On success → mark_success, return text
4. On 429 → mark_failure(is_rate_limit=True), retry with a DIFFERENT key (up to N attempts across the pool)
5. On 401/invalid key → mark_failure(is_invalid=True), retry with different key
6. If all keys exhausted → fall back to the Persian template (existing behavior)

```python
async def generate_message(prompt: str, ...) -> str:
    from app.services.ai_key_pool import get_working_key, mark_success, mark_failure
    
    PROVIDER_ORDER = ["openai", "deepseek", "gemini"]
    attempts = 0
    max_attempts = 6  # try up to 6 different keys
    tried_key_ids = set()
    
    while attempts < max_attempts:
        attempts += 1
        # Try preferred providers in order, then any
        key_obj = None
        for prov in PROVIDER_ORDER:
            k = await get_working_key(prov)
            if k and k.id not in tried_key_ids:
                key_obj = k
                break
        if not key_obj:
            key_obj = await get_working_key(None)  # any provider
        if not key_obj or key_obj.id in tried_key_ids:
            break
        
        tried_key_ids.add(key_obj.id)
        
        try:
            text = await _call_provider(key_obj.provider, key_obj.api_key, prompt, ...)
            if text:
                await mark_success(key_obj.id)
                return text
        except Exception as e:
            msg = str(e)
            is_rl = "429" in msg or "rate" in msg.lower() or "quota" in msg.lower()
            is_inv = "401" in msg or "invalid" in msg.lower() or "unauthorized" in msg.lower()
            await mark_failure(key_obj.id, msg, is_rate_limit=is_rl, is_invalid=is_inv)
            continue
    
    # All keys failed → template fallback
    return _fallback_message(...)
```

Implement `_call_provider(provider, key, prompt, ...)` that routes to the right API:
- openai: POST https://api.openai.com/v1/chat/completions (model gpt-4o-mini or existing)
- deepseek: POST https://api.deepseek.com/v1/chat/completions (model deepseek-chat) — OpenAI-compatible format
- gemini: POST https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}

Extract token usage from each provider's response and log to ai_usage_logs as before (keep the existing token-logging logic, associate with provider).

IMPORTANT: keep env-var keys as a fallback source too — if the ai_keys table is empty, fall back to reading OPENAI_API_KEY/DEEPSEEK_API_KEY/GEMINI_API_KEY from env (so nothing breaks for existing setups). But the DB pool takes priority when it has keys.

---

## PHASE 4 — Backend: CRUD + health-check endpoints

Create `backend/app/api/v1/ai_keys.py`:
```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
from app.database import get_db
from app.models.ai_key import AIKey

router = APIRouter(prefix="/ai-keys", tags=["ai-keys"])

def _mask(key: str) -> str:
    if len(key) <= 8:
        return "****"
    return key[:6] + "..." + key[-4:]

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
    keys = result.scalars().all()
    return [
        {
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
        for k in keys
    ]

@router.post("/")
async def create_key(body: AIKeyCreate, db: AsyncSession = Depends(get_db)):
    if body.provider not in ("openai", "deepseek", "gemini"):
        raise HTTPException(400, "provider must be openai, deepseek, or gemini")
    key = AIKey(provider=body.provider, api_key=body.api_key.strip(), label=body.label)
    db.add(key)
    await db.commit()
    return {"id": str(key.id), "status": "added"}

@router.post("/bulk")
async def create_keys_bulk(keys: list[AIKeyCreate], db: AsyncSession = Depends(get_db)):
    added = 0
    for body in keys:
        if body.provider in ("openai", "deepseek", "gemini") and body.api_key.strip():
            db.add(AIKey(provider=body.provider, api_key=body.api_key.strip(), label=body.label))
            added += 1
    await db.commit()
    return {"added": added}

@router.put("/{key_id}")
async def update_key(key_id: str, body: AIKeyUpdate, db: AsyncSession = Depends(get_db)):
    k = await db.get(AIKey, uuid.UUID(key_id))
    if not k:
        raise HTTPException(404, "Key not found")
    if body.api_key is not None:
        k.api_key = body.api_key.strip()
        k.status = "unknown"  # reset status on key change
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
        text = await _call_provider(k.provider, k.api_key, "بگو سلام", max_tokens=10)
        await mark_success(k.id)
        return {"status": "working", "response": text[:100]}
    except Exception as e:
        msg = str(e)
        is_rl = "429" in msg or "rate" in msg.lower() or "quota" in msg.lower()
        is_inv = "401" in msg or "invalid" in msg.lower()
        await mark_failure(k.id, msg, is_rate_limit=is_rl, is_invalid=is_inv)
        return {"status": "failed", "error": msg[:200]}

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
            is_inv = "401" in msg or "invalid" in msg.lower()
            await mark_failure(k.id, msg, is_rate_limit=is_rl, is_invalid=is_inv)
            if is_rl: summary["rate_limited"] += 1
            elif is_inv: summary["invalid"] += 1
            else: summary["failed"] += 1
    return summary

@router.get("/pool-status")
async def pool_status(db: AsyncSession = Depends(get_db)):
    """Summary of the key pool by provider and status."""
    result = await db.execute(select(AIKey))
    keys = result.scalars().all()
    by_provider = {}
    for k in keys:
        p = k.provider
        if p not in by_provider:
            by_provider[p] = {"total": 0, "working": 0, "active": 0}
        by_provider[p]["total"] += 1
        if k.is_active:
            by_provider[p]["active"] += 1
        if k.status == "working":
            by_provider[p]["working"] += 1
    return {"by_provider": by_provider, "total_keys": len(keys)}
```

Register the router in main.py.

---

## PHASE 5 — Optional periodic health check

Add a Celery beat task that runs every 30 minutes, re-tests keys that are 'failed'/'rate_limited' (to auto-recover them when quota resets), and clears rate_limited_until when expired:
```python
@celery_app.task(name="tasks.recheck_ai_keys")
def task_recheck_ai_keys():
    from app.services.ai_key_pool import recheck_stale_keys
    run_async(recheck_stale_keys())
```
Add to beat_schedule: 1800 seconds. recheck_stale_keys re-tests keys whose status is failed/rate_limited and last_checked > 15 min ago.

---

## PHASE 6 — Frontend: AI Keys management page

New page under "ابزارها" (or "تنظیمات"): "کلیدهای هوش مصنوعی"

Layout:
1. **Pool summary card** (from /ai-keys/pool-status): per-provider counts — total, active, working. Colored badges.
2. **"تست همه کلیدها" button** (calls /ai-keys/test-all) → shows summary: X working, Y rate-limited, Z invalid
3. **"افزودن کلید" button** → modal:
   - provider dropdown: OpenAI (GPT) / DeepSeek / Gemini
   - api_key input (password field with show toggle)
   - label input (optional, e.g. "کلید اصلی GPT")
4. **Bulk add** — textarea + provider selector: paste multiple keys (one per line), all added under the selected provider
5. **Keys table**:
   - provider badge (colored: OpenAI green, DeepSeek blue, Gemini orange)
   - masked key (sk-abc...xyz)
   - label
   - status badge: working ✅ / rate_limited ⏳ / failed ❌ / invalid ⛔ / unknown ❓
   - success/fail counts
   - last checked
   - actions: تست (test single) | ویرایش (edit) | فعال/غیرفعال (toggle) | حذف (delete)
6. Auto-refresh status every 60s
7. Info banner: "سیستم به صورت خودکار از بین کلیدهای فعال و سالم به صورت رندوم استفاده می‌کند. کلیدهایی که به سقف رسیده‌اند موقتاً کنار گذاشته می‌شوند و بعد از مدتی دوباره امتحان می‌شوند."

api.js additions:
```javascript
export const AIKeysApi = {
  list: () => http.get("/ai-keys/").then(r => r.data),
  create: (body) => http.post("/ai-keys/", body).then(r => r.data),
  bulk: (keys) => http.post("/ai-keys/bulk", keys).then(r => r.data),
  update: (id, body) => http.put(`/ai-keys/${id}`, body).then(r => r.data),
  delete: (id) => http.delete(`/ai-keys/${id}`).then(r => r.data),
  test: (id) => http.post(`/ai-keys/${id}/test`).then(r => r.data),
  testAll: () => http.post("/ai-keys/test-all").then(r => r.data),
  poolStatus: () => http.get("/ai-keys/pool-status").then(r => r.data),
};
```

Add nav link in the sidebar under ابزارها.

---

## PHASE 7 — Verify, rebuild, push

```bash
cd C:/Users/AFRA/Desktop/bots/claudegreenapi/backend
python -m py_compile app/main.py app/models/*.py app/services/*.py app/api/v1/*.py app/workers/*.py
python -m pytest tests/ -v
cd ..
docker compose up -d --build backend worker-general worker-webhooks beat
sleep 10
curl -s http://localhost:8002/api/v1/ai-keys/pool-status | python -m json.tool
curl -s http://localhost:8002/api/v1/ai-keys/ | python -m json.tool
cd frontend && npm run build && cd ..
docker compose up -d --build --no-deps frontend
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:3002/
```

Commit:
```bash
git add -A
git commit -m "feat: V12 — AI key pool manager (multi-key, multi-provider, random working-key selection)

- ai_keys table: provider, key, label, status, counts, rate-limit tracking
- ai_key_pool service: random selection among active non-rate-limited keys, prefers 'working'
- gpt_service rewrite: tries up to 6 different keys across openai→deepseek→gemini,
  marks success/failure, auto-skips rate-limited/invalid keys, template fallback if all fail
- _call_provider: routes to OpenAI, DeepSeek (OpenAI-compatible), Gemini APIs
- env-var keys remain a fallback when ai_keys table is empty
- CRUD endpoints: GET/POST/PUT/DELETE /ai-keys, bulk add, per-key test, test-all, pool-status
- Celery task recheck_ai_keys (every 30min): auto-recovers failed/rate-limited keys
- Frontend AI Keys page: pool summary, add/bulk-add/edit/delete/toggle, per-key + test-all,
  status badges, auto-refresh, provider-colored badges
- token usage logging preserved per provider"
git push origin main
```

## AUTONOMOUS NOTES TO RECORD
- Confirm random selection actually distributes across keys (not always the same one).
- Confirm a rate-limited key is skipped and a different one is chosen.
- Confirm env fallback still works when the table is empty.
- Keys are masked in all API responses (never return full key to frontend).