
# CLAUDE CODE MASTER PROMPT — V5 Feature Expansion (27 Items)
# Afrakala WhatsApp Sender
# Repo: https://github.com/mohammadrezaafra66-arch/greenapiwhatsapp
# Local: C:\Users\AFRA\Desktop\bots\claudegreenapi

## EXECUTION CONTRACT
Run every phase sequentially. Never stop for confirmation. Never ask questions.
Fix any error before moving to next phase. At end: pytest, docker rebuild, push.

---

## CONTEXT (current state)
- Backend: FastAPI, Python 3.11, PostgreSQL, Redis, Celery
- Frontend: React + Vite + Tailwind, RTL Persian, dark theme, port 3002
- Green API instance: 7105325764, account_id: 2e95cde4-fd12-40c0-b42c-3529705543d5
- Supabase self-hosted: http://192.168.170.10:8000, anon key in config
- All existing features from V1-V4 remain unchanged

---

## PHASE 0 — DB Migrations (idempotent)

In `backend/app/main.py` lifespan, after existing DDL block, add:

```python
        ddl_v5 = [
            # Keyword rules fix: scope 'group' means send reply to group, not PV
            # (no schema change needed, logic fix in webhook.py)

            # Contact groups (virtual groups of contacts)
            """CREATE TABLE IF NOT EXISTS contact_groups (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                name varchar(200) NOT NULL,
                description text,
                color varchar(20) DEFAULT '#25D366',
                created_at timestamp DEFAULT now()
            )""",

            # Contact ↔ Group mapping
            """CREATE TABLE IF NOT EXISTS contact_group_members (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                group_id uuid NOT NULL REFERENCES contact_groups(id) ON DELETE CASCADE,
                contact_id uuid NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
                UNIQUE(group_id, contact_id)
            )""",

            # WhatsApp group collections (virtual group of WA groups)
            """CREATE TABLE IF NOT EXISTS wa_group_collections (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                name varchar(200) NOT NULL,
                description text,
                created_at timestamp DEFAULT now()
            )""",

            # WA group ↔ Collection mapping
            """CREATE TABLE IF NOT EXISTS wa_group_collection_members (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                collection_id uuid NOT NULL REFERENCES wa_group_collections(id) ON DELETE CASCADE,
                group_chat_id varchar(200) NOT NULL,
                group_name varchar(200),
                UNIQUE(collection_id, group_chat_id)
            )""",

            # Emergency numbers
            """CREATE TABLE IF NOT EXISTS emergency_contacts (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                name varchar(100),
                phone varchar(20) NOT NULL,
                purpose varchar(100) DEFAULT 'alert',
                is_active boolean DEFAULT true,
                created_at timestamp DEFAULT now()
            )""",

            # Night report subscribers
            """CREATE TABLE IF NOT EXISTS report_subscribers (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                phone varchar(20) NOT NULL UNIQUE,
                name varchar(100),
                is_active boolean DEFAULT true,
                created_at timestamp DEFAULT now()
            )""",

            # Daily send log (for night report)
            """CREATE TABLE IF NOT EXISTS daily_send_logs (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                date date NOT NULL DEFAULT CURRENT_DATE,
                account_id uuid REFERENCES accounts(id),
                account_name varchar(100),
                campaign_name varchar(200),
                recipient_phone varchar(20),
                recipient_name varchar(200),
                status varchar(50),
                sent_at timestamp DEFAULT now()
            )""",

            # Product mention log (who mentioned our product in WA groups)
            """CREATE TABLE IF NOT EXISTS product_mention_logs (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                product_name varchar(500),
                product_id varchar(100),
                sender_phone varchar(20),
                sender_name varchar(200),
                group_name varchar(200),
                group_chat_id varchar(200),
                instance_id varchar(50),
                message_text text,
                mentioned_at timestamp DEFAULT now()
            )""",

            # Campaign extensions
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS description text",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS is_active boolean DEFAULT true",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS append_date boolean DEFAULT false",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS append_seller_name boolean DEFAULT false",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS seller_name varchar(200)",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS append_seller_phone boolean DEFAULT false",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS seller_phone varchar(20)",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS seller_phone2 varchar(20)",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS emoji_level varchar(20) DEFAULT 'medium'",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS contact_group_id uuid",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS wa_collection_id uuid",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS product_label_filter varchar(200)",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS is_always_on boolean DEFAULT false",

            # Account emergency contact
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS emergency_phones text",
        ]
        for stmt in ddl_v5:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V5] {e}")
```

---

## PHASE 1 — Fix Bug #2: Keyword Reply Scope

**Problem:** When scope='group', reply is going to PV instead of the group.

**Fix in `backend/app/api/v1/webhook.py`** in `handle_incoming`:

Find the keyword reply block. Change the send logic:
```python
# BEFORE (wrong):
await client.send_message(sender_phone, kw_reply)

# AFTER (correct):
if kw_matched and kw_reply and account:
    # scope determines WHERE to reply
    target_chat_id = msg.sender_phone  # default: PV
    if rule_scope == "group" and msg.is_group:
        # reply to the group, not PV
        target_chat_id = payload.get("senderData", {}).get("chatId", sender_phone)
    elif rule_scope == "both" and msg.is_group:
        target_chat_id = payload.get("senderData", {}).get("chatId", sender_phone)
    
    await client.send_message(target_chat_id, kw_reply)
```

To get `rule_scope`, update `keyword_service.py` to also return scope:
```python
async def check_keywords(...) -> tuple[bool, str | None, str | None, str | None]:
    # returns (matched, reply_message, rule_id, scope)
    ...
    if matched:
        return True, rule.reply_message, str(rule.id), rule.scope
return False, None, None, None
```

Update all callers of `check_keywords` to handle the 4-tuple.

---

## PHASE 2 — Fix Bug #3: Show WhatsApp Groups

**Problem:** Groups page shows nothing because it's showing local DB groups, not actual WA groups.

**Fix:** Add a "sync from WhatsApp" button to `backend/app/api/v1/groups.py`:

```python
@router.post("/sync/{account_id}")
async def sync_groups_from_wa(account_id: str, db: AsyncSession = Depends(get_db)):
    """Fetch all WhatsApp groups this account is member of and save to DB."""
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    
    client = GreenAPIClient(account.instance_id, account.api_token)
    chats = await client.get_chats()
    
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
```

Update frontend Groups.jsx to add "همگام‌سازی با واتساپ" button that calls this endpoint.

---

## PHASE 3 — New Models

### `backend/app/models/contact_group.py`
```python
import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class ContactGroup(Base):
    __tablename__ = "contact_groups"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str] = mapped_column(String(20), default='#25D366')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class ContactGroupMember(Base):
    __tablename__ = "contact_group_members"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contact_groups.id"), index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contacts.id"), index=True)

class WaGroupCollection(Base):
    __tablename__ = "wa_group_collections"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class WaGroupCollectionMember(Base):
    __tablename__ = "wa_group_collection_members"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    collection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("wa_group_collections.id"), index=True)
    group_chat_id: Mapped[str] = mapped_column(String(200), nullable=False)
    group_name: Mapped[str | None] = mapped_column(String(200))
```

### `backend/app/models/reporting.py`
```python
import uuid
from datetime import datetime, date as date_type
from sqlalchemy import String, Text, Boolean, DateTime, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class EmergencyContact(Base):
    __tablename__ = "emergency_contacts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    purpose: Mapped[str] = mapped_column(String(100), default='alert')
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class ReportSubscriber(Base):
    __tablename__ = "report_subscribers"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class DailySendLog(Base):
    __tablename__ = "daily_send_logs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    date: Mapped[date_type] = mapped_column(Date, default=datetime.utcnow)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"))
    account_name: Mapped[str | None] = mapped_column(String(100))
    campaign_name: Mapped[str | None] = mapped_column(String(200))
    recipient_phone: Mapped[str | None] = mapped_column(String(20))
    recipient_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str | None] = mapped_column(String(50))
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class ProductMentionLog(Base):
    __tablename__ = "product_mention_logs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_name: Mapped[str | None] = mapped_column(String(500))
    product_id: Mapped[str | None] = mapped_column(String(100))
    sender_phone: Mapped[str | None] = mapped_column(String(20))
    sender_name: Mapped[str | None] = mapped_column(String(200))
    group_name: Mapped[str | None] = mapped_column(String(200))
    group_chat_id: Mapped[str | None] = mapped_column(String(200))
    instance_id: Mapped[str | None] = mapped_column(String(50))
    message_text: Mapped[str | None] = mapped_column(Text)
    mentioned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

Update `backend/app/models/__init__.py` to import all new models.

---

## PHASE 4 — Product Mention Detection in Webhook

In `backend/app/api/v1/webhook.py` `handle_incoming`, after saving to inbox_messages,
add product mention detection for group messages:

```python
        # Product mention detection (only in groups)
        if msg.is_group and text:
            try:
                from app.services.price_service import get_products
                from app.models.reporting import ProductMentionLog
                products = await get_products(200)  # get all products
                text_lower = text.lower()
                for product in products:
                    pname = (product.get("name") or "").lower()
                    if pname and len(pname) > 3 and pname in text_lower:
                        async with AsyncSessionLocal() as log_db:
                            mention = ProductMentionLog(
                                product_name=product.get("name"),
                                sender_phone=sender_phone,
                                sender_name=sender.get("senderName", ""),
                                group_name=sender.get("chatName", ""),
                                group_chat_id=sender.get("chatId", ""),
                                instance_id=instance_id,
                                message_text=text[:500]
                            )
                            log_db.add(mention)
                            await log_db.commit()
                        break  # one mention per message
            except Exception as e:
                print(f"[ProductMention] detection error: {e}")
```

Add Celery beat task to clear product_mention_logs older than 2 days:
```python
@celery_app.task(name="tasks.clear_old_product_mentions")
def task_clear_old_product_mentions():
    async def _c():
        from app.database import AsyncSessionLocal
        from app.models.reporting import ProductMentionLog
        from sqlalchemy import delete
        from datetime import datetime, timedelta
        async with AsyncSessionLocal() as db:
            cutoff = datetime.utcnow() - timedelta(days=2)
            await db.execute(delete(ProductMentionLog).where(ProductMentionLog.mentioned_at < cutoff))
            await db.commit()
    asyncio.run(_c())
```

Add to beat_schedule: `"clear-product-mentions": {"task": "tasks.clear_old_product_mentions", "schedule": 86400.0}`

---

## PHASE 5 — Night Report Service

### `backend/app/services/night_report.py`
```python
"""
Night report: sends daily summary via WhatsApp to report subscribers.
Called by Celery beat at 23:00 Tehran time.
"""
import asyncio
from datetime import datetime, date
import pytz
from app.database import AsyncSessionLocal
from app.models.reporting import ReportSubscriber, DailySendLog
from app.models.account import Account, AccountStatus
from app.services.green_api import GreenAPIClient
from sqlalchemy import select, func

TEHRAN_TZ = pytz.timezone("Asia/Tehran")


async def send_night_report():
    today = date.today()
    
    async with AsyncSessionLocal() as db:
        # Get today's stats
        stats_result = await db.execute(
            select(
                DailySendLog.account_name,
                func.count().label("total"),
                func.sum(
                    (DailySendLog.status == 'sent').cast(int)
                ).label("sent")
            )
            .where(DailySendLog.date == today)
            .group_by(DailySendLog.account_name)
        )
        stats = stats_result.all()
        
        if not stats:
            return  # Nothing to report
        
        # Build report message
        total_sent = sum(s.total for s in stats)
        report = f"📊 گزارش روزانه افراکالا\n"
        report += f"📅 {today.strftime('%Y/%m/%d')}\n\n"
        report += f"✅ کل ارسال امروز: {total_sent} پیام\n\n"
        for s in stats:
            report += f"• {s.account_name or 'نامشخص'}: {s.total} پیام\n"
        
        # Get active account for sending
        acc_result = await db.execute(
            select(Account).where(Account.status == AccountStatus.active)
        )
        account = acc_result.scalars().first()
        if not account:
            return
        
        client = GreenAPIClient(account.instance_id, account.api_token)
        
        # Get subscribers
        subs_result = await db.execute(
            select(ReportSubscriber).where(ReportSubscriber.is_active == True)
        )
        subscribers = subs_result.scalars().all()
        
        for sub in subscribers:
            try:
                await client.send_message(sub.phone, report)
                await asyncio.sleep(3)
            except Exception as e:
                print(f"[NightReport] Failed to send to {sub.phone}: {e}")
```

Add Celery task:
```python
@celery_app.task(name="tasks.send_night_report")
def task_send_night_report():
    from app.services.night_report import send_night_report
    asyncio.run(send_night_report())
```

Add to beat_schedule:
```python
"night-report": {"task": "tasks.send_night_report", "schedule": crontab(hour=23, minute=0, tz=pytz.timezone("Asia/Tehran"))}
```
Import crontab and pytz in celery_app.py.

---

## PHASE 6 — Update campaign_runner.py

After `cc.status = MessageStatus.sent`, add daily log entry:
```python
                    # Log to daily_send_logs for night report
                    from app.models.reporting import DailySendLog
                    log_entry = DailySendLog(
                        account_id=account.id,
                        account_name=account.name,
                        campaign_name=campaign.name,
                        recipient_phone=contact.phone,
                        recipient_name=contact.full_name,
                        status="sent"
                    )
                    db.add(log_entry)
```

Also update message building to support new campaign fields:

After `message = ...` generation block, add:
```python
                # Append seller signature if configured
                if campaign.append_seller_name and campaign.seller_name:
                    message += f"\n\n👤 {campaign.seller_name}"
                if campaign.append_seller_phone and campaign.seller_phone:
                    message += f"\n📱 {campaign.seller_phone}"
                    if campaign.seller_phone2:
                        message += f"\n☎️ {campaign.seller_phone2}"
                
                # Append Shamsi date if configured
                if campaign.append_date:
                    import jdatetime
                    today_jalali = jdatetime.date.today().strftime('%Y/%m/%d')
                    message += f"\n\n📅 {today_jalali}"
```

Add `jdatetime` to `backend/requirements.txt`.

Update GPT prompt in gpt_service.py to include emoji level:
```python
async def generate_message(first_name, last_name, gpt_prompt, products=None, emoji_level="medium"):
    emoji_instruction = {
        "none": "هیچ ایموجی استفاده نکن",
        "low": "حداکثر ۱-۲ ایموجی استفاده کن",
        "medium": "از ۳-۵ ایموجی مناسب استفاده کن",
        "high": "از ایموجی‌های متنوع و زیاد استفاده کن (۵-۱۰ ایموجی)"
    }.get(emoji_level, "از ۳-۵ ایموجی مناسب استفاده کن")
    # Add emoji_instruction to the system prompt
```

---

## PHASE 7 — New API Routers

### `backend/app/api/v1/contact_groups.py`
Full CRUD for contact groups + member management:
- GET /contact-groups/
- POST /contact-groups/
- PUT /contact-groups/{id}
- DELETE /contact-groups/{id}
- POST /contact-groups/{id}/members (add contact_ids list)
- DELETE /contact-groups/{id}/members/{contact_id}
- GET /contact-groups/{id}/contacts (list contacts in group)

### `backend/app/api/v1/wa_collections.py`
Full CRUD for WA group collections:
- GET /wa-collections/
- POST /wa-collections/
- PUT /wa-collections/{id}
- DELETE /wa-collections/{id}
- POST /wa-collections/{id}/groups (add {group_chat_id, group_name})
- DELETE /wa-collections/{id}/groups/{group_chat_id}
- GET /wa-collections/{id}/groups

### `backend/app/api/v1/reporting.py`
- GET /reporting/emergency-contacts
- POST /reporting/emergency-contacts
- DELETE /reporting/emergency-contacts/{id}
- GET /reporting/subscribers
- POST /reporting/subscribers
- DELETE /reporting/subscribers/{id}
- GET /reporting/daily-logs?date=YYYY-MM-DD
- GET /reporting/product-mentions
- DELETE /reporting/product-mentions (clear all)

### Update `backend/app/api/v1/campaigns.py`
Update `CampaignCreateBody` to include new fields:
```python
    description: str | None = None
    append_date: bool = False
    append_seller_name: bool = False
    seller_name: str | None = None
    append_seller_phone: bool = False
    seller_phone: str | None = None
    seller_phone2: str | None = None
    emoji_level: str = "medium"  # none/low/medium/high
    contact_group_id: str | None = None  # use contacts from this group
    wa_collection_id: str | None = None  # send to WA groups in this collection
    product_label_filter: str | None = None  # filter products by category
    is_always_on: bool = False
    is_active: bool = True
```

In `create_campaign`, persist all new fields.

In `start_campaign`, if `contact_group_id` is set:
- Fetch all contacts in that group
- Auto-add them as campaign_contacts

If `wa_collection_id` is set:
- Set campaign_scope='group'
- Auto-populate group_ids from collection members

### Update `backend/app/api/v1/dashboard.py`
Add endpoint:
```python
@router.get("/product-mentions/recent")
async def get_product_mentions(limit: int = 50, db: AsyncSession = Depends(get_db)):
    from app.models.reporting import ProductMentionLog
    result = await db.execute(
        select(ProductMentionLog).order_by(ProductMentionLog.mentioned_at.desc()).limit(limit)
    )
    items = result.scalars().all()
    return [
        {"product": i.product_name, "sender": i.sender_phone, "sender_name": i.sender_name,
         "group": i.group_name, "time": str(i.mentioned_at), "text": i.message_text}
        for i in items
    ]
```

### Update `backend/app/main.py`
Import and register new routers:
```python
from app.api.v1 import contact_groups, wa_collections, reporting as reporting_router
```

---

## PHASE 8 — Pricing Service: Product Label Filter

In `backend/app/services/price_service.py`, update the fetch function to support filtering by category:

```python
async def get_products(count: int = 3, category_filter: str | None = None) -> list[dict]:
    # ... existing cache logic ...
    
    # Build URL with optional category filter
    url = f"{settings.supabase_url}/rest/v1/products?is_active=eq.true&stock_status=neq.unavailable&select=id,name,model,capacity,brand_id,category"
    if category_filter:
        url += f"&category=eq.{category_filter}"
    
    # ... rest of fetch logic ...
```

Update `get_products` callers in campaign_runner.py to pass `campaign.product_label_filter` when set.

---

## PHASE 9 — Frontend Updates

### New pages:

#### `frontend/src/pages/ContactGroups.jsx`
- List contact groups (name, description, color, member count)
- Create/Edit/Delete group modal
- Click group → view members list
- Add contacts to group (searchable multi-select from contacts)
- Remove contact from group
- Color picker for group

#### `frontend/src/pages/WaCollections.jsx`
- List WA group collections
- Create/Edit/Delete
- Add WA groups to collection (input: group_chat_id + group_name)
- Remove from collection
- "همگام‌سازی گروه‌های واتساپ" button → calls /groups/sync/{account_id} first, then shows available groups to pick from

#### `frontend/src/pages/Reporting.jsx`
Three tabs:
1. **شماره‌های اضطراری** — CRUD for emergency contacts + report subscribers
   - Table: نام | شماره | نوع | فعال
   - Add/delete buttons
   - Separate section for "گیرندگان گزارش شبانه"
2. **گزارش روزانه** — Date picker + daily_send_logs table
   - Columns: حساب | کمپین | گیرنده | وضعیت | زمان
3. **رصد محصولات در گروه‌ها** — product_mention_logs table
   - Columns: محصول | فرستنده | گروه | پیام | زمان
   - "پاک کردن لاگ" button
   - Auto-refreshes every 30s

#### `frontend/src/pages/Products.jsx`
- Fetches all products from Supabase via backend
- Table: نام | مدل | ظرفیت | قیمت | وضعیت موجودی
- Search/filter
- Shows which WA group members mentioned each product (from product_mention_logs)
- Auto-refreshes every 60s

### Update `frontend/src/pages/Campaigns.jsx`
In create modal, add new fields:
- **توضیحات کمپین** (textarea, optional)
- **گروه مخاطبین** (dropdown from contact_groups API) — alternative to manual contact selection
- **مجموعه گروه‌های واتساپ** (dropdown from wa_collections) — for group campaigns
- **فیلتر محصولات بر اساس دسته** (text input, optional)
- **سطح ایموجی** (radio: بدون ایموجی / کم / متوسط / زیاد)
- **امضای فروشنده** section:
  - Checkbox "نام فروشنده اضافه شود"
  - If checked: text input for seller name
  - Checkbox "شماره فروشنده اضافه شود"
  - If checked: two text inputs (موبایل + ثابت)
- **تاریخ شمسی** checkbox "تاریخ امروز اخر پیام اضافه شود"

### Update `frontend/src/pages/Campaigns.jsx` — campaign card
Add Edit and Deactivate buttons to each campaign card:
- ✏️ ویرایش → opens edit modal (same as create but pre-filled)
- 🗑️ حذف → existing delete
- ⏸️ غیرفعال / ▶️ فعال → toggle is_active

### Update `frontend/src/components/Layout.jsx`
Restructure nav into 5 main categories with sub-items:

```javascript
const NAV = [
  { label: "داشبورد", to: "/", icon: "📊", end: true },
  {
    label: "ارسال پیام", icon: "📨", children: [
      { to: "/campaigns", label: "گروه‌های پیام" },
      { to: "/contact-groups", label: "گروه مخاطبین" },
      { to: "/wa-collections", label: "مجموعه گروه‌های واتساپ" },
    ]
  },
  {
    label: "مخاطبین", icon: "👥", children: [
      { to: "/contacts", label: "مخاطبین" },
      { to: "/blacklist", label: "لیست سیاه" },
    ]
  },
  {
    label: "حساب‌ها", icon: "📱", children: [
      { to: "/accounts", label: "حساب‌های واتساپ" },
      { to: "/account-schedules", label: "زمان‌بندی حساب‌ها" },
    ]
  },
  {
    label: "ابزارها", icon: "🔧", children: [
      { to: "/inbox", label: "صندوق ورودی" },
      { to: "/groups", label: "گروه‌های واتساپ" },
      { to: "/keyword-rules", label: "پاسخ خودکار" },
      { to: "/templates", label: "قالب‌های پیام" },
      { to: "/statuses", label: "استوری‌ها" },
      { to: "/files", label: "فایل‌ها" },
      { to: "/journals", label: "تاریخچه پیام‌ها" },
      { to: "/ai-settings", label: "هوش مصنوعی" },
    ]
  },
  {
    label: "گزارش‌ها", icon: "📋", children: [
      { to: "/reporting", label: "گزارش روزانه" },
      { to: "/products", label: "رصد محصولات" },
    ]
  },
];
```

Implement collapsible sub-menus in Layout.jsx.

### Add help text to Groups page
In `frontend/src/pages/Groups.jsx`:
- Add info banner: "برای نمایش گروه‌های واتساپ، ابتدا روی 'همگام‌سازی با واتساپ' کلیک کنید"
- Add "همگام‌سازی با واتساپ" button that calls POST /api/v1/groups/sync/{first_active_account_id}

### Explain Check WhatsApp button
In `frontend/src/pages/Contacts.jsx`, add tooltip/modal to "بررسی واتساپ" button:
"این دکمه شماره‌های انتخاب‌شده را بررسی می‌کند که آیا واتساپ دارند یا خیر. شماره‌هایی که واتساپ ندارند از ارسال کمپین خودکار حذف می‌شوند."

### Update `frontend/src/api.js`
Add API clients:
```javascript
export const ContactGroupsApi = {
  list: () => http.get("/contact-groups/").then(r => r.data),
  create: (body) => http.post("/contact-groups/", body).then(r => r.data),
  update: (id, body) => http.put(`/contact-groups/${id}`, body).then(r => r.data),
  delete: (id) => http.delete(`/contact-groups/${id}`).then(r => r.data),
  addMembers: (id, contact_ids) => http.post(`/contact-groups/${id}/members`, {contact_ids}).then(r => r.data),
  removeMember: (id, contact_id) => http.delete(`/contact-groups/${id}/members/${contact_id}`).then(r => r.data),
  contacts: (id) => http.get(`/contact-groups/${id}/contacts`).then(r => r.data),
};

export const WaCollectionsApi = {
  list: () => http.get("/wa-collections/").then(r => r.data),
  create: (body) => http.post("/wa-collections/", body).then(r => r.data),
  update: (id, body) => http.put(`/wa-collections/${id}`, body).then(r => r.data),
  delete: (id) => http.delete(`/wa-collections/${id}`).then(r => r.data),
  addGroup: (id, body) => http.post(`/wa-collections/${id}/groups`, body).then(r => r.data),
  removeGroup: (id, chat_id) => http.delete(`/wa-collections/${id}/groups/${chat_id}`).then(r => r.data),
  groups: (id) => http.get(`/wa-collections/${id}/groups`).then(r => r.data),
};

export const ReportingApi = {
  emergencyContacts: () => http.get("/reporting/emergency-contacts").then(r => r.data),
  addEmergency: (body) => http.post("/reporting/emergency-contacts", body).then(r => r.data),
  deleteEmergency: (id) => http.delete(`/reporting/emergency-contacts/${id}`).then(r => r.data),
  subscribers: () => http.get("/reporting/subscribers").then(r => r.data),
  addSubscriber: (body) => http.post("/reporting/subscribers", body).then(r => r.data),
  deleteSubscriber: (id) => http.delete(`/reporting/subscribers/${id}`).then(r => r.data),
  dailyLogs: (date) => http.get(`/reporting/daily-logs?date=${date}`).then(r => r.data),
  productMentions: () => http.get("/dashboard/product-mentions/recent").then(r => r.data),
  clearMentions: () => http.delete("/reporting/product-mentions").then(r => r.data),
};

export const ProductsApi = {
  list: () => http.get("/reporting/products").then(r => r.data),
};
```

---

## PHASE 10 — Add to requirements.txt

```
jdatetime==4.1.1
```

---

## PHASE 11 — Fix Account Status Display (Bug #22)

In `frontend/src/pages/Accounts.jsx`, fix status badge:
```javascript
// BEFORE (wrong):
const STATUS_FA = { active: "فعال", disconnected: "در انتظار", ... }

// AFTER (correct):
const STATUS_FA = {
  active: "متصل ✅",
  banned: "مسدود 🚫",
  disconnected: "قطع 🔌",
  pending: "در انتظار اتصال ⏳"
}
```

---

## PHASE 12 — Verify, Build, Push

```bash
cd C:/Users/AFRA/Desktop/bots/claudegreenapi/backend
pip install jdatetime --quiet
python -m py_compile app/main.py app/models/*.py app/services/*.py app/api/v1/*.py app/workers/*.py
python -m pytest tests/ -v
cd ..
docker-compose up -d --build backend worker beat
sleep 8
curl -s http://localhost:8002/health
curl -s http://localhost:8002/api/v1/contact-groups/
curl -s http://localhost:8002/api/v1/wa-collections/
curl -s http://localhost:8002/api/v1/reporting/subscribers
docker logs claudegreenapi-backend-1 --tail 20
cd frontend && npm run build && cd ..
docker-compose up -d --build --no-deps frontend
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:3002/
```

```bash
git add -A
git commit -m "feat: V5 — 27 new features

Bug fixes:
- Keyword reply scope: group replies now go to group chatId not PV
- Groups page: sync button to fetch WA groups, not just show empty DB
- Account status: correct labels (متصل/قطع/مسدود/در انتظار)

New features:
- Contact groups (virtual groups of contacts) with color coding
- WA group collections (group multiple WA groups for campaign targeting)
- Campaign: description, is_active toggle, edit button
- Campaign: seller signature (name + 2 phones, optional per campaign)  
- Campaign: Shamsi date append option
- Campaign: emoji level control (none/low/medium/high)
- Campaign: contact_group_id and wa_collection_id targeting
- Campaign: product category filter
- Campaign: is_always_on flag
- Product mention detection in WA group messages
- Product mention log auto-clear every 2 days
- Emergency contacts management
- Night report subscribers
- Daily send log (detailed per-message log)
- Night report: automatic WhatsApp summary at 23:00 Tehran
- Products page with mention tracking
- Reporting page (daily logs, product mentions, contacts)
- Collapsible 5-category nav menu
- Groups page sync button + info banner
- Contact check-WhatsApp tooltip explanation
- jdatetime dependency for Shamsi dates"
git push origin main
```

---

## NOTES

- مورد ۱۳ (broadcast lists/communities): Green API این را پشتیبانی نمی‌کند — communities فقط از app رسمی قابل مدیریت است.
- مورد ۱۲ (product label): در انتظار خروجی PowerShell از لپ‌تاپ برای تعیین ستون tags در Supabase.
- مورد ۱۰ (WA group collections): پیاده شد — یه مجموعه مجازی که شامل چند group_chat_id است.
- مورد ۲۰ (per-account per-hour schedule): قبلاً در V3 پیاده شده (account_hour_schedules).

---

## PHASE 13 — Product Label Filter (Real Implementation)

Schema confirmed from self-hosted Supabase (192.168.170.10):
- `product_labels`: id, title, color, description, is_active
- `product_label_links`: product_id, label_id, created_at
- GRANT SELECT already given to anon role

### New endpoint `backend/app/api/v1/reporting.py` — add:
```python
@router.get("/product-labels")
async def get_product_labels():
    """Fetch all active product labels from self-hosted Supabase."""
    import httpx
    from app.config import settings
    url = f"{settings.supabase_url}/rest/v1/product_labels?is_active=eq.true&select=id,title,color&order=weight.asc"
    headers = {"apikey": settings.supabase_anon_key, "Authorization": f"Bearer {settings.supabase_anon_key}"}
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(url, headers=headers)
        if r.status_code == 200:
            return r.json()
    return []
```

### Update `backend/app/services/price_service.py` — add label_id filter:
```python
async def get_products_by_label(label_id: str, count: int = 3) -> list[dict]:
    """Get products that have a specific label."""
    import httpx
    from app.config import settings
    
    headers = {
        "apikey": settings.supabase_anon_key,
        "Authorization": f"Bearer {settings.supabase_anon_key}"
    }
    
    # Get product_ids with this label
    links_url = f"{settings.supabase_url}/rest/v1/product_label_links?label_id=eq.{label_id}&select=product_id"
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(links_url, headers=headers)
        if r.status_code != 200:
            return []
        links = r.json()
    
    if not links:
        return []
    
    product_ids = [l["product_id"] for l in links]
    ids_filter = "(" + ",".join(product_ids) + ")"
    
    # Get products + prices
    products_url = f"{settings.supabase_url}/rest/v1/products?id=in.{ids_filter}&is_active=eq.true&select=id,name,model,capacity"
    prices_url = f"{settings.supabase_url}/rest/v1/product_computed_prices_public?product_id=in.{ids_filter}&select=product_id,rounded_sale_price"
    
    async with httpx.AsyncClient(timeout=10) as c:
        pr = await c.get(products_url, headers=headers)
        prr = await c.get(prices_url, headers=headers)
    
    products = pr.json() if pr.status_code == 200 else []
    prices = {p["product_id"]: p["rounded_sale_price"] for p in (prr.json() if prr.status_code == 200 else [])}
    
    result = []
    for p in products[:count]:
        result.append({"name": p.get("name", ""), "price": prices.get(p["id"])})
    
    return result
```

### Update `backend/app/services/campaign_runner.py`:
When `campaign.product_label_filter` is set (contains a label_id):
```python
        if campaign.include_products:
            if campaign.product_label_filter:
                from app.services.price_service import get_products_by_label
                products = await get_products_by_label(campaign.product_label_filter, campaign.product_count)
            else:
                products = await get_products(campaign.product_count)
```

### Update `frontend/src/api.js`:
```javascript
export const LabelsApi = {
  list: () => http.get("/reporting/product-labels").then(r => r.data),
};
```

### Update `frontend/src/pages/Campaigns.jsx` create modal:
When "افزودن محصولات روز" is checked, show a second dropdown:
"فیلتر بر اساس برچسب (اختیاری)" — loads from LabelsApi.list(), shows label title + color badge.
Sends `product_label_filter` (= selected label id) to create API.