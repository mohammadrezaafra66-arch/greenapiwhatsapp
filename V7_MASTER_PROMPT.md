# CLAUDE CODE MASTER PROMPT — V7
# Afrakala WhatsApp Sender
# Repo: https://github.com/mohammadrezaafra66-arch/greenapiwhatsapp
# Local: C:\Users\AFRA\Desktop\bots\claudegreenapi

## EXECUTION CONTRACT
Run every phase sequentially. Never stop for confirmation. Fix errors before moving on.
At end: pytest, rebuild, push.

---

## FEATURES (5 items)

28. Per-account per-hour message intro template with presets
29. Search/filter in Groups page
30. Fix WA collections sync — show synced groups as selectable list
31. Easy account/number switching UI (accounts already in DB, just improve UX)
32. Multi-account dashboard overview (already works, improve visualization)

---

## PHASE 1 — Feature 28: Per-hour intro templates with presets

### Context
`account_hour_schedules` table (from V3) already has:
- account_id, hour_start, hour_end, max_per_hour
- gpt_prompt (text) — used by campaign_runner
- message_template (text)

The gpt_prompt already controls GPT output per hour. Just need better UI.

### Backend: add preset templates endpoint

In `backend/app/api/v1/account_schedules.py`, add:

```python
HOUR_PRESETS = {
    "morning_energy": {
        "label": "صبح‌بخیر و انرژی مثبت",
        "gpt_prompt": "یک پیام صبح‌بخیر انرژی‌بخش و انگیزشی کوتاه فارسی برای مشتری بنویس. شروع پیام باید با سلام و صبح‌بخیر باشد. یک جمله انگیزشی مرتبط با موفقیت در کسب‌وکار اضافه کن.",
        "example": "صبح‌بخیر {نام} جان! امیدوارم روزتون پر از انرژی و موفقیت باشه 🌅"
    },
    "company_intro": {
        "label": "معرفی شرکت افراکالا",
        "gpt_prompt": "یک پیام کوتاه معرفی شرکت افراکالا (عمده‌فروشی لوازم خانگی) برای مشتری بنویس. نقاط قوت: قیمت مناسب، تنوع محصول، تحویل سریع.",
        "example": "سلام {نام} عزیز، افراکالا با بیش از ۲۰۰ برند لوازم خانگی در خدمت شماست 🏠"
    },
    "product_showcase": {
        "label": "معرفی محصولات با قیمت",
        "gpt_prompt": "یک پیام معرفی محصولات لوازم خانگی با قیمت روز برای مشتری بنویس. محصولات را با قیمت ذکر کن. لحن فروشندگی داشته باشد.",
        "example": "پیشنهاد ویژه امروز افراکالا: {محصول۱} {قیمت۱} | {محصول۲} {قیمت۲} 🛒"
    },
    "follow_up": {
        "label": "پیگیری و سوال از مشتری",
        "gpt_prompt": "یک پیام پیگیری دوستانه برای مشتری بنویس. بپرس آیا به محصول خاصی نیاز دارند یا سوالی دارند. لحن صمیمی.",
        "example": "سلام {نام}، امیدوارم حالتون خوب باشه. آیا در این روزها به لوازم خانگی نیاز دارید؟ 😊"
    },
    "discount_offer": {
        "label": "پیشنهاد تخفیف ویژه",
        "gpt_prompt": "یک پیام اعلام تخفیف و پیشنهاد ویژه فروش لوازم خانگی بنویس. احساس فوریت ایجاد کن. محصولات درج شده را با قیمت ذکر کن.",
        "example": "فرصت محدود! تخفیف ویژه تا آخر هفته روی {محصول} 🔥"
    },
    "evening_wrap": {
        "label": "جمع‌بندی پایان روز",
        "gpt_prompt": "یک پیام کوتاه پایان روز برای مشتری بنویس. یادآوری پیشنهاد روز، آرزوی شب‌بخیر، اعلام ساعات کاری فردا.",
        "example": "شب‌بخیر {نام} جان! فردا از ساعت ۸ در خدمتیم 🌙"
    }
}

@router.get("/presets")
async def get_hour_presets():
    """Return available hour message presets."""
    return [
        {"key": k, "label": v["label"], "example": v["example"], "gpt_prompt": v["gpt_prompt"]}
        for k, v in HOUR_PRESETS.items()
    ]

@router.post("/{slot_id}/apply-preset")
async def apply_preset_to_slot(slot_id: str, preset_key: str, db: AsyncSession = Depends(get_db)):
    """Apply a preset GPT prompt to an existing schedule slot."""
    if preset_key not in HOUR_PRESETS:
        raise HTTPException(400, f"Unknown preset: {preset_key}")
    slot = await db.get(AccountHourSchedule, uuid.UUID(slot_id))
    if not slot:
        raise HTTPException(404, "Slot not found")
    slot.gpt_prompt = HOUR_PRESETS[preset_key]["gpt_prompt"]
    await db.commit()
    return {"applied": True, "preset": preset_key, "label": HOUR_PRESETS[preset_key]["label"]}
```

Also update `backend/app/api/v1/account_schedules.py` — in the slot create/update endpoints, add `include_products` bool field:

```python
class ScheduleCreate(BaseModel):
    account_id: str
    hour_start: int
    hour_end: int
    max_per_hour: int = 0
    gpt_prompt: str | None = None
    message_template: str | None = None
    is_active: bool = True
    include_products: bool = False  # NEW: attach products to this hour's messages
```

Store `include_products` — add column to DB:
```python
"ALTER TABLE account_hour_schedules ADD COLUMN IF NOT EXISTS include_products boolean DEFAULT false"
```

Add this to Phase 0 DDL in main.py.

### Frontend: improve AccountSchedules.jsx

Add preset selector to the slot modal. When user is creating/editing a slot:

1. Show a "پیش‌نویس‌های آماده" section with cards for each preset (fetched from GET /account-schedules/presets):
   - Each card shows: label + example text
   - Click → fills the gpt_prompt textarea automatically
   - Selected preset highlighted with green border

2. Add "افزودن محصولات به پیام" checkbox in slot modal

3. In the slot table, show a truncated preview of gpt_prompt (first 50 chars)

4. Add a "کپی از پیش‌نویس" icon button next to each slot in the table

Example usage description to show users:
```
💡 مثال:
ساعت ۸-۹: پیش‌نویس "صبح‌بخیر و انرژی مثبت" → GPT پیام انگیزشی می‌سازد
ساعت ۱۰-۱۱: پیش‌نویس "معرفی شرکت" → GPT شرکت را معرفی می‌کند
ساعت ۱۱-۱۲: پیش‌نویس "محصولات با قیمت" + چک‌باکس "افزودن محصولات" → قیمت لحظه‌ای درج می‌شود
```

Add to api.js:
```javascript
export const PresetsApi = {
  list: () => http.get("/account-schedules/presets").then(r => r.data),
  applyToSlot: (slotId, presetKey) => http.post(`/account-schedules/${slotId}/apply-preset?preset_key=${presetKey}`).then(r => r.data),
};
```

---

## PHASE 2 — Feature 29: Search in Groups page

In `frontend/src/pages/Groups.jsx`:

1. Add a search input at the top:
```jsx
const [search, setSearch] = useState("");
const filtered = groups.filter(g =>
  g.name?.toLowerCase().includes(search.toLowerCase()) ||
  g.green_group_id?.includes(search)
);
```

2. Show `filtered` instead of `groups` in the list

3. Add placeholder: "جستجو بر اساس نام گروه یا شناسه..."

4. Show count: `{filtered.length} گروه پیدا شد`

---

## PHASE 3 — Feature 30: Fix WA Collections sync

### Problem
Currently in WaCollections page, adding a group requires manually typing `group_chat_id`. 
The sync button calls `/groups/sync/{account_id}` which saves groups to `whatsapp_groups` table.
But WaCollections.jsx doesn't show those synced groups for selection.

### Fix: backend add endpoint

In `backend/app/api/v1/wa_collections.py`, add endpoint to get synced groups:

```python
from app.models.group import WhatsAppGroup

@router.get("/available-groups/{account_id}")
async def get_available_groups(account_id: str, db: AsyncSession = Depends(get_db)):
    """Get all WhatsApp groups synced from this account — for use in WA collections."""
    result = await db.execute(
        select(WhatsAppGroup)
        .where(WhatsAppGroup.account_id == uuid.UUID(account_id))
        .order_by(WhatsAppGroup.name)
    )
    groups = result.scalars().all()
    return [
        {
            "id": str(g.id),
            "group_chat_id": g.green_group_id,
            "name": g.name,
            "member_count": g.member_count
        }
        for g in groups
    ]
```

### Fix: frontend WaCollections.jsx

Replace the plain text input for adding groups with a two-step flow:

**Step 1:** Account selector → "همگام‌سازی گروه‌ها" button
- Calls POST /api/v1/groups/sync/{account_id}
- Shows loading spinner
- On success: shows list of synced groups

**Step 2:** Checkboxes for group selection
- Each group shows: name + member count + group_chat_id
- Multi-select checkboxes
- "افزودن گروه‌های انتخابی" button → calls POST /wa-collections/{id}/groups for each selected group

```jsx
// In "add groups" modal:
const [syncedGroups, setSyncedGroups] = useState([]);
const [selectedGroups, setSelectedGroups] = useState([]);

const syncGroups = async () => {
  await GroupsApi.sync(selectedAccountId);  // POST /groups/sync/{account_id}
  const groups = await WaCollectionsApi.availableGroups(selectedAccountId);  // GET /wa-collections/available-groups/{account_id}
  setSyncedGroups(groups);
};

// render:
syncedGroups.map(g => (
  <label key={g.group_chat_id} className="flex items-center gap-2 cursor-pointer">
    <input type="checkbox" 
           checked={selectedGroups.includes(g.group_chat_id)}
           onChange={() => toggleGroup(g.group_chat_id)} />
    <span>{g.name}</span>
    <span className="text-xs text-gray-400">{g.member_count} عضو</span>
  </label>
))
```

Add to api.js:
```javascript
export const WaCollectionsApi = {
  ...existing...,
  availableGroups: (accountId) => http.get(`/wa-collections/available-groups/${accountId}`).then(r => r.data),
};

export const GroupsApi = {
  ...existing...,
  sync: (accountId) => http.post(`/groups/sync/${accountId}`).then(r => r.data),
  list: () => http.get("/groups/").then(r => r.data),
};
```

Also update Groups page "همگام‌سازی با واتساپ" button to use the active account automatically:
```javascript
// Get first active account from /accounts/, use its id for sync
const activeAccount = accounts.find(a => a.status === "active");
if (activeAccount) {
  await GroupsApi.sync(activeAccount.id);
  await refetchGroups();
}
```

---

## PHASE 4 — Feature 31: Account switching UX

The system already supports multiple Green API accounts. What's missing is a clear UI.

### In `frontend/src/pages/Accounts.jsx`

1. Add "حساب فعال" badge on the account that's currently being used most (highest days_active)

2. Add "تنظیم به عنوان پیش‌فرض" button per account → calls new endpoint:
   POST /accounts/{id}/set-default
   Sets a `is_default boolean` column on accounts table

3. Add explanation banner:
   "هر حساب یک شماره واتساپ مستقل است. می‌توانید چندین حساب همزمان فعال داشته باشید. کمپین‌ها به صورت round-robin بین حساب‌های فعال ارسال می‌شوند."

4. In the "+ افزودن حساب" modal, add a clear step-by-step:
   - گام ۱: در green-api.com وارد شوید
   - گام ۲: Instance جدید بسازید
   - گام ۳: Instance ID و API Token را کپی کنید
   - گام ۴: اینجا وارد کنید و QR را اسکن کنید

### Backend: add default account tracking

In main.py DDL:
```python
"ALTER TABLE accounts ADD COLUMN IF NOT EXISTS is_default boolean DEFAULT false"
```

In `backend/app/api/v1/accounts.py`, add:
```python
@router.post("/{account_id}/set-default")
async def set_default_account(account_id: str, db: AsyncSession = Depends(get_db)):
    """Set one account as default (used for single-account operations like checkWhatsapp)."""
    # Clear existing default
    from sqlalchemy import update
    await db.execute(update(Account).values(is_default=False))
    # Set new default
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    account.is_default = True
    await db.commit()
    return {"default_account": str(account.id), "name": account.name}
```

---

## PHASE 5 — Feature 32: Multi-account dashboard

In `frontend/src/pages/Dashboard.jsx`, update the accounts section to show:

1. Summary: "X حساب فعال از Y کل" با progress bar به رنگ سبز
2. Per-account stat cards (already partially there) — make them more visual:
   - Account name + phone
   - Status dot (pulse if active)
   - Sent today / daily limit (progress bar)
   - Days active badge
   - "پیش‌فرض" badge if is_default

3. Add "مجموع ارسال امروز" at the bottom — sum across all accounts

4. If any account is banned → red alert banner: "⚠️ حساب {name} مسدود شده — فوراً بررسی کنید"

5. Rate limiter now shows per-account status (fetch from /account-schedules/{id} for each active account):
   - Shows if account has a custom schedule or using global
   - Shows current hour's limit for each account

---

## PHASE 6 — Verify, build, commit, push

```bash
cd C:/Users/AFRA/Desktop/bots/claudegreenapi/backend
python -m py_compile app/main.py app/models/*.py app/services/*.py app/api/v1/*.py
python -m pytest tests/ -v
cd ..
docker-compose up -d --build backend worker beat
sleep 8
curl -s http://localhost:8002/health
curl -s http://localhost:8002/api/v1/account-schedules/presets
curl -s http://localhost:8002/api/v1/wa-collections/available-groups/2e95cde4-fd12-40c0-b42c-3529705543d5
cd frontend && npm run build && cd ..
docker-compose up -d --build --no-deps frontend
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:3002/
```

```bash
git add -A
git commit -m "feat: V7 — per-hour presets, group search, wa-collections fix, multi-account UX

Feature 28: Per-hour message presets
- 6 built-in presets: morning_energy, company_intro, product_showcase,
  follow_up, discount_offer, evening_wrap
- GET /account-schedules/presets endpoint
- POST /account-schedules/{slot_id}/apply-preset
- include_products bool per slot
- AccountSchedules.jsx: preset cards in slot modal, truncated preview

Feature 29: Groups search
- Search input filters by group name or chat_id
- Shows count of filtered results

Feature 30: WA Collections sync fix
- GET /wa-collections/available-groups/{account_id}
- WaCollections.jsx now shows checkbox list of synced groups
- Two-step flow: sync first, then select from list
- Groups.jsx sync button auto-uses active account

Feature 31: Account switching UX
- is_default column on accounts
- POST /accounts/{id}/set-default
- Accounts page: default badge, step-by-step add instructions
- Multi-account explanation banner

Feature 32: Multi-account dashboard
- Per-account stat cards with progress bars
- Total sent today across all accounts
- Banned account alert banner
- Per-account rate limit display"
git push origin main
```