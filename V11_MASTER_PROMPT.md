# CLAUDE CODE MASTER PROMPT — V11 (Status Scheduling, Reports, Auto-Join)
# Afrakala WhatsApp Sender
# Repo: https://github.com/mohammadrezaafra66-arch/greenapiwhatsapp
# Local: C:\Users\AFRA\Desktop\bots\claudegreenapi

## AUTONOMOUS EXECUTION CONTRACT
- Run every phase sequentially. NEVER ask for confirmation or present choices.
- At each decision point, pick the safest reasonable option, note it in the summary, continue.
- Verify → commit → push each logical unit (backend tests + browser-check frontend).
- Only hard-stop on irreversible data loss (dropping DB, force-push). Everything else: proceed.
- Use afrakala/whatsapp_sender for DB, real container/service names.
- Adapt all code snippets to the app's real conventions. Keep changes additive.
- Preserve ALL existing features.

## DB / ENV FACTS
- DB container: claudegreenapi-db-1, user afrakala, db whatsapp_sender
- Backend :8002, Frontend :3002
- Green API instance 7105325764, account 2e95cde4-fd12-40c0-b42c-3529705543d5
- Supabase self-hosted http://192.168.170.10:8000 (products, prices, brands, labels)

---

# ═══════════════════════════════════════════════
# FEATURE 1 — Status history + scheduled status roadmap
# ═══════════════════════════════════════════════

## PHASE 1 — Backend: status history from Green API

Add to `backend/app/services/green_api.py` if missing:
```python
    async def get_outgoing_statuses(self, minutes: int = 10080) -> list[dict]:
        """Get statuses we posted (last 7 days default)."""
        r = await self._get(f"getOutgoingStatuses?minutes={minutes}")
        return r if isinstance(r, list) else []

    async def get_status_statistic(self, status_id: str) -> dict:
        """Get who viewed a status."""
        r = await self._get(f"getStatusStatistic?idMessage={status_id}")
        return r if isinstance(r, dict) else {}
```

Add endpoints in `backend/app/api/v1/statuses.py`:
```python
@router.get("/history/{account_id}")
async def status_history(account_id: str, db: AsyncSession = Depends(get_db)):
    """Posted status history from Green API for this account."""
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    client = GreenAPIClient(account.instance_id, account.api_token)
    statuses = await client.get_outgoing_statuses(10080)
    return {"account": account.name, "statuses": statuses}

@router.get("/scheduled/{account_id}")
async def scheduled_statuses(account_id: str, db: AsyncSession = Depends(get_db)):
    """Future scheduled statuses for this account (from status_schedules table)."""
    result = await db.execute(
        select(StatusSchedule)
        .where(StatusSchedule.account_id == uuid.UUID(account_id))
        .where(StatusSchedule.is_active == True)
        .order_by(StatusSchedule.next_run_at)
    )
    schedules = result.scalars().all()
    from app.utils.shamsi import to_shamsi
    return [
        {
            "id": str(s.id),
            "status_type": s.status_type,
            "content_type": s.content_type,
            "next_run_shamsi": to_shamsi(s.next_run_at),
            "days_of_week": s.days_of_week,
            "times": s.times,
            "is_active": s.is_active,
        }
        for s in schedules
    ]
```

## PHASE 2 — Frontend: Statuses.jsx history + roadmap tabs

Add two tabs to the existing Statuses page:
- **تاریخچه استوری** — table of posted statuses (from /statuses/history/{account_id}): time, type, content preview, view count
- **برنامه آینده** — table of scheduled statuses per account (from /statuses/scheduled/{account_id}): shows exactly what each account WILL post, on which days/dates/times, Shamsi formatted

Account selector at top switches which account's history/schedule is shown.

---

# ═══════════════════════════════════════════════
# FEATURE 2 — Top repeated products report
# ═══════════════════════════════════════════════

## PHASE 3 — Backend: aggregate product mentions

Add endpoint in `backend/app/api/v1/reporting.py`:
```python
@router.get("/top-products")
async def top_repeated_products(limit: int = 150, days: int = 30, db: AsyncSession = Depends(get_db)):
    """
    Most-frequently-mentioned products across all groups/communities/broadcasts.
    Live aggregation from product_mention_logs.
    """
    from app.models.reporting import ProductMentionLog
    from datetime import datetime, timedelta
    from sqlalchemy import func as sa_func
    
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    result = await db.execute(
        select(
            ProductMentionLog.product_name,
            sa_func.count().label("mention_count"),
            sa_func.count(sa_func.distinct(ProductMentionLog.group_chat_id)).label("group_count"),
            sa_func.count(sa_func.distinct(ProductMentionLog.sender_phone)).label("sender_count"),
            sa_func.max(ProductMentionLog.mentioned_at).label("last_mention"),
        )
        .where(ProductMentionLog.mentioned_at >= cutoff)
        .group_by(ProductMentionLog.product_name)
        .order_by(sa_func.count().desc())
        .limit(limit)
    )
    rows = result.all()
    
    from app.utils.shamsi import to_shamsi
    return {
        "total_products": len(rows),
        "period_days": days,
        "products": [
            {
                "rank": i + 1,
                "product_name": r.product_name,
                "mention_count": r.mention_count,
                "group_count": r.group_count,
                "sender_count": r.sender_count,
                "last_mention_shamsi": to_shamsi(r.last_mention),
            }
            for i, r in enumerate(rows)
        ]
    }
```

## PHASE 4 — Frontend: top products report in Reporting page

Add a new tab/button "جدول محصولات پر تکرار" in Reporting.jsx:
- Fetches /reporting/top-products?limit=150
- Live table auto-refreshing every 30s
- Columns: رتبه | نام محصول | تعداد تکرار | تعداد گروه | تعداد فرستنده | آخرین ذکر
- Filter control for period (۷ روز / ۳۰ روز / ۹۰ روز) and limit (۵۰/۱۰۰/۱۵۰)
- Export to Excel button
- Rank badge coloring: top 10 gold, top 50 silver

---

# ═══════════════════════════════════════════════
# FEATURE 3 — Group/community/broadcast auto-join
# ═══════════════════════════════════════════════

## PHASE 5 — Investigate Green API join capability FIRST

IMPORTANT: Green API's standard API does NOT have a documented "join group by invite link" method for all plans. Before building, check what's available:
- Test if the instance supports a join method (some Green API versions have no join-by-link at all — joining via link is often a phone-only action).
- If NO join method exists: build the storage + management UI anyway, and implement join as a "best effort" that records the link and surfaces a clear status. Document the limitation honestly in the UI banner.

## PHASE 6 — Backend: group link registry

DB migration (main.py DDL):
```python
        ddl_v11_links = [
            """CREATE TABLE IF NOT EXISTS group_join_links (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                name varchar(300),
                invite_link text NOT NULL,
                link_type varchar(20) DEFAULT 'group',
                is_active boolean DEFAULT true,
                created_at timestamp DEFAULT now()
            )""",
            """CREATE TABLE IF NOT EXISTS account_join_status (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                account_id uuid REFERENCES accounts(id) ON DELETE CASCADE,
                link_id uuid REFERENCES group_join_links(id) ON DELETE CASCADE,
                status varchar(30) DEFAULT 'pending',
                joined_at timestamp,
                error text,
                UNIQUE(account_id, link_id)
            )""",
        ]
```

Endpoints in a new `backend/app/api/v1/join_links.py`:
```python
@router.get("/")
async def list_links(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GroupJoinLink).where(GroupJoinLink.is_active == True))
    return [{"id": str(l.id), "name": l.name, "invite_link": l.invite_link, "link_type": l.link_type} for l in result.scalars().all()]

@router.post("/")
async def add_link(name: str, invite_link: str, link_type: str = "group", db: AsyncSession = Depends(get_db)):
    link = GroupJoinLink(name=name, invite_link=invite_link, link_type=link_type)
    db.add(link)
    await db.commit()
    return {"id": str(link.id)}

@router.post("/bulk")
async def add_links_bulk(links: list[dict], db: AsyncSession = Depends(get_db)):
    """Add multiple links at once. Each: {name, invite_link, link_type}."""
    added = 0
    for l in links:
        if l.get("invite_link"):
            db.add(GroupJoinLink(name=l.get("name", ""), invite_link=l["invite_link"], link_type=l.get("link_type", "group")))
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

@router.post("/join-all/{account_id}")
async def join_all_links(account_id: str, db: AsyncSession = Depends(get_db)):
    """Attempt to join all registered links with this account (background task)."""
    from app.workers.tasks import task_join_all_links
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    result = await db.execute(select(GroupJoinLink).where(GroupJoinLink.is_active == True))
    links = [(str(l.id), l.invite_link, l.name) for l in result.scalars().all()]
    task = task_join_all_links.delay(str(account.id), account.instance_id, account.api_token, links)
    return {"task_id": task.id, "links_to_join": len(links)}
```

Add join method to green_api.py (attempt — Green API may not support it):
```python
    async def join_group_via_link(self, invite_link: str) -> dict:
        """
        Attempt to join a group via invite link.
        NOTE: Green API support for this is version/plan dependent.
        Extract invite code from link and try. Returns result or error.
        """
        # Extract code from https://chat.whatsapp.com/XXXX
        code = invite_link.rstrip("/").split("/")[-1]
        try:
            r = await self._post("joinGroupViaLink", {"inviteLink": invite_link})
            return {"success": True, "response": r}
        except Exception as e:
            return {"success": False, "error": str(e)}
```

Celery task `task_join_all_links`: iterates links, calls join with 5s delay between each (avoid rate limit), records status in account_join_status. If join method returns error (unsupported), record status="unsupported" with the error — do not crash.

## PHASE 7 — AUTO-JOIN on account connect

When a new account becomes authorized (in the account state sync task or QR-connect flow), automatically queue task_join_all_links for it. Add this hook to the account authorization detection so every newly-connected number auto-joins all registered links.

## PHASE 8 — Frontend: JoinLinks.jsx page

New page under "ابزارها" nav: "لینک‌های گروه و کانال"
- List of registered links (name, type badge, link)
- Add single link form (name + link + type: گروه/انجمن/لیست انتشار)
- Bulk paste: textarea where user pastes multiple links (one per line), parse and bulk-add
- Per-account "عضویت در همه" button → calls join-all, shows progress
- Status table: which accounts joined which links (joined/pending/unsupported/error)
- Honest info banner explaining that WhatsApp/Green API may restrict programmatic joining, and that joining may need to be completed from the phone for some link types

---

# ═══════════════════════════════════════════════
# FEATURE 4 — Dynamic status scheduling per account
# ═══════════════════════════════════════════════

## PHASE 9 — DB: status schedules

```python
        ddl_v11_status = [
            """CREATE TABLE IF NOT EXISTS status_schedules (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                account_id uuid REFERENCES accounts(id) ON DELETE CASCADE,
                name varchar(200),
                status_type varchar(50) NOT NULL,
                content_type varchar(30) DEFAULT 'text',
                intro_subtype varchar(50),
                custom_text text,
                show_price boolean DEFAULT false,
                include_image boolean DEFAULT false,
                include_caption boolean DEFAULT true,
                image_url text,
                product_selection varchar(20) DEFAULT 'random',
                product_pool jsonb,
                product_pick_count integer DEFAULT 3,
                days_of_week jsonb,
                specific_dates jsonb,
                times jsonb,
                is_active boolean DEFAULT true,
                next_run_at timestamp,
                last_run_at timestamp,
                created_at timestamp DEFAULT now()
            )""",
        ]
```

status_type values: intro (معرفی مجموعه) | special_offer (پیشنهاد ویژه) | custom (متن دلخواه)
intro_subtype values: history (تاریخچه) | services (خدمات) | differentiators (تمایزها) | collaboration (شیوه همکاری) | purchase (شیوه خرید) | contact (راه‌های ارتباطی)
content_type: text | text_price | image | image_caption
product_selection: manual | random

## PHASE 10 — Backend: intro content templates

Create `backend/app/services/status_content.py`:
```python
"""Pre-written Afrakala intro status content (Persian)."""

INTRO_CONTENT = {
    "history": {
        "title": "تاریخچه افراکالا",
        "text": "🏢 افراکالا\nبا سال‌ها تجربه در عرصه عمده‌فروشی لوازم خانگی، همراه مطمئن کسب‌وکار شما هستیم. از یک فروشگاه کوچک تا یکی از بزرگ‌ترین پخش‌کننده‌های لوازم خانگی."
    },
    "services": {
        "title": "خدمات افراکالا",
        "text": "🛎 خدمات ما:\n✅ عمده‌فروشی با قیمت رقابتی\n✅ تنوع بالای محصولات\n✅ تحویل سریع\n✅ ضمانت اصالت کالا\n✅ پشتیبانی حرفه‌ای"
    },
    "differentiators": {
        "title": "تمایزهای افراکالا",
        "text": "⭐ چرا افراکالا؟\n🔹 قیمت مستقیم از منبع\n🔹 بدون واسطه\n🔹 به‌روزرسانی لحظه‌ای قیمت\n🔹 مشاوره تخصصی\n🔹 اعتماد صدها همکار"
    },
    "collaboration": {
        "title": "شیوه همکاری",
        "text": "🤝 همکاری با افراکالا:\n۱. عضویت در کانال\n۲. دریافت لیست قیمت روزانه\n۳. ثبت سفارش\n۴. تحویل سریع\nهمین امروز همکار ما شوید!"
    },
    "purchase": {
        "title": "شیوه خرید",
        "text": "🛒 مراحل خرید:\n۱. انتخاب محصول از لیست\n۲. تماس با کارشناس فروش\n۳. تأیید سفارش و قیمت\n۴. پرداخت و ارسال\nساده و سریع!"
    },
    "contact": {
        "title": "راه‌های ارتباطی",
        "text": "📞 ارتباط با افراکالا:\n☎️ تلفن: [شماره]\n📱 واتساپ: همین شماره\n🌐 آدرس: [آدرس]\nمنتظر تماس شما هستیم!"
    },
}

def get_intro_text(subtype: str) -> str:
    return INTRO_CONTENT.get(subtype, INTRO_CONTENT["history"])["text"]
```

## PHASE 11 — Backend: status scheduler service + Celery

Create `backend/app/services/status_scheduler.py`:
```python
"""Builds and posts scheduled statuses per account per plan."""
import random
from datetime import datetime
import pytz
from app.database import AsyncSessionLocal
from app.models.status_schedule import StatusSchedule
from app.models.account import Account
from app.services.green_api import GreenAPIClient
from app.services.status_content import get_intro_text
from app.services.price_service import get_products, get_products_by_label
from sqlalchemy import select

TEHRAN_TZ = pytz.timezone("Asia/Tehran")

async def build_status_text(schedule) -> str:
    """Build the status text based on schedule config."""
    if schedule.status_type == "intro":
        return get_intro_text(schedule.intro_subtype or "history")
    
    if schedule.status_type == "custom":
        return schedule.custom_text or ""
    
    if schedule.status_type == "special_offer":
        # Select products
        pool = schedule.product_pool or []
        pick = schedule.product_pick_count or 3
        
        if schedule.product_selection == "manual" and pool:
            # pool contains product identifiers; pick N randomly from the chosen pool
            selected_ids = random.sample(pool, min(pick, len(pool)))
            products = await _fetch_products_by_ids(selected_ids)
        else:
            # random from all products
            all_products = await get_products(50)
            products = random.sample(all_products, min(pick, len(all_products)))
        
        text = "🔥 پیشنهاد ویژه افراکالا 🔥\n\n"
        for p in products:
            if schedule.show_price and p.get("price"):
                text += f"• {p['name']}: {p['price']:,} تومان\n"
            else:
                text += f"• {p['name']}\n"
        text += "\n📞 برای سفارش تماس بگیرید"
        return text
    
    return ""

async def post_scheduled_status(schedule_id: str):
    """Post one scheduled status now."""
    async with AsyncSessionLocal() as db:
        schedule = await db.get(StatusSchedule, schedule_id)
        if not schedule or not schedule.is_active:
            return
        account = await db.get(Account, schedule.account_id)
        if not account or account.status.value != "active":
            return
        
        client = GreenAPIClient(account.instance_id, account.api_token)
        text = await build_status_text(schedule)
        
        try:
            if schedule.content_type in ("image", "image_caption") and schedule.image_url:
                caption = text if schedule.include_caption else ""
                await client.send_media_status(schedule.image_url, caption)
            else:
                await client.send_text_status(text)
            
            schedule.last_run_at = datetime.utcnow()
            await db.commit()
        except Exception as e:
            print(f"[StatusScheduler] {e}")
```

Add send_text_status / send_media_status to green_api.py if missing:
```python
    async def send_text_status(self, text: str, bg_color: str = "#25D366") -> dict:
        r = await self._post("sendTextStatus", {"message": text, "backgroundColor": bg_color})
        return r

    async def send_media_status(self, url: str, caption: str = "") -> dict:
        r = await self._post("sendMediaStatus", {"urlFile": url, "fileName": "status.jpg", "caption": caption})
        return r
```

Celery beat task (runs every 5 min) that checks all active status_schedules and posts any whose scheduled time (day-of-week + time, or specific date + time) matches the current Tehran time and hasn't run in this slot yet:
```python
@celery_app.task(name="tasks.check_status_schedules")
def task_check_status_schedules():
    from app.services.status_scheduler import check_and_post_due_statuses
    run_async(check_and_post_due_statuses())
```
Add to beat_schedule: every 300 seconds.

check_and_post_due_statuses logic:
- For each active schedule, compute if NOW (Tehran) matches days_of_week + times OR specific_dates + times
- Dedup: don't post if last_run_at is within the same hour slot
- Post via post_scheduled_status

## PHASE 12 — Frontend: StatusScheduler.jsx page

New page under "ابزارها": "برنامه استوری"

Create/edit status schedule modal with full config:
1. **حساب** — account dropdown
2. **نوع استوری**: معرفی مجموعه / پیشنهاد ویژه / متن دلخواه
3. If معرفی مجموعه → **زیرنوع**: تاریخچه / خدمات / تمایزها / شیوه همکاری / شیوه خرید / راه‌های ارتباطی
4. If پیشنهاد ویژه:
   - **انتخاب محصول**: دستی / رندوم
   - If دستی → multi-select product picker (pick pool, e.g. 15 products)
   - **تعداد انتخاب**: number (e.g. always pick 3 from the pool) — configurable
   - **نمایش قیمت**: checkbox (if on → live price)
5. If متن دلخواه → textarea
6. **نوع محتوا**: متنی / متنی با قیمت / عکس / عکس با کپشن
7. If عکس → image URL input + **کپشن**: checkbox
8. **زمان‌بندی**:
   - **روزهای هفته**: multi-select (شنبه...جمعه)
   - OR **تاریخ‌های مشخص** (شمسی): add specific dates
   - **ساعت‌ها**: add times (e.g. 09:00, 14:00, 20:00)
9. **فعال/غیرفعال** toggle

List view: all schedules grouped by account, showing type, timing summary, next run (Shamsi), active status. Edit/delete/toggle per schedule.

api.js additions:
```javascript
export const StatusScheduleApi = {
  list: (accountId) => http.get(`/status-schedules/?account_id=${accountId}`).then(r => r.data),
  create: (body) => http.post("/status-schedules/", body).then(r => r.data),
  update: (id, body) => http.put(`/status-schedules/${id}`, body).then(r => r.data),
  delete: (id) => http.delete(`/status-schedules/${id}`).then(r => r.data),
  toggle: (id) => http.post(`/status-schedules/${id}/toggle`).then(r => r.data),
  history: (accountId) => http.get(`/statuses/history/${accountId}`).then(r => r.data),
  scheduled: (accountId) => http.get(`/statuses/scheduled/${accountId}`).then(r => r.data),
};
export const TopProductsApi = {
  get: (limit = 150, days = 30) => http.get(`/reporting/top-products?limit=${limit}&days=${days}`).then(r => r.data),
};
export const JoinLinksApi = {
  list: () => http.get("/join-links/").then(r => r.data),
  add: (name, link, type) => http.post(`/join-links/?name=${encodeURIComponent(name)}&invite_link=${encodeURIComponent(link)}&link_type=${type}`).then(r => r.data),
  bulk: (links) => http.post("/join-links/bulk", links).then(r => r.data),
  delete: (id) => http.delete(`/join-links/${id}`).then(r => r.data),
  joinAll: (accountId) => http.post(`/join-links/join-all/${accountId}`).then(r => r.data),
};
```

Models: create backend/app/models/status_schedule.py and backend/app/models/join_links.py with the tables above. Import in models/__init__.py. Register all new routers in main.py.

---

# ═══════════════════════════════════════════════
# VERIFICATION & DEPLOY
# ═══════════════════════════════════════════════

```bash
cd C:/Users/AFRA/Desktop/bots/claudegreenapi/backend
python -m py_compile app/main.py app/models/*.py app/services/*.py app/api/v1/*.py app/workers/*.py
python -m pytest tests/ -v
cd ..
docker-compose up -d --build backend worker beat
sleep 10
curl -s http://localhost:8002/health/detailed | python -m json.tool
curl -s "http://localhost:8002/api/v1/reporting/top-products?limit=10" | python -m json.tool
curl -s "http://localhost:8002/api/v1/join-links/" | python -m json.tool
curl -s "http://localhost:8002/api/v1/status-schedules/?account_id=2e95cde4-fd12-40c0-b42c-3529705543d5"
cd frontend && npm run build && cd ..
docker-compose up -d --build --no-deps frontend
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:3002/
```

Commit each feature separately:
- FEATURE 1: "feat: V11.1 — status history + scheduled status roadmap view"
- FEATURE 2: "feat: V11.2 — top repeated products live report + Excel export"
- FEATURE 3: "feat: V11.3 — group/community/broadcast link registry + auto-join on connect"
- FEATURE 4: "feat: V11.4 — dynamic per-account status scheduler (intro/special-offer, price/image, day/date/time)"

Push after each.

## AUTONOMOUS NOTES TO RECORD IN SUMMARY
- If Green API join-by-link is unsupported on this plan: record it, keep the registry + UI, mark joins "unsupported" gracefully.
- If sendTextStatus/sendMediaStatus behave differently than expected: adapt and note.
- Confirm the status scheduler dedup prevents double-posting in the same time slot.