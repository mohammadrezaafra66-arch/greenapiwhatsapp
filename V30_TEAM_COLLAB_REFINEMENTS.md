# V30 MASTER PROMPT — Afrakala WhatsApp Sender
## Complete «همکاری تیمی» frontend + 10 refinements (pacing, variety, work-hours, escalation, typing, counters, dashboard bug)

> **MODE: FULLY AUTONOMOUS.** Execute every PART end-to-end WITHOUT asking questions and
> WITHOUT waiting for approval. After each PART: run a heavy test suite and verify it
> works; only advance once every test passes. Commit and push each PART separately.
> Produce a final report.

---

## 0. CONTEXT (read first)

Project: `C:\Users\AFRA\Desktop\bots\claudegreenapi`
(GitHub: `mohammadrezaafra66-arch/greenapiwhatsapp`). Baseline: latest main — V29 «همکاری
تیمی» is merged and deployed (11 commits, all tests passing). Backend/API for V29 is fully
built and tested: `warmup_helper` (contact, extended with rich-profile columns),
`warmup_helper_task`, `warmup_helper_thread`, `warmup_thread_alert`,
`warmup_team_enrollment`, `warmup_helper_log`, `warmup_sender_config`, warmth scoring
(`/warmup-helpers/warmth`), and Celery beat ticks `process-cold-replies` (120s) and
`process-team-schedule` (300s) are all live. **What's missing/needed now is (a) the
FRONTEND pages that surface this API, and (b) ten specific behavior refinements the user
has since requested, plus (c) a dashboard bug fix.** This prompt does NOT change the V29
data model's fundamentals — it EXTENDS the existing code, adds missing UI, and refines
pacing/content/scheduling rules.

### NON-NEGOTIABLE GUARDRAILS
1. **NEVER enable Green API polling.** Webhook-only stays intact.
2. **Do NOT touch ngrok/webhook wiring, the mesh (V17–V25), V26 group-monitoring, V27
   anti-ban hardening, or the Telegram platform.** This is additive/refining to V29 only.
3. **Do not create a parallel schema.** Extend `warmup_helper*` tables from V29; do not
   invent new contact/thread/log tables that duplicate existing ones.
4. **Every send in this feature continues to route through `warmup_helper_engine`'s
   existing `can_send_now` (V27) + shared `peer_pacer`** — the new refinements in this
   prompt (20-min ask spacing, 9am–7pm window, staggered thank-yous) are ADDITIONAL
   constraints layered on top of those existing rails, never a replacement/bypass.
5. **All UI strings Persian (Farsi), RTL.** Code/vars/comments English.
6. **Commit + push each PART separately** (`V30 PART N: ...`).

### WORKFLOW PER PART
Explore the ACTUAL current V29 code first (Warmup.jsx's «همکاری تیمی» panel, the
`warmup_helper_engine` pacing/gate logic, the `/warmup-helpers/*` API surface, the AI
message-generation service) → extend it → write/extend tests → run the FULL existing test
suite → verify zero regressions → commit + push → next PART.

---

## PART 1 — Complete the frontend pages (dashboard, log, alerts, warmth badge, sender/cold-account assignment)

**Why:** V29's backend is fully done and tested, but per the last report, the dashboard,
log, alerts, warmth badge, and cold-account picker are only reachable via API — not
rendered as pages yet. This PART surfaces all of it in the UI.

### 1.1 Build these as real, navigable pages/panels under «همکاری تیمی» (reuse the
existing `api.js` clients already wired: `teamDashboard`, `warmth`, `log`, `threadAlerts`,
`teamEnroll`, `generateThreadPreview`, cold-account assign):
- **Sender & contact management (extend, don't rebuild the existing rich-profile capture
  form):** clearly editable UI to pick a sender account, add/edit contacts (full name,
  phone, optional work phone, job title, years experience, benefit note), and assign each
  contact to 1 (preferred) or up to 2 cold accounts — this directly answers the user's Q18:
  make this assignment clearly visible and editable, not just possible via raw API calls.
- **Cold-account picker/roster:** a clear list of cold accounts eligible for «همکاری
  تیمی», each with its own enrollment toggle (from V29 PART 7) and current day-in-cycle.
- **Warmth badge:** show each sender candidate's computed warmth score/level
  (کم/متوسط/بالا) inline wherever a sender is selected, and on a dedicated senders list.
- **Team Collaboration dashboard:** per cold account — enrollment status, day-in-cycle,
  active threads, thread status (active/paused/done); per sender — contact count, current
  brief, warmth score.
- **Dedicated log page:** the Shamsi-dated event log from V29 PART 9 (from-account →
  to-account, message type, sent/received text, timestamp), filterable by sender/contact/
  cold account.
- **Thread alerts page:** list of paused/flagged threads (from V29's forbidden-word
  safety flagging) with a way to review and manually resume a thread if the user decides
  it's a false positive.

### 1.2 Tests
Each page renders and correctly reflects backend state (mock/seed data): sender
assignment is editable and persists; warmth badge shows correct score; dashboard reflects
real enrollment/thread state; log page filters correctly; alerts page lists paused threads
and supports manual resume. Run full suite (backend + any frontend test setup this repo
already uses). Commit + push
`V30 PART 1: complete Team Collaboration frontend (dashboard, log, alerts, warmth, assignment UI)`.

---

## PART 2 — Per-sender minimum 20-minute spacing between ask-requests

**Why:** With up to 25–30 contacts, the user wants extra-conservative spacing between
outbound ask-requests, on top of the existing anti-ban floor.

### 2.1 Implementation
- Add a per-SENDER-instance constraint (design decision: enforced per sender, since
  per-instance risk is what matters — consistent with V27's peer-level pacing
  philosophy): a given sender may send at most one Team Collaboration ASK-message every
  **20 minutes minimum** (in addition to, not instead of, the existing baseline
  anti-ban/`peer_pacer` floor). This applies specifically to ask-requests (not reminders/
  thank-yous/cold-replies, which have their own rules in later PARTs) — if multiple
  ask-steps are due around the same time for one sender, queue and space them ≥20 min apart.

### 2.2 Tests
Two ask-requests from the same sender scheduled close together are verifiably ≥20 minutes
apart in actual send timestamps; different senders are NOT rate-limited against each other
by this rule (only the existing global anti-ban considerations apply across senders, per
design).
Run full suite. Commit + push `V30 PART 2: 20-minute minimum spacing between ask-requests per sender`.

---

## PART 3 — Team Collaboration work-hours window: 09:00–19:00 Asia/Tehran

**Why:** The user wants a SPECIFIC, narrower work-hours window for this feature (distinct
from whatever window the general mesh uses).

### 3.1 Implementation
- Introduce a Team-Collaboration-specific constant window: **09:00–19:00 Asia/Tehran**
  (not the mesh's own waking-hours window — a separate constant). NO ask/reminder/
  thank-you/cold-reply send for this feature may occur outside this window, regardless of
  any other scheduling logic; defer to the next valid window instead.

### 3.2 Tests
A send scheduled for 19:30 or 08:00 Tehran time is deferred to the next day's 09:00+
window, never sent outside 09:00–19:00; the mesh's own separate window (used for
non-Team-Collaboration sends) is unaffected by this change.
Run full suite. Commit + push `V30 PART 3: Team Collaboration work-hours window (09:00-19:00 Tehran)`.

---

## PART 4 — Completion-based escalation (assign 2 new cold accounts after success)

**Why:** Instead of either stopping after one task or repeatedly nagging, successful
completion should naturally grow the relationship; non-completion stays capped at one
reminder (unchanged).

### 4.1 Implementation
- When a contact's current assigned cold-account task(s) reach `done` (via the existing
  detection), and there ARE additional cold accounts in the roster not yet assigned to
  that contact, automatically assign up to **2 NEW** cold accounts to that contact as
  their next round (respecting the existing "max 2 referenced per single message" rule
  and the existing per-sender 20-min/work-hours/pacing constraints for when that next
  ask actually goes out). If no unassigned cold accounts remain, do nothing further for
  that contact (don't re-assign already-completed ones).
- Non-completion within the window continues to follow the EXISTING single-reminder rule
  (unchanged) — no additional escalation logic there.

### 4.2 Tests
A contact completing their assigned cold-account task gets 2 new cold accounts assigned
automatically (when available); if fewer than 2 remain unassigned, only that many are
assigned; if none remain, nothing happens; a contact who does NOT complete still only gets
the existing single reminder, no escalation.
Run full suite. Commit + push `V30 PART 4: completion-based escalation to 2 new cold accounts`.

---

## PART 5 — Message content refinements: variety, emoji, tone, and staggered thank-yous

### 5.1 Ask-messages
- Strengthen the existing anti-repeat/similarity check specifically for ask-messages so
  consecutive asks (even to the same or different contacts) are never near-duplicate.
- Require the AI generation prompt to naturally include appropriate emoji in ask-messages
  (not forced/spammy — a natural amount, e.g. 1–2 relevant emoji).

### 5.2 Thank-you messages — make them AI-generated and varied (not a static template)
- If thank-you messages currently use a single static Persian line, change this to
  AI-generated, warm/positive-toned, VARIED text per thank-you (reuse the same
  anti-repeat check + emoji guidance as ask-messages) — apply the exact same V24
  identifier-leak safeguard.

### 5.3 Staggered thank-yous for multiple completions
- If a contact completes multiple tasks in a short window (e.g. 3 separate cold-account
  tasks), do NOT send 3 thank-yous back-to-back/simultaneously — space them out using the
  SAME per-sender pacing rails (at minimum the existing baseline floor; reasonable to also
  respect the spirit of "don't burst" even if not the full 20-min ask-specific rule, since
  thank-yous are lower-risk but still real sends — space them by at least the existing
  baseline anti-ban floor, jittered).

### 5.4 Tests
Ask-messages include emoji and are never near-duplicate across a sample of generations;
thank-you messages are AI-generated, varied, warm-toned, include emoji, and never leak
identifiers; 3 simultaneous completions for one contact produce 3 thank-yous with verified
spacing between their actual send timestamps (not simultaneous).
Run full suite. Commit + push `V30 PART 5: varied AI content (emoji, tone) + staggered thank-yous`.

---

## PART 6 — Variable typing-time + genuinely-random jitter (Green API compliance pass)

### 6.1 Typing time scales with message length
- Ensure `typingTime` sent to Green API scales with the actual message's character count
  (longer message → longer simulated typing), bounded within Green API's documented
  1000–20000ms range. Verify this is actually wired for every send type in this feature
  (ask/reminder/thank-you/cold-reply), not just some.

### 6.2 Genuinely variable send interval
- Audit the jitter logic: confirm the "random" interval is NOT effectively a fixed/
  constant value due to a bug (e.g. a fixed seed, a rounding issue, or a jitter range that
  collapses to one value) — write a test asserting that across N consecutive sends from
  one sender, no two consecutive intervals are identical, and the intervals vary across a
  reasonable spread within the allowed bounds.

### 6.3 General Green API compliance pass
- Re-verify (don't just assume) that every send path in this feature respects: message
  length limits, the existing delay/typing constants, and any other documented Green API
  sending constraint already established elsewhere in this codebase (reuse, don't
  reinvent).

### 6.4 Tests
`typingTime` correlates with message length within bounds; a sample of N send intervals
from one sender shows genuine variation (no repeated identical gaps); no send path
violates any known Green API constraint.
Run full suite. Commit + push `V30 PART 6: variable typing-time + genuinely random jitter + compliance pass`.

---

## PART 7 — Running request-count display

### 7.1 Counter
- Alongside each sent ask-request (in the log page from PART 1 and/or the dashboard),
  show a running count, e.g. «این درخواست شماره ۵ برای این مخاطب است» (or a per-sender
  total, whichever reads more naturally given the existing log's grouping) — a simple
  computed/displayed counter, not necessarily a new stored column if it can be derived from
  existing log rows.

### 7.2 Tests
The displayed counter correctly reflects the number of ask-requests sent so far for the
relevant scope (contact or sender). Run full suite. Commit + push
`V30 PART 7: running request-count display in the log/dashboard`.

---

## PART 8 — Diagnose + fix: "today's sent count" not reflecting on the dashboard

**Why:** The user reports «داشبورد زنده»'s "کل پیام‌های ارسالی امروز" doesn't correctly
reflect today's real send count.

### 8.1 Investigate first, then fix
- Trace the actual query/component behind this stat. Check specifically for: timezone
  handling (UTC vs Asia/Tehran off-by-one at day boundaries), a stale/cached value, a
  query that only counts certain send types (e.g. excluding Team Collaboration sends, or
  excluding sends from newer instance types), or a broken date filter. Compare the
  displayed value against a manual count of today's actual sends (Tehran calendar day) to
  confirm the discrepancy before fixing. Fix the actual root cause found — do not
  guess-patch without confirming the cause first.

### 8.2 Tests
A test that seeds known sends across a day boundary (in both UTC and Tehran time)
confirms the stat now correctly reflects the Tehran-calendar "today" count.
Run full suite. Commit + push `V30 PART 8: fix "today's sent count" dashboard bug`.

---

## PART 9 — Final wiring + full regression pass

### 9.1 Wiring
- Confirm every new constraint added in this prompt (20-min ask spacing, 9–19 work-hours
  window, escalation logic, varied/emoji content, staggered thank-yous, variable typing/
  jitter) is active on the LIVE `warmup_helper_engine` send path and visible in the newly
  completed frontend (PART 1).

### 9.2 Tests
Full end-to-end simulation covering the new rules together: an ask fires within
09:00–19:00 only, ≥20 min after the sender's previous ask; on completion, 2 new cold
accounts are assigned; the next ask (later, per pacing/window rules) is varied text with
emoji; multiple completions produce staggered, varied thank-yous; a sample of intervals
shows genuine jitter; the dashboard "today" stat is correct. Re-run the FULL pre-existing
suite (V17–V29, Telegram) to confirm zero regressions.
Run full suite. Commit + push `V30 PART 9: final wiring + full regression pass`.

---

## FINAL REPORT
- Test count before → after, per-PART deltas, "zero regressions" confirmed.
- Confirm each of points 16–26 is addressed, one line each, referencing which PART.
- Confirm the frontend is now fully navigable (list every new/completed page).
- Confirm: polling never enabled; ngrok/webhook untouched; mesh/V26/V27/Telegram code
  unchanged; no parallel schema created; every send still routes through
  `warmup_helper_engine`'s `can_send_now` + `peer_pacer`, with the new constraints layered
  on top, not bypassing them.
- Report the root cause AND the fix for the dashboard bug (PART 8) clearly.
- The list of pushed commits, and the redeploy reminder:
  `docker compose build frontend && docker compose up -d frontend` and
  `docker compose up -d --force-recreate worker-general worker-webhooks beat backend`.

Then STOP and await review.

---
### REALITY NOTE (short version in the report)
These refinements make an already-conservative system even more conservative (extra
spacing, a narrower work-hours window, escalation only on success, and stronger content
variety) — all good practice, but none of it eliminates the underlying reality that this
is still real outbound activity from real accounts. Keep the roster small and genuinely
known, and keep monitoring warmth scores and thread-alerts regularly.