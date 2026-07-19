# V25 MASTER PROMPT — Afrakala WhatsApp Sender
## Automatic "human helpers" warm-up assist (≤25 known people) + inbox account filter

> **MODE: FULLY AUTONOMOUS.** Execute every PART end-to-end WITHOUT asking questions and
> WITHOUT waiting for approval. After each PART: run a heavy test suite and verify it
> works; only advance once every test passes. Commit and push each PART separately.
> Produce a final report.

---

## 0. CONTEXT (read first)

Project: `C:\Users\AFRA\Desktop\bots\claudegreenapi`
(GitHub: `mohammadrezaafra66-arch/greenapiwhatsapp`). Baseline: latest main (V24 — the
number-in-text leak fix is already done and pushed; 245 warm-up tests pass). Stack:
FastAPI + PostgreSQL + Redis + Celery + React/Vite, Green API, multi-provider AI key pool.
Backend 8002, frontend 3002. Webhook-only.

**Two features to build:**
- **PART 1 — "Human helpers" warm-up assist:** the user has a SMALL list of REAL known
  people (staff + friends, **max 25**) who already have the user's number saved. The main
  warm account automatically asks each helper (slowly) to send a quick friendly WhatsApp
  message to a NEW cold number, to give it genuine human incoming traffic. This is NOT bulk
  messaging — it's a fixed, tiny list of ≤25 known contacts, sent slowly.
- **PART 2 — Inbox account filter:** in the inbox («صندوق ورودی»), let the user pick WHICH
  account's incoming messages are shown (a filter/selector).

### NON-NEGOTIABLE GUARDRAILS
1. **NEVER enable Green API polling.** Webhook-only.
2. **Do NOT touch ngrok / webhook wiring. Do NOT weaken the existing send path, the V17-V24
   warm-up mesh, or the group track.** PART 1 is a NEW, separate, additive helper flow.
3. **The helper list is capped at 25 and is only people the user explicitly adds** (known
   contacts who already have the user's number). NEVER auto-import contacts, never message
   strangers, never exceed 25. This is the hard anti-spam boundary.
4. **Protect the main account:** the helper-ask messages must be sent SLOWLY with jitter
   (see rate limits below), never all at once, only in waking hours — so the sending
   account is not flagged. Default OFF.
5. **All UI strings Persian (Farsi), RTL.** Code/vars/comments English.
6. **Commit + push each PART separately** (`V25 PART N: ...`).

### WORKFLOW PER PART
Explore existing code first → implement → write/extend tests → run FULL `pytest` → verify →
commit + push → next PART.

---

## PART 1 — "Human helpers" warm-up assist (automatic, ≤25 known people)

**Concept:** For a cold number being warmed, the system automatically asks real human
helpers (from a capped list of ≤25) to send it a friendly WhatsApp message. When a helper
actually sends (we detect the cold number received an incoming message from that helper),
mark it done and thank the helper. If a helper hasn't acted after 1 hour, send ONE reminder.

### 1.1 Data model
- `warmup_helper`: `id`, `name`, `phone` (the helper's WhatsApp number, a known contact),
  `is_active` (bool), `created_at`. **Enforce a hard cap of 25 active helpers** at the DB/
  service layer — adding a 26th must be rejected with a clear Persian error.
- `warmup_helper_task`: `id`, `helper_id`, `cold_instance_id` (the new number to be
  greeted), `status` (pending/asked/reminded/done/skipped), `asked_at`, `reminded_at`,
  `done_at`, `attempts`, `created_at`.

### 1.2 The sending account
The helper-ask messages are sent FROM the user's main warm account (the one that already
sends via API — reuse the same sending path). Do NOT use a cold number to ask helpers.

### 1.3 The automatic flow (one toggle)
Add a single toggle **«کمک‌گیری از افراد واقعی برای گرم‌سازی»** (default OFF). When ON, for
each cold number enrolled in warm-up:
1. Create `warmup_helper_task` rows pairing the cold number with active helpers (spread
   over time — do NOT create/send all 25 at once; see rate limits).
2. For each task, the main account sends the helper a Persian message asking them to greet
   the new number, INCLUDING:
   - a short friendly request, e.g. «سلام [نام]، لطف می‌کنی به این شماره‌ی جدید ما یک پیام
     کوتاه بدی؟ داریم فعالش می‌کنیم.»
   - a **click-to-chat wa.me link** for the cold number so it's one tap:
     `https://wa.me/<coldNumberDigits>` (build from the cold number's real phone; if the
     phone is null, resolve it via getWaSettings first — reuse the phone-backfill logic
     already added).
   - a short **suggested message text** the helper can copy/paste, e.g. «سلام، خوبی؟».
   Mark task `asked`, set `asked_at`.
3. **Detection of success (via webhook):** when the cold number receives an INCOMING
   message from that helper's phone (match on the webhook's sender = helper phone), mark
   the task `done`, and automatically send the helper a Persian thank-you, e.g. «ممنون از
   لطفت 🙏».
4. **Reminder:** if a task is still `asked` (not done) after **1 hour**, send ONE reminder
   to the helper, mark `reminded`. Do not remind more than once.

### 1.4 Rate limits (protect the main account — MANDATORY)
- The main account must NOT blast all helpers at once. Send helper-ask messages **slowly**:
  no more than ~1 helper-ask every few minutes, with randomized jitter, waking hours only
  (09:00–21:00 Asia/Tehran). Spread the ≤25 asks across time.
- Respect the existing Green API `delaySendMessagesMilliseconds` and typing-simulation
  settings so these look human.
- Never re-ask the same helper for the same cold number more than: 1 ask + 1 reminder.

### 1.5 UI
- A page/section «افراد کمک‌کننده (گرم‌سازی)» to add/edit/delete helpers (name + phone),
  showing the count («۱۸ از ۲۵») and blocking a 26th with a Persian notice.
- Show, per cold number, the helper tasks and their status (pending/asked/reminded/done),
  so the user can see who greeted the new number.
- The single toggle to enable/disable the automatic helper flow (default OFF).

### 1.6 Guardrails recap in code
Hard-cap 25; never auto-import; only user-added known contacts; slow jittered sends from
the main account; default OFF; webhook-only detection; never message a helper more than
ask+reminder.

### 1.7 Tests
- 25-cap enforced (26th rejected).
- Toggle ON creates helper tasks and sends asks SLOWLY (assert not all-at-once; jitter/rate
  respected; waking-hours only).
- wa.me link is built correctly from the cold number's real phone (and phone is resolved if
  null).
- Incoming message from helper phone → task marked done + thank-you sent (simulate webhook).
- No done within 1h → exactly ONE reminder; never a second.
- Main account never exceeds the rate limit even with 25 helpers × multiple cold numbers.
Run full suite. Commit + push `V25 PART 1: automatic human-helper warm-up assist (max 25)`.

---

## PART 2 — Inbox account filter

**Why:** The inbox shows incoming messages from all accounts mixed together; the user wants
to pick which account's incoming messages are shown.

### 2.1 Implementation
- In the inbox («صندوق ورودی»), add an account selector/filter (dropdown or tabs) listing
  the user's instances. Selecting one shows only that account's incoming messages; an "all"
  option shows everything (current behavior).
- Filter server-side where the inbox data is fetched (by instance), and reflect the choice
  in the UI. Persist the selection in component state (not browser storage).

### 2.2 Tests
- Selecting an account returns only that account's incoming messages; "all" returns
  everything. Run full suite. Commit + push `V25 PART 2: inbox account filter`.

---

## PART 3 — Confirm the number-in-text fix is active (verification only)

The V24 fix (never leak account number/id/label into warm-up message bodies, with a hard
pre-send filter + AI prompt hardening + curated human names) is already done. As part of
this run:
- Re-run the V24 leak tests and confirm they pass.
- Generate and include in the final report 10 fresh sample warm-up messages (mix of AI and
  fallback) confirming NONE contain account numbers, long digit runs, or system labels.
No code change expected here unless a leak is found; if one is found, fix it the same way
(reject + regenerate/fallback).

---

## FINAL REPORT
- Test count before → after, per-PART deltas, "zero regressions" confirmed.
- PART 1: how the automatic helper flow works, the 25-cap, the slow/jittered sending that
  protects the main account, wa.me link + suggested text, webhook-based done-detection +
  auto thank-you, and the 1-hour single reminder. Default OFF.
- PART 2: inbox account filter working.
- PART 3: V24 leak tests pass; 10 clean sample messages included.
- Confirmation: polling never enabled; ngrok/webhook untouched; existing send path + mesh +
  group track unchanged; helper list hard-capped at 25 known contacts; main account
  protected by slow jittered sending; everything default OFF.
- The list of pushed commits, and the redeploy reminder:
  `docker compose build frontend && docker compose up -d frontend` and
  `docker compose up -d --force-recreate worker-general worker-webhooks beat`.

Then STOP and await review.

---
### REALITY NOTE (short version in the report)
This helper flow uses a tiny list of ≤25 REAL known people who already have the user's
number — that's why it's low-risk (genuine human traffic, near-zero report risk). It is NOT
bulk messaging and must never become that. It reduces ban risk for the cold numbers but
does not eliminate it, and the main account is still doing outbound sends, so the slow
jittered pacing and the 25-cap must stay. Number quality (non-sequential, aged SIMs, 24h
wait) remains the biggest factor.