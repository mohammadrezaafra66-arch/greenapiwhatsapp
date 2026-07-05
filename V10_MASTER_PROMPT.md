# CLAUDE CODE MASTER PROMPT — V10 (Scale, Robustness, UX, Features)
# Afrakala WhatsApp Sender
# Repo: https://github.com/mohammadrezaafra66-arch/greenapiwhatsapp
# Local: C:\Users\AFRA\Desktop\bots\claudegreenapi

## EXECUTION CONTRACT
Run every phase sequentially. Never stop for confirmation. Fix errors before moving on.
This is a large refactor — work methodically, phase by phase.
At end: all tests pass, rebuild, push. If a phase risks breaking existing behavior, add a test first.

## GOAL
Make this system production-ready for:
- 80+ concurrent Green API accounts sending simultaneously
- 500,000+ contacts and millions of message rows
- Reliable long-running operation without manual intervention

DO NOT break any existing feature. Preserve all current functionality.

---

# ═══════════════════════════════════════════════
# PART A — SCALING & ARCHITECTURE (highest priority)
# ═══════════════════════════════════════════════

## PHASE A1 — Database connection pooling

The current setup likely uses a single async engine that won't survive 80 accounts × concurrent workers.

In `backend/app/database.py`:
```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import AsyncAdaptedQueuePool

engine = create_async_engine(
    settings.database_url,
    pool_size=20,              # base connections
    max_overflow=40,           # burst capacity → 60 total
    pool_timeout=30,
    pool_recycle=1800,         # recycle every 30 min (avoid stale conns)
    pool_pre_ping=True,        # validate connection before use
    echo=False,
)

# For Celery workers, use a separate smaller pool via env or NullPool
# to avoid connection explosion across many worker processes
```

For the sync engine (Celery), review pool settings similarly.

Also update PostgreSQL max_connections in docker-compose.yml:
```yaml
  db:
    command: postgres -c max_connections=300 -c shared_buffers=256MB
```

## PHASE A2 — Per-account Celery queues & task isolation

CRITICAL for 80 accounts: one slow/banned account must NOT block others.

In `backend/app/workers/celery_app.py`:
```python
from kombu import Queue

celery_app.conf.task_routes = {
    "tasks.run_campaign": {"queue": "campaigns"},
    "tasks.run_campaign_account": {"queue": "sending"},
    "tasks.poll_notifications": {"queue": "webhooks"},
    "tasks.extract_all_groups": {"queue": "extraction"},
    "tasks.backfill_group_member_counts": {"queue": "backfill"},
}

celery_app.conf.task_queues = (
    Queue("campaigns"),
    Queue("sending"),
    Queue("webhooks"),
    Queue("extraction"),
    Queue("backfill"),
    Queue("celery"),  # default
)

# Prevent one task from hogging a worker
celery_app.conf.worker_prefetch_multiplier = 1
celery_app.conf.task_acks_late = True
```

Refactor campaign sending to be per-account:
- `task_run_campaign` splits work into per-account subtasks
- Each account's sends run as independent `task_send_account_batch` tasks
- A banned/slow account fails its own task without affecting others

Update docker-compose.yml to run multiple worker types:
```yaml
  worker-sending:
    <<: *worker-base
    command: celery -A app.workers.celery_app worker -Q sending --concurrency=20 -n sending@%h
  worker-general:
    <<: *worker-base
    command: celery -A app.workers.celery_app worker -Q campaigns,extraction,backfill,celery --concurrency=4 -n general@%h
  worker-webhooks:
    <<: *worker-base
    command: celery -A app.workers.celery_app worker -Q webhooks --concurrency=8 -n webhooks@%h
```

## PHASE A3 — Redis-based rate limiting (not DB reads)

Currently rate limits likely read/write account counters in Postgres on every send — won't scale.

Create `backend/app/services/redis_rate_limiter.py`:
```python
"""Redis-backed per-account rate limiting for high concurrency."""
import redis.asyncio as aioredis
from datetime import datetime
import pytz
from app.config import settings

TEHRAN_TZ = pytz.timezone("Asia/Tehran")
_redis = None

async def get_redis():
    global _redis
    if _redis is None:
        _redis = await aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis

async def can_send(account_id: str, daily_limit: int, hourly_limit: int) -> tuple[bool, str]:
    """Check if account can send now. Uses atomic Redis counters."""
    r = await get_redis()
    now = datetime.now(TEHRAN_TZ)
    day_key = f"sent:{account_id}:{now:%Y%m%d}"
    hour_key = f"sent:{account_id}:{now:%Y%m%d%H}"
    
    day_count = int(await r.get(day_key) or 0)
    hour_count = int(await r.get(hour_key) or 0)
    
    if day_count >= daily_limit:
        return False, f"سقف روزانه ({daily_limit}) پر شده"
    if hour_count >= hourly_limit:
        return False, f"سقف ساعتی ({hourly_limit}) پر شده"
    return True, "ok"

async def record_send(account_id: str):
    """Atomically increment counters with TTL."""
    r = await get_redis()
    now = datetime.now(TEHRAN_TZ)
    day_key = f"sent:{account_id}:{now:%Y%m%d}"
    hour_key = f"sent:{account_id}:{now:%Y%m%d%H}"
    
    pipe = r.pipeline()
    pipe.incr(day_key)
    pipe.expire(day_key, 172800)  # 2 days
    pipe.incr(hour_key)
    pipe.expire(hour_key, 7200)   # 2 hours
    await pipe.execute()

async def get_counts(account_id: str) -> dict:
    r = await get_redis()
    now = datetime.now(TEHRAN_TZ)
    day_key = f"sent:{account_id}:{now:%Y%m%d}"
    return {"sent_today": int(await r.get(day_key) or 0)}
```

Integrate into campaign_runner: check `can_send` before each send, call `record_send` after. Keep the DB counter as a periodic sync (every 5 min) for dashboard display, but Redis is the source of truth for rate decisions.

## PHASE A4 — Database indexes

Add indexes on all hot query columns. In main.py DDL:
```python
        ddl_indexes = [
            "CREATE INDEX IF NOT EXISTS idx_contacts_phone ON contacts(phone)",
            "CREATE INDEX IF NOT EXISTS idx_contacts_blacklisted ON contacts(blacklisted)",
            "CREATE INDEX IF NOT EXISTS idx_contacts_has_whatsapp ON contacts(has_whatsapp)",
            "CREATE INDEX IF NOT EXISTS idx_contacts_created ON contacts(created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_campaign_contacts_campaign ON campaign_contacts(campaign_id)",
            "CREATE INDEX IF NOT EXISTS idx_campaign_contacts_status ON campaign_contacts(status)",
            "CREATE INDEX IF NOT EXISTS idx_campaign_contacts_composite ON campaign_contacts(campaign_id, status)",
            "CREATE INDEX IF NOT EXISTS idx_campaign_contacts_msgid ON campaign_contacts(green_api_message_id)",
            "CREATE INDEX IF NOT EXISTS idx_inbox_instance ON inbox_messages(instance_id)",
            "CREATE INDEX IF NOT EXISTS idx_inbox_timestamp ON inbox_messages(timestamp DESC)",
            "CREATE INDEX IF NOT EXISTS idx_inbox_sender ON inbox_messages(sender_phone)",
            "CREATE INDEX IF NOT EXISTS idx_wa_groups_account ON whatsapp_groups(account_id)",
            "CREATE INDEX IF NOT EXISTS idx_wa_groups_admin ON whatsapp_groups(is_admin)",
            "CREATE INDEX IF NOT EXISTS idx_daily_send_logs_date ON daily_send_logs(date)",
            "CREATE INDEX IF NOT EXISTS idx_ai_usage_created ON ai_usage_logs(created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status)",
        ]
        for stmt in ddl_indexes:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[IDX] {e}")
```

## PHASE A5 — Fix N+1 queries and use bulk operations

Audit these hotspots and convert to bulk:
1. Campaign contact loading — use `selectinload` for relationships, fetch in one query
2. Group extraction import — use `INSERT ... ON CONFLICT DO NOTHING` bulk insert instead of per-row check-then-insert
3. Contact check-whatsapp — batch Green API calls where possible

Example bulk insert for contacts (in extraction task):
```python
from sqlalchemy.dialects.postgresql import insert as pg_insert

# Instead of per-row exists check + add:
if new_contacts:
    stmt = pg_insert(Contact).values([
        {"phone": p, "source": src, "group_source": grp}
        for p in new_phones
    ])
    stmt = stmt.on_conflict_do_nothing(index_elements=["phone"])
    await db.execute(stmt)
    await db.commit()
```

Requires a UNIQUE constraint on contacts.phone:
```python
"CREATE UNIQUE INDEX IF NOT EXISTS uq_contacts_phone ON contacts(phone)",
```
(First dedupe existing rows: keep the oldest per phone.)

## PHASE A6 — Green API concurrency safety

Each account = one Green API instance with its own rate limits. For 80 accounts:
- Add per-instance semaphore in GreenAPIClient to cap concurrent requests (e.g. 5 concurrent per instance)
- Add exponential backoff on 429 responses from Green API
- Add a circuit breaker: if an instance returns 5 consecutive errors, mark account as `degraded` and skip for 5 minutes

```python
# In green_api.py
import asyncio
_semaphores = {}

def _get_semaphore(instance_id: str) -> asyncio.Semaphore:
    if instance_id not in _semaphores:
        _semaphores[instance_id] = asyncio.Semaphore(5)
    return _semaphores[instance_id]

# Wrap each request:
async def _post(self, method, payload):
    async with _get_semaphore(self.instance_id):
        # ... existing request with retry/backoff on 429 ...
```

---

# ═══════════════════════════════════════════════
# PART B — BUG FIXES & TECH DEBT
# ═══════════════════════════════════════════════

## PHASE B1 — Audit and fix known issues

1. **asyncio.run() in Celery tasks** — repeatedly creating/closing event loops is fragile. Create one reusable async runner helper:
```python
# app/workers/async_helper.py
import asyncio

def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)
```
Replace all `asyncio.run(...)` in tasks.py with `run_async(...)`.

2. **Webhook idempotency** — Green API may deliver the same webhook twice. Add a dedup check using the message idMessage: store processed idMessages in Redis with a TTL (24h), skip if already seen.

3. **Campaign resumption** — if the backend restarts mid-campaign, running campaigns should resume. Add a startup task that finds campaigns with status=running and re-queues them.

4. **Orphaned pending contacts** — add a periodic task to detect campaigns stuck with pending contacts and no active task, and re-queue them.

5. **Timezone consistency** — audit all datetime usage. Store UTC in DB, convert to Tehran only for display and scheduling decisions. Fix any naive datetime comparisons.

6. **Error handling in webhook handlers** — wrap each handler so one malformed webhook doesn't crash the whole processing loop.

## PHASE B2 — Add global error handling & logging

Add structured logging throughout:
```python
import logging
logger = logging.getLogger("afrakala")
```
Replace print() statements with proper logging (info/warning/error levels).

Add a global exception handler in FastAPI main.py that logs and returns clean JSON errors.

Add a `/health/detailed` endpoint that checks: DB connection, Redis connection, Celery worker heartbeat, and returns status of each.

---

# ═══════════════════════════════════════════════
# PART C — FRONTEND UX IMPROVEMENTS
# ═══════════════════════════════════════════════

## PHASE C1 — Global UX primitives

1. **Toast notifications** — replace all `alert()` calls with a proper toast system (react-hot-toast or a custom context). Success=green, error=red, info=blue.

2. **Confirmation dialogs** — replace `confirm()` with a styled modal for destructive actions (delete, blacklist, clear).

3. **Loading states** — every async action shows a spinner; buttons disable during submit and show inline spinner.

4. **Error boundaries** — wrap the app in an error boundary so one component crash doesn't white-screen everything.

5. **Empty states** — every list/table shows a friendly message + primary action when empty.

## PHASE C2 — Data tables

Create a reusable `<DataTable>` component with:
- Column sorting (click header)
- Client-side + server-side search
- Row selection (checkbox) with "select all"
- Bulk action bar that appears when rows selected
- Sticky header
- Loading skeleton
- Pagination controls

Apply it to Contacts, Groups, Campaigns, Inbox pages.

## PHASE C3 — Dashboard improvements

1. Make all KPI cards clickable → navigate to the relevant filtered page
2. Add a "system health" widget (from /health/detailed): DB/Redis/workers status dots
3. Add per-account mini-cards in a grid: name, status pulse, sent today/limit bar, days_active
4. Add a "recent activity" feed: last 10 sends/receives across all accounts
5. Auto-refresh with a visible "last updated Xs ago" indicator and manual refresh button

## PHASE C4 — Campaign wizard clarity

1. Multi-step wizard with clear progress: انتخاب مخاطبین → تنظیم پیام → زمان‌بندی → بررسی نهایی → ارسال
2. Live preview of the message as it will appear (with sample contact name + products)
3. The validation engine (feature 36) result shown prominently before the send button
4. Send button disabled until validation passes or user explicitly overrides
5. "ارسال آزمایشی" always available in the review step

## PHASE C5 — Mobile responsiveness

Ensure all pages work on a phone screen (the user may manage from mobile):
- Collapsible sidebar → hamburger menu on small screens
- Tables scroll horizontally or reflow to cards
- Touch-friendly button sizes

---

# ═══════════════════════════════════════════════
# PART D — NEW USEFUL FEATURES
# ═══════════════════════════════════════════════

## PHASE D1 — Retry failed sends
Add a "تلاش مجدد برای ناموفق‌ها" button on campaigns that re-queues only the failed/yellowCard contacts.

## PHASE D2 — Contact export
Add GET /contacts/export → streams a CSV/Excel of contacts (respecting current filters). Frontend "خروجی اکسل" button.

## PHASE D3 — Campaign analytics
Per-campaign report page: sent/delivered/read/failed counts, delivery rate %, timeline chart, per-account breakdown. Export to Excel.

## PHASE D4 — Contact deduplication tool
Add a "پاک‌سازی مخاطبین تکراری" admin action that merges duplicate phones (keeping oldest, merging names/source).

## PHASE D5 — Auto-reconnect monitoring
Periodic task checks each account's Green API state; if notAuthorized/disconnected, flag it on dashboard with a red alert and (optionally) attempt a reboot via the Green API reboot method.

## PHASE D6 — Message template library
Enhance templates: variables ({نام}, {شهر}, {محصولات}), categories, preview, and reuse across campaigns.

---

# ═══════════════════════════════════════════════
# VERIFICATION & DEPLOY
# ═══════════════════════════════════════════════

## PHASE V — Final verification

```bash
cd C:/Users/AFRA/Desktop/bots/claudegreenapi/backend
python -m py_compile app/main.py app/models/*.py app/services/*.py app/api/v1/*.py app/workers/*.py app/utils/*.py
python -m pytest tests/ -v
cd ..

# Rebuild everything
docker-compose down
docker-compose up -d --build
sleep 15

# Health checks
curl -s http://localhost:8002/health/detailed | python -m json.tool
curl -s http://localhost:8002/api/v1/dashboard/stats | python -m json.tool
curl -s "http://localhost:8002/api/v1/contacts/count"

# Verify all workers are up
docker-compose ps
docker logs claudegreenapi-worker-sending-1 --tail 10 2>/dev/null || docker logs claudegreenapi-worker-general-1 --tail 10

cd frontend && npm run build && cd ..
docker-compose up -d --build --no-deps frontend
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:3002/
```

## Commit

```bash
git add -A
git commit -m "feat: V10 — scale to 80 accounts + robustness + UX + features

PART A — Scaling:
- DB connection pooling (pool_size=20, max_overflow=40, pre_ping, recycle)
- Postgres max_connections=300
- Per-account Celery queues (sending/campaigns/webhooks/extraction/backfill)
- Multiple worker types with isolated concurrency
- Redis-based rate limiting (atomic counters, source of truth for send decisions)
- 16 database indexes on hot columns
- Bulk INSERT ... ON CONFLICT for contact import (removes N+1)
- UNIQUE constraint on contacts.phone
- Per-instance Green API semaphore + 429 backoff + circuit breaker

PART B — Bug fixes:
- Reusable async runner (replaces fragile asyncio.run in tasks)
- Webhook idempotency via Redis idMessage dedup
- Campaign resumption on backend restart
- Orphaned pending-contact recovery task
- Timezone consistency audit (UTC storage, Tehran display)
- Per-handler webhook error isolation
- Structured logging + /health/detailed endpoint

PART C — Frontend UX:
- Toast notifications (replace alert)
- Confirmation modals (replace confirm)
- Loading states + spinners everywhere
- Error boundary
- Reusable DataTable (sort/search/select/bulk)
- Dashboard: clickable KPIs, health widget, per-account grid, activity feed
- Campaign wizard: steps, live preview, validation gate
- Mobile responsive

PART D — Features:
- Retry failed sends
- Contact CSV/Excel export
- Per-campaign analytics report
- Contact deduplication tool
- Auto-reconnect monitoring + alerts
- Enhanced template library with variables"
git push origin main
```

## IMPORTANT NOTES
- If any phase is too large to complete safely, commit what's done and note remaining work — do NOT leave the system in a broken state.
- Preserve ALL existing features. This is additive + hardening, not a rewrite.
- The Redis rate limiter must coexist with the existing warmup 5-msg cap and Meta limits — Redis checks the hard ceiling; the computed_daily_limit still applies.