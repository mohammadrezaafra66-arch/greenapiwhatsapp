# CLAUDE CODE MASTER PROMPT — V8 (Features 35-43)
# Afrakala WhatsApp Sender
# Repo: https://github.com/mohammadrezaafra66-arch/greenapiwhatsapp
# Local: C:\Users\AFRA\Desktop\bots\claudegreenapi

## EXECUTION CONTRACT
Run every phase sequentially. Never stop for confirmation. Fix errors before moving on.
At end: all 47 tests pass, rebuild, push.

---

## PHASE 0 — DB migrations

In `backend/app/main.py` lifespan DDL block, add:

```python
        ddl_v8 = [
            # Feature 35: schedule dates per campaign (already have columns, add Shamsi display support via backend)
            # Feature 37: parallel account sending
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS parallel_accounts boolean DEFAULT false",
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS max_parallel_accounts integer DEFAULT 1",
            # Feature 39: per-account send limits with Meta standards
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS max_daily_absolute integer DEFAULT 200",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS incoming_ratio_multiplier numeric DEFAULT 0.5",
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS max_sends_per_minute numeric DEFAULT 2.0",
            # Feature 40: group admin tracking
            "ALTER TABLE whatsapp_groups ADD COLUMN IF NOT EXISTS is_admin boolean DEFAULT false",
            "ALTER TABLE whatsapp_groups ADD COLUMN IF NOT EXISTS participant_count integer DEFAULT 0",
            # Feature 42: hide price option in campaigns
            "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS show_product_prices boolean DEFAULT true",
        ]
        for stmt in ddl_v8:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                print(f"[DDL V8] {e}")
```

---

## PHASE 1 — Feature 35: Shamsi date display + campaign scheduling UI

### Backend: add Jalali date utility

Create `backend/app/utils/shamsi.py`:

```python
"""Utilities for Shamsi (Jalali) date conversion."""
import jdatetime
from datetime import datetime
import pytz

TEHRAN_TZ = pytz.timezone("Asia/Tehran")


def to_shamsi(dt: datetime | None) -> str | None:
    """Convert UTC datetime to Shamsi string for display."""
    if not dt:
        return None
    tehran_dt = dt.replace(tzinfo=pytz.utc).astimezone(TEHRAN_TZ)
    jdt = jdatetime.datetime.fromgregorian(datetime=tehran_dt)
    return jdt.strftime("%Y/%m/%d %H:%M")


def from_shamsi(shamsi_str: str) -> datetime | None:
    """Parse Shamsi datetime string to UTC datetime."""
    if not shamsi_str:
        return None
    try:
        jdt = jdatetime.datetime.strptime(shamsi_str, "%Y/%m/%d %H:%M")
        gregorian = jdt.togregorian()
        tehran_dt = TEHRAN_TZ.localize(gregorian)
        return tehran_dt.astimezone(pytz.utc).replace(tzinfo=None)
    except Exception:
        return None
```

### Backend: update campaigns API to accept Shamsi dates

In `backend/app/api/v1/campaigns.py`, update CampaignCreateBody:
```python
    schedule_start_shamsi: str | None = None  # "1403/01/15 08:00"
    schedule_end_shamsi: str | None = None    # "1403/01/20 22:00"
```

In create_campaign handler, convert Shamsi to UTC:
```python
    from app.utils.shamsi import from_shamsi
    if body.schedule_start_shamsi:
        campaign.schedule_start = from_shamsi(body.schedule_start_shamsi)
    if body.schedule_end_shamsi:
        campaign.schedule_end = from_shamsi(body.schedule_end_shamsi)
```

In list/progress endpoints, add Shamsi display:
```python
    from app.utils.shamsi import to_shamsi
    # Add to response:
    "schedule_start_shamsi": to_shamsi(c.schedule_start),
    "schedule_end_shamsi": to_shamsi(c.schedule_end),
```

Also update campaign_runner.py to check schedule_end:
```python
        # Check if campaign has ended
        if campaign.schedule_end and datetime.utcnow() > campaign.schedule_end:
            campaign.status = CampaignStatus.completed
            campaign.completed_at = datetime.utcnow()
            await db.commit()
            return
        
        # Check if campaign hasn't started yet
        if campaign.schedule_start and datetime.utcnow() < campaign.schedule_start:
            # Re-queue for later
            seconds_until_start = (campaign.schedule_start - datetime.utcnow()).total_seconds()
            task_run_campaign.apply_async(args=[campaign_id], countdown=int(seconds_until_start))
            campaign.status = CampaignStatus.paused
            campaign.pause_reason = f"زمان شروع: {to_shamsi(campaign.schedule_start)}"
            await db.commit()
            return
```

### Frontend: add Shamsi date picker to campaign modal

In `frontend/src/pages/Campaigns.jsx`, in the create/edit modal, replace plain datetime inputs with Shamsi format:

```jsx
{/* Schedule section */}
<div className="border-t border-gray-700 pt-3 mt-3">
  <h4 className="text-sm font-semibold mb-2">⏰ زمان‌بندی ارسال</h4>
  <div className="grid grid-cols-2 gap-2">
    <div>
      <label className="text-xs text-gray-400">شروع (شمسی)</label>
      <input 
        placeholder="۱۴۰۳/۰۱/۱۵ ۰۸:۰۰"
        value={form.schedule_start_shamsi}
        onChange={e => setForm({...form, schedule_start_shamsi: e.target.value})}
        className="input-dark text-sm w-full mt-1"
        dir="ltr"
      />
      <p className="text-xs text-gray-500 mt-1">فرمت: YYYY/MM/DD HH:MM</p>
    </div>
    <div>
      <label className="text-xs text-gray-400">پایان (شمسی)</label>
      <input 
        placeholder="۱۴۰۳/۰۱/۲۰ ۲۲:۰۰"
        value={form.schedule_end_shamsi}
        onChange={e => setForm({...form, schedule_end_shamsi: e.target.value})}
        className="input-dark text-sm w-full mt-1"
        dir="ltr"
      />
    </div>
  </div>
</div>
```

Show Shamsi dates on campaign cards:
```jsx
{(campaign.schedule_start_shamsi || campaign.schedule_end_shamsi) && (
  <div className="text-xs text-gray-400 mt-1">
    📅 {campaign.schedule_start_shamsi || "—"} تا {campaign.schedule_end_shamsi || "—"}
  </div>
)}
```

---

## PHASE 2 — Feature 36: Pre-send validation engine

### Backend: new endpoint

In `backend/app/api/v1/dashboard.py`, add:

```python
@router.post("/validate-campaign")
async def validate_campaign(
    contact_count: int,
    account_ids: list[str],
    min_delay: int = 45,
    max_delay: int = 110,
    hours_available: int = 14,  # e.g. 08:00-22:00 = 14 hours
    db: AsyncSession = Depends(get_db)
):
    """
    Pre-send validation engine.
    Returns feasibility analysis and recommendations.
    """
    from app.services.rate_limiter import DEFAULT_SCHEDULE
    import math
    
    # Get accounts
    accounts = []
    for aid in account_ids:
        a = await db.get(Account, uuid.UUID(aid))
        if a and a.status == AccountStatus.active:
            accounts.append(a)
    
    if not accounts:
        return {"feasible": False, "reason": "هیچ حساب فعالی انتخاب نشده", "color": "red"}
    
    # Calculate max sends per day per account
    avg_limit = sum(a.computed_daily_limit for a in accounts) / len(accounts)
    total_daily_capacity = sum(min(a.computed_daily_limit, a.max_daily_absolute) for a in accounts)
    
    # Average delay in seconds
    avg_delay = (min_delay + max_delay) / 2
    
    # Messages per hour at this speed
    msgs_per_hour = 3600 / avg_delay
    
    # Total hourly capacity from schedule
    total_hourly_from_schedule = sum(
        slot["max_per_hour"] * (slot["hour_end"] - slot["hour_start"])
        for slot in DEFAULT_SCHEDULE
    )
    
    # Estimated days to complete
    days_needed = math.ceil(contact_count / total_daily_capacity) if total_daily_capacity > 0 else 999
    
    # Hours needed at current speed (ignoring daily limits)
    hours_needed_raw = (contact_count * avg_delay) / 3600
    
    # Warnings
    warnings = []
    
    if total_daily_capacity < 10:
        warnings.append("⚠️ محدودیت روزانه بسیار پایین — حساب‌ها نیاز به warm-up دارند")
    
    if avg_delay < 30:
        warnings.append("⚠️ تاخیر کمتر از ۳۰ ثانیه خطر بلاک دارد")
    
    if contact_count / len(accounts) > 100:
        warnings.append(f"⚠️ هر حساب باید {contact_count // len(accounts)} پیام بفرستد — در چند روز تقسیم کنید")
    
    if days_needed > 30:
        warnings.append(f"⛔ با این تنظیمات {days_needed} روز طول می‌کشد")
    
    # Recommendations
    recommendations = []
    
    if days_needed > 7:
        extra_accounts_needed = math.ceil(contact_count / (7 * total_daily_capacity / len(accounts))) - len(accounts)
        if extra_accounts_needed > 0:
            recommendations.append(f"💡 برای تکمیل در ۷ روز: {extra_accounts_needed} حساب اضافی نیاز دارید")
    
    if avg_delay < 45:
        recommendations.append("💡 تاخیر را به حداقل ۴۵ ثانیه افزایش دهید")
    
    # Feasibility
    if days_needed <= 7 and len(warnings) == 0:
        color = "green"
        feasible = True
        status = "✅ تنظیمات مناسب است"
    elif days_needed <= 30 and not any("⛔" in w for w in warnings):
        color = "amber"
        feasible = True
        status = "⚠️ ممکن است اما نیاز به بررسی دارد"
    else:
        color = "red"
        feasible = False
        status = "❌ تنظیمات مناسب نیست — تغییر لازم است"
    
    return {
        "feasible": feasible,
        "color": color,
        "status": status,
        "summary": {
            "contact_count": contact_count,
            "active_accounts": len(accounts),
            "total_daily_capacity": total_daily_capacity,
            "avg_daily_per_account": round(avg_limit, 1),
            "avg_delay_seconds": avg_delay,
            "msgs_per_hour_per_account": round(msgs_per_hour, 1),
            "estimated_days": days_needed,
            "estimated_hours_raw": round(hours_needed_raw, 1),
        },
        "warnings": warnings,
        "recommendations": recommendations,
    }
```

### Frontend: validation engine panel in Campaigns.jsx

Add a "بررسی امکان‌سنجی" button in the campaign creation wizard Step 2 (after selecting contacts):

```jsx
const [validation, setValidation] = useState(null);
const [validating, setValidating] = useState(false);

const runValidation = async () => {
  setValidating(true);
  try {
    const res = await http.post("/dashboard/validate-campaign", null, {
      params: {
        contact_count: selectedContacts.length,
        account_ids: selectedAccountIds,
        min_delay: form.min_delay || 45,
        max_delay: form.max_delay || 110,
      }
    });
    setValidation(res.data);
  } finally {
    setValidating(false);
  }
};

// Render validation result:
{validation && (
  <div className={`rounded-lg p-4 mt-3 border ${
    validation.color === "green" ? "border-green-500 bg-green-900/20" :
    validation.color === "amber" ? "border-amber-500 bg-amber-900/20" :
    "border-red-500 bg-red-900/20"
  }`}>
    <p className="font-bold text-sm mb-2">{validation.status}</p>
    <div className="grid grid-cols-2 gap-2 text-xs mb-3">
      <span>مخاطبین: {validation.summary.contact_count}</span>
      <span>حساب‌های فعال: {validation.summary.active_accounts}</span>
      <span>ظرفیت روزانه کل: {validation.summary.total_daily_capacity}</span>
      <span>تخمین زمان: {validation.summary.estimated_days} روز</span>
    </div>
    {validation.warnings.map((w, i) => (
      <p key={i} className="text-xs mb-1">{w}</p>
    ))}
    {validation.recommendations.map((r, i) => (
      <p key={i} className="text-xs text-blue-300 mb-1">{r}</p>
    ))}
  </div>
)}

<button onClick={runValidation} disabled={validating}
        className="btn-outline w-full mt-2 text-sm">
  {validating ? "در حال بررسی..." : "🔍 بررسی امکان‌سنجی"}
</button>
```

---

## PHASE 3 — Feature 37: Parallel multi-account sending

In `backend/app/services/campaign_runner.py`, add parallel sending mode:

```python
async def run_campaign_parallel(campaign_id: str, account_ids: list[str]):
    """Run campaign using multiple accounts in parallel — splits contacts across accounts."""
    async with AsyncSessionLocal() as db:
        campaign = await db.get(Campaign, uuid.UUID(campaign_id))
        if not campaign or campaign.status != CampaignStatus.running:
            return
        
        # Get pending contacts
        result = await db.execute(
            select(CampaignContact, Contact)
            .join(Contact, CampaignContact.contact_id == Contact.id)
            .where(
                CampaignContact.campaign_id == campaign.id,
                CampaignContact.status == MessageStatus.pending
            )
        )
        pending = result.all()
        if not pending:
            return
        
        # Split contacts across accounts
        chunks = [[] for _ in account_ids]
        for i, item in enumerate(pending):
            chunks[i % len(account_ids)].append(item)
        
        # Run each chunk concurrently
        tasks = []
        for acc_id, chunk in zip(account_ids, chunks):
            if chunk:
                tasks.append(_send_chunk(campaign_id, acc_id, chunk))
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Check completion
        async with AsyncSessionLocal() as db2:
            camp = await db2.get(Campaign, uuid.UUID(campaign_id))
            remaining = await db2.execute(
                select(CampaignContact).where(
                    CampaignContact.campaign_id == camp.id,
                    CampaignContact.status == MessageStatus.pending
                )
            )
            if not remaining.scalars().first():
                camp.status = CampaignStatus.completed
                camp.completed_at = datetime.utcnow()
                await db2.commit()


async def _send_chunk(campaign_id: str, account_id: str, contacts: list):
    """Send a chunk of contacts using one specific account."""
    # Import here to avoid circular
    from app.database import AsyncSessionLocal
    # ... similar to run_campaign but fixed to one account
    # Use existing run_campaign logic but with account pre-assigned
    pass  # Implementation follows run_campaign closely but account is fixed
```

In campaign Celery task, check parallel flag:
```python
@celery_app.task(bind=True, name="tasks.run_campaign", max_retries=3)
def task_run_campaign(self, campaign_id: str, account_ids: list[str] | None = None):
    try:
        import asyncio
        from app.database import AsyncSessionLocal
        from sqlalchemy import select as sa_select
        from app.models.campaign import Campaign

        async def _get_parallel():
            async with AsyncSessionLocal() as db:
                c = await db.get(Campaign, __import__("uuid").UUID(campaign_id))
                return c.parallel_accounts if c else False

        is_parallel = asyncio.run(_get_parallel())
        
        if is_parallel and account_ids:
            from app.services.campaign_runner import run_campaign_parallel
            asyncio.run(run_campaign_parallel(campaign_id, account_ids))
        else:
            from app.services.campaign_runner import run_campaign
            asyncio.run(run_campaign(campaign_id))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)
```

In `start_campaign` API endpoint, if `parallel_accounts=true`:
```python
    # Get active accounts
    if campaign.parallel_accounts:
        acc_result = await db.execute(select(Account).where(Account.status == AccountStatus.active))
        active_accounts = [str(a.id) for a in acc_result.scalars().all()]
        task_run_campaign.delay(campaign_id, active_accounts)
    else:
        task_run_campaign.delay(campaign_id)
```

In campaign create body, add:
```python
    parallel_accounts: bool = False
    max_parallel_accounts: int = 1
```

In frontend Campaigns.jsx create modal, add toggle:
```jsx
<div className="flex items-center justify-between mt-2">
  <span className="text-sm">ارسال موازی با چند حساب</span>
  <input type="checkbox" checked={form.parallel_accounts}
         onChange={e => setForm({...form, parallel_accounts: e.target.checked})} />
</div>
{form.parallel_accounts && (
  <p className="text-xs text-blue-300 mt-1">
    💡 مخاطبین به صورت مساوی بین حساب‌های فعال تقسیم می‌شوند
  </p>
)}
```

---

## PHASE 4 — Feature 39: Per-account limits with Meta standards

### Backend: update computed_daily_limit

In `backend/app/models/account.py`, update `computed_daily_limit` property:

```python
    @property
    def computed_daily_limit(self) -> int:
        """Calculate daily limit following Meta best practices."""
        days = self.days_active or 0
        
        # Week 1 hard cap (already enforced in campaign_runner for warmup)
        if days < 7:
            return min(5, self.max_daily_absolute)
        
        # Base formula
        base = min(days, 10)
        incoming = min(int((self.received_yesterday or 0) * (self.incoming_ratio_multiplier or 0.5)), 20)
        replies = min((self.quick_replies_yesterday or 0) * 5, 50)
        calculated = base + incoming + replies
        
        # Never exceed absolute maximum
        return min(calculated, self.max_daily_absolute or 200)
```

### Backend: new endpoint to show daily limit with explanation

In `backend/app/api/v1/accounts.py`, add:

```python
@router.get("/{account_id}/daily-limit-detail")
async def get_daily_limit_detail(account_id: str, db: AsyncSession = Depends(get_db)):
    """Return daily limit with full breakdown and Meta compliance notes."""
    account = await _get_account(account_id, db)
    days = account.days_active or 0
    
    base = min(days, 10)
    incoming = min(int((account.received_yesterday or 0) * (account.incoming_ratio_multiplier or 0.5)), 20)
    replies = min((account.quick_replies_yesterday or 0) * 5, 50)
    calculated = base + incoming + replies
    effective = min(calculated, account.max_daily_absolute or 200)
    
    # Week 1 override
    if days < 7:
        effective = min(5, account.max_daily_absolute or 200)
        week1_cap = True
    else:
        week1_cap = False
    
    return {
        "account_name": account.name,
        "days_active": days,
        "sent_today": account.sent_today,
        "remaining_today": max(0, effective - account.sent_today),
        "effective_limit": effective,
        "breakdown": {
            "base_days": base,
            "incoming_bonus": incoming,
            "reply_bonus": replies,
            "calculated": calculated,
            "absolute_cap": account.max_daily_absolute,
            "week1_cap_active": week1_cap,
        },
        "explanation": (
            f"هفته اول (روز {days}/7) — سقف ۵ پیام" if week1_cap else
            f"پایه: {base} + دریافتی: {incoming} + پاسخ: {replies} = {calculated} (سقف: {account.max_daily_absolute})"
        ),
        "meta_compliance": {
            "status": "✅ مناسب" if days >= 7 else "⚠️ دوره warm-up",
            "notes": [
                "هرگز بیش از ۲۰۰ پیام/روز به یک حساب جدید ارسال نکنید",
                "تاخیر حداقل ۴۵ ثانیه بین پیام‌ها رعایت کنید",
                "در هفته اول حداکثر ۵ پیام/روز ارسال کنید",
                "از ارسال یک پیام یکسان به چند نفر خودداری کنید (GPT این را حل می‌کند)",
            ]
        }
    }
```

### Backend: endpoint to update per-account limits

In accounts.py, add:
```python
class AccountLimitsUpdate(BaseModel):
    max_daily_absolute: int = 200
    incoming_ratio_multiplier: float = 0.5
    max_sends_per_minute: float = 2.0

@router.put("/{account_id}/limits")
async def update_account_limits(account_id: str, body: AccountLimitsUpdate, db: AsyncSession = Depends(get_db)):
    account = await _get_account(account_id, db)
    account.max_daily_absolute = body.max_daily_absolute
    account.incoming_ratio_multiplier = body.incoming_ratio_multiplier
    account.max_sends_per_minute = body.max_sends_per_minute
    await db.commit()
    return {"updated": True, "effective_limit": account.computed_daily_limit}
```

### Frontend: limits panel in Accounts.jsx

Add a "محدودیت‌های ارسال" section in account detail panel:

```jsx
{/* Limits section */}
<div className="mt-4 border-t border-gray-700 pt-4">
  <h4 className="text-sm font-semibold mb-1">
    📊 محدودیت‌های ارسال
    <button onClick={() => loadLimitDetail(account.id)}
            className="text-xs text-blue-400 mr-2">← جزئیات</button>
  </h4>
  
  {limitDetail && (
    <div className="bg-gray-900 rounded-lg p-3 text-xs mb-3">
      <p className="font-bold text-green-400 mb-1">
        سقف امروز: {limitDetail.effective_limit} پیام
        ({limitDetail.sent_today} ارسال، {limitDetail.remaining_today} باقی)
      </p>
      <p className="text-gray-300 mb-1">{limitDetail.explanation}</p>
      <p className={limitDetail.breakdown.week1_cap_active ? "text-amber-400" : "text-green-400"}>
        {limitDetail.meta_compliance.status}
      </p>
    </div>
  )}
  
  <div className="space-y-2">
    <div>
      <label className="text-xs text-gray-400">حداکثر ارسال روزانه (مطلق)</label>
      <input type="number" min="1" max="500"
             value={accountLimits.max_daily_absolute}
             onChange={e => setAccountLimits({...accountLimits, max_daily_absolute: e.target.value})}
             className="input-dark text-sm w-full mt-1" />
    </div>
    <div>
      <label className="text-xs text-gray-400">ضریب پیام‌های دریافتی (0.1 - 2.0)</label>
      <input type="number" min="0.1" max="2.0" step="0.1"
             value={accountLimits.incoming_ratio_multiplier}
             onChange={e => setAccountLimits({...accountLimits, incoming_ratio_multiplier: e.target.value})}
             className="input-dark text-sm w-full mt-1" />
      <p className="text-xs text-gray-500">بیشتر = پیام دریافتی بیشتر سقف را بالا می‌برد</p>
    </div>
    <button onClick={() => saveLimits(account.id)}
            className="btn-green w-full text-sm">ذخیره محدودیت‌ها</button>
  </div>
</div>
```

---

## PHASE 5 — Feature 40: Auto-add contacts to admin groups

In `backend/app/api/v1/groups.py`, add endpoint:

```python
@router.post("/auto-add-members")
async def auto_add_contacts_to_group(
    group_id: str,
    contact_phones: list[str],
    account_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Add phone numbers to a WhatsApp group where this account is admin.
    Only works if account is admin in the group.
    """
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    
    # Check admin status
    grp_result = await db.execute(
        select(WhatsAppGroup).where(
            WhatsAppGroup.green_group_id == group_id,
            WhatsAppGroup.account_id == uuid.UUID(account_id)
        )
    )
    grp = grp_result.scalar_one_or_none()
    if not grp or not grp.is_admin:
        raise HTTPException(403, "این حساب ادمین این گروه نیست")
    
    client = GreenAPIClient(account.instance_id, account.api_token)
    
    added = 0
    failed = 0
    errors = []
    
    for phone in contact_phones:
        try:
            result = await client.add_group_participant(group_id, phone)
            if result:
                added += 1
            else:
                failed += 1
            await asyncio.sleep(2)  # Rate limiting
        except Exception as e:
            failed += 1
            errors.append(f"{phone}: {str(e)}")
    
    return {"added": added, "failed": failed, "errors": errors[:10]}


@router.post("/import-excel-to-group")
async def import_excel_to_group(
    group_id: str,
    account_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """Upload Excel of phone numbers and add them all to a group."""
    from app.services.excel_service import parse_contacts_excel
    content = await file.read()
    contacts_data = parse_contacts_excel(content)
    phones = [c["phone"] for c in contacts_data if c.get("phone")]
    
    # Delegate to auto_add
    return await auto_add_contacts_to_group(group_id, phones, account_id, db)
```

In `frontend/src/pages/Groups.jsx`, add per-group "افزودن اعضا از اکسل" button (only visible when is_admin=true):

```jsx
{group.is_admin && (
  <button onClick={() => openAddMembersModal(group)}
          className="btn-green-sm text-xs mt-2 w-full">
    ➕ افزودن اعضا از اکسل
  </button>
)}
```

Add modal:
```jsx
{/* Add members modal */}
<Modal title={`افزودن اعضا به ${selectedGroup?.name}`}>
  <p className="text-xs text-gray-400 mb-3">
    فایل اکسل با ستون phone آپلود کنید. اعضا به صورت خودکار اضافه می‌شوند.
    فقط در گروه‌هایی که ادمین هستید کار می‌کند.
  </p>
  <input type="file" accept=".xlsx,.xls"
         onChange={e => setMembersFile(e.target.files[0])} />
  <button onClick={submitAddMembers} className="btn-green w-full mt-3">
    شروع افزودن
  </button>
  {addResult && (
    <p className="text-sm mt-2">
      ✅ {addResult.added} نفر اضافه شد | ❌ {addResult.failed} خطا
    </p>
  )}
</Modal>
```

---

## PHASE 6 — Feature 41: Admin status in groups

### Backend: update sync to detect admin status

In `backend/app/api/v1/groups.py`, in `sync_groups_from_wa`, after getting getGroupData:

```python
        # Detect if account is admin
        if chat_type == "group":
            try:
                group_data = await client.get_group_data(chat_id)
                participants = group_data.get("participants", [])
                member_count = len(participants)
                description = group_data.get("description", "")
                
                # Find account's own phone (from getWaSettings)
                wa_settings = await client.get_wa_settings()
                my_phone = str(wa_settings.get("wid", "")).split("@")[0]
                
                # Check admin
                is_admin = any(
                    str(p.get("id", "")).split("@")[0] == my_phone and
                    p.get("isAdmin", False)
                    for p in participants
                )
                participant_count = len(participants)
            except Exception:
                is_admin = False
                description = ""
                participant_count = 0
```

Update WhatsAppGroup upsert to include is_admin and participant_count.

Update `GET /groups/` to accept `is_admin` filter:
```python
@router.get("/")
async def list_groups(
    account_id: str | None = None,
    chat_type: str | None = None,
    min_members: int | None = None,
    is_admin: bool | None = None,  # NEW filter
    db: AsyncSession = Depends(get_db)
):
    ...
    if is_admin is not None:
        query = query.where(WhatsAppGroup.is_admin == is_admin)
```

### Frontend: admin badge and filter in Groups.jsx

Add to filter row:
```jsx
<div className="flex gap-1 bg-gray-800 rounded-lg p-1">
  {[
    { key: null, label: "همه" },
    { key: true, label: "👑 ادمین" },
    { key: false, label: "عضو عادی" },
  ].map(f => (
    <button key={String(f.key)}
      onClick={() => setIsAdminFilter(f.key)}
      className={`px-3 py-1 rounded text-sm ${isAdminFilter === f.key ? "bg-green-600 text-white" : "text-gray-400"}`}>
      {f.label}
    </button>
  ))}
</div>
```

Add admin badge to each group card:
```jsx
{group.is_admin && (
  <span className="text-xs text-amber-400 font-bold">👑 ادمین</span>
)}
```

---

## PHASE 7 — Feature 42: Option to hide product prices

In campaign create body, add:
```python
    show_product_prices: bool = True  # False = show product names only, no prices
```

In `backend/app/services/campaign_runner.py`, update GPT prompt and template when show_product_prices=False:

```python
        # Get products (already fetched)
        if campaign.include_products and products:
            products_for_gpt = []
            for p in products:
                if campaign.show_product_prices:
                    products_for_gpt.append({"name": p["name"], "price": p.get("price")})
                else:
                    products_for_gpt.append({"name": p["name"], "price": None})  # No price
```

In `gpt_service.py`, update price display when price is None:
```python
    if products:
        products_section = "\n\nمحصولات امروز افراکالا:\n"
        for p in products[:3]:
            if p.get("price"):
                price_formatted = f"{p['price']:,} تومان"
            else:
                price_formatted = None  # Don't show price
            if price_formatted:
                products_section += f"• {p['name']}: {price_formatted}\n"
            else:
                products_section += f"• {p['name']}\n"
```

In frontend campaign create modal, add toggle:
```jsx
{form.include_products && (
  <div className="flex items-center justify-between mt-2 mr-4">
    <span className="text-xs text-gray-400">نمایش قیمت در پیام</span>
    <input type="checkbox"
           checked={form.show_product_prices !== false}
           onChange={e => setForm({...form, show_product_prices: e.target.checked})} />
  </div>
)}
```

---

## PHASE 8 — Feature 43: Products page sort by brand then price

In `backend/app/api/v1/reporting.py`, add endpoint for products with brand grouping:

```python
@router.get("/products")
async def get_products_by_brand(db: AsyncSession = Depends(get_db)):
    """Get products grouped by brand, sorted by price within each brand."""
    from app.services.price_service import _fetch_products_from_supabase, _fetch_price_map
    
    # Fetch products with brand info
    from app.config import settings
    import httpx
    headers = {
        "apikey": settings.supabase_anon_key,
        "Authorization": f"Bearer {settings.supabase_anon_key}"
    }
    
    # Fetch products with brand_id
    products_url = f"{settings.supabase_url}/rest/v1/products?is_active=eq.true&stock_status=neq.unavailable&select=id,name,model,capacity,brand_id,category"
    brands_url = f"{settings.supabase_url}/rest/v1/brands?select=id,name&is_active=eq.true"
    
    async with httpx.AsyncClient(timeout=15) as c:
        pr = await c.get(products_url, headers=headers)
        br = await c.get(brands_url, headers=headers)
    
    products = pr.json() if pr.status_code == 200 else []
    brands = {b["id"]: b["name"] for b in (br.json() if br.status_code == 200 else [])}
    
    # Fetch prices
    price_map = {}
    try:
        prices_url = f"{settings.supabase_url}/rest/v1/product_computed_prices_public?select=product_id,rounded_sale_price"
        async with httpx.AsyncClient(timeout=10) as c:
            pr2 = await c.get(prices_url, headers=headers)
            if pr2.status_code == 200:
                for row in pr2.json():
                    price_map[row["product_id"]] = row.get("rounded_sale_price")
    except Exception:
        pass
    
    # Group by brand
    grouped = {}
    for p in products:
        brand_id = p.get("brand_id", "")
        brand_name = brands.get(brand_id, "سایر")
        price = price_map.get(p["id"])
        product_data = {
            "id": p["id"],
            "name": p.get("name", ""),
            "model": p.get("model", ""),
            "capacity": p.get("capacity", ""),
            "price": price,
            "price_formatted": f"{price:,}" if price else None,
        }
        if brand_name not in grouped:
            grouped[brand_name] = []
        grouped[brand_name].append(product_data)
    
    # Sort within each brand by price (cheap to expensive, None last)
    result = []
    for brand_name in sorted(grouped.keys()):
        products_in_brand = sorted(
            grouped[brand_name],
            key=lambda x: (x["price"] is None, x["price"] or 0)
        )
        result.append({
            "brand": brand_name,
            "product_count": len(products_in_brand),
            "products": products_in_brand
        })
    
    return result
```

Note: also GRANT SELECT on brands table if needed. Check with:
```sql
GRANT SELECT ON public.brands TO anon;
```
Add this to PHASE 0 DDL equivalent (run via psql on the self-hosted Supabase).

### Frontend: update Products.jsx

Rewrite to show brand sections:

```jsx
export default function Products() {
  const [data, setData] = useState([]);  // [{brand, products}]
  const [search, setSearch] = useState("");
  const [expandedBrands, setExpandedBrands] = useState({});

  useEffect(() => {
    loadProducts();
    const timer = setInterval(loadProducts, 60000);
    return () => clearInterval(timer);
  }, []);

  const loadProducts = async () => {
    const res = await http.get("/reporting/products");
    setData(res.data);
    // Auto-expand first brand
    if (res.data.length > 0) {
      setExpandedBrands({ [res.data[0].brand]: true });
    }
  };

  const filtered = data.map(brandGroup => ({
    ...brandGroup,
    products: brandGroup.products.filter(p =>
      p.name?.includes(search) || p.model?.includes(search)
    )
  })).filter(bg => bg.products.length > 0);

  return (
    <div className="p-6 rtl">
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-bold">محصولات افراکالا</h1>
        <input value={search} onChange={e => setSearch(e.target.value)}
               placeholder="جستجو در محصولات..."
               className="input-dark text-sm" />
      </div>
      
      <p className="text-sm text-gray-400 mb-4">
        {data.reduce((s, b) => s + b.product_count, 0)} محصول در {data.length} برند
        | مرتب‌شده از ارزان به گران
      </p>
      
      {filtered.map(brandGroup => (
        <div key={brandGroup.brand} className="mb-4">
          {/* Brand header */}
          <button
            onClick={() => setExpandedBrands(prev => ({...prev, [brandGroup.brand]: !prev[brandGroup.brand]}))}
            className="w-full flex justify-between items-center bg-gray-800 rounded-lg p-3 mb-2">
            <span className="font-bold">{brandGroup.brand}</span>
            <span className="text-gray-400 text-sm">{brandGroup.product_count} محصول</span>
          </button>
          
          {/* Products table */}
          {expandedBrands[brandGroup.brand] && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-gray-400 border-b border-gray-700">
                    <th className="py-2 text-right">نام محصول</th>
                    <th className="py-2 text-right">مدل</th>
                    <th className="py-2 text-right">ظرفیت</th>
                    <th className="py-2 text-left">قیمت (تومان)</th>
                  </tr>
                </thead>
                <tbody>
                  {brandGroup.products.map(p => (
                    <tr key={p.id} className="border-b border-gray-800 hover:bg-gray-800">
                      <td className="py-2">{p.name}</td>
                      <td className="py-2 text-gray-400">{p.model || "—"}</td>
                      <td className="py-2 text-gray-400">{p.capacity || "—"}</td>
                      <td className="py-2 text-left">
                        {p.price_formatted
                          ? <span className="text-green-400">{p.price_formatted}</span>
                          : <span className="text-gray-500">تماس بگیرید</span>
                        }
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
```

---

## PHASE 9 — Verify, rebuild, push

```bash
# Grant brands table access on self-hosted Supabase
# Run this separately on the laptop server:
# docker exec afrakala-lan-db psql -U postgres -c "GRANT SELECT ON public.brands TO anon;"

cd C:/Users/AFRA/Desktop/bots/claudegreenapi/backend
python -m py_compile app/main.py app/models/*.py app/services/*.py app/api/v1/*.py app/workers/*.py app/utils/*.py
python -m pytest tests/ -v
echo "=== Tests done ==="
cd ..
docker-compose up -d --build backend worker beat
sleep 8
curl -s http://localhost:8002/health
curl -s "http://localhost:8002/api/v1/dashboard/validate-campaign?contact_count=100&account_ids=2e95cde4-fd12-40c0-b42c-3529705543d5"
curl -s "http://localhost:8002/api/v1/accounts/2e95cde4-fd12-40c0-b42c-3529705543d5/daily-limit-detail"
cd frontend && npm run build && cd ..
docker-compose up -d --build --no-deps frontend
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:3002/
```

```bash
git add -A
git commit -m "feat: V8 — features 35-43

Feature 35: Shamsi date input/display for campaign scheduling
- backend/app/utils/shamsi.py: to_shamsi() / from_shamsi() converters
- Campaigns API: accepts schedule_start_shamsi/end_shamsi (YYYY/MM/DD HH:MM)
- campaign_runner: checks schedule_start (waits) and schedule_end (stops)
- Frontend: Shamsi date inputs in campaign modal, display on cards

Feature 36: Pre-send validation engine
- POST /dashboard/validate-campaign: feasibility check with color code
- Returns: daily capacity, estimated days, warnings, recommendations
- Frontend: 'بررسی امکان‌سنجی' button in campaign wizard with colored result panel

Feature 37: Parallel multi-account sending
- campaigns.parallel_accounts (bool) + max_parallel_accounts
- run_campaign_parallel: splits contacts across accounts, runs concurrently
- Frontend: toggle in campaign create modal

Feature 39: Per-account limits with Meta standards  
- accounts.max_daily_absolute (default 200), incoming_ratio_multiplier, max_sends_per_minute
- GET /accounts/{id}/daily-limit-detail: full breakdown + Meta compliance notes
- PUT /accounts/{id}/limits: update per-account limits
- Frontend: limits panel in Accounts with detail view

Feature 40: Auto-add contacts to admin groups
- POST /groups/auto-add-members: adds phone list to group (admin only)
- POST /groups/import-excel-to-group: upload Excel to add to group
- Frontend: 'افزودن اعضا از اکسل' button on admin groups

Feature 41: Admin status in groups
- whatsapp_groups.is_admin + participant_count columns
- Sync detects admin status via getGroupData participants
- GET /groups/?is_admin=true filter
- Frontend: admin badge per group, filter buttons (همه/ادمین/عضو)

Feature 42: Option to hide product prices in campaigns
- campaigns.show_product_prices (default True)
- GPT service: omits price when False, shows name only
- Frontend: toggle under 'افزودن محصولات' checkbox

Feature 43: Products page sorted by brand then price
- GET /reporting/products: groups by brand, sorts cheap→expensive within brand
- Frontend: collapsible brand sections, price color-coded"
git push origin main
```