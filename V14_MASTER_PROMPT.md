# CLAUDE CODE MASTER PROMPT — V14
# Green API Partner: 24 Features + Full Menu Redesign
# Project: Afrakala WhatsApp Sender
# Repo: https://github.com/mohammadrezaafra66-arch/greenapiwhatsapp
# Local: C:\Users\AFRA\Desktop\bots\claudegreenapi

═══════════════════════════════════════════════════════════════════════════════
# SECTION 0 — AUTONOMOUS EXECUTION CONTRACT (READ FIRST, OBEY ALWAYS)
═══════════════════════════════════════════════════════════════════════════════

Execute this ENTIRE document end-to-end WITHOUT asking the user anything.
The user is NOT available. Every decision is yours.

1. NEVER ask for confirmation. NEVER present choices. NEVER wait for input.
2. On ambiguity: choose the SAFEST option, record it under "AUTONOMOUS DECISIONS"
   in the final report, and continue.
3. Work PHASE by PHASE, PART by PART, in the exact written order.
4. After each PART: run pytest → rebuild containers → verify live → commit → push.
   ONE COMMIT PER PART. Never batch.
5. HARD STOP only if an action would irreversibly destroy REAL data (real contacts,
   real groups, real campaigns, real sent messages). Everything else: proceed.
6. If a Green API method returns 403 (plan-restricted): DO NOT remove the feature.
   Build it, catch the 403, record it in `method_support`, show a Persian
   «پشتیبانی نمی‌شود» state in the UI. This is a REQUIREMENT.
7. NEVER break the existing send path. Every new column/flag DEFAULTS to a value
   that reproduces today's exact behavior.
8. NEVER enable Green API polling (`receiveNotification`). This instance is in
   WEBHOOK mode. Polling and webhooks are MUTUALLY EXCLUSIVE here.
9. NEVER print, log, or return any `apiTokenInstance` or `partnerToken`. There is a
   mandatory test for this.

## Environment (verified — use as-is, do not re-discover)
- Containers: `claudegreenapi-db-1` (postgres; user `afrakala`, db `whatsapp_sender`),
  `redis`, `backend` (:8002), `worker-general`, `worker-webhooks`, `beat`, `frontend` (:3002).
- All containers already have `restart: always`. Do not change.
- Backend FastAPI in `backend/app/`. Frontend React/Vite in `frontend/src/`.
- Celery queues: `sending`, `webhooks`, `campaigns`, `extraction`, `backfill`.
  NOTE: `poll_accounts` routes to the **`webhooks`** queue, not `worker-general`.
- DDL is applied idempotently at startup in `backend/app/main.py`
  (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` / `CREATE TABLE IF NOT EXISTS`).
  Follow that existing pattern for ALL new DDL. No Alembic migration needed.
- All user-facing dates: **Asia/Tehran**, displayed as **Shamsi (Jalali)**.
- 142 backend tests currently pass. Do not regress. Add tests per feature.
- LAN URL: `http://192.168.170.8:3002` (frontend uses relative `/api/v1`, nginx proxies).

## Green API — verified account facts
- Account type: **PARTNER**. Partner token format `gac.xxxxx…`.
- Live instance: **idInstance 7105325764**, WhatsApp **989122270261**, state `authorized`.
- Webhook (reserved ngrok domain — DO NOT CHANGE):
  `https://multidisciplinary-jeri-physiognomically.ngrok-free.dev/api/v1/webhook/7105325764`
- Instance methods: `POST {apiUrl}/waInstance{idInstance}/{method}/{apiTokenInstance}` (JSON)
- Media host `{mediaUrl}` for: `sendFileByUpload`, `uploadFile`, `downloadFile`.
- Partner methods: `POST {partnerApiUrl}/partner/{method}/{partnerToken}`
- chatId: `{number}@c.us` (personal) · `{groupId}@g.us` (group)

## GREEN API RATE LIMITS — ENFORCE ALL (per instance, per method; exceed → HTTP 429)
Build a Redis token-bucket limiter keyed `ratelimit:{idInstance}:{method}`. Wrap EVERY
outbound Green API call. On 429: exponential backoff with jitter, max 3 retries.

| req/sec | Methods |
|---|---|
| **50** | sendMessage, sendFileByUrl, sendFileByUpload, sendLocation, sendContact, sendPoll, forwardMessages, AND partner methods (getInstances, createInstance, deleteInstanceAccount) |
| **10** | getMessage, addGroupParticipant, removeGroupParticipant, setGroupAdmin, removeAdmin, leaveGroup, readChat, checkWhatsapp, getAvatar, deleteMessage, archiveChat, unarchiveChat, deleteStatus |
| **5** | sendTextStatus, sendVoiceStatus, sendMediaStatus, downloadFile |
| **3** | qr |
| **1** | **sendInteractiveButtons**, **sendInteractiveButtonsReply**, getSettings, setSettings, getStateInstance, reboot, logout, scanQrCode, getWaSettings, getChatHistory, lastIncomingMessages, lastOutgoingMessages, createGroup, updateGroupName, getGroupData, setGroupPicture, getContacts, getContactInfo, editMessage, setDisappearingChat, getMessagesCount, showMessagesQueue, clearMessagesQueue, getWebhooksCount, clearWebhooksQueue, getIncomingStatuses, getOutgoingStatuses, getStatusStatistic |
| **0.1** | **setProfilePicture** — ONE call per 10 SECONDS. Critical. |

## GREEN API ERROR CODES
- 400 bad request · 401 auth (bad token) · **403 = method not available on this plan**
- **429** = rate limit exceeded → back off + jitter
- **466** = Developer-plan monthly quota exceeded (shouldn't occur on Partner; log loudly if seen)

## KNOWN-RESTRICTED METHODS (expect 403 — build anyway, degrade gracefully)
- `getIncomingStatuses`, `joinGroupViaLink`, `getContactsBlock` → already 403 on this instance.
- Legacy `sendButtons`, `sendTemplateButtons`, `sendListMessage` → **HARD 403, DEPRECATED.**
  DO NOT USE. Use `sendInteractiveButtons` / `sendInteractiveButtonsReply`.
- `sendReaction` → **NOT A DOCUMENTED HTTP METHOD.** See FEATURE 11 for exact handling.

═══════════════════════════════════════════════════════════════════════════════
# PHASE 0 — PREFLIGHT (before ANY feature code)
═══════════════════════════════════════════════════════════════════════════════

## 0.1 Health check
```bash
cd C:/Users/AFRA/Desktop/bots/claudegreenapi
docker compose ps
curl -s http://localhost:8002/health/detailed | python -m json.tool
git status --short && git log --oneline -3
```
Confirm stack up, HEAD == origin/main, clean tree, branch `main`.
If not on main: `git checkout main && git pull origin main`.

## 0.2 Partner token wiring
Add to `.env` (create keys if absent; DO NOT overwrite existing values):
```
GREEN_PARTNER_TOKEN=
GREEN_PARTNER_API_URL=https://api.green-api.com
PARTNER_DAILY_RATE=0
```
Add the same keys with EMPTY values to `.env.example`. Never commit a real token.
Expose in config: `GREEN_PARTNER_TOKEN: str = ""`,
`GREEN_PARTNER_API_URL: str = "https://api.green-api.com"`, `PARTNER_DAILY_RATE: float = 0`.

**If `GREEN_PARTNER_TOKEN` is empty at runtime:** every Partner UI element RENDERS but is
DISABLED with the Persian note «توکن پارتنر تنظیم نشده است — آن را در فایل .env قرار دهید».
Nothing crashes. All non-Partner features work normally. (The user may not have pasted it yet.)

## 0.3 CAPABILITY PROBE (throwaway script — DELETE after running)
Write `backend/scripts/probe_methods.py`. It calls each method below against the LIVE
instance and prints:  `| method | HTTP | SUPPORTED / 403-UNSUPPORTED / ERROR |`

⚠️ **PROBE SAFETY RULES — VIOLATION IS A HARD STOP:**
- NEVER send to a real contact or real group.
- NEVER add/remove a real group participant; never change a real group's name/picture/settings.
- NEVER delete or edit a real (non-probe) message.
- NEVER change the real profile picture. NEVER leave a real group. NEVER create a group.
- If a probe REQUIRES a send, target ONLY the account's own number `989122270261@c.us`,
  send text `probe`, then clean it up with `deleteMessage`. At most ONCE.
- Destructive group methods: DO NOT probe. Mark `UNKNOWN-NOT-PROBED`; the runtime 403
  handler will classify them on first real use.
- `setProfilePicture`: DO NOT probe (0.1/s + it would change the real avatar).
  Mark `UNKNOWN-NOT-PROBED`.

Probe (read-only or self-targeted only):
```
getSettings, getStateInstance, getWaSettings, getChats, getContacts, getContactInfo,
getAvatar, checkWhatsapp, getChatHistory, lastIncomingMessages, lastOutgoingMessages,
lastIncomingCalls, lastOutgoingCalls, getMessagesCount, showMessagesQueue,
getWebhooksCount, getStatusStatistic, getOutgoingStatuses, getIncomingStatuses,
getGroupData (READ-ONLY, on a group we already belong to),
sendInteractiveButtons (self only), sendInteractiveButtonsReply (self only),
sendContact (self only), sendLocation (self only), forwardMessages (self→self),
editMessage (on the self probe msg), deleteMessage (on the self probe msg),
readChat (self), archiveChat then immediately unarchiveChat (self),
setDisappearingChat (self, value 0 = off → no-op),
sendReaction (self — to DEFINITIVELY determine whether this endpoint exists)
```
Partner probes (only if GREEN_PARTNER_TOKEN set):
```
getInstances            ← safe, read-only. RUN IT.
createInstance          ← DO NOT PROBE (would create a billable instance). UNKNOWN-NOT-PROBED.
deleteInstanceAccount   ← DO NOT PROBE. UNKNOWN-NOT-PROBED.
```
Persist every result into `method_support` (see PART G). Then **DELETE the probe script**
(`git rm` if staged) — it must not ship. Print the full table in the final report.

═══════════════════════════════════════════════════════════════════════════════
# PART A — PARTNER API (Features 1–6)
═══════════════════════════════════════════════════════════════════════════════

## A.0 Shared Partner client
`backend/app/services/green_partner.py`:
```python
"""Green API Partner client. Token NEVER logged, NEVER returned."""
import httpx
from app.core.config import settings

class PartnerNotConfigured(Exception):
    """GREEN_PARTNER_TOKEN missing."""

def _require_token() -> str:
    if not settings.GREEN_PARTNER_TOKEN:
        raise PartnerNotConfigured("توکن پارتنر تنظیم نشده است")
    return settings.GREEN_PARTNER_TOKEN

async def _partner_post(method: str, body: dict | None = None):
    token = _require_token()
    url = f"{settings.GREEN_PARTNER_API_URL.rstrip('/')}/partner/{method}/{token}"
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(url, json=body or {})
    if r.status_code >= 400:
        # NEVER include url/token in the error.
        raise RuntimeError(f"Partner method {method} failed: HTTP {r.status_code}")
    return r.json()

async def get_instances() -> list[dict]:
    return await _partner_post("getInstances")

async def create_instance(payload: dict) -> dict:
    return await _partner_post("createInstance", payload)

async def delete_instance_account(id_instance: int) -> dict:
    return await _partner_post("deleteInstanceAccount", {"idInstance": int(id_instance)})
```
⚠️ The token lives IN THE URL. Never log the URL, never put it in an exception, never echo it.
**Mandatory test:** assert the raised error string contains neither the token nor `gac.`.

## A.1 DB (idempotent DDL in main.py)
```sql
CREATE TABLE IF NOT EXISTS partner_instance_log (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    id_instance bigint,
    action varchar(30),          -- created | deleted | synced
    detail text,
    created_at timestamp DEFAULT now()
);
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS created_via_partner boolean DEFAULT false;
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS partner_created_at timestamp;
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS profile_picture_url text;
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS tariff varchar(40);
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS is_orphaned boolean DEFAULT false;
```

## A.2 FEATURE 1 — createInstance (ساخت شماره جدید از داشبورد)
`POST /api/v1/partner/instances`  body `{ "name": str, "delay_ms": int = 15000 }`

Build the payload EXACTLY like this (verified param names; booleans are the STRINGS
"yes"/"no"; delay is an integer):
```python
payload = {
    "name": name,
    "webhookUrl": "https://multidisciplinary-jeri-physiognomically.ngrok-free.dev/api/v1/webhook/",
    "webhookUrlToken": "",
    "delaySendMessagesMilliseconds": delay_ms,   # default 15000 — anti-ban
    "markIncomingMessagesReaded": "no",
    "markIncomingMessagesReadedOnReply": "no",
    "outgoingWebhook": "yes",
    "outgoingMessageWebhook": "yes",
    "outgoingAPIMessageWebhook": "yes",
    "incomingWebhook": "yes",
    "stateWebhook": "yes",           # REQUIRED for FEATURE 23 (yellowCard)
    "deviceWebhook": "no",
    "keepOnlineStatus": "no",
    "pollMessageWebhook": "yes",
    "incomingBlockWebhook": "yes",   # REQUIRED for smart blacklist
    "incomingCallWebhook": "yes",    # REQUIRED for FEATURE 24
    "editedMessageWebhook": "yes",
    "deletedMessageWebhook": "yes",
}
```
**Webhook-URL bootstrap problem:** the app route is `/api/v1/webhook/{idInstance}` but we
don't know the new id until createInstance returns. Therefore:
1. Create with the BASE url above (trailing slash, no id).
2. Read the returned `idInstance` + `apiTokenInstance`.
3. IMMEDIATELY call that instance's own `setSettings` with the full correct
   `.../api/v1/webhook/{idInstance}`.
4. ALSO add a `POST /api/v1/webhook/` route (no id) that reads `instanceData.idInstance`
   from the body and dispatches to the same handler. Safer regardless. Implement it.

Green API creation timing (documented):
- Poll `getStateInstance` every **5 s**. A `null`/empty body = "still being created".
- QR is only available ~**2 minutes** after creation. Do not error before then.
- Once state is `notAuthorized`, the QR is ready.

Persist `accounts` row: `instance_id=idInstance`, `api_token=apiTokenInstance`,
`status='pending'`, `created_via_partner=true`, `partner_created_at=now()`,
`days_active=0` (so warm-up applies), `delay_ms`. Log `partner_instance_log(action='created')`.

Response: `{ "id": <uuid>, "id_instance": 1101…, "qr_url": "https://qr.green-api.com/waInstance{id}/{token}" }`
⚠️ That URL necessarily contains the token. It is the ONLY place a token may leave the backend,
and only to the dashboard user. Generate on demand. Never log it. Never store it.

## A.3 FEATURE 2 — deleteInstanceAccount (حذف شماره)
`DELETE /api/v1/partner/instances/{id_instance}`

⚠️ **VERBATIM Green API warning — surface in Persian:** deleting an instance does NOT log out
the linked device; an active session remains in the mobile app. Recommended: Logout first.

Flow:
1. Frontend **typed-confirmation modal**: user must type the phone number (or the word `حذف`)
   to enable the confirm button.
2. Persian warning in the modal:
   «⚠️ حذف instance، دستگاه متصل را logout نمی‌کند و نشست فعال در گوشی باقی می‌ماند.
    توصیه: ابتدا «خروج از حساب» را بزنید، سپس حذف کنید.»
3. Backend: if the account is authorized → call instance `logout` FIRST, wait, then
   `deleteInstanceAccount`.
4. Success `{"deleteInstanceAccount": true}` → soft-delete locally (`status='deleted'`),
   log `partner_instance_log(action='deleted')`.
5. `{"code":404}` (already gone) → treat as success, clean up locally.
   `{"code":401}` → Persian error «توکن پارتنر نامعتبر است».
6. UI note: «پس از حذف، صورتحساب روزانه این شماره متوقف می‌شود.»

## A.4 FEATURE 3 — getInstances sync (همگام‌سازی)
`POST /api/v1/partner/sync` + Celery beat `sync_partner_instances` every **6 hours**.

- Call `getInstances()` (returns ALL instances incl. ones deleted in the last 3 months,
  flagged `deleted: true`).
- For each with `deleted == false`:
  - local row exists → update `tariff`, and `name` only if the local name is still the
    auto-generated default; clear `is_orphaned`.
  - no local row → CREATE (`status='pending'`, `created_via_partner=true`). This pulls in
    instances the user made in the console.
- For each LOCAL account whose `instance_id` is absent from the response (or flagged deleted
  there) → set `is_orphaned = true`. **NEVER auto-delete a local account.** Show a Persian
  badge «در Green API یافت نشد» + a manual delete button.
- Log `partner_instance_log(action='synced', detail=<counts>)`.

## A.5 FEATURE 4 — Partner management page (مدیریت پارتنر)
Route `/partner-instances`, Persian RTL, dark theme.

Table columns: نام (inline-editable) · شماره · idInstance · وضعیت (متصل / در انتظار اتصال /
مسدود / یافت‌نشده) · تعرفه · تاریخ ساخت (Shamsi) · روزهای فعال · هزینه تخمینی ماه ·
اقدامات (QR · اتصال با کد · خروج · حذف).

Summary card above:
- «تعداد instanceهای فعال: N»
- «هزینه تخمینی این ماه» = Σ(days active this month) × `PARTNER_DAILY_RATE`.
  If `PARTNER_DAILY_RATE == 0`, show ONLY the day-count — **do not invent a price.**
- Persian explainer: «صورتحساب پارتنر روزانه است و ساعت ۰۰:۰۰ (UTC+3) کسر می‌شود.
  با موجودی منفی هم instanceها کار می‌کنند.»

Primary button: «➕ افزودن شماره جدید» → create-instance modal (FEATURE 1).

## A.6 FEATURE 5 — In-app QR
`GET /api/v1/partner/instances/{account_id}/qr` → `{ "qr_url": "https://qr.green-api.com/waInstance{id}/{token}" }`
Frontend: render in an `<iframe>` inside a modal; auto-refresh every **2 s**; poll
`GET /accounts/{id}/state` every **3 s**. On `authorized`: close modal, toast
«✅ شماره با موفقیت متصل شد», refresh list.
Persian instructions in the modal:
```
۱. در گوشی، واتساپ را باز کنید
۲. تنظیمات ← دستگاه‌های متصل ← اتصال دستگاه
۳. این کد QR را اسکن کنید
⚠️ ساخت کد QR تا ۲ دقیقه پس از ساخت شماره ممکن است طول بکشد.
```

## A.7 FEATURE 6 — Phone-code auth (اتصال با کد تلفن)
Method: `POST {apiUrl}/waInstance{id}/getAuthorizationCode/{token}`
Body: `{ "phoneNumber": 989122270261 }` — **INTEGER**, international, NO `+`, NO `00`,
no spaces/dashes/parens. Normalize server-side; reject anything else with a Persian 400.
Response: `{ "status": true, "code": "GAPI2015" }`

`POST /api/v1/partner/instances/{account_id}/auth-code` body `{ "phone": "989122270261" }`

⚠️ Preconditions (enforce):
- Instance must be `notAuthorized`. If `authorized`, the UI first offers
  «خروج از حساب (Logout)». **Do NOT auto-logout an authorized account.**
- **The code is valid ~2.5 minutes.** Show a live countdown + a «دریافت کد جدید» button on expiry.

UI: next to «QR» on both the accounts page and partner page → button «اتصال با کد».
```
۱. شماره را وارد کنید (مثال: 989122270261) → [دریافت کد]
۲. کد:   G A P I 2 0 1 5      ⏳ ۰۲:۲۹
۳. در گوشی: واتساپ ← تنظیمات ← دستگاه‌های متصل ← اتصال دستگاه
   ← «اتصال با شماره تلفن» ← کد را وارد کنید
```
Large, letter-spaced, copyable code. Poll state every 3 s; on `authorized` close + toast.

## A.8 Verify + commit PART A
```bash
cd backend && python -m pytest tests/ -v && cd ..
docker compose up -d --build backend worker-general worker-webhooks beat
sleep 10 && curl -s http://localhost:8002/health/detailed | python -m json.tool
curl -s http://localhost:8002/api/v1/partner/instances | python -m json.tool | head -30
cd frontend && npm run build && cd .. && docker compose up -d --build --no-deps frontend
git add -A && git commit -m "feat: V14 PART A — Partner API (create/delete/sync instances, billing page, in-app QR, phone-code auth)" && git push origin main
```

═══════════════════════════════════════════════════════════════════════════════
# PART B — INTERACTIVE & RICH MESSAGING (Features 7, 8, 11, 12, 13, 14)
═══════════════════════════════════════════════════════════════════════════════

## B.1 FEATURE 7 — sendInteractiveButtons (دکمه‌های تعاملی)
⚠️ Rate limit **1 req/sec**. ⚠️ Legacy `sendButtons`/`sendTemplateButtons`/`sendListMessage`
are DEPRECATED and hard-403 — DO NOT USE THEM.

Method: `POST {apiUrl}/waInstance{id}/sendInteractiveButtons/{token}`
```json
{
  "chatId": "79876543210@c.us",
  "header": "Header",
  "body": "Body",
  "footer": "Footer",
  "buttons": [
    { "type": "copy",  "buttonId": "1", "buttonText": "کپی کد",    "copyCode": "3333" },
    { "type": "call",  "buttonId": "2", "buttonText": "تماس",      "phoneNumber": "989122270261" },
    { "type": "url",   "buttonId": "3", "buttonText": "وب‌سایت",   "url": "https://example.com" },
    { "type": "reply", "buttonId": "4", "buttonText": "قیمت" }
  ]
}
```
**HARD CONSTRAINTS (enforce in backend validation AND in the UI):**
- **MAX 3 buttons per message.**
- **Button text ≤ 25 characters.**
- Each button can be pressed **only once**.
- `copy` requires `copyCode`; `call` requires `phoneNumber`; `url` requires `url`;
  `reply` requires nothing extra.
Response: `{ "idMessage": "3EB0C767D097B7C7C030" }`

`sendInteractiveButtonsReply` (reply-only buttons, personal chats, **beta**) — same limits:
```json
{ "chatId":"...", "header":"...", "body":"...", "footer":"...",
  "buttons":[ {"buttonId":"1","buttonText":"بله"}, {"buttonId":"2","buttonText":"خیر"} ] }
```

### DB
```sql
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS use_interactive_buttons boolean DEFAULT false;
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS buttons_config jsonb;      -- array of button objs
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS button_header text;
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS button_footer text;
```

### Runner integration
When `use_interactive_buttons` is true AND `method_support` says sendInteractiveButtons is
SUPPORTED → send via `sendInteractiveButtons` with `body` = the fully built message text
(from the existing `build_message_text()`), plus header/footer/buttons from the campaign.
**⚠️ CRITICAL FALLBACK:** if the call returns 403 at runtime → record UNSUPPORTED in
`method_support`, then **immediately re-send the SAME message as plain text** via the normal
`sendMessage` path so the recipient is never skipped. Log the fallback. Never lose a send.
**⚠️ ALSO:** because buttons render low-level and WhatsApp can break them, ALWAYS append a
plain-text mirror of the button choices to the body (e.g. «۱) قیمت  ۲) موجودی») so the
message still works if buttons don't render.

### Rate-limit interaction (IMPORTANT)
sendInteractiveButtons is **1/sec** while sendMessage is 50/sec. A button campaign to 500
groups will therefore take ≥500 seconds minimum. Surface this in the campaign UI:
«⚠️ ارسال با دکمه حداکثر ۱ پیام در ثانیه است — این کمپین حدود X دقیقه طول می‌کشد.»
Compute X = recipients × 1s and show it live as the user toggles buttons on.

### Frontend
In the campaign create/edit modal, a new collapsible section «دکمه‌های تعاملی»:
- Toggle «ارسال با دکمه‌های تعاملی»
- Fields: سربرگ (header), پانویس (footer)
- Button builder: up to **3** rows. Each row: نوع (پاسخ / کپی / تماس / لینک) +
  متن دکمه (with a live 25-char counter, red past 25) + the type-specific field.
- Live preview showing the WhatsApp bubble with the buttons rendered.
- If `method_support` says UNSUPPORTED → the whole section is disabled + Persian note
  «پشتیبانی نمی‌شود».

## B.2 FEATURE 8 — Button replies (دریافت پاسخ دکمه)
Incoming webhook `incomingMessageReceived` with
`messageData.typeMessage == "interactiveButtons"` or `"interactiveButtonsReply"`.
Shape (parse defensively — treat missing keys as absent, never crash):
```json
{ "typeWebhook":"incomingMessageReceived",
  "messageData": { "typeMessage":"interactiveButtonsReply",
    "interactiveButtonsReply": { "titleText":"...","contentText":"...","footerText":"...",
      "buttons":[ {"type":"reply","buttonId":"1","buttonText":"قیمت"} ] } } }
```
Identify the pressed button by `buttonId` (+ `buttonText`).

### DB
```sql
CREATE TABLE IF NOT EXISTS button_replies (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id uuid,
    contact_phone varchar(20),
    chat_id varchar(60),
    button_id varchar(20),
    button_text text,
    message_id varchar(80),
    created_at timestamp DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_button_replies_campaign ON button_replies(campaign_id);

CREATE TABLE IF NOT EXISTS button_auto_replies (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    button_id varchar(20),          -- match on buttonId
    button_text text,               -- OR match on exact buttonText
    reply_text text NOT NULL,
    enabled boolean DEFAULT true,
    created_at timestamp DEFAULT now()
);
```
On a button-reply webhook:
1. Insert into `button_replies`.
2. Best-effort match the sender phone to a recent `campaign_contacts` row → set
   `replied = true` (feeds the existing V13.7 ROI funnel).
3. If an enabled `button_auto_replies` row matches (by `button_id` or exact `button_text`) →
   send `reply_text` back (through the normal rate-limited send path).

### Frontend
- New page section under محتوا → «دکمه‌های تعاملی»: CRUD for `button_auto_replies`
  (button id/text → reply text, enable/disable).
- Campaign detail: a «پاسخ دکمه‌ها» panel — a bar chart of press counts per buttonId and a
  table of who pressed what (name, phone, button, Shamsi time) + CSV export.

## B.3 FEATURE 11 — Reactions (ری‌اکشن) — ⚠️ SPECIAL HANDLING
**`sendReaction` is NOT in the documented Green API HTTP method list.** Reactions are
documented only on the RECEIVING side (`typeMessage: "reactionMessage"`).

Therefore do BOTH of these:
**(a) RECEIVE (guaranteed to work — build it fully):**
Handle incoming `reactionMessage` webhooks. Store:
```sql
CREATE TABLE IF NOT EXISTS message_reactions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id varchar(60),
    sender_phone varchar(20),
    sender_name text,
    emoji text,
    reacted_message_id varchar(80),   -- quotedMessage.stanzaId
    created_at timestamp DEFAULT now()
);
```
Show reactions inline in the Inbox thread (emoji + who reacted). This is real, useful data
(e.g. a 👍 on a price message = a warm lead) — surface it.

**(b) SEND (probe-gated):**
PHASE 0 probes `sendReaction` against our own number. IF the probe returned a 2xx →
the endpoint exists undocumented: implement `POST /api/v1/messages/react`
`{chatId, messageId, emoji}` and add an emoji bar (👍 ❤️ 😂 😮 😢 🙏) to Inbox messages.
IF the probe returned 404/403/error → record UNSUPPORTED in `method_support`, do NOT ship a
send-reaction button, and note it in the capabilities page as
«ارسال ری‌اکشن: پشتیبانی نمی‌شود (فقط دریافت)».
**Do not guess. Let the probe decide.** Report which branch you took.

## B.4 FEATURE 12 — sendContact (ارسال کارت مخاطب)
`POST {apiUrl}/waInstance{id}/sendContact/{token}` — rate 50/sec.
```json
{ "chatId":"79876543210@c.us",
  "contact": { "phoneContact": 79001234567, "firstName":"...", "middleName":"",
               "lastName":"...", "company":"افراکالا" } }
```
`phoneContact` is REQUIRED (integer, no `+`). Others optional.

Endpoint `POST /api/v1/messages/contact`. UI: in Inbox, a «ارسال کارت تماس» button →
modal with the fields + a saved **«کارت افراکالا»** preset (company = افراکالا, phone =
the default account's number) so staff can send it in one click.
Also add a saved-contacts list (a small `saved_contact_cards` table) so common cards
(sales rep, support) are one click.

## B.5 FEATURE 13 — sendLocation (ارسال موقعیت)
`POST {apiUrl}/waInstance{id}/sendLocation/{token}` — rate 50/sec.
```json
{ "chatId":"...", "nameLocation":"فروشگاه افراکالا", "address":"تهران، ...",
  "latitude":35.6892, "longitude":51.3890 }
```
```sql
CREATE TABLE IF NOT EXISTS saved_locations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    address text,
    latitude double precision NOT NULL,
    longitude double precision NOT NULL,
    is_default boolean DEFAULT false,
    created_at timestamp DEFAULT now()
);
```
Endpoint `POST /api/v1/messages/location`. UI: page محتوا → «کارت تماس و موقعیت» with CRUD
for `saved_locations`; from Inbox, «ارسال موقعیت» → pick a saved location → send.

## B.6 FEATURE 14 — forwardMessages (فوروارد)
`POST {apiUrl}/waInstance{id}/forwardMessages/{token}` — rate 50/sec.
```json
{ "chatId":"<destination>", "chatIdFrom":"<source>", "messages":["BAE587FA1CECF760"] }
```
Endpoint `POST /api/v1/messages/forward`. UI: in Inbox and تاریخچه پیام‌ها, each message gets
a «فوروارد» action → modal to pick destination chat(s) (multi-select from known chats/groups)
→ forward. Show a success/failure toast per destination.

## B.7 Verify + commit PART B
Tests for: 3-button cap, 25-char cap, per-type required fields, the 403→plain-text fallback,
button-reply parsing (all shapes), reaction webhook parsing.
```bash
cd backend && python -m pytest tests/ -v && cd ..
docker compose up -d --build backend worker-general worker-webhooks beat
cd frontend && npm run build && cd .. && docker compose up -d --build --no-deps frontend
git add -A && git commit -m "feat: V14 PART B — interactive buttons + replies, reactions (receive), contact cards, locations, forwarding" && git push origin main
```

═══════════════════════════════════════════════════════════════════════════════
# PART C — MESSAGE CONTROL (Features 9, 10, 20, 21)
═══════════════════════════════════════════════════════════════════════════════

## C.1 FEATURE 9 — editMessage (ویرایش پیام)
`POST {apiUrl}/waInstance{id}/editMessage/{token}` — rate **1/sec**.
`{ "chatId":"...", "idMessage":"...", "message":"متن جدید" }`

⚠️ **HARD RULES (from Green API docs — implement all three):**
1. **15-MINUTE LIMIT.** Only messages younger than 15 minutes can be edited.
2. **Only messages sent VIA API** can be edited (not ones sent from the phone / WhatsApp Web).
3. **The API returns HTTP 200 EVEN WHEN THE EDIT SILENTLY FAILS.** You must watch for an
   `outgoingMessageStatus` webhook with `status:"failed"` and
   `description:"15 minute editing time gap has been expired"`.

Implementation:
- Store `sent_at` for every message we send (already in `campaign_contacts`; also store it
  for Inbox-sent messages).
- UI: the «ویرایش» button only appears if `now() - sent_at < 15 min` AND the message was
  sent by us via API. Show a live countdown («۱۲:۳۴ تا پایان مهلت ویرایش»).
- Backend: re-check the 15-minute window server-side; reject with a Persian 400 if expired.
- Subscribe to `editedMessage` webhook (`editedMessageData.stanzaId`) → mark the local row
  `is_edited=true`, store the new text.
- If an `outgoingMessageStatus` failed-webhook arrives for an edit → toast the user
  «ویرایش انجام نشد: مهلت ۱۵ دقیقه‌ای تمام شده است» and revert the optimistic UI update.
```sql
ALTER TABLE campaign_contacts ADD COLUMN IF NOT EXISTS is_edited boolean DEFAULT false;
ALTER TABLE campaign_contacts ADD COLUMN IF NOT EXISTS edited_at timestamp;
```

## C.2 FEATURE 10 — deleteMessage + campaign recall (حذف پیام)
`POST {apiUrl}/waInstance{id}/deleteMessage/{token}` — rate 10/sec.
`{ "chatId":"...", "idMessage":"..." }` → delete for everyone (within WhatsApp's window).
Add `"onlySenderDelete": true` → delete only on our side.

⚠️ Same silent-failure caveat as edit: HTTP 200 does not guarantee success. Watch the
`deletedMessage` webhook (`deletedMessageData.stanzaId`) to confirm.

Per-message: a «حذف» action in Inbox/history, with a Persian choice
«حذف برای همه» vs «حذف فقط برای من» (`onlySenderDelete`).

**⭐ CAMPAIGN RECALL (the high-value part):**
`POST /api/v1/campaigns/{id}/recall`
- Deletes EVERY message this campaign sent (iterates `campaign_contacts` where
  `green_api_message_id IS NOT NULL`), rate-limited at 10/sec, in a Celery task.
- **Typed-confirmation required**: the user must type the campaign name to enable the button.
- Persian warning: «⚠️ این کار تمام پیام‌های این کمپین را برای همه گیرندگان حذف می‌کند.
  پیام‌هایی که از مهلت حذف واتساپ گذشته باشند حذف نخواهند شد. این عمل برگشت‌ناپذیر است.»
- Progress UI: «حذف شد: X از Y» live.
- Records outcome per contact (`recalled` boolean column).
```sql
ALTER TABLE campaign_contacts ADD COLUMN IF NOT EXISTS recalled boolean DEFAULT false;
```
This is the "I sent the wrong price to 500 groups" panic button. Make it obvious and safe.

## C.3 FEATURE 20 — Send-queue management (مدیریت صف ارسال) — ⭐ EMERGENCY STOP
Methods (all rate 1/sec):
- `getMessagesCount` → number of messages waiting to send
- `showMessagesQueue` (GET) → the queued messages: `messageID`, `type`, `body`
- `clearMessagesQueue` (GET) → **empties the send queue**
- `getWebhooksCount` / `clearWebhooksQueue` → incoming-webhook queue

Meaning: this is the queue **Green API holds before WhatsApp delivery** (messages persist 24h).

Endpoints: `GET /api/v1/queue/{account_id}` (count + contents),
`DELETE /api/v1/queue/{account_id}` (clear).

UI — new page ارسال پیام → «صف ارسال»:
- Big red card per account: «صف ارسال: N پیام در انتظار»
- Table of queued messages (type + body preview).
- **«🛑 خالی کردن صف»** button with typed-confirmation (`پاک کن`) and the Persian warning
  «⚠️ تمام پیام‌های در صف حذف می‌شوند و ارسال نخواهند شد. برای توقف اضطراری یک کمپین اشتباه.»
- **Dashboard integration:** whenever any account's queue count > 0, show a persistent amber
  banner on the dashboard: «⏳ N پیام در صف ارسال — مشاهده صف» linking here.
- **Also expose it in the yellowCard incident flow (FEATURE 23)** — see PART F.
- Green API best practice: before (re)connecting a number, check + clear the queue.
  Add that as a Persian tip on the page.

## C.4 FEATURE 21 — readChat (علامت‌گذاری خوانده‌شده)
`POST {apiUrl}/waInstance{id}/readChat/{token}` — rate 10/sec.
`{ "chatId":"...", "idMessage":"..." }` (idMessage optional).
UI: in Inbox, a «علامت‌گذاری به‌عنوان خوانده‌شده» action per chat + a bulk
«همه را خوانده‌شده کن» button. Update the unread badge (which feeds the sidebar badge).

## C.5 Verify + commit PART C
```bash
cd backend && python -m pytest tests/ -v && cd ..
docker compose up -d --build backend worker-general worker-webhooks beat
curl -s http://localhost:8002/api/v1/queue/<account_id> | python -m json.tool
cd frontend && npm run build && cd .. && docker compose up -d --build --no-deps frontend
git add -A && git commit -m "feat: V14 PART C — edit/delete message (with 15-min + silent-failure handling), campaign recall, send-queue emergency stop, readChat" && git push origin main
```

═══════════════════════════════════════════════════════════════════════════════
# PART D — CHAT & PROFILE (Features 15, 16, 17, 18)
═══════════════════════════════════════════════════════════════════════════════

## D.1 FEATURE 15 — archive / unarchive (آرشیو چت)
`archiveChat` / `unarchiveChat`, body `{ "chatId":"..." }`, rate 10/sec each.
UI: Inbox gets an «آرشیو» action per chat + an «آرشیوشده‌ها» filter tab. Archived chats hide
from the main list. Store `archived boolean` locally so the UI is instant (and reconcile
from `getChats.archive` on sync).

## D.2 FEATURE 16 — setDisappearingChat (پیام ناپدیدشونده)
`POST …/setDisappearingChat/…` — rate 1/sec. `{ "chatId":"...", "ephemeralExpiration": 0 }`
**Allowed values ONLY (seconds):** `0` (خاموش) · `86400` (۲۴ ساعت) · `604800` (۷ روز) ·
`7776000` (۹۰ روز). Validate strictly — reject anything else.
UI: per-chat dropdown in Inbox with exactly those four Persian options.

## D.3 FEATURE 17 — setProfilePicture (عکس پروفایل)
`POST {apiUrl}/waInstance{id}/setProfilePicture/{token}` — **multipart/form-data**, field `file`.
⚠️ **RATE LIMIT 0.1/sec = ONE CALL PER 10 SECONDS.** This is the tightest limit in the API.
Response: `{ "reason": null, "urlAvatar": "https://pps.whatsapp.net/...", "setProfilePicture": true }`
Use a square JPG/PNG.

Endpoint `POST /api/v1/accounts/{id}/profile-picture` (file upload).
Store the returned `urlAvatar` in `accounts.profile_picture_url` and show it on the account card.

**⭐ "Apply to all accounts" (brand consistency):** a button «اعمال روی همه شماره‌ها» that
sets the same picture on every active account. Because of the 0.1/s limit this MUST be a
Celery task with a **10-second sleep between accounts**, with live progress
(«۳ از ۸ شماره به‌روزرسانی شد») and a Persian warning up front:
«⚠️ به دلیل محدودیت Green API، هر شماره ۱۰ ثانیه فاصله دارد. برای ۸ شماره حدود ۸۰ ثانیه طول می‌کشد.»

## D.4 FEATURE 18 — getContactInfo (اطلاعات کامل مخاطب)
`POST …/getContactInfo/…` — rate 1/sec. `{ "chatId":"..." }`
Response fields: `avatar`, `name`, `contactName`, `email`, `category`, `description`,
`products[]` (id, imageUrls{requested, original}, review status), `isBusiness`.

```sql
CREATE TABLE IF NOT EXISTS contact_info_cache (
    chat_id varchar(60) PRIMARY KEY,
    payload jsonb,
    fetched_at timestamp DEFAULT now()
);
```
Cache for **24 hours** (rate limit is only 1/sec — do not hammer it).
Endpoint `GET /api/v1/contacts/{phone}/info` (serves cache; refreshes if stale).

UI: clicking a contact anywhere (مخاطبین، Inbox، فروشندگان اخیر) opens a right-side drawer:
avatar · name · contactName · «حساب تجاری» badge if `isBusiness` · category · description ·
email · product thumbnails if `products` exists · buttons (ارسال پیام / افزودن به لیست سیاه /
مشاهده تاریخچه). **This is a lead-qualification tool** — a contact with `isBusiness=true` and
a product catalog is a competitor/reseller; surface that clearly.

## D.5 Verify + commit PART D
```bash
cd backend && python -m pytest tests/ -v && cd ..
docker compose up -d --build backend worker-general worker-webhooks beat
cd frontend && npm run build && cd .. && docker compose up -d --build --no-deps frontend
git add -A && git commit -m "feat: V14 PART D — archive chats, disappearing messages, profile picture (0.1/s-safe bulk), rich contact info drawer" && git push origin main
```

═══════════════════════════════════════════════════════════════════════════════
# PART E — STATUSES & GROUPS (Features 19, 22)
═══════════════════════════════════════════════════════════════════════════════

## E.1 FEATURE 19 — sendVoiceStatus + targeted statuses (استوری صوتی و هدفمند)
All status methods are rate **5/sec** and ALL accept an optional `participants` array.

- `sendTextStatus`: `{ "message", "backgroundColor":"#228B22", "font":"SERIF", "participants":[...] }`
- `sendVoiceStatus`: `{ "urlFile":"...mp3", "fileName":"...", "backgroundColor":"#228B22", "participants":[...] }`
- `sendMediaStatus`: `{ "urlFile":"...png", "fileName":"...", "caption":"...", "participants":[...] }`
- `deleteStatus` (rate 10/sec) · `getStatusStatistic` (rate 1/sec) · `getOutgoingStatuses` (1/sec)
- ⚠️ `getIncomingStatuses` → **known 403 on this instance.** Build + degrade.

`participants` semantics: omit/empty = public to all contacts; non-existent numbers in the
array simply don't receive it.

### DB
```sql
ALTER TABLE status_schedules ADD COLUMN IF NOT EXISTS content_type varchar(20) DEFAULT 'text';
   -- text | media | voice
ALTER TABLE status_schedules ADD COLUMN IF NOT EXISTS voice_file_url text;
ALTER TABLE status_schedules ADD COLUMN IF NOT EXISTS target_participants jsonb;
   -- null/[] = public
```
Extend `status_content.py` + `status_scheduler.py` to handle `content_type='voice'` and to
pass `participants` when `target_participants` is set.

### ⭐ IMPORTANT INSIGHT TO SURFACE IN THE UI
The user's API-posted **text** status got 107 views while their manual **image** statuses got
266/232/217. The most likely cause is CONTENT TYPE (image > text for engagement), not API
throttling. Therefore, on the status page, show this Persian tip prominently:
«💡 استوری عکس‌دار معمولاً بازدید بیشتری از استوری متنی می‌گیرد. برای تبلیغات، «عکس با کپشن»
را انتخاب کنید.»
And make **media** the DEFAULT content type for new promotional status schedules
(text remains available).

### UI
Status page gains: نوع محتوا (متن / عکس / صوت) · فایل صوتی (upload → `uploadFile` → url) ·
«ارسال فقط به افراد خاص» (multi-select of contacts → `target_participants`) ·
a stats panel using `getStatusStatistic` (sent / delivered / read per recipient).

## E.2 FEATURE 22 — Full group management (مدیریت کامل گروه) — ⚠️ HIGHEST BAN RISK
Methods: `createGroup` (1/s) · `updateGroupName` (1/s) · `getGroupData` (1/s) ·
`updateGroupSettings` (beta) · `addGroupParticipant` (10/s) · `removeGroupParticipant` (10/s) ·
`setGroupAdmin` (10/s) · `removeAdmin` (10/s) · `setGroupPicture` (1/s) · `leaveGroup` (10/s)

`getGroupData` returns: owner, subject, creation, subjectTime, subjectOwner, groupInviteLink,
ephemeralExpiration, allowParticipantsEditGroupSettings, allowParticipantsSendMessages,
allowParticipantsAddMembers, isCommunity, isCommunityAnnounce, size,
`participants[]` = `{id, lid, isAdmin, isSuperAdmin}`.

`updateGroupSettings` (beta): `{ "groupId", "allowParticipantsEditGroupSettings": bool,
"allowParticipantsSendMessages": bool }` → `{ "updateGroupSettings": true|false, "reason": "..." }`

### ⚠️⚠️ BAN-RISK RULES — IMPLEMENT ALL OF THESE. NON-NEGOTIABLE.
Green API documents that **adding a non-existent number to a group can get your number BLOCKED.**
Adds also fail (legitimately, not a bug) when: you are not a group admin · you don't have the
number saved in the phonebook · the contact is already a member · the group has 1024 members ·
the contact restricted who can add them · the contact blocked you.

Therefore, `addGroupParticipant` MUST go through this pipeline:
1. **`checkWhatsapp` FIRST** on every number. If `existsWhatsapp == false` → **DO NOT ADD.**
   Mark the row «شماره واتساپ ندارد» and skip. This is the single most important ban guard.
2. **`AddContact` before adding** (save the number to the phonebook) — Green API explicitly
   recommends this; adds frequently fail otherwise.
3. **Hard rate cap, enforced in Redis** (stricter than the API's 10/s — this is about BANS,
   not rate limits): **max 5 adds per minute** and **max 30 adds per hour, per account.**
   Key: `groupadd:{idInstance}:{minute}` and `groupadd:{idInstance}:{hour}`.
   When the cap is hit, queue the rest and continue next window. Show the Persian message
   «سقف افزودن عضو (۵ در دقیقه / ۳۰ در ساعت) — بقیه در نوبت هستند».
4. **Group size guard:** refuse if `size >= 1024`.
5. **Persian warning banner at the top of the Group Manager page (always visible):**
   «⚠️ افزودن عضو به گروه پرخطرترین کار در واتساپ است. افزودن شماره‌ای که واتساپ ندارد
    می‌تواند باعث مسدود شدن خط شما شود. سامانه قبل از افزودن، وجود واتساپ را چک می‌کند و
    سرعت را محدود می‌کند (۵ در دقیقه). بهتر است ابتدا در پیام خصوصی از فرد اجازه بگیرید.»
6. When an add fails, WhatsApp typically prompts to send an INVITE instead. Handle the
   failure gracefully; show «افزودن ممکن نشد — لینک دعوت بفرستید» and offer to send the
   group's `groupInviteLink` (from `getGroupData`) via a normal message.
7. **`createGroup` with a non-existent number is the documented ban trigger.** So creating a
   group MUST also run `checkWhatsapp` on every seed member first, and drop invalid ones.

### UI — new «مدیریت گروه» section (inside مخاطبان → گروه‌های واتساپ)
Per group, an expandable manager:
- Header: group name (inline-edit → `updateGroupName`), picture (upload → `setGroupPicture`),
  size, invite link (copy button), «خروج از گروه» (typed-confirm).
- Settings toggles (beta): «فقط ادمین‌ها پیام بفرستند» · «فقط ادمین‌ها تنظیمات را تغییر دهند».
- Participants table: name/phone · «ادمین» badge · actions (ارتقا به ادمین / حذف ادمین /
  حذف از گروه — each with confirm).
- «➕ افزودن عضو»: paste/select numbers → the pipeline above runs → live progress table with
  per-number result (✅ افزوده شد / ⛔ واتساپ ندارد / ⏳ در نوبت / ❌ ناموفق — دعوت بفرستید).

## E.3 Verify + commit PART E
Tests: checkWhatsapp gate blocks a non-WhatsApp number from being added; Redis 5/min + 30/hr
caps hold; 1024 guard; participants array reaches the status payload; voice status schema.
```bash
cd backend && python -m pytest tests/ -v && cd ..
docker compose up -d --build backend worker-general worker-webhooks beat
cd frontend && npm run build && cd .. && docker compose up -d --build --no-deps frontend
git add -A && git commit -m "feat: V14 PART E — voice/targeted statuses, full group management with checkWhatsapp ban-guard and 5-per-min add cap" && git push origin main
```

═══════════════════════════════════════════════════════════════════════════════
# PART F — SAFETY & CALLS (Features 23, 24)  ⭐ HIGHEST VALUE — BUILD MOST CAREFULLY
═══════════════════════════════════════════════════════════════════════════════

## F.1 FEATURE 23 — yellowCard AUTOMATIC INCIDENT RESPONSE

### F.1.0 — What yellowCard actually is (verbatim from Green API; encode this behavior)
- yellowCard = WhatsApp detected **suspicious activity**. WhatsApp filters the messages
  **on its side**.
- **Green API returns HTTP 200, then WhatsApp silently drops the message.** There is NO
  delivery. The message appears on neither phone. It shows `yellowCard` status in the logs.
- Messages sent AFTER receiving the status are **queued for 24 hours**.
- **To continue running the instance you must `reboot` it.**
- ⚠️ **BUT:** "After restarting the instance and attempting to send a message or create a
  group, the yellowCard status will return" — **if the underlying behavior hasn't changed.**
  → **Reboot alone does NOT fix it. Reboot + reduced activity is required.**
- Triggers: mailing to NEW numbers (no prior dialogue) · being blocked/reported by recipients ·
  WhatsApp's internal spam heuristics.
- Blocking severity varies: "from 10% of messages to complete blocking of sending."
- Official remedy: (1) rest the account for a few days · (2) switch account type
  (WhatsApp ↔ WhatsApp Business) · (3) write to WhatsApp support from the mobile app ·
  (4) last resort: change the number.
- yellowCard surfaces in: `stateInstanceChanged` webhook, `getStateInstance`, `getWaSettings`,
  `outgoingMessageStatus`, `lastOutgoingMessages`, `getChatHistory`, `getMessage`.

### F.1.1 — Detection (BOTH channels — do not rely on one)
1. **Webhook** `stateInstanceChanged` — `stateInstance` ∈ {authorized, notAuthorized, blocked,
   sleepMode, starting, **yellowCard**}. Instant.
2. **Polling** `getStateInstance` on a Celery beat task **every 2 minutes** per active account.
   (Green API explicitly recommends polling IN ADDITION to webhooks for state tracking —
   webhooks can be missed if the tunnel dies, which has already happened twice on this system.)
3. Also detect from `outgoingMessageStatus` webhooks carrying a `yellowCard` status, and from
   the 429/403 patterns.

### F.1.2 — DB
```sql
CREATE TABLE IF NOT EXISTS account_incidents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id uuid,
    id_instance bigint,
    incident_type varchar(30),        -- yellowCard | blocked | notAuthorized | quotaExceeded | sleepMode
    detected_via varchar(20),         -- webhook | poll | messageStatus
    severity varchar(10),             -- critical | warning
    auto_actions jsonb,               -- what we did automatically
    campaigns_paused jsonb,           -- ids we paused
    queue_snapshot jsonb,             -- the send-queue contents at detection time
    resolved boolean DEFAULT false,
    resolved_at timestamp,
    resolved_by varchar(20),          -- auto | manual
    notes text,
    created_at timestamp DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_incidents_account ON account_incidents(account_id, created_at DESC);

ALTER TABLE accounts ADD COLUMN IF NOT EXISTS throttle_factor double precision DEFAULT 1.0;
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS throttle_until timestamp;
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS cooldown_until timestamp;
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS incident_count_7d integer DEFAULT 0;
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS last_incident_at timestamp;
```

### F.1.3 — ⭐ AUTOMATIC ACTIONS (no human needed — ZERO RISK, do ALL of these)
`backend/app/services/incident_handler.py` → `async def handle_yellow_card(account, via, db)`

Execute IN THIS ORDER, all automatic:

**1. INSTANT SEND-STOP.** Pause every `running` campaign that uses this account.
   Set `status='paused'`, `pause_reason='کارت زرد — ارسال خودکار متوقف شد'`.
   Revoke queued Celery send tasks for this account where possible.
   *(Zero risk: stopping sends can never make things worse.)*

**2. SNAPSHOT + CLEAR THE SEND QUEUE.** Call `showMessagesQueue` → store the contents in
   `account_incidents.queue_snapshot` → then call `clearMessagesQueue`.
   **Rationale:** messages already queued will be sent by WhatsApp and each one deepens the
   yellowCard. Green API's own best practice is to clear the queue before reconnecting.
   The snapshot means nothing is lost — we can show the user exactly what was cancelled.
   *(Zero risk: those messages were going to be dropped/filtered anyway.)*

**3. AUTO-THROTTLE.** Set `throttle_factor = 0.5` and `throttle_until = now() + 7 days`.
   The effective daily cap becomes `computed_daily_limit × throttle_factor`.
   ALSO raise the account's `delaySendMessagesMilliseconds` to at least **15000 ms**
   (Green API's own anti-ban recommendation) via `setSettings`.
   *(Zero risk: sending slower is always safer.)*

**4. MANDATORY COOLDOWN.** Set `cooldown_until = now() + 3 days`.
   While `cooldown_until` is in the future, this account **cannot be used for any campaign**
   (the runner skips it; the UI shows «در دوره خنک‌سازی تا [Shamsi date]»).
   **Rationale — this is the ONLY thing that actually fixes yellowCard.** Green API's official
   remedy is "give the account a rest for a few days." Rebooting without resting just brings
   the yellowCard straight back.
   *(Zero risk: this is literally the documented cure.)*

**5. INSTANT ALERT.** Persistent red banner on the dashboard + a notification. If the user has
   configured emergency numbers (the existing شماره‌های اضطراری feature), send a WhatsApp
   alert **from a DIFFERENT, healthy account** (never from the carded one):
   «🔴 هشدار: شماره [name] کارت زرد گرفت. ارسال متوقف شد. کمپین‌های متوقف‌شده: N.
    دوره خنک‌سازی تا [Shamsi date].»

**6. FULL LOGGING.** Write the `account_incidents` row with every auto-action taken,
   the paused campaign ids, and the queue snapshot. Increment `incident_count_7d`.

**7. HEALTH SCORE PENALTY.** The existing V13.2 `account_health.py` already factors
   yellowCard rate. Additionally force `health_score → 0` while `cooldown_until` is active,
   so smart rotation automatically routes around this account.

### F.1.4 — ⚙️ SEMI-AUTOMATIC (opt-in, default OFF, one settings toggle)
**AUTO-FAILOVER** — `settings.auto_failover_on_yellow_card` (default **false**).
When ON: after pausing, automatically resume each paused campaign on the HEALTHIEST other
active account (by V13.2 health score, excluding any account in cooldown). The campaign
continues seamlessly on a different number.
Default OFF because it silently moves load onto another number — which, if the *content* is
what triggered the card, would just card the next number too. Present it honestly in the UI:
«اگر روشن باشد، کمپین‌ها خودکار روی سالم‌ترین شماره دیگر ادامه می‌یابند.
 ⚠️ اگر علت کارت زرد محتوای پیام باشد، ممکن است شماره بعدی هم کارت زرد بگیرد.»

### F.1.5 — 🚫 NEVER AUTOMATIC (manual buttons only, each with a risk warning)
These are on the incident card as buttons the user must click. **Never fire them automatically.**

- **«ری‌بوت شماره»** — calls `reboot`. Persian warning shown ON the button's confirm dialog:
  «⚠️ ری‌بوت، صف را از سر می‌گیرد ولی کارت زرد را پاک نمی‌کند. اگر بلافاصله دوباره ارسال کنید،
   کارت زرد برمی‌گردد. اول باید دوره خنک‌سازی تمام شود.»
  **Additionally: DISABLE this button entirely while `cooldown_until` is in the future.**
  This is the single most dangerous "helpful" action and the docs are explicit that it
  re-triggers. Let the cooldown run.
- **«ادامه ارسال»** (resume campaigns) — DISABLED until `cooldown_until` passes. After that,
  enabled with a warning: «توصیه: با حجم کم شروع کنید (سقف روزانه نصف شده است).»
- **«اتصال مجدد»** (logout + re-QR) — always manual.
- **«حل شد» (mark resolved)** — sets `resolved=true, resolved_by='manual'`.

### F.1.6 — 🛡️ PREVENTION (build these guards INTO the runner — better than any cure)
Encode Green API's documented numeric guidance as HARD, enforced governors:
- **≤ 200 messages per day per number** (their explicit recommendation). Cap
  `computed_daily_limit` at 200 regardless of other settings. Persian tip in the UI.
- **Warm-up: 10 days**, not 7. Green API says the first 10 days are the highest-risk period.
  Extend the existing warm-up ramp to 10 days. During warm-up:
  **≤ 20 NEW contacts per day** (a "new contact" = one we have never messaged before).
  Track this: `contacts` needs a `first_messaged_at` column; count distinct new ones per day.
- **≥ 500 ms between messages to different chats.** Anything faster is flagged as automated.
  The account default `delaySendMessagesMilliseconds` should be **15000** (Green API's own
  safe recommendation) — enforce a floor of 500 ms absolutely, and default to 15000.
- **Reply-rate monitor.** Green API states that ~50% reply rate dramatically reduces ban risk.
  Compute a 7-day reply rate per account (from the V13.7 `replied` flag). If it drops
  below **20%**, show an amber dashboard warning:
  «⚠️ نرخ پاسخ شماره [X] پایین است (Y٪). خطر مسدود شدن بالا می‌رود — حجم ارسال را کم کنید.»
  If it drops below **10%**, AUTO-throttle to 0.5 (same mechanism as yellowCard, but a
  warning-severity incident, no cooldown).
- **Save the number to contacts before messaging** (`AddContact`) — Green API recommends it.
  Add this as an optional campaign toggle «افزودن شماره به مخاطبین قبل از ارسال» (default ON
  for PV campaigns).
- **Post-complaint quiet period:** after an `incomingBlock` webhook spike, Green API advises
  resuming no sooner than **10 days** after complaints normalize. Track block-webhook counts;
  if ≥3 blocks in 24h for one account → auto-throttle 0.5 for 10 days + warning incident.

### F.1.7 — UI
**New page شماره‌ها → «محافظت و سلامت»** (`/protection`):
- Per-account health card: health score bar (V13.2), state, daily usage vs cap, 7-day
  yellowCard rate, 7-day reply rate, cooldown countdown, throttle factor.
- Incident timeline (from `account_incidents`), newest first, with Shamsi timestamps, the
  auto-actions taken (as a checklist), the paused campaigns, and the queue snapshot
  («۱۲ پیام از صف حذف شد — مشاهده»).
- Manual action buttons per F.1.5 (with their disabled states + warnings).
- The prevention settings (200/day cap, warm-up days, delay ms, auto-failover toggle).
- **Dashboard:** a persistent RED banner whenever any unresolved `critical` incident exists:
  «🔴 شماره [X] کارت زرد گرفت — ارسال متوقف شد. مشاهده جزئیات»
  and an AMBER banner for warning-severity ones.
- **Sidebar badge:** red count of unresolved incidents on «محافظت و سلامت».

## F.2 FEATURE 24 — Call logs (تماس‌ها)
`lastIncomingCalls` / `lastOutgoingCalls` (journals) + `incomingCall` / `outgoingCall` webhooks
(require `incomingCallWebhook: "yes"` — already set in FEATURE 1's payload; also set it on the
EXISTING instance via `setSettings`).
```sql
CREATE TABLE IF NOT EXISTS call_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id uuid,
    direction varchar(10),        -- incoming | outgoing
    from_phone varchar(20),
    status varchar(20),           -- offer | pickUp | hangUp | missed | declined
    contact_name text,
    called_at timestamp,
    created_at timestamp DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_call_logs_time ON call_logs(called_at DESC);
```
Beat task `sync_call_logs` every 30 min (pulls the journals) + live webhook ingestion.
UI: page گفتگوها → «تماس‌ها»: table (جهت · شماره · نام · وضعیت · زمان Shamsi) with filters.
**⭐ Missed incoming calls are HOT LEADS** — highlight them in red with a «تماس بگیرید» action
and a «پیام بفرست» quick action. Add a dashboard stat: «تماس‌های بی‌پاسخ امروز: N».

## F.3 Verify + commit PART F
Tests (critical — these protect the business):
- yellowCard webhook → campaigns paused + queue snapshotted+cleared + throttle 0.5 +
  cooldown 3d + incident row written + health forced to 0.
- Reboot button is DISABLED during cooldown.
- Resume is blocked during cooldown.
- Auto-failover does nothing when the toggle is off (default).
- The 200/day cap, the 20-new-contacts/day warm-up cap, the 500ms floor, the 10-day warm-up.
- Reply-rate <10% → auto-throttle. ≥3 blocks/24h → auto-throttle 10 days.
```bash
cd backend && python -m pytest tests/ -v && cd ..
docker compose up -d --build backend worker-general worker-webhooks beat
curl -s http://localhost:8002/api/v1/incidents | python -m json.tool
cd frontend && npm run build && cd .. && docker compose up -d --build --no-deps frontend
git add -A && git commit -m "feat: V14 PART F — automatic yellowCard incident response (stop/clear-queue/throttle/cooldown/alert), ban-prevention governors, call logs with hot-lead detection" && git push origin main
```

═══════════════════════════════════════════════════════════════════════════════
# PART G — CAPABILITY REGISTRY & GRACEFUL DEGRADATION
═══════════════════════════════════════════════════════════════════════════════

```sql
CREATE TABLE IF NOT EXISTS method_support (
    method varchar(60) PRIMARY KEY,
    supported boolean,                -- null = unknown/not probed
    last_status_code integer,
    last_checked timestamp DEFAULT now(),
    note text
);
```
- The PHASE 0 probe seeds this table.
- **Every** Green API call site records its outcome: a 403 → `supported=false`;
  a 2xx → `supported=true`. This is how UNKNOWN-NOT-PROBED methods get classified on first
  real use, with no risky probing.
- `GET /api/v1/capabilities` returns the table.
- **Frontend:** any button/section whose underlying method is `supported=false` renders
  DISABLED with a Persian tooltip «این قابلیت روی پلن فعلی پشتیبانی نمی‌شود».
  Never show a broken button. Never let a 403 surface as a raw error.
- Beat task `recheck_method_support` **weekly** — re-probes only the SAFE, read-only methods
  (never the destructive ones) so newly-enabled entitlements get picked up.
- **New page تنظیمات → «قابلیت‌های Green API»**: the full table (method · وضعیت ·
  آخرین بررسی · توضیح), grouped by category, with ✅ / ⛔ / ❓ badges. This is the user's
  single source of truth for what their plan can do.

═══════════════════════════════════════════════════════════════════════════════
# PART H — MENU / INFORMATION ARCHITECTURE REDESIGN  ⭐ DO THIS LAST
═══════════════════════════════════════════════════════════════════════════════

Do this AFTER A–G so all the new pages land in their correct final homes.

## H.0 The problem being fixed
- «ابزارها» has become a junk drawer (10 unrelated items) and V14 adds ~6 more pages.
- Four confusingly similar names: «گروه‌های پیام» / «گروه مخاطبین» /
  «مجموعه گروه‌های واتساپ» / «گروه‌های واتساپ» — two DIFFERENT concepts
  (contact groups in our DB ≠ WhatsApp groups) with near-identical labels.
- «رصد محصولات» exists both as a standalone page AND as a tab in گزارش‌ها (duplication).

## H.1 The new structure — 7 top-level groups, max 2 levels deep
```
🏠 داشبورد                      ← overview + incident banners

📤 ارسال پیام
   ├ کمپین‌ها
   ├ ارسال گروهی
   └ صف ارسال                  (NEW — Feature 20)

👥 مخاطبان                      ← answers "به چه کسی؟"
   ├ مخاطبین
   ├ دسته‌بندی مخاطبین          (renamed from «گروه مخاطبین» — disambiguates)
   ├ گروه‌های واتساپ            (+ the new Group Manager, Feature 22)
   ├ مجموعه‌های گروهی
   └ لیست سیاه

✍️ محتوا                        ← answers "چه چیزی؟"
   ├ قالب‌های پیام
   ├ دکمه‌های تعاملی            (NEW — Feature 8 auto-replies)
   ├ استوری‌ها                  (incl. voice + targeted, Feature 19)
   ├ فایل‌ها
   └ کارت تماس و موقعیت        (NEW — Features 12 & 13)

💬 گفتگوها                      ← answers "تعامل زنده"
   ├ صندوق ورودی
   ├ تاریخچه پیام‌ها
   ├ پاسخ خودکار
   └ تماس‌ها                    (NEW — Feature 24)

📱 شماره‌ها                      ← answers "از چه شماره‌ای؟"
   ├ حساب‌های واتساپ
   ├ زمان‌بندی حساب‌ها
   ├ محافظت و سلامت            (NEW — Feature 23) ⚠️ red badge when incidents exist
   └ مدیریت پارتنر              (NEW — Features 1–6)

📊 گزارش‌ها
   ├ گزارش روزانه
   ├ رصد محصولات               (single home — remove the duplicate standalone page,
   │                             redirect the old route here)
   ├ بهترین ساعت ارسال
   └ بازده کمپین (ROI)

──────────────────────────────  ← visual separator

⚙️ تنظیمات                      ← pinned at the BOTTOM, visually separated
   ├ کلیدهای هوش مصنوعی
   ├ قابلیت‌های Green API       (NEW — PART G)
   ├ لینک‌های گروه و کانال
   └ شماره‌های اضطراری
```
**«ابزارها» is DISSOLVED.** Every item moves to where it logically belongs.

⚠️ **ROUTE SAFETY:** keep ALL old routes working via redirects (`/tools/inbox` → `/inbox`
etc.). Never 404 a bookmarked page. Staff are actively using this system today.

## H.2 Required menu behaviors
1. **⌘K / Ctrl+K command palette** — with ~30 pages this is ESSENTIAL, not a luxury.
   Fuzzy search over Persian page names + common synonyms. Enter navigates. Escape closes.
   Also reachable via a search icon in the sidebar header.
2. **Badges ONLY for actionable things:**
   - ✅ «صندوق ورودی ۳» (unread) · ✅ «محافظت و سلامت ۱» (unresolved incidents — RED)
   - ✅ «صف ارسال ۱۲» (queued messages — AMBER)
   - ❌ NEVER «مخاطبین ۱۳۷۰۳» — a vanity number is just noise.
3. **Collapsible icon-rail mode** — a toggle collapses the sidebar to icons+tooltips.
   **Persist the choice** (localStorage) so it survives reload.
4. **Persist group open/closed state** per group (localStorage).
5. **Auto-expand the group containing the current route** + highlight the active item.
6. **Icon + text always.** Icon-only is acceptable ONLY in the collapsed rail (with tooltips).
7. **Status footer:** keep «متصل به سرور 🟢»; add «آخرین همگام‌سازی: ۲ دقیقه پیش».
8. **Mobile:** hamburger drawer + a bottom bar with the 4 most-used
   (داشبورد · ارسال پیام · گفتگوها · گزارش‌ها).
9. **Animations 150–200 ms, `ease-out`.** No longer — long animations feel slow.
10. **NEVER reorder items dynamically** (no "recently used" reshuffling — it destroys muscle
    memory). If you want recents, put them in a separate pinned section.

## H.3 Accessibility & typography standards (WCAG 2.2 AA — enforce)
- **Text contrast ≥ 4.5:1** (normal), **≥ 3:1** (large ≥24px).
- **UI-component contrast ≥ 3:1** (active indicator bar, borders) — criterion 1.4.11.
- **Touch targets ≥ 44×44 px** (Apple) / 48×48 (Material). WCAG's floor is 24×24 — exceed it.
- **Never convey state by color alone** — the active item needs an indicator bar
  **AND** a heavier font weight (for color-blind users).
- **Full keyboard navigation** + a clearly visible focus ring.

**Persian typography (commonly botched — get it right):**
- Font: **Vazirmatn** (or IRANSans). NOT an Arabic-only font.
- **Never go below 13–14px for Persian** (unlike Latin, which survives 12px).
- **`line-height: 1.7`** — Persian has descenders/dots and needs more room.
- Persian has **no capital letters** → you cannot use CAPS for hierarchy.
  Use **font-weight** and **color** instead.
- Use **Persian numerals** (۰۱۲۳۴۵۶۷۸۹) in badges and counts.

**RTL:**
- Active-item indicator bar on the **RIGHT** edge.
- Icon to the **RIGHT** of the label.
- Chevrons **mirrored**.

**Dark theme (current):**
- **No pure black.** Use a very dark grey (e.g. `#0F1214`) — pure black causes halation/eye strain.
- **No pure white text.** Use a slightly muted `#E6E8EA`.
- **ONE accent color** (Afrakala green). Everything else neutral. Color noise = cognitive noise.

## H.4 Update the Persian manual
The two manuals (`راهنمای_افراکالا` and `راهنمای_تصویری_افراکالا`) document the OLD menu.
Regenerate/patch the chapter on menu structure to match the new IA, and add short sections
for every new V14 page. Renaming pages will briefly confuse staff who are used to the old
menu — an updated manual is the mitigation.

## H.5 Verify + commit PART H
- Click through EVERY route; confirm no 404s and that all old routes redirect.
- Verify Ctrl+K opens, searches Persian, and navigates.
- Verify collapse state and group open/closed state survive a reload.
- Verify badges appear only for inbox/incidents/queue.
- Check contrast with a checker; confirm ≥4.5:1 text and ≥3:1 for the active indicator.
```bash
cd frontend && npm run build && cd .. && docker compose up -d --build --no-deps frontend
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:3002/
git add -A && git commit -m "feat: V14 PART H — information-architecture redesign (7 groups, dissolve ابزارها, Ctrl+K palette, WCAG AA, Persian typography, RTL, actionable badges)" && git push origin main
```

═══════════════════════════════════════════════════════════════════════════════
# FINAL VERIFICATION (after ALL parts)
═══════════════════════════════════════════════════════════════════════════════
```bash
cd C:/Users/AFRA/Desktop/bots/claudegreenapi/backend
python -m py_compile app/main.py app/models/*.py app/services/*.py app/api/v1/*.py app/workers/*.py
python -m pytest tests/ -v
cd .. && docker compose up -d --build
sleep 15
curl -s http://localhost:8002/health/detailed | python -m json.tool
curl -s http://localhost:8002/api/v1/capabilities | python -m json.tool
curl -s http://localhost:8002/api/v1/incidents | python -m json.tool
curl -s -o /dev/null -w "frontend HTTP %{http_code}\n" http://localhost:3002/
git log --oneline -8
git status --short          # must be clean
```
Confirm: 8 commits (PART A…H), all pushed, working tree clean, all containers healthy,
test count grew, no regressions.

═══════════════════════════════════════════════════════════════════════════════
# GLOBAL REQUIREMENTS (apply to EVERY part — non-negotiable)
═══════════════════════════════════════════════════════════════════════════════
1. **Persian RTL everywhere.** Every label, error, tooltip, empty state, confirm dialog.
   Every date in **Shamsi**. Every number in Persian numerals in the UI.
2. **Graceful 403.** A plan-restricted method must NEVER surface as a raw error. It becomes a
   disabled control + «پشتیبانی نمی‌شود» + a `method_support` row.
3. **Token safety.** Tokens never in a response body, a log line, an error message, or the
   frontend — except the unavoidable `qr_url`. Write a test that asserts this.
4. **Rate limiting.** EVERY new outbound call goes through the Redis token-bucket limiter
   using the exact table in SECTION 0. Especially: interactive buttons **1/s**,
   setProfilePicture **0.1/s**, group adds **5/min + 30/hr** (ban guard, stricter than the API).
5. **Anti-ban first.** When a feature and safety conflict, safety wins. Every risky action
   gets a Persian warning + a confirm.
6. **Typed confirmation** for destructive actions: delete instance, campaign recall, clear
   queue, leave group, remove participant.
7. **Tests per feature.** Especially the FEATURE 23 automation — those tests protect the
   business's phone numbers.
8. **One commit per PART** (A–H), each pushed.
9. **Never break the send path.** Defaults reproduce today's behavior exactly.
10. **No polling.** Webhook mode only.

═══════════════════════════════════════════════════════════════════════════════
# FINAL REPORT (produce this at the end — the user reads only this)
═══════════════════════════════════════════════════════════════════════════════
1. **METHOD SUPPORT TABLE** — every probed method: ✅ SUPPORTED / ⛔ 403-UNSUPPORTED /
   ❓ UNKNOWN-NOT-PROBED. Explicitly state what the `sendReaction` probe returned and which
   branch of FEATURE 11 you took.
2. **PER-FEATURE STATUS** — all 24, numbered, each ✅ built & working / ⚠️ built but
   unsupported by the plan / ❌ not built (with the reason).
3. **AUTONOMOUS DECISIONS** — every judgment call you made and why.
4. **COMMIT HASHES** — PART A through PART H.
5. **TEST COUNT** — before → after.
6. **MANUAL TO-DOs** — anything the user must do themselves (e.g. paste
   `GREEN_PARTNER_TOKEN` into `.env`, set `PARTNER_DAILY_RATE`).
7. **NEW PAGES & BUTTONS** — where the user finds each new capability in the new menu.
8. **FEATURE 23 SUMMARY** — precisely what now happens automatically on a yellowCard, what is
   opt-in, and what remains manual (and why).