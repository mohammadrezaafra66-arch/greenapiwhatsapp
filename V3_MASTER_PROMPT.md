# CLAUDE CODE MASTER PROMPT — V3 Feature Expansion
# Afrakala WhatsApp Sender — Advanced Scheduling, Group Campaigns, Keyword Auto-Reply
# Repo: https://github.com/mohammadrezaafra66-arch/greenapiwhatsapp
# Local: C:\Users\AFRA\Desktop\bots\claudegreenapi

## EXECUTION CONTRACT

Run every phase sequentially to completion. Never stop for confirmation.
Never ask a question. If a file already has the content described, skip and continue.
After every phase: run the listed verification. If verification fails: debug, fix,
re-verify, then continue. At the end: full pytest, docker rebuild, push to GitHub.
Only stop for a genuine unresolvable blocker.

---

## ARCHITECTURE OVERVIEW (what's being added)

```
┌─────────────────────────────────────────────────────────────────┐
│                    NEW V3 FEATURES                               │
│                                                                  │
│  1. Per-account send delay (min/max seconds, stored in DB)      │
│  2. Group campaigns (schedule messages to WhatsApp groups)      │
│  3. Keyword auto-reply (exact/contains, PV/group/both scope)    │
│  4. Per-account per-hour rate limits (replaces hardcoded)       │
│  5. Per-account per-hour schedule (rate + message type/prompt)  │
└─────────────────────────────────────────────────────────────────┘

New DB tables:
  account_send_config     → per-account delay settings
  keyword_rules           → keyword → auto-reply mapping
  account_hour_schedule   → per-account, per-hour: max_per_hour + optional gpt_prompt

Modified tables:
  accounts                → no schema change needed (delays move to account_send_config)
  campaigns               → add campaign_scope (pv/group), group_ids JSON column
  hour_rate_limits        → keep as global fallback, but account_hour_schedule takes priority

New services:
  keyword_service.py      → check incoming message against keyword_rules, fire reply
  group_campaign_runner.py → send campaign messages to WhatsApp groups on schedule

New API routers:
  /api/v1/keyword-rules   → CRUD for keyword rules
  /api/v1/account-schedules → CRUD for per-account hour schedules

Modified:
  webhook.py              → call keyword_service after auto_reply check
  campaign_runner.py      → read per-account delay from account_send_config
  rate_limiter.py         → check account_hour_schedule before DEFAULT_SCHEDULE
  accounts API            → expose send delay config endpoints
  campaigns API           → support group_campaign type
  frontend                → new pages: KeywordRules, AccountSchedules; update Accounts, Campaigns
```

---

## PHASE 0 — Idempotent DB migrations

Edit `backend/app/main.py`. Add `from sqlalchemy import text` to imports if not
already there. Inside `lifespan`, after `await conn.run_sync(Base.metadata.create_all)`,
add exactly these ALTER TABLE statements (all IF NOT EXISTS — safe to run repeatedly):

```python
        ddl = [
            # account_send_config
            """CREATE TABLE IF NOT EXISTS account_send_configs (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                account_id uuid UNIQUE NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                min_delay_seconds integer NOT NULL DEFAULT 45,
                max_delay_seconds integer NOT NULL DEFAULT 110,
                created_at timestamp DEFAULT now(),
                updated_at timestamp DEFAULT now()
            )""",
            # keyword_rules
            """CREATE TABLE IF NOT EXISTS keyword_rules (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                account_id uuid REFERENCES accounts(id) ON DELETE CASCADE,
                keyword varchar(500) NOT NULL,
                reply_message text NOT NULL,
                match_type varchar(20) NOT NULL DEFAULT 'contains',
                scope varchar(20) NOT NULL DEFAULT 'both',
                is_active boolean NOT NULL DEFAULT true,
                use_count integer NOT NULL DEFAULT 0,
                created_at timestamp DEFAULT now()
            )""",
            # account_hour_schedule
            """CREATE TABLE IF NOT EXISTS account_hour_schedules (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                hour_start integer NOT NULL,
                hour_end integer NOT NULL,
                max_per_hour integer NOT NULL DEFAULT 0,
                gpt_prompt text,
                message_template text,
                is_active boolean NOT NULL DEFAULT true,
                created_at timestamp DEFAULT now(),
                UNIQUE (account_id, hour_start, hour_end)
            )""",
            # campaigns: add group campaign columns
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS campaign_scope varchar(20) DEFAULT 'pv'",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS group_ids text",
        ]
        for stmt in ddl:
            await conn.execute(text(stmt))
```

Verification: start backend — no errors in `docker logs claudegreenapi-backend-1 --tail 20`.

---

## PHASE 1 — New SQLAlchemy models

### `backend/app/models/account_send_config.py` (new file)
```python
import uuid
from datetime import datetime
from sqlalchemy import Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class AccountSendConfig(Base):
    __tablename__ = "account_send_configs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), unique=True, nullable=False)
    min_delay_seconds: Mapped[int] = mapped_column(Integer, default=45)
    max_delay_seconds: Mapped[int] = mapped_column(Integer, default=110)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

### `backend/app/models/keyword_rule.py` (new file)
```python
import uuid
from datetime import datetime
from sqlalchemy import String, Text, Boolean, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class KeywordRule(Base):
    __tablename__ = "keyword_rules"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=True)
    keyword: Mapped[str] = mapped_column(String(500), nullable=False)
    reply_message: Mapped[str] = mapped_column(Text, nullable=False)
    match_type: Mapped[str] = mapped_column(String(20), default="contains")  # exact | contains
    scope: Mapped[str] = mapped_column(String(20), default="both")           # pv | group | both
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

### `backend/app/models/account_hour_schedule.py` (new file)
```python
import uuid
from datetime import datetime
from sqlalchemy import Integer, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class AccountHourSchedule(Base):
    __tablename__ = "account_hour_schedules"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False)
    hour_start: Mapped[int] = mapped_column(Integer, nullable=False)
    hour_end: Mapped[int] = mapped_column(Integer, nullable=False)
    max_per_hour: Mapped[int] = mapped_column(Integer, default=0)
    gpt_prompt: Mapped[str | None] = mapped_column(Text)
    message_template: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

### Update `backend/app/models/__init__.py`
Add these three new imports and export names (follow exact existing pattern in file):
```python
from app.models.account_send_config import AccountSendConfig
from app.models.keyword_rule import KeywordRule
from app.models.account_hour_schedule import AccountHourSchedule
```
Add `"AccountSendConfig"`, `"KeywordRule"`, `"AccountHourSchedule"` to `__all__`.

Also add to Campaign model in `backend/app/models/campaign.py` — these two columns
already added via DDL migration, but add to the ORM model too so SQLAlchemy knows
about them. In the `Campaign` class, after `reply_count`:
```python
    campaign_scope: Mapped[str] = mapped_column(String(20), default="pv")  # pv | group
    group_ids: Mapped[str | None] = mapped_column(Text)  # JSON list of group chatIds
```

---

## PHASE 2 — Keyword service

### `backend/app/services/keyword_service.py` (new file)
```python
"""
Check an incoming message against all active keyword_rules.
Returns (matched: bool, reply_message: str | None).
Rules are checked in creation order; first match wins.
account_id=None rules apply globally to all accounts.
"""
from sqlalchemy import select
from app.models.keyword_rule import KeywordRule
from app.database import AsyncSessionLocal


async def check_keywords(
    instance_id: str,
    message_text: str,
    is_group: bool,
    account_id: str | None = None,
) -> tuple[bool, str | None, str | None]:
    """
    Returns (matched, reply_message, rule_id).
    scope: 'pv' only matches non-group, 'group' only group, 'both' always.
    """
    if not message_text:
        return False, None, None

    text_lower = message_text.lower().strip()

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(KeywordRule)
            .where(KeywordRule.is_active == True)
            .order_by(KeywordRule.created_at)
        )
        rules = result.scalars().all()

    for rule in rules:
        # account filter: None = global, otherwise must match
        if rule.account_id is not None and str(rule.account_id) != account_id:
            continue

        # scope filter
        if rule.scope == "pv" and is_group:
            continue
        if rule.scope == "group" and not is_group:
            continue

        # match
        kw = rule.keyword.lower().strip()
        matched = False
        if rule.match_type == "exact":
            matched = text_lower == kw
        else:  # contains
            matched = kw in text_lower

        if matched:
            return True, rule.reply_message, str(rule.id)

    return False, None, None


async def increment_use_count(rule_id: str):
    async with AsyncSessionLocal() as db:
        rule = await db.get(KeywordRule, __import__("uuid").UUID(rule_id))
        if rule:
            rule.use_count += 1
            await db.commit()
```

---

## PHASE 3 — Update webhook to call keyword service

In `backend/app/api/v1/webhook.py`, inside `handle_incoming`:

After the existing `process_auto_reply` block (where `auto_reply` is checked and
`msg.auto_replied` is potentially set), add the following block. Do NOT remove or
change any existing code — only append this block before `await db.commit()`:

```python
        # Keyword auto-reply (runs even if auto_reply already fired — both can reply)
        if text and not msg.is_group or text:
            try:
                from app.services.keyword_service import check_keywords, increment_use_count
                kw_matched, kw_reply, kw_rule_id = await check_keywords(
                    instance_id=instance_id,
                    message_text=text,
                    is_group=msg.is_group,
                    account_id=str(account.id) if account else None,
                )
                if kw_matched and kw_reply and account:
                    await client.send_message(sender_phone, kw_reply)
                    if kw_rule_id:
                        await increment_use_count(kw_rule_id)
            except Exception as e:
                print(f"[Keyword] match/reply failed (non-fatal): {e}")
```

---

## PHASE 4 — Per-account send delay

### `backend/app/services/delay_service.py` (new file)
```python
"""
Get the send delay (min, max seconds) for a given account.
Falls back to env-configured defaults if no per-account config exists.
"""
from app.database import AsyncSessionLocal
from app.models.account_send_config import AccountSendConfig
from app.config import settings
import uuid


async def get_delay(account_id: str) -> tuple[int, int]:
    """Returns (min_seconds, max_seconds) for this account."""
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(
            select(AccountSendConfig).where(
                AccountSendConfig.account_id == uuid.UUID(account_id)
            )
        )
        config = result.scalar_one_or_none()
        if config:
            return config.min_delay_seconds, config.max_delay_seconds
    return settings.default_min_delay, settings.default_max_delay


async def set_delay(account_id: str, min_sec: int, max_sec: int):
    """Upsert the per-account send delay config."""
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(
            select(AccountSendConfig).where(
                AccountSendConfig.account_id == uuid.UUID(account_id)
            )
        )
        config = result.scalar_one_or_none()
        if config:
            config.min_delay_seconds = min_sec
            config.max_delay_seconds = max_sec
        else:
            db.add(AccountSendConfig(
                account_id=uuid.UUID(account_id),
                min_delay_seconds=min_sec,
                max_delay_seconds=max_sec,
            ))
        await db.commit()
```

### Update `backend/app/services/campaign_runner.py`

Find the line near the end of the inner loop:
```python
            delay = random.uniform(settings.default_min_delay, settings.default_max_delay)
```
Replace with:
```python
            from app.services.delay_service import get_delay
            min_d, max_d = await get_delay(str(account.id))
            delay = random.uniform(min_d, max_d)
```

---

## PHASE 5 — Per-account per-hour rate limits

### Update `backend/app/services/rate_limiter.py`

The current `can_send` and `get_max_per_hour` functions only read from `DEFAULT_SCHEDULE`.
Replace them with versions that check `account_hour_schedules` from DB first, then
fall back to `DEFAULT_SCHEDULE`. Keep all existing function names and the
`DEFAULT_SCHEDULE` list as fallback. The new versions:

Add this helper (insert before `can_send`):

```python
async def get_max_per_hour_for_account(account_id: str) -> int:
    """
    Returns max messages/hour for a specific account at current Tehran hour.
    Checks account_hour_schedules first; falls back to DEFAULT_SCHEDULE.
    Returns 0 if sending is blocked.
    """
    from app.database import AsyncSessionLocal
    from app.models.account_hour_schedule import AccountHourSchedule
    from sqlalchemy import select
    import uuid as _uuid

    h = get_tehran_hour()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AccountHourSchedule).where(
                AccountHourSchedule.account_id == _uuid.UUID(account_id),
                AccountHourSchedule.is_active == True,
                AccountHourSchedule.hour_start <= h,
                AccountHourSchedule.hour_end > h,
            )
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return row.max_per_hour
    # fallback to global
    return get_max_per_hour()
```

Update `can_send` to accept an optional `account_id` kwarg and use the new helper
when provided:

```python
async def can_send(account_id: str) -> bool:
    max_h = await get_max_per_hour_for_account(account_id)
    if max_h == 0:
        return False
    h = get_tehran_hour()
    count = await redis_client.get(f"rate:{account_id}:{h}")
    return not count or int(count) < max_h
```

Keep `can_send_now = can_send` alias.

Also add a helper to get the hour schedule's gpt_prompt/template for the current
hour (campaign runner will use this):

```python
async def get_hour_prompt_for_account(account_id: str) -> tuple[str | None, str | None]:
    """Returns (gpt_prompt, message_template) for account at current hour, or (None, None)."""
    from app.database import AsyncSessionLocal
    from app.models.account_hour_schedule import AccountHourSchedule
    from sqlalchemy import select
    import uuid as _uuid
    h = get_tehran_hour()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AccountHourSchedule).where(
                AccountHourSchedule.account_id == _uuid.UUID(account_id),
                AccountHourSchedule.is_active == True,
                AccountHourSchedule.hour_start <= h,
                AccountHourSchedule.hour_end > h,
            )
        )
        row = result.scalar_one_or_none()
        if row:
            return row.gpt_prompt, row.message_template
    return None, None
```

### Update campaign_runner.py to use hour-specific prompt

Inside the message-generation block (where `campaign.gpt_prompt` is used), add
this BEFORE the existing `if campaign.use_gpt ...` block:

```python
                # Per-account per-hour override: if the account has a schedule for this
                # hour with a custom prompt/template, it takes precedence.
                from app.services.rate_limiter import get_hour_prompt_for_account
                hour_gpt_prompt, hour_template = await get_hour_prompt_for_account(str(account.id))
                effective_gpt_prompt = hour_gpt_prompt or campaign.gpt_prompt
                effective_template = hour_template or campaign.message_template
```

Then change the existing `campaign.gpt_prompt` reference to `effective_gpt_prompt`
and `campaign.message_template` reference to `effective_template`.

---

## PHASE 6 — Group campaign runner

### `backend/app/services/group_campaign_runner.py` (new file)
```python
"""
Runs a group-scope campaign: sends the campaign message to each configured
WhatsApp group on the scheduled interval. Respects per-account rate limits.
"""
import asyncio, random, json, uuid
from datetime import datetime
from sqlalchemy import select
from app.models.campaign import Campaign, CampaignStatus
from app.models.account import Account, AccountStatus
from app.services.green_api import GreenAPIClient
from app.services.gpt_service import generate_message
from app.services.price_service import get_products
from app.services.rate_limiter import can_send, record_send
from app.services.delay_service import get_delay
from app.database import AsyncSessionLocal
from app.config import settings


async def run_group_campaign(campaign_id: str):
    """Send campaign message to every group_id in the campaign."""
    async with AsyncSessionLocal() as db:
        campaign = await db.get(Campaign, uuid.UUID(campaign_id))
        if not campaign or campaign.status != CampaignStatus.running:
            return
        if not campaign.group_ids:
            campaign.status = CampaignStatus.completed
            await db.commit()
            return

        try:
            group_ids = json.loads(campaign.group_ids)
        except Exception:
            campaign.status = CampaignStatus.completed
            await db.commit()
            return

        accounts_result = await db.execute(
            select(Account).where(Account.status == AccountStatus.active)
        )
        accounts = accounts_result.scalars().all()
        if not accounts:
            return

        products = []
        if campaign.include_products:
            products = await get_products(campaign.product_count)

        acc_idx = 0
        for group_id in group_ids:
            await db.refresh(campaign)
            if campaign.status != CampaignStatus.running:
                break

            account = accounts[acc_idx % len(accounts)]
            acc_idx += 1

            if not await can_send(str(account.id)):
                await asyncio.sleep(60)
                continue

            try:
                if campaign.use_gpt and settings.openai_api_key:
                    message = await generate_message(
                        first_name="گروه",
                        last_name="",
                        gpt_prompt=campaign.gpt_prompt or "یک پیام تبلیغاتی مختصر بنویس",
                        products=products if campaign.include_products else None
                    )
                else:
                    message = campaign.message_template or "پیام افراکالا"

                client = GreenAPIClient(account.instance_id, account.api_token)

                if campaign.campaign_type and campaign.campaign_type.value == "image" and campaign.image_url:
                    msg_id = await client.send_image(group_id, campaign.image_url, message)
                else:
                    msg_id = await client.send_group_message(group_id, message)

                if msg_id:
                    campaign.sent_count += 1
                    account.sent_today += 1
                    await record_send(str(account.id))
                else:
                    campaign.failed_count += 1

            except Exception as e:
                campaign.failed_count += 1
                print(f"[GroupCampaign] group {group_id} error: {e}")
            finally:
                await db.commit()

            min_d, max_d = await get_delay(str(account.id))
            await asyncio.sleep(random.uniform(min_d, max_d))

        campaign.status = CampaignStatus.completed
        campaign.completed_at = datetime.utcnow()
        await db.commit()
```

### Update `backend/app/workers/tasks.py`

Add new Celery task:
```python
@celery_app.task(bind=True, name="tasks.run_group_campaign", max_retries=3)
def task_run_group_campaign(self, campaign_id: str):
    try:
        from app.services.group_campaign_runner import run_group_campaign
        asyncio.run(run_group_campaign(campaign_id))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)
```

### Update `backend/app/api/v1/campaigns.py`

In `start_campaign` handler, after determining campaign should start, check
`campaign.campaign_scope`:

```python
    campaign.status = CampaignStatus.running
    await db.commit()
    if campaign.campaign_scope == "group":
        from app.workers.tasks import task_run_group_campaign
        task_run_group_campaign.delay(campaign_id)
    else:
        task_run_campaign.delay(campaign_id)
    return {"status": "started", "campaign_id": campaign_id, "scope": campaign.campaign_scope}
```

Also update `CampaignCreateBody` Pydantic model — add two fields:
```python
    campaign_scope: str = "pv"      # pv | group
    group_ids: list[str] | None = None   # list of WhatsApp group chatIds (e.g. "120363xxxxxxxx@g.us")
```

In `create_campaign` handler, persist these when building the `Campaign` object:
```python
        campaign_scope=body.campaign_scope,
        group_ids=json.dumps(body.group_ids) if body.group_ids else None,
```

---

## PHASE 7 — New API routers

### `backend/app/api/v1/keyword_rules.py` (new file)
```python
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
```

### `backend/app/api/v1/account_schedules.py` (new file)
```python
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.account_hour_schedule import AccountHourSchedule
from app.models.account_send_config import AccountSendConfig

router = APIRouter(prefix="/account-schedules", tags=["account-schedules"])


class ScheduleCreate(BaseModel):
    account_id: str
    hour_start: int
    hour_end: int
    max_per_hour: int = 0
    gpt_prompt: str | None = None
    message_template: str | None = None
    is_active: bool = True


class DelayUpdate(BaseModel):
    min_delay_seconds: int = 45
    max_delay_seconds: int = 110


@router.get("/{account_id}")
async def get_account_schedule(account_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AccountHourSchedule)
        .where(AccountHourSchedule.account_id == uuid.UUID(account_id))
        .order_by(AccountHourSchedule.hour_start)
    )
    rows = result.scalars().all()
    delay_result = await db.execute(
        select(AccountSendConfig).where(AccountSendConfig.account_id == uuid.UUID(account_id))
    )
    delay = delay_result.scalar_one_or_none()
    return {
        "account_id": account_id,
        "delay": {
            "min_delay_seconds": delay.min_delay_seconds if delay else 45,
            "max_delay_seconds": delay.max_delay_seconds if delay else 110,
        },
        "schedule": [
            {
                "id": str(r.id),
                "hour_start": r.hour_start,
                "hour_end": r.hour_end,
                "max_per_hour": r.max_per_hour,
                "gpt_prompt": r.gpt_prompt,
                "message_template": r.message_template,
                "is_active": r.is_active,
            }
            for r in rows
        ],
    }


@router.post("/")
async def create_schedule_slot(body: ScheduleCreate, db: AsyncSession = Depends(get_db)):
    slot = AccountHourSchedule(
        account_id=uuid.UUID(body.account_id),
        hour_start=body.hour_start,
        hour_end=body.hour_end,
        max_per_hour=body.max_per_hour,
        gpt_prompt=body.gpt_prompt,
        message_template=body.message_template,
        is_active=body.is_active,
    )
    db.add(slot)
    await db.commit()
    await db.refresh(slot)
    return {"id": str(slot.id)}


@router.put("/{slot_id}")
async def update_schedule_slot(slot_id: str, body: ScheduleCreate, db: AsyncSession = Depends(get_db)):
    slot = await db.get(AccountHourSchedule, uuid.UUID(slot_id))
    if not slot:
        raise HTTPException(404, "Slot not found")
    slot.hour_start = body.hour_start
    slot.hour_end = body.hour_end
    slot.max_per_hour = body.max_per_hour
    slot.gpt_prompt = body.gpt_prompt
    slot.message_template = body.message_template
    slot.is_active = body.is_active
    await db.commit()
    return {"updated": True}


@router.delete("/{slot_id}")
async def delete_schedule_slot(slot_id: str, db: AsyncSession = Depends(get_db)):
    slot = await db.get(AccountHourSchedule, uuid.UUID(slot_id))
    if not slot:
        raise HTTPException(404, "Slot not found")
    await db.delete(slot)
    await db.commit()
    return {"deleted": True}


@router.put("/{account_id}/delay")
async def update_account_delay(account_id: str, body: DelayUpdate, db: AsyncSession = Depends(get_db)):
    from app.services.delay_service import set_delay
    await set_delay(account_id, body.min_delay_seconds, body.max_delay_seconds)
    return {"account_id": account_id, "min_delay_seconds": body.min_delay_seconds, "max_delay_seconds": body.max_delay_seconds}
```

### Update `backend/app/main.py`

Add two new routers to the imports and the router loop:
```python
from app.api.v1 import keyword_rules, account_schedules
```

Add to the `for router in [...]` list:
```python
    keyword_rules.router, account_schedules.router,
```

---

## PHASE 8 — Tests

### `backend/tests/test_v3.py` (new file)
```python
"""Smoke tests for V3 features."""
import pytest
import inspect
from app.services.keyword_service import check_keywords
from app.services.delay_service import get_delay, set_delay
from app.models.keyword_rule import KeywordRule
from app.models.account_send_config import AccountSendConfig
from app.models.account_hour_schedule import AccountHourSchedule


def test_new_models_importable():
    assert KeywordRule.__tablename__ == "keyword_rules"
    assert AccountSendConfig.__tablename__ == "account_send_configs"
    assert AccountHourSchedule.__tablename__ == "account_hour_schedules"


def test_keyword_service_is_async():
    assert inspect.iscoroutinefunction(check_keywords)


def test_delay_service_is_async():
    assert inspect.iscoroutinefunction(get_delay)
    assert inspect.iscoroutinefunction(set_delay)


def test_campaign_model_has_group_fields():
    from app.models.campaign import Campaign
    assert hasattr(Campaign, "campaign_scope")
    assert hasattr(Campaign, "group_ids")
```

---

## PHASE 9 — Frontend new pages

### `frontend/src/api.js`

Add these API client sections (follow the exact existing pattern — each is an object
with methods calling `http.get/post/put/delete`):

```javascript
// ── Keyword Rules ──────────────────────────────────────────
export const KeywordRulesApi = {
  list: () => http.get("/keyword-rules/").then(r => r.data),
  create: (body) => http.post("/keyword-rules/", body).then(r => r.data),
  update: (id, body) => http.put(`/keyword-rules/${id}`, body).then(r => r.data),
  delete: (id) => http.delete(`/keyword-rules/${id}`).then(r => r.data),
};

// ── Account Schedules ──────────────────────────────────────
export const AccountSchedulesApi = {
  get: (accountId) => http.get(`/account-schedules/${accountId}`).then(r => r.data),
  createSlot: (body) => http.post("/account-schedules/", body).then(r => r.data),
  updateSlot: (id, body) => http.put(`/account-schedules/${id}`, body).then(r => r.data),
  deleteSlot: (id) => http.delete(`/account-schedules/${id}`).then(r => r.data),
  updateDelay: (accountId, body) => http.put(`/account-schedules/${accountId}/delay`, body).then(r => r.data),
};
```

### `frontend/src/pages/KeywordRules.jsx` (new file)

Build a full CRUD page. Structure:

- Header: "قوانین پاسخ خودکار" + "افزودن قانون" button
- Table columns: کلیدواژه | پاسخ (truncated 60 chars) | نوع تطبیق | حوزه | وضعیت | تعداد استفاده | ویرایش | حذف
- match_type display: exact → "دقیق" | contains → "شامل"
- scope display: pv → "خصوصی" | group → "گروه" | both → "هر دو"
- Add/Edit modal fields:
  - کلیدواژه (text input)
  - متن پاسخ (textarea)
  - نوع تطبیق (select: دقیق / شامل)
  - حوزه (select: خصوصی / گروه / هر دو)
  - فعال (toggle)
- On save: call `KeywordRulesApi.create` or `.update`
- On delete: call `KeywordRulesApi.delete` + reload
- Follow exact same pattern (useAsync, Modal, Badge, Spinner, Empty) as existing pages

### `frontend/src/pages/AccountSchedules.jsx` (new file)

Build a page to configure per-account schedule and delay:

- Account selector dropdown at top (GET /accounts/ to populate)
- On account select: load schedule via `AccountSchedulesApi.get(accountId)`
- Delay section: two number inputs (min_delay / max_delay seconds) + Save button
- Schedule table: hour_start | hour_end | max_per_hour | GPT prompt (short) | template (short) | فعال | ویرایش | حذف
- "افزودن بازه" button → modal: hour_start (0-23), hour_end (1-24), max_per_hour, gpt_prompt (textarea), message_template (textarea), is_active toggle
- Explanation banner: "بازه‌های تعریف‌شده اینجا برای این اکانت جایگزین زمان‌بندی پیش‌فرض می‌شوند"
- RTL, same component pattern as other pages

### Update `frontend/src/App.jsx`

Add two new route imports and `<Route>` elements:
```jsx
import KeywordRules from "./pages/KeywordRules.jsx";
import AccountSchedules from "./pages/AccountSchedules.jsx";
```

Inside `<Routes>`:
```jsx
<Route path="/keyword-rules" element={<KeywordRules />} />
<Route path="/account-schedules" element={<AccountSchedules />} />
```

### Update `frontend/src/components/Layout.jsx`

Add two new nav items to the `NAV` array (after existing items):
```javascript
  { to: "/keyword-rules", label: "یدیلکاه خساپ", icon: "🔑" },
  { to: "/account-schedules", label: "لودج یاهب‌اسح", icon: "⏱️" },
```

Note: the labels above are written RTL-mirrored in source but render correctly in
the browser. Match the exact pattern of existing nav items.

### Update `frontend/src/pages/Campaigns.jsx`

In the campaign creation wizard (Step 1), add:
- "حوزه کمپین" radio/select: "خصوصی (PV)" | "گروه"
- When "گروه" selected: show a text area "شناسه گروه‌ها (هر خط یک chatId)" where user
  pastes group chatIds like `120363xxxxxxxx@g.us`
- Pass `campaign_scope` and `group_ids` (parsed as array from textarea lines) to the
  create API call

---

## PHASE 10 — Compile check, rebuild, verify

```bash
cd C:/Users/AFRA/Desktop/bots/claudegreenapi/backend
python -m py_compile app/main.py app/models/*.py app/services/*.py app/api/v1/*.py app/workers/*.py
echo "=== py_compile OK ==="
python -m pytest tests/ -v
echo "=== pytest done ==="
cd ..
```

```bash
docker-compose up -d --build backend worker beat
sleep 8
curl -s http://localhost:8002/health
curl -s http://localhost:8002/api/v1/keyword-rules/
curl -s http://localhost:8002/api/v1/account-schedules/00000000-0000-0000-0000-000000000000
docker logs claudegreenapi-backend-1 --tail 20
docker logs claudegreenapi-worker-1 --tail 15
```

Expected:
- `/health` → `{"status":"ok","version":"2.0.0"}`
- `/api/v1/keyword-rules/` → `[]` (empty array — no rules yet)
- `/api/v1/account-schedules/...` → 404 or empty (no such account — that's correct)
- Backend logs: no import errors, tables created/migrated
- Worker logs: `tasks.run_group_campaign` registered

```bash
cd frontend
npm run build
echo "=== frontend build OK ==="
cd ..
```

```bash
docker-compose up -d --build --no-deps frontend
sleep 4
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:3002/
```
Expected: HTTP 200

---

## PHASE 11 — Commit and push

```bash
cd C:/Users/AFRA/Desktop/bots/claudegreenapi
git add -A
git commit -m "feat: V3 — per-account delay, group campaigns, keyword auto-reply, per-account per-hour schedule

New features:
- Per-account send delay (min/max seconds) stored in account_send_configs table,
  configurable per-account from frontend; fallback to env defaults
- Group campaigns: campaign_scope=group sends message to a list of WhatsApp
  group chatIds on a schedule via separate group_campaign_runner + Celery task
- Keyword auto-reply: keyword_rules table (keyword, reply_message, match_type
  exact/contains, scope pv/group/both, per-account or global); checked in
  webhook handle_incoming after auto_reply; first-match wins
- Per-account per-hour schedule: account_hour_schedules table overrides global
  DEFAULT_SCHEDULE per account; also stores optional gpt_prompt/message_template
  override per time slot so campaign runner uses time-appropriate message style
- All DB changes via idempotent CREATE TABLE IF NOT EXISTS + ALTER TABLE IF NOT EXISTS
  in lifespan (no Alembic migration files needed)

New API endpoints:
  GET/POST/PUT/DELETE /api/v1/keyword-rules/
  GET /api/v1/account-schedules/{account_id}
  POST/PUT/DELETE /api/v1/account-schedules/ and /{slot_id}
  PUT /api/v1/account-schedules/{account_id}/delay

New frontend pages:
  /keyword-rules — full CRUD for keyword auto-reply rules
  /account-schedules — per-account delay + per-hour rate/prompt schedule

Tests: all existing pass + new test_v3.py smoke tests"
git push origin main
```

---

## FINAL REPORT FORMAT

After push, output:
1. Git commit hash
2. py_compile result
3. pytest N passed / N failed
4. Docker health check results (backend :8002/health, keyword-rules endpoint, frontend :3002)
5. Worker logs confirmation (task registration)
6. Any items NOT verified without a live Green API account