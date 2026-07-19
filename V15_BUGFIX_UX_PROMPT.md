# CLAUDE CODE MASTER PROMPT — V15
# Afrakala WhatsApp Sender: 26 Bug Fixes + UX Improvements + Features
# Repo: https://github.com/mohammadrezaafra66-arch/greenapiwhatsapp
# Local: C:\Users\AFRA\Desktop\bots\claudegreenapi

═══════════════════════════════════════════════════════════════════════════════
# AUTONOMOUS EXECUTION CONTRACT
═══════════════════════════════════════════════════════════════════════════════

Execute this ENTIRE document end-to-end WITHOUT asking the user anything.
The user is NOT available. Every decision is yours.

1. NEVER ask for confirmation. NEVER present choices. NEVER wait for input.
2. On ambiguity: choose the SAFEST option, record it under "AUTONOMOUS DECISIONS"
   in the final report, and continue.
3. Work PART by PART in the exact written order.
4. After each PART: run pytest → rebuild affected containers → verify → commit → push.
   ONE COMMIT PER PART.
5. NEVER break the existing send path. Every change is ADDITIVE or a FIX.
6. NEVER enable polling. Webhook mode only.
7. NEVER print/log/return tokens.
8. All UI text in Persian RTL. All dates in Shamsi.

## Environment (same as V14 — verified)
- Containers: claudegreenapi-db-1, redis, backend(:8002), worker-general, worker-webhooks,
  beat, frontend(:3002). All restart:always.
- Backend: FastAPI backend/app/. Frontend: React/Vite frontend/src/.
- DB: postgres, user afrakala, db whatsapp_sender. DDL idempotent in main.py.
- Products/prices from Supabase at 192.168.170.10:8000.
- ~213 tests currently pass. Do not regress.

## PREFLIGHT
```bash
cd C:/Users/AFRA/Desktop/bots/claudegreenapi
docker compose ps
curl -s http://localhost:8002/health/detailed | python -m json.tool
git checkout main && git pull origin main
git status --short && git log --oneline -3
cd backend && python -m pytest tests/ -v --tb=short | tail -5
```
Confirm stack up, on main, clean tree, tests pass. Then proceed.

═══════════════════════════════════════════════════════════════════════════════
# PART 1 — CRITICAL BUGS (Items 2, 3, 12, 22)
═══════════════════════════════════════════════════════════════════════════════

## 1.1 — BUG FIX: Group filter by selected account (Item 2)

**Problem:** On the WhatsApp Groups page (گروه‌های واتساپ), when account 1 is selected
in the dropdown, groups from OTHER accounts are also shown. The filter is broken.

**Fix:**
- Find the frontend page that lists WhatsApp groups (likely frontend/src/pages/ with groups).
- Find the API call that fetches groups (likely GET /api/v1/groups or similar).
- The API endpoint MUST accept an `account_id` query parameter.
- When a specific account is selected in the dropdown, the frontend MUST pass that account_id
  to the API, and the backend MUST filter: `WHERE account_id = :selected_account_id`.
- Verify: select account 1 → only account 1's groups shown. Select account 2 → only account 2's.
- If the groups table doesn't have an account_id column, it should — groups are synced
  per-account via getGroupData. Find how groups are associated with accounts and fix the filter.

## 1.2 — BUG FIX: Extract members only for selected account's groups (Item 3)

**Problem:** When clicking "استخراج" (extract members) with account 1 selected, it extracts
members from ALL accounts' groups, not just account 1's groups.

**Fix:**
- The extract endpoint/task MUST receive the selected `account_id`.
- It MUST only process groups belonging to that account.
- Find the extract button's onClick handler → ensure it passes the currently selected account_id.
- Find the backend extraction endpoint/task → ensure it filters groups by account_id.
- Verify: select account 1 → extract → only members from account 1's groups are extracted.

## 1.3 — BUG FIX: Price display when "نمایش قیمت" is checked (Item 12)

**Problem:** User checks "نمایش قیمت در پیام" (show price in message), but the AI writes
"تماس بگیرید" (call us) or "تماس با ما" instead of the actual price.

**Root cause:** The GPT prompt doesn't ENFORCE price inclusion strongly enough. When
`show_prices=True`, the prompt must make it MANDATORY, not optional.

**Fix:**
- Find the message generation code (likely `gpt_service.py` or `generate_message` or
  `build_message_text`).
- Find where `show_prices` is read and how it affects the GPT system prompt.
- When `show_prices=True`:
  - The system prompt MUST contain an EXPLICIT instruction like:
    «حتماً قیمت دقیق هر محصول را به تومان بنویس. هرگز «تماس بگیرید» یا «تماس با ما» ننویس.
     قیمت باید عدد دقیق باشد مثلاً ۷۶,۹۰۰,۰۰۰ تومان.»
  - ALSO add a POST-GENERATION CHECK: after AI returns the text, scan for phrases like
    "تماس بگیرید", "تماس با ما", "برای قیمت تماس". If found AND show_prices is True AND
    products with prices were provided → LOG a warning and RETRY once with a stronger prompt.
    If still no price, at least append the prices as a simple list at the end:
    «قیمت‌ها: [product1]: [price1] تومان | [product2]: [price2] تومان»
- When `show_prices=False`: the current behavior (no price, "تماس بگیرید" is OK) is correct.
- Add a test: generate with show_prices=True and mock products with prices → assert the output
  contains at least one numeric price string and does NOT contain "تماس بگیرید".

## 1.4 — BUG FIX: No duplicate products across groups (Item 22)

**Problem:** When "محصولات متفاوت در گروه‌ها" (different products per group) is enabled,
some groups still receive the same products.

**Fix:**
- Find the per-group product selection logic (likely in `group_campaign_runner.py`,
  the `select_group_products` or `weighted_sample` function, or
  `product_variation_mode` handling).
- When `product_variation_mode` is `per_group_random` or `rotate`:
  - Maintain a SET of already-used products across groups within the same campaign run.
  - Each group draws from the REMAINING pool (excluding already-used products).
  - If the pool is exhausted (more groups than products), then AND ONLY THEN allow reuse
    (start a new cycle).
  - For `rotate` mode: strict round-robin, no repeats until the full product list is cycled.
- Add a test: 5 groups, 10 products, per_group_random with 2 products each → assert the
  10 selected products across all groups are all distinct (no repeats).
- Another test: 5 groups, 3 products, per_group_random with 2 each → assert max reuse is
  minimal (pigeonhole: some reuse is unavoidable, but no group gets the exact same pair).

## 1.5 — Verify + commit PART 1
```bash
cd backend && python -m pytest tests/ -v && cd ..
docker compose up -d --build backend worker-general worker-webhooks beat
cd frontend && npm run build && cd .. && docker compose up -d --build --no-deps frontend
git add -A && git commit -m "fix: V15 PART 1 — group filter by account, extract per-account, enforce price display, no duplicate products across groups" && git push origin main
```

═══════════════════════════════════════════════════════════════════════════════
# PART 2 — CAMPAIGN UX (Items 4, 5, 7, 8, 9, 10, 11, 17, 18)
═══════════════════════════════════════════════════════════════════════════════

## 2.1 — Context-sensitive fields by send type (Item 4)

**Problem:** When send type is "ارسال به افراد" (PV/individual), group-specific fields like
"تنوع محصولات بین گروه‌ها" still show. They should be hidden/disabled for PV sends.

**Fix:** In the campaign create/edit modal:
- When send type = **گروه (group)**: show all current fields as-is.
- When send type = **افراد (PV/individual)**: HIDE these fields:
  - «تنوع محصولات بین گروه‌ها» (product_variation_mode) — hide entirely
  - «محصولات وزن‌دار» (product_weights) — hide if variation is hidden
  - Any label that says "گروه" should change to "مخاطب" where applicable
- Use conditional rendering (not just CSS display:none — actually don't render, so the form
  doesn't send irrelevant fields).

## 2.2 — Preview at the bottom of the page (Item 5)

**Problem:** The preview button is somewhere in the middle. It should be at the BOTTOM,
after all settings are configured.

**Fix:**
- Move the «پیش‌نمایش» button + the WhatsApp preview bubble to the VERY BOTTOM of the
  campaign create/edit modal, just ABOVE the final «ارسال» (send) button.
- Layout order: all settings → preview button + bubble → send button.
- Keep the existing preview logic (calls /campaigns/preview) — just move its position.

## 2.3 — Opening line control for groups (Items 7, 17)

**Problem:** When sending to groups, the AI writes "سلام به گروه فلان" or
"سلام به اعضای گروه فلان" which is unnatural and reveals automation.

**Fix:**
- When send type = **group** AND opening_mode = **ai**:
  Add to the GPT system prompt:
  «هرگز نام گروه را در سلام یا ابتدای پیام ننویس. هرگز «سلام به گروه» یا
   «سلام به اعضای گروه» ننویس. فقط یک سلام عمومی کوتاه بنویس مثل «سلام»
   یا «سلام و درود» یا مستقیم با پیشنهاد شروع کن.»
- When opening_mode = **fixed**: the user's exact text is used (no change needed).
- When opening_mode = **none**: already handled (best-effort skip greeting).

## 2.4 — Product description length control (Item 8)

**Problem:** AI writes too much detail about each product. User wants control.

**Fix:** Add a new campaign field:
```sql
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS product_detail_level varchar(20) DEFAULT 'medium';
-- values: 'minimal' | 'medium' | 'detailed'
```
- **minimal** (مختصر): فقط نام + قیمت. GPT prompt: «فقط نام محصول و قیمت را بنویس.
  هیچ توضیح اضافی ننویس.»
- **medium** (متوسط): نام + قیمت + ۱–۲ مشخصه کلیدی. GPT prompt:
  «نام محصول، قیمت و حداکثر ۲ مشخصه مهم (مثل ظرفیت، نوع) را بنویس. کوتاه باش.»
- **detailed** (مفصل): current behavior (no change to prompt).

Frontend: a dropdown «سطح جزئیات محصول» with these three Persian options, default «متوسط».

## 2.5 — Product formatting order (Item 9)

**Problem:** Products appear as a messy paragraph instead of a clean list.

**Fix:** Add to the GPT system prompt (for ALL detail levels):
«محصولات را به صورت لیست مرتب بنویس. هر محصول در یک خط جداگانه. از علامت ✅ یا • ابتدای
هر خط استفاده کن. مثال:
✅ یونیوا ۱۸۰۰۰ اینورتر — ۷۶,۹۰۰,۰۰۰ تومان
✅ اسپلیت بوش ۲۴۰۰۰ — ۸۹,۵۰۰,۰۰۰ تومان»

Also, in the template fallback path, format products as a bullet list (one per line with ✅).

## 2.6 — Rename "تعداد محصول (اندازه مخزن)" → "تعداد محصول در پیام" (Item 10)

**Fix:** Find every occurrence of "اندازه مخزن" or "تعداد محصول (اندازه مخزن)" in the
frontend and replace with «تعداد محصول در هر پیام». Also update any tooltip/help text.
Backend field name can stay the same (products_per_group or equivalent) — this is a UI label change only.

## 2.7 — Account selector when parallel sending is OFF (Item 11)

**Problem:** When "ارسال موازی با چند حساب" is OFF, there's no way to choose WHICH account
sends the campaign.

**Fix:**
- When the parallel toggle is OFF, show a dropdown «ارسال با شماره:» listing all active accounts
  (name + phone number). Default to the default account.
- Store the selection: `ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS selected_account_id uuid;`
- The runner uses this account (instead of round-robin) when parallel is off.
- When parallel is ON, hide this dropdown (round-robin across all active accounts).

## 2.8 — Contact name only for PV, no name = no greeting name (Item 18)

**Problem:** In group sends, the AI uses individual names (wrong — it's a group message,
no individual names). In PV sends with contacts that have no name, the AI writes
"سلام عزیز" or similar placeholder.

**Fix:**
- **Group sends:** NEVER pass the contact name to the GPT prompt. Remove any
  `{contact_name}` or `{name}` placeholder injection for group campaigns.
- **PV sends with a name:** pass the name → «سلام محمد»
- **PV sends WITHOUT a name (name is null/empty):** pass NO name placeholder.
  Add to GPT prompt: «اگر نام مخاطب مشخص نیست، فقط «سلام» بنویس بدون هیچ صفت یا
  کلمه اضافی مثل عزیز یا دوست.»
- Template path: if `{name}` is empty, replace `{name}` with empty string (so
  "سلام {name}" becomes "سلام ").  Then strip double spaces.

## 2.9 — Verify + commit PART 2
```bash
cd backend && python -m pytest tests/ -v && cd ..
docker compose up -d --build backend worker-general worker-webhooks beat
cd frontend && npm run build && cd .. && docker compose up -d --build --no-deps frontend
git add -A && git commit -m "fix: V15 PART 2 — campaign UX: context-sensitive fields, preview at bottom, opening line control, product detail level/formatting, account selector, contact name rules" && git push origin main
```

═══════════════════════════════════════════════════════════════════════════════
# PART 3 — GROUPS PAGE UX (Items 19, 20)
═══════════════════════════════════════════════════════════════════════════════

## 3.1 — "All accounts" option in group dropdown (Item 19)

**Fix:** In the WhatsApp Groups page account dropdown, add a first option:
«همه اکانت‌ها» (value: null or "all").
When selected: show groups from ALL accounts (current default behavior, but now explicit).
When a specific account is selected: show only that account's groups (per PART 1 fix).

## 3.2 — Show group name on every group card (Item 20)

**Problem:** Group cards don't always show the group name.

**Fix:** Ensure every group card/row in the WhatsApp Groups page displays the group name
(`subject` from getGroupData, or the stored `name` column) prominently. If the name is null
or empty, show the groupId as fallback with a «(بدون نام)» label.

## 3.3 — Verify + commit PART 3
```bash
cd frontend && npm run build && cd .. && docker compose up -d --build --no-deps frontend
git add -A && git commit -m "fix: V15 PART 3 — groups page: all-accounts option, always show group name" && git push origin main
```

═══════════════════════════════════════════════════════════════════════════════
# PART 4 — CAMPAIGN SCHEDULING & DATE PICKER (Item 21)
═══════════════════════════════════════════════════════════════════════════════

## 4.1 — Shamsi date picker + time picker (Item 21)

**Problem:** Campaign start/end date and time must be typed manually. Should be a
dropdown/picker, and MUST be Shamsi (Jalali).

**Fix:**
- Install a Jalali date-picker library for React. Options (pick whichever is available
  in the npm registry and works with the existing build):
  - `react-multi-date-picker` with `persian` locale (most popular)
  - `react-datepicker2` (Jalali support)
  - Or any working Jalali picker. If none installs cleanly, build a simple one using
    `jalaali-js` for conversion + a basic calendar grid.
- Replace the manual text input for start date / end date with the Jalali date picker.
- Replace the manual text input for start time / end time with a time picker
  (dropdown of hours 00–23 + minutes 00/15/30/45, or a proper time-picker component).
- The picker MUST display Persian numerals and Persian month names
  (فروردین، اردیبهشت، ...).
- Backend: continue to store as UTC internally; convert Shamsi→Gregorian on submit,
  Gregorian→Shamsi on display (the existing pattern).
- Verify: open campaign create → click date field → a Shamsi calendar appears → select →
  date is set correctly.

## 4.2 — Verify + commit PART 4
```bash
cd frontend && npm run build && cd .. && docker compose up -d --build --no-deps frontend
git add -A && git commit -m "feat: V15 PART 4 — Shamsi (Jalali) date picker + time picker for campaign scheduling" && git push origin main
```

═══════════════════════════════════════════════════════════════════════════════
# PART 5 — INSTANCE INFO TOOLTIPS (Item 25)
═══════════════════════════════════════════════════════════════════════════════

## 5.1 — Help tooltips on account fields (Item 25)

**Fix:** On the accounts page and partner page, next to each field label, add a ❓ icon
that shows a tooltip on hover with a Persian explanation:

| Field | Tooltip |
|---|---|
| شناسه (idInstance) | «شناسه عددی instance در Green API — خودکار پر می‌شود. دست نزنید.» |
| شماره واتساپ | «شماره تلفنی که با QR یا کد وصل شده — خودکار پر می‌شود.» |
| توکن اتصال | «رمز اتصال به Green API — مخفی و محرمانه. هرگز به کسی ندهید.» |
| نام حساب | «نام دلخواه برای شناسایی در سامانه — اختیاری. می‌توانید تغییر دهید.» |
| تعرفه | «نوع اشتراک Green API (Partner/Business) — خودکار از Green API خوانده می‌شود.» |
| روزهای فعال | «تعداد روزهایی که این شماره متصل و فعال بوده — مهم برای دوره گرم‌سازی (warm-up).» |
| سلامت حساب | «امتیاز ۰ تا ۱۰۰ بر اساس ظرفیت باقی‌مانده و نرخ کارت زرد ۷ روز اخیر.» |

Use a small `?` icon (e.g. lucide-react `HelpCircle`) with a CSS tooltip or a library tooltip.
Style: dark background, white text, Persian RTL, max-width 250px, appears on hover/focus.

## 5.2 — Verify + commit PART 5
```bash
cd frontend && npm run build && cd .. && docker compose up -d --build --no-deps frontend
git add -A && git commit -m "feat: V15 PART 5 — help tooltips (❓) on all account/instance fields with Persian explanations" && git push origin main
```

═══════════════════════════════════════════════════════════════════════════════
# PART 6 — REAL-TIME PRICING VERIFICATION (Item 24)
═══════════════════════════════════════════════════════════════════════════════

## 6.1 — Ensure price is fetched per-message, not cached at campaign start (Item 24)

**Problem:** User wants ABSOLUTE CERTAINTY that if a price changes at 11:30 during a
campaign that started at 10:00, messages sent after 11:30 use the NEW price.

**Fix:**
- Find where products/prices are fetched in the send flow (likely in `generate_message`,
  `build_message_text`, or the runner's per-contact/per-group loop).
- VERIFY that the Supabase price query happens INSIDE the per-message loop, NOT before
  the loop. If it's fetched once at campaign start and reused, MOVE it inside the loop.
- Specifically: the products + prices must be fetched FRESH for each message (or at minimum,
  re-fetched every N minutes with a short TTL cache of ≤ 5 minutes).
- If there's a `get_products()` call that caches results: reduce cache TTL to **5 minutes max**
  or remove caching entirely for the send path. (Caching for the UI/reporting is fine.)
- Add a code comment at the fetch site:
  ```python
  # CRITICAL: fetch prices PER-MESSAGE (not per-campaign) so mid-campaign price changes
  # are reflected immediately. See V15 Item 24.
  ```
- Add a test: mock `get_products` to return price X on first call and price Y on second call;
  run the message builder twice; assert the second message contains price Y, not price X.

## 6.2 — Verify + commit PART 6
```bash
cd backend && python -m pytest tests/ -v && cd ..
docker compose up -d --build backend worker-general worker-webhooks beat
git add -A && git commit -m "fix: V15 PART 6 — ensure per-message real-time price fetch (not cached at campaign start)" && git push origin main
```

═══════════════════════════════════════════════════════════════════════════════
# PART 7 — STRAY ACCOUNT CLEANUP (Item 13)
═══════════════════════════════════════════════════════════════════════════════

## 7.1 — Investigate and clean up account 9048249558 (Item 13)

The user added account 9048249558 but never sent any messages with it, yet it shows issues.

**Steps (read-only investigation first):**
```bash
docker exec claudegreenapi-db-1 psql -U afrakala -d whatsapp_sender -c "
  SELECT id, instance_id, name, status, created_via_partner, phone, days_active,
         throttle_factor, cooldown_until, is_orphaned
  FROM accounts
  WHERE instance_id::text LIKE '%9048%' OR phone LIKE '%9048%'
  ORDER BY created_at;"
```
```bash
docker exec claudegreenapi-db-1 psql -U afrakala -d whatsapp_sender -c "
  SELECT COUNT(*) as incidents FROM account_incidents
  WHERE id_instance::text LIKE '%9048%';"
```

**Then decide:**
- If the account was created by the PHASE 0 probe (created_via_partner=true, days_active=0,
  no real sends) → **soft-delete it** (status='deleted') and call deleteInstanceAccount
  via Partner API to stop billing. Log the deletion.
- If it has real data (campaigns, contacts assigned) → leave it, just disconnect
  (set status='disconnected') and note it for the user.
- If it shows yellowCard in account_incidents → it got carded because it was connected
  via API without warm-up. This is expected behavior. Note this in the report.

**Report clearly:** what this account is, why it has issues, and what you did with it.

## 7.2 — Verify + commit PART 7
```bash
cd backend && python -m pytest tests/ -v && cd ..
docker compose up -d --build backend
git add -A && git commit -m "fix: V15 PART 7 — investigate and clean up stray account 9048249558" && git push origin main
```

═══════════════════════════════════════════════════════════════════════════════
# PART 8 — WARM-UP AUTOMATION IMPROVEMENT (Item 26)
═══════════════════════════════════════════════════════════════════════════════

## 8.1 — Auto warm-up toggle for new accounts (Item 26)

**Context:** When adding 50 new accounts, they all need 10 days of warm-up before being
usable for bulk sending. The user wants a toggle so new accounts automatically warm up
without manual intervention.

**Current state:** V14 PART F already built the 10-day warm-up governor (≤5/day first 10 days,
≤20 new contacts/day). But the user wants the system to ACTIVELY warm up new accounts
(not just passively limit them).

**Implementation:**
```sql
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS auto_warmup boolean DEFAULT false;
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS warmup_started_at timestamp;
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS warmup_completed boolean DEFAULT false;
```

- On the accounts page and partner page, each account gets a toggle:
  «🔥 گرم‌سازی خودکار» (default OFF).
- When ON: the account enters a **managed warm-up** state:
  - Day 1–3: only RECEIVE messages (the account is connected but does NOT send anything
    proactively; if someone messages it, the auto-reply system can respond).
  - Day 4–7: start sending ≤ 3 messages/day to contacts who have messaged us first
    (reply-only mode — the safest sends).
  - Day 8–10: increase to ≤ 10 messages/day, still prioritizing contacts who initiated.
  - Day 11+: set `warmup_completed = true`, toast «✅ گرم‌سازی کامل شد — آماده ارسال انبوه».
    The account is now available for campaign selection.

- **Celery beat task** `process_warmup_accounts` (daily at 09:00 Tehran):
  - For each account with `auto_warmup=True AND warmup_completed=False`:
    - Calculate day number (now - warmup_started_at).
    - If day 4–10: find contacts who have recently messaged this account (from inbox_messages)
      and send a simple, friendly reply (e.g. from a pool of warm-up templates:
      «سلام، ممنون از پیامتان. در خدمتیم.» / «با تشکر، بله موجود است.»).
      Use the normal rate-limited send path.
    - Cap at the day's limit (3 or 10).
    - Day 11+: mark completed.
  - Accounts with `warmup_completed=True` are treated normally by the campaign runner.
  - Accounts with `auto_warmup=True AND warmup_completed=False` are EXCLUDED from campaign
    account selection (the runner skips them, same as cooldown_until).

- **UI:**
  - Account card shows a warm-up progress bar: «گرم‌سازی: روز ۴ از ۱۰ — ۳ پیام امروز».
  - When warmup completes: green badge «آماده».
  - Persian explainer: «۱۰ روز اول پس از اتصال، سامانه به‌آرامی با این شماره کار می‌کند
    تا واتساپ آن را بشناسد و مسدود نکند. پس از ۱۰ روز، شماره آماده ارسال انبوه می‌شود.»

- **Green API's documented warm-up schedule** (encode it):
  - Days 2–4: only receive (~1 msg every 2h incoming).
  - Day 4+: start writing back ~1 msg every 2h.
  - Gradually increase over 7 days.
  - After 25–30 days of no suspicious activity → green light.
  We use a more conservative 10-day active phase (matching V14 F.1.6).

## 8.2 — Verify + commit PART 8
```bash
cd backend && python -m pytest tests/ -v && cd ..
docker compose up -d --build backend worker-general worker-webhooks beat
cd frontend && npm run build && cd .. && docker compose up -d --build --no-deps frontend
git add -A && git commit -m "feat: V15 PART 8 — auto warm-up toggle for new accounts (10-day managed ramp, reply-only, daily beat task)" && git push origin main
```

═══════════════════════════════════════════════════════════════════════════════
# FINAL VERIFICATION
═══════════════════════════════════════════════════════════════════════════════
```bash
cd C:/Users/AFRA/Desktop/bots/claudegreenapi/backend
python -m pytest tests/ -v
cd .. && docker compose up -d --build
sleep 15
curl -s http://localhost:8002/health/detailed | python -m json.tool
curl -s -o /dev/null -w "frontend HTTP %{http_code}\n" http://localhost:3002/
git log --oneline -8
git status --short
```
Confirm: 8 commits (PART 1–8), all pushed, clean tree, all containers healthy,
test count grew, no regressions.

═══════════════════════════════════════════════════════════════════════════════
# FINAL REPORT
═══════════════════════════════════════════════════════════════════════════════

Produce a clear report with:

1. **PER-ITEM STATUS** — all 26 items, numbered, each:
   ✅ fixed/built | ⚠️ partially done (with explanation) | ❌ not done (with reason)

   Map: Item 1 = answered (no code change — "don't delete on yellowCard"),
   Items 2,3 = PART 1, Item 4 = PART 2, Item 5 = PART 2, Items 6,14,15,16,23 = answered
   (explanations only — no code change), Items 7,17 = PART 2, Item 8 = PART 2, Item 9 = PART 2,
   Item 10 = PART 2, Item 11 = PART 2, Item 12 = PART 1, Item 13 = PART 7, Item 18 = PART 2,
   Item 19 = PART 3, Item 20 = PART 3, Item 21 = PART 4, Item 22 = PART 1, Item 24 = PART 6,
   Item 25 = PART 5, Item 26 = PART 8.

2. **AUTONOMOUS DECISIONS** — every judgment call.
3. **COMMIT HASHES** — PART 1 through PART 8.
4. **TEST COUNT** — before → after.
5. **Items that were EXPLANATIONS only** (1, 6, 13, 14, 15, 16, 23) — note that these
   required no code change, just user education (already provided in chat).