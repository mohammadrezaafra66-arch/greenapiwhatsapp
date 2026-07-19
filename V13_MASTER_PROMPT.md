# CLAUDE CODE MASTER PROMPT — V13 (Send System Enhancements)
# Afrakala WhatsApp Sender
# Repo: https://github.com/mohammadrezaafra66-arch/greenapiwhatsapp
# Local: C:\Users\AFRA\Desktop\bots\claudegreenapi

## AUTONOMOUS EXECUTION CONTRACT
- Run every phase sequentially. NEVER ask for confirmation or present choices.
- At each decision point, pick the safest reasonable option, note it in the summary, continue.
- Verify → commit → push each FEATURE as its own commit (backend tests + browser-check frontend).
- Only hard-stop on irreversible data loss. Everything else: proceed.
- Use afrakala/whatsapp_sender DB, real container/service names (claudegreenapi-db-1, backend, worker-general, worker-webhooks, beat, frontend).
- Adapt all snippets to the app's real conventions. Keep changes ADDITIVE. Preserve ALL existing features.
- After each feature: run pytest, rebuild affected services, verify, commit, push. Then move to next.

## CONTEXT (current send system — do not break)
- Tables: campaigns, campaign_contacts (+ delivery_status, green_api_message_id), accounts, contacts, daily_send_logs.
- Runners: campaign_runner.py (PV), group_campaign_runner.py (groups).
- generate_message: multi-provider AI (OpenAI→DeepSeek→Gemini + DB key pool) + template fallback.
- Rate limiting: Redis hour/day counters (redis_rate_limiter.py). Per-instance semaphore + circuit breaker.
- Webhooks update delivery_status (delivered/read/yellowCard).
- Opt-out line "برای لغو عدد ۱۱ ارسال کنید" (include_opt_out toggle).
- Shamsi scheduling, per-group product variation, weighted selection all exist.

Build these 8 features, each as its own commit.

---

# ═══════════════════════════════════════════════
# FEATURE 1 — A/B message testing
# ═══════════════════════════════════════════════

## Goal
Create a campaign with TWO message variants (A and B). System splits recipients 50/50, sends each half
its variant, then reports which variant had better delivery/read rates.

## DB (main.py DDL)
```python
"ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS ab_test_enabled boolean DEFAULT false",
"ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS variant_b_prompt text",
"ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS variant_b_template text",
"ALTER TABLE campaign_contacts ADD COLUMN IF NOT EXISTS ab_variant varchar(1)",  # 'A' or 'B'
```

## Backend
- Campaign create body: `ab_test_enabled: bool`, `variant_b_prompt: str|None`, `variant_b_template: str|None`.
- When a campaign starts with ab_test_enabled, assign each campaign_contact a variant: alternate A/B
  (or random 50/50) at queue time, store in campaign_contacts.ab_variant.
- In the runner, when building the message for a contact: if ab_variant=='B', use variant_b_prompt/template;
  else use the normal prompt/template.
- Add endpoint GET /campaigns/{id}/ab-results:
  For each variant, count sent/delivered/read/failed and compute delivered% and read%. Return both + a winner
  (higher read%, tiebreak delivered%).

```python
@router.get("/{campaign_id}/ab-results")
async def ab_results(campaign_id: str, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import func as f
    rows = await db.execute(
        select(
            CampaignContact.ab_variant,
            f.count().label("total"),
            f.sum(case((CampaignContact.delivery_status == "delivered", 1), else_=0)).label("delivered"),
            f.sum(case((CampaignContact.delivery_status == "read", 1), else_=0)).label("read"),
            f.sum(case((CampaignContact.status == "failed", 1), else_=0)).label("failed"),
        ).where(CampaignContact.campaign_id == uuid.UUID(campaign_id))
         .group_by(CampaignContact.ab_variant)
    )
    variants = {}
    for r in rows.all():
        if not r.ab_variant:
            continue
        total = r.total or 1
        variants[r.ab_variant] = {
            "total": r.total, "delivered": r.delivered or 0, "read": r.read or 0, "failed": r.failed or 0,
            "delivered_pct": round(100*(r.delivered or 0)/total, 1),
            "read_pct": round(100*(r.read or 0)/total, 1),
        }
    winner = None
    if "A" in variants and "B" in variants:
        a, b = variants["A"], variants["B"]
        winner = "A" if (a["read_pct"], a["delivered_pct"]) >= (b["read_pct"], b["delivered_pct"]) else "B"
    return {"variants": variants, "winner": winner}
```

## Frontend
- Campaign create modal: a toggle "تست A/B". When on, show a second message/prompt field labeled "نسخه B".
- Campaign detail/analytics: an "نتایج تست A/B" panel showing both variants' delivered%/read% side by side
  with the winner highlighted (🏆).

Commit: "feat: V13.1 — A/B message testing (two variants, 50/50 split, winner by read/delivered rate)"

---

# ═══════════════════════════════════════════════
# FEATURE 2 — Smart account rotation (health-weighted)
# ═══════════════════════════════════════════════

## Goal
Instead of plain round-robin, prefer HEALTHIER accounts (lower yellowCard rate, not near daily cap) when
picking which account sends the next message. Unhealthy accounts get fewer sends.

## Backend
Add a health score per account, computed from recent stats:
- yellowCard rate (last 7 days) → lower is better
- remaining daily capacity (computed_daily_limit - sent_today) → more is better
- account not in circuit-breaker/degraded state

Create `backend/app/services/account_health.py`:
```python
async def account_health_score(account, db) -> float:
    """0..1 score; higher = healthier/preferred for sending."""
    # remaining capacity ratio
    limit = account.computed_daily_limit or 1
    remaining = max(0, limit - (account.sent_today or 0))
    cap_ratio = remaining / limit if limit else 0
    # yellowCard rate last 7d from campaign_contacts of this account
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(days=7)
    total_q = await db.execute(select(func.count()).where(
        CampaignContact.account_id == account.id, CampaignContact.sent_at >= cutoff))
    total = total_q.scalar() or 0
    yellow_q = await db.execute(select(func.count()).where(
        CampaignContact.account_id == account.id,
        CampaignContact.sent_at >= cutoff,
        CampaignContact.delivery_status == "yellowCard"))
    yellow = yellow_q.scalar() or 0
    yellow_rate = (yellow / total) if total else 0
    health = (0.6 * cap_ratio) + (0.4 * (1 - yellow_rate))
    return max(0.0, min(1.0, health))
```
(Adapt column names — account_id may live on campaign_contacts; if not, associate via campaign→account.
If per-contact account isn't tracked, add `ALTER TABLE campaign_contacts ADD COLUMN IF NOT EXISTS account_id uuid` and populate it at send time.)

In the runner's account-selection (where round-robin picks the next active account), replace with weighted
choice by health score:
```python
import random
def pick_account_weighted(accounts, scores):
    weights = [max(0.01, scores.get(str(a.id), 0.5)) for a in accounts]
    return random.choices(accounts, weights=weights, k=1)[0]
```
Keep round-robin as a fallback when all scores are equal/unavailable.

Add a toggle so the user can choose "چرخش ساده" vs "چرخش هوشمند (بر اساس سلامت)":
```python
"ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS smart_rotation boolean DEFAULT false",
```

## Frontend
- Campaign create modal: toggle "چرخش هوشمند حساب‌ها (اولویت با حساب سالم‌تر)".
- Accounts page or dashboard: show each account's health score as a colored bar (green/amber/red).
- Add GET /accounts/{id}/health returning the score + breakdown.

Commit: "feat: V13.2 — smart health-weighted account rotation (prefers low-yellowCard, high-capacity accounts)"

---

# ═══════════════════════════════════════════════
# FEATURE 3 — Auto best-time detection
# ═══════════════════════════════════════════════

## Goal
Analyze historical delivered/read data by hour-of-day (Tehran) and surface which hours perform best, so the
user can schedule campaigns at high-performing times. Optionally auto-suggest the hourly ramp.

## Backend
Add GET /reporting/best-hours:
```python
@router.get("/best-hours")
async def best_hours(days: int = 30, db: AsyncSession = Depends(get_db)):
    """Read rate and delivered rate by Tehran hour-of-day from campaign_contacts."""
    # Group sent messages by hour (converted to Tehran), compute read%/delivered% per hour
    # Use sent_at; convert UTC→Asia/Tehran; bucket 0..23
    ...
    return {
        "by_hour": [
            {"hour": h, "sent": s, "delivered_pct": dp, "read_pct": rp}
            for h in range(24)
        ],
        "best_hours": [top 3 hours by read_pct with enough volume],
    }
```
Implement the Tehran-hour bucketing in SQL or Python (fetch sent_at + delivery_status, convert, aggregate).
Only include hours with a minimum sample size (e.g. ≥5 sends) in "best_hours".

## Frontend
- Reporting page: new tab "بهترین ساعت ارسال" — a bar chart of read%/delivered% by hour (۰ تا ۲۳),
  with the top 3 hours highlighted and a note "بهترین ساعت‌ها برای ارسال: ...".
- In the campaign scheduler, add a hint/button "استفاده از بهترین ساعت‌ها" that pre-fills the send-window
  hours with the detected best hours.

Commit: "feat: V13.3 — best-time analytics (read/delivered rate by Tehran hour + top-hours suggestion)"

---

# ═══════════════════════════════════════════════
# FEATURE 4 — Smart blacklist (auto opt-out / block)
# ═══════════════════════════════════════════════

## Goal
When a contact replies with the opt-out keyword (e.g. "۱۱" or "لغو") OR blocks the account (incomingBlock
webhook), automatically add them to the blacklist so future campaigns skip them. Show an opt-out log.

## Backend
- In the webhook handler for incoming messages: if the message text matches an opt-out pattern
  (normalize digits; match "۱۱"/"11"/"لغو"/"لغو ۱۱"/"stop"/"unsubscribe"), set the contact's blacklisted=true
  and record the reason + timestamp.
- The incomingBlock webhook already auto-blacklists (from V6) — ensure it also logs the reason.
- Add a table opt_out_log (or reuse a column) capturing: contact phone, reason (opt_out_keyword / blocked),
  campaign_id if known, timestamp.
```python
"""CREATE TABLE IF NOT EXISTS opt_out_log (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    phone varchar(20),
    reason varchar(50),
    campaign_id uuid,
    created_at timestamp DEFAULT now()
)"""
```
- Ensure the campaign runner already skips blacklisted contacts (it does) — verify.
- Add GET /blacklist/opt-out-log returning recent auto opt-outs.
- Make the opt-out keyword configurable (settings or a constant): default set {"۱۱","11","لغو","لغو۱۱","stop","unsubscribe","لغو عضویت"}.

## Frontend
- Blacklist page: a section "لغو خودکار" listing auto opt-outs (phone, reason, time) from /blacklist/opt-out-log.
- A small stat on the dashboard: "X نفر این هفته لغو کردند".

Commit: "feat: V13.4 — smart blacklist: auto opt-out on keyword reply + block, with opt-out log"

---

# ═══════════════════════════════════════════════
# FEATURE 5 — Rich message formatting
# ═══════════════════════════════════════════════

## Goal
Let users apply WhatsApp formatting in templates/messages: *bold*, _italic_, ~strikethrough~, ```monospace```,
and bullet lists. Provide a small formatting toolbar in the message editor.

## Backend
- WhatsApp uses inline markers already (*bold*, _italic_, ~strike~, ```mono```). No API change needed for
  text sends — just ensure the message text passes through unmodified (don't strip these characters).
- If the GPT prompt should produce formatted output, add an option `use_rich_formatting: bool` on the campaign
  that instructs GPT to use WhatsApp formatting (bold product names, etc.):
```python
"ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS use_rich_formatting boolean DEFAULT false",
```
  When true, add to the GPT system prompt: "از قالب‌بندی واتساپ استفاده کن: نام محصولات را با *ستاره* پررنگ کن،
  نکات مهم را برجسته کن." When false, keep plain.

## Frontend
- In the message/template editor, add a formatting toolbar: buttons for Bold (*), Italic (_), Strikethrough (~),
  Monospace (```), and a bullet-list helper. Clicking wraps the selected text with the marker.
- Add a small legend showing how each renders in WhatsApp.
- Toggle "قالب‌بندی هوشمند با هوش مصنوعی" that sets use_rich_formatting.

Commit: "feat: V13.5 — rich WhatsApp formatting (bold/italic/strike/mono + toolbar + optional AI rich output)"

---

# ═══════════════════════════════════════════════
# FEATURE 6 — Live message preview
# ═══════════════════════════════════════════════

## Goal
Before sending, show a live WhatsApp-style preview of the message as it will appear for a sample contact,
including the greeting, injected products with live prices, formatting, and opt-out line.

## Backend
- Add POST /campaigns/preview that takes the campaign config (prompt/template, opening settings, product
  settings, opt-out, rich formatting) + an optional sample contact, and returns the FULLY BUILT message text
  exactly as the runner would produce it (call the same generate_message path, but don't send).
```python
@router.post("/preview")
async def preview_message(body: CampaignPreviewBody, db: AsyncSession = Depends(get_db)):
    # Build the message using the SAME code path as the runner (generate_message + product injection +
    # opening + opt-out + formatting), with a sample contact (first contact or a dummy).
    text = await build_campaign_message_preview(body, db)
    return {"preview": text}
```
Reuse the real message-building functions so the preview matches actual output (don't reimplement).

## Frontend
- In the campaign create modal, a "پیش‌نمایش" button that calls /campaigns/preview and shows the result in a
  WhatsApp-style chat bubble (green bubble, RTL, emojis, formatting rendered). Update live as settings change
  (debounced).
- Render WhatsApp markers (*bold* → bold, _italic_ → italic) in the preview bubble so it looks real.

Commit: "feat: V13.6 — live WhatsApp-style message preview (same build path as runner, rendered formatting)"

---

# ═══════════════════════════════════════════════
# FEATURE 7 — Campaign ROI report
# ═══════════════════════════════════════════════

## Goal
Per campaign, track outcomes beyond delivery: how many replied, and manual tags for "interested" / "purchased"
so the user can measure ROI. Provide a report.

## DB
```python
"ALTER TABLE campaign_contacts ADD COLUMN IF NOT EXISTS replied boolean DEFAULT false",
"ALTER TABLE campaign_contacts ADD COLUMN IF NOT EXISTS outcome varchar(30)",  # interested | purchased | not_interested | null
"ALTER TABLE campaign_contacts ADD COLUMN IF NOT EXISTS outcome_note text",
```

## Backend
- Webhook: when an incoming message arrives from a number that is a campaign_contact of a recent campaign,
  mark that campaign_contact.replied=true (best-effort match by phone + recency).
- Endpoints:
  - PUT /campaigns/{id}/contacts/{contact_id}/outcome — set outcome (interested/purchased/not_interested) + note.
  - GET /campaigns/{id}/roi — returns: sent, delivered, read, replied counts + reply rate; and counts by outcome
    (interested/purchased) + a simple conversion funnel (sent → delivered → read → replied → purchased).

## Frontend
- Campaign detail: an "گزارش بازده (ROI)" panel: funnel (ارسال → تحویل → خوانده → پاسخ → خرید) with counts and
  percentages; plus a per-contact list where the user can tag each replied contact as علاقه‌مند / خرید کرد /
  علاقه‌مند نیست with an optional note.
- Show reply rate and purchase count prominently.

Commit: "feat: V13.7 — campaign ROI: reply tracking + manual outcome tags + conversion funnel report"

---

# ═══════════════════════════════════════════════
# FEATURE 8 — Drip sending (spread over days)
# ═══════════════════════════════════════════════

## Goal
Instead of sending the whole campaign at once, spread it over N days with a daily quota, automatically
continuing each day until done — safer for deliverability and warm-up.

## DB
```python
"ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS drip_enabled boolean DEFAULT false",
"ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS drip_per_day integer DEFAULT 50",
"ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS drip_last_run_date date",
```

## Backend
- When drip_enabled, the campaign should send at most drip_per_day contacts per day, then pause until the next
  day, then resume automatically.
- Implement via the existing rate-limit/window logic + a daily counter per campaign: track how many were sent
  today for this campaign; when it hits drip_per_day, stop for the day (set a pause reason "سهمیه روزانه drip پر شد").
- A beat task (daily at start of send window, Tehran) resumes drip campaigns that still have pending contacts,
  resetting the per-day counter.
- Reuse Redis counters keyed by campaign+date for the per-day drip count.

## Frontend
- Campaign create modal: toggle "ارسال تدریجی (drip)" + number "تعداد در روز". Show an estimate: "با N در روز،
  کل کمپین در حدود X روز تکمیل می‌شود" (computed from recipient count / drip_per_day).
- Campaign detail: show drip progress — "امروز: X از N ارسال شد | باقی‌مانده کل: Y".

Commit: "feat: V13.8 — drip sending (daily quota, auto-resume next day, completion estimate)"

---

# ═══════════════════════════════════════════════
# FINAL VERIFICATION (after all 8)
# ═══════════════════════════════════════════════

```bash
cd C:/Users/AFRA/Desktop/bots/claudegreenapi/backend
python -m py_compile app/main.py app/models/*.py app/services/*.py app/api/v1/*.py app/workers/*.py
python -m pytest tests/ -v
cd ..
docker compose up -d --build backend worker-general worker-webhooks beat
sleep 10
curl -s http://localhost:8002/health/detailed | python -m json.tool
# spot-check new endpoints:
curl -s "http://localhost:8002/api/v1/reporting/best-hours?days=30" | python -m json.tool | head
curl -s "http://localhost:8002/api/v1/blacklist/opt-out-log" | python -m json.tool | head
cd frontend && npm run build && cd ..
docker compose up -d --build --no-deps frontend
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:3002/
```

Each feature already committed+pushed separately above. Confirm `git log --oneline -8` shows V13.1–V13.8.

## NOTES TO RECORD IN SUMMARY
- Any feature where the existing schema lacked a needed column (e.g. campaign_contacts.account_id) and you added it.
- Confirm A/B split actually assigns A/B and the results endpoint computes a winner.
- Confirm smart rotation falls back to round-robin when health scores are equal/missing.
- Confirm preview uses the SAME build path as the runner (not a re-implementation).
- Confirm drip stops at the daily quota and auto-resumes next day.
- Note that best-hours/ROI/health data will be sparse until more real sends accumulate — logic verified regardless.