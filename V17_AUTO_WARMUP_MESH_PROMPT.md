# V17 MASTER PROMPT — Afrakala WhatsApp Sender
## Automatic, AI-driven, mesh-based warm-up + typing simulation

> **MODE: FULLY AUTONOMOUS.** Execute every PART below, end-to-end, WITHOUT asking the
> user any questions and WITHOUT waiting for approval. After each PART: run a heavy test
> suite and verify the feature actually works; ONLY advance to the next PART once every
> test passes. Commit and push each PART separately. Produce a final report at the end.

---

## 0. CONTEXT (read first — do not skip)

Project: `C:\Users\AFRA\Desktop\bots\claudegreenapi`
(GitHub: `mohammadrezaafra66-arch/greenapiwhatsapp`). Baseline: **V16**, all tests
passing, `origin/main` clean.

Stack: **FastAPI + PostgreSQL + Redis + Celery + React/Vite**, Green API gateway,
multi-provider AI key pool (OpenAI/DeepSeek/Gemini). Backend port **8002**, frontend
port **3002**. Self-hosted Supabase catalog at `192.168.170.10:8000`. The connected
WhatsApp number is `989122270261` on Green API instance `7105325764` (BUSINESS/partner
tariff). The user has a **partner account** and can create/manage multiple instances.

There is ALREADY a basic warm-up feature (from V15/V16). **V17 replaces/upgrades it**
into a fully automatic, intelligent, AI-driven, mesh-based warm-up that follows Green
API's official anti-ban recommendations exactly. The user wants: **add a new account →
flip ONE toggle → everything else happens automatically at the right times.**

### NON-NEGOTIABLE GUARDRAILS (violating any of these is a failure)

1. **NEVER enable Green API polling / `receiveNotification`.** This deployment is
   **webhook-only**; webhook URL and polling are mutually exclusive. All warm-up event
   detection (message received, read, delivered, blocked, state change) MUST come
   through webhooks. Do not add/re-enable any polling loop anywhere.
2. **Do NOT disrupt the running ngrok tunnel or webhook wiring.** Webhook ingestion is
   fragile and has caused outages. Do not touch ngrok in this build.
3. **Do NOT break the existing send path** (`campaign_runner.py` /
   `group_campaign_runner.py`). PART 1 (typing simulation) touches sending — keep the
   campaign send flow byte-identical when the new typing option is OFF, and re-run all
   send-related tests after the change.
4. **Mesh warm-up may ONLY message numbers the user controls** (the user's own Green API
   instances), and only after they are saved as MUTUAL CONTACTS on both sides. A warming
   number must NEVER message a stranger. This is the single most important anti-ban rule.
5. **All user-facing UI strings in Persian (Farsi), RTL.** Code/vars/comments in English.
6. **Warm-up is OFF by default** on every account. Nothing happens until the user flips
   the toggle for a specific account.
7. **Commit and push each PART separately** (`V17 PART N: <summary>`). No uncommitted
   work between parts.

### WORKFLOW PER PART
Explore existing code first → implement → write/extend tests → run the FULL `pytest`
suite (not just new tests) → verify it works → `git add -A && commit && push` → next PART.
If an external dependency blocks a part (e.g. a Green API call needs a live second
instance you don't have in the test env), implement it fully with mocked Green API
responses, note it under "NEEDS LIVE TEST" in the final report, and continue.

---

## AUTHORITATIVE SPEC (from Green API docs + deep research — implement these EXACT values)

These are the ground-truth parameters. Every number below is deliberate; expose them as
configurable settings with THESE as the shipped defaults.

**Green API official warm-up sequence:**
- 24-hour cooldown between WhatsApp registration/authorization and any messaging.
- Days 2–4: the new number RECEIVES messages from other (warmed) accounts, ~1 message
  every 2 hours, active hours only.
- Day 4 onward: the new number STARTS REPLYING, ~1 message every 2 hours, ONLY to
  numbers in its contacts.
- Over 7 days: ramp daily message flow from **12 → 100**.
- After 10 days: much more ban-resistant. Full "green light" after **25–30 days** of
  clean activity.
- If the number is blocked, warm-up RESETS and restarts from the beginning.

**Green API caps & ratios:**
- Real campaigns (post-graduation): ≤ **200 recipients/day per number**.
- New numbers: ≤ **20 NEW contacts/day**.
- Target reply ratio ≥ **50%** (for every 100 sent, ~50 replies) — the mesh guarantees
  this by design.

**Green API sending/typing parameters (exact units):**
- `typingTime` (per-message field in SendMessage / SendTyping): integer **1000–20000 ms**.
- `autoTyping` (instance setting): `2` = 10 chars/sec (Green API's recommended value).
  Formula `typingTime = (textLength / (autoTyping×5)) × 1000`, floored 500 ms, capped
  20000 ms. NOTE: a per-message `typingTime` OVERRIDES `autoTyping` — pick one per send.
- `SendTyping` method: params `chatId`, `typingTime` (1000–20000), optional
  `typingType: "recording"` for the voice-recording indicator.
- `delaySendMessagesMilliseconds` (instance queue delay): min 500 ms, max 600000 ms;
  set to **15000 ms** for warming instances (Green API anti-ban recommendation). Spacing
  < 500 ms across chats reads as automated mailing.

**Instance settings to apply to a warming instance (via SetSettings) — webhook-only:**
`incomingWebhook: yes`, `outgoingAPIMessageWebhook: yes`, `stateWebhook: yes`,
`incomingBlockWebhook: yes`, `delaySendMessagesMilliseconds: 15000`, `autoTyping: 2`,
`keepOnlineStatus: no`, `markIncomingMessagesReadedOnReply: yes`,
`markIncomingMessagesReaded: no`. **Never enable polling.**

**Kill-switch signals (from webhooks):**
- `stateWebhook` → `yellowCard` / `blocked` / `notAuthorized`.
- `incomingBlockWebhook` → a recipient blocked the number.
- Delivery ratio (`delivered` double-tick) < ~60% → treat as soft-ban signal.
- **yellowCard is silent:** `sendMessage` returns HTTP 200 but the message is NOT
  delivered. NEVER treat HTTP 200 as delivery — rely on delivery/state webhooks.

**Reset/erosion triggers to detect:** app reinstall, account transfer, extra device
linked, 14-day inactivity (erosion), 30-day inactivity (auto-logout). On any → restart
warm-up and notify.

---

## PART 1 — Typing simulation on the send path (low-risk, do first)

**Why:** Green API explicitly recommends simulating the "typing…" indicator so sends
look human. This is additive and benefits BOTH warm-up and real campaigns.

### 1.1 Backend
- Add a helper that, before sending a message, optionally triggers the typing indicator:
  either by setting `typingTime` on the SendMessage call, OR by calling `SendTyping`
  first, then sending. Randomize `typingTime` per message (NEVER a constant) — e.g. draw
  from a range scaled to message length, clamped to 1000–20000 ms. Occasionally use
  `typingType: "recording"` for variety (configurable, low frequency).
- Add a campaign-level option **«شبیه‌سازی تایپ»** (typing simulation) that turns this
  on/off for a campaign. Default: available but OFF, so existing behavior is unchanged.
- Also add the ability to set `autoTyping: 2` at the instance level via SetSettings for
  warming instances (used by PART 3/4).

### 1.2 Guardrail
When the typing option is OFF, campaign output and behavior must be byte-identical to
V16. Prove it with a regression test.

### 1.3 Tests
Unit-test the randomized `typingTime` computation (always within 1000–20000; varies;
scales with length). Test that SendTyping is called when enabled and NOT called when
disabled. Run full suite. Commit + push `V17 PART 1: typing simulation (typingTime/SendTyping)`.

---

## PART 2 — Warm-up data model + per-number state machine

**Why:** The automatic warm-up needs durable state per number and a mesh graph.

### 2.1 Schema (PostgreSQL, use existing migration style)
- `warmup_enrollment`: `id`, `instance_id`, `phone`, `state` (enum below), `day_index`,
  `started_at`, `authorized_at`, `last_activity_at`, `sent_today`, `received_today`,
  `reply_ratio` (float), `next_action_at`, `is_enabled` (bool, default false),
  `created_at`, `updated_at`.
- `warmup_mesh_edge`: `id`, `new_instance_id`, `peer_instance_id`, `direction`,
  `handshake_state` (none/contact_saved/active), `saved_as_contact_new` (bool),
  `saved_as_contact_peer` (bool), `last_msg_at`, `msg_count`, `created_at`.
- `warmup_event_log`: `id`, `enrollment_id`, `edge_id` (nullable), `event_type`
  (send/receive/read/typing/delivered/state_change/block/kill), `content_hash`
  (nullable), `delivery_status` (nullable), `payload_json`, `created_at`.

### 2.2 States (enum)
`ENROLLED → COOLDOWN → RECEIVING → REPLYING → RAMPING → MATURING → GRADUATED`, plus side
states `PAUSED`, `YELLOWCARD`, `BLOCKED_RESET`. Document the allowed transitions in code.

### 2.3 Configurable defaults (ship these exact values, admin-editable)
`cooldown_hours=24`, `receiving_days=[2,3,4]`, `reply_start_day=4`,
`ramp_curve=[12,20,32,48,66,84,100]`, `daily_campaign_cap=200`,
`new_contacts_per_day_cap=20`, `min_reply_ratio=0.50`, `peers_per_new_number_min=3`,
`peers_per_new_number_max=6`, `keepwarm_max_idle_days=10`, `max_msgs_per_minute=2`,
`max_active_hours_per_day=6`, `active_hours_start="09:00"`, `active_hours_end="21:00"`,
`timezone="Asia/Tehran"`, `queue_delay_ms=15000`, `auto_typing=2`.

### 2.4 Tests
Test state-transition validity (illegal transitions rejected), daily-counter reset at
local midnight, and reply_ratio computation. Run full suite. Commit + push
`V17 PART 2: warm-up state machine + mesh schema`.

---

## PART 3 — Enrollment, pre-flight, and the mesh handshake (the "one toggle")

**Why:** This is the one-click entry point. Flipping the toggle must set everything up
automatically and safely.

### 3.1 One toggle
On the accounts UI, a single **«🔥 گرم‌سازی خودکار»** toggle per account. Turning it ON
creates a `warmup_enrollment` (state `ENROLLED`, `is_enabled=true`) and kicks off
pre-flight. Turning it OFF pauses everything for that number immediately.

### 3.2 Pre-flight (automatic, on enrollment — before ANY messaging)
1. Apply the warming instance settings via SetSettings (the exact block in the spec
   above: webhooks on, `delaySendMessagesMilliseconds:15000`, `autoTyping:2`,
   `keepOnlineStatus:no`, `markIncomingMessagesReadedOnReply:yes`). NEVER enable polling.
2. Clear any stale send queue (`showMessagesQueue` → `clearMessagesQueue`) before binding.
3. Enforce the **24h COOLDOWN**: if `authorized_at` is unknown or <24h ago, hold in
   COOLDOWN and do not message until 24h have elapsed.
4. **Build the mesh:** pick 3–6 existing WARMED/GRADUATED instances as peers. For each
   peer↔new pair, save each other as contacts on BOTH sides (`AddContact` on each
   instance) BEFORE any message flows; set `saved_as_contact_*` and `handshake_state`.
   A number may not receive/send a mesh message on an edge until BOTH contact flags are
   true.

### 3.3 Peer selection
Only instances in state GRADUATED (or a manually-marked "warm" flag for the user's
existing known-good numbers, e.g. `989122270261`) are eligible peers. If there are not
enough warm peers, still enroll, hold in COOLDOWN/RECEIVING, and surface a clear Persian
notice: **«برای گرم‌کردن به اکانت گرم کافی نیاز است — حداقل یک اکانت گرم اضافه کنید.»**
Do NOT invent peers and do NOT message strangers.

### 3.4 Tests
Mock Green API. Test: toggle ON creates enrollment + applies settings; queue cleared;
cooldown enforced; mutual-contact handshake completes before any edge becomes active;
insufficient-peers path surfaces the notice and sends nothing. Run full suite. Commit +
push `V17 PART 3: enrollment + pre-flight + mutual-contact mesh handshake`.

---

## PART 4 — The automatic scheduler (day-by-day, jittered, AI-driven)

**Why:** This is the engine. It runs the whole warm-up automatically via Celery beat +
scheduled tasks, with no manual steps, following the Green API schedule with human-like
randomization.

### 4.1 Scheduling engine
- A Celery beat tick (e.g. every few minutes) advances each enrollment's state by
  `day_index` and drives `next_action_at`. Each number runs its OWN jittered schedule —
  peers must NOT fire on synchronized timestamps.
- **Interval logic (never fixed):** base cadence ~120 min during RECEIVING/early
  REPLYING, but each gap drawn from a randomized distribution, e.g.
  `gap = clamp(Normal(μ=120min, σ=35min), 45min, 210min)`. As daily volume ramps, shrink
  μ to fit the day's target into the active-hours window, keep σ jitter, enforce a hard
  min gap (~8–10 min), and NEVER exceed 2 messages/minute per number.
- **Circadian + weekend:** apply a multiplier so mornings/late nights are slower, midday
  slightly faster; weekends ~0.5–0.7× volume. Insert 1–2 random quiet gaps/day.

### 4.2 Active hours
All sends/typing/read-marks only within `active_hours_start`–`active_hours_end`
(Asia/Tehran), ≤ `max_active_hours_per_day`. Jobs landing outside the window defer to the
next window with fresh jitter.

### 4.3 Day-by-day behavior (mesh messages between the user's own numbers)
- **Day 1 (COOLDOWN):** zero messages.
- **Days 2–4 (RECEIVING):** warmed peers send TO the new number ~1 every 2h (jittered),
  active hours only (~6–10 inbound/day, ramping D2≈6, D3≈8, D4≈10). New number does not
  send yet, but marks-as-read after a randomized delay and may show typing occasionally.
- **Day 4 onward (REPLYING):** new number begins replying ~1 every 2h, ONLY to peers in
  contacts. Count both directions.
- **Days 4–10 (RAMPING):** combined daily events follow `ramp_curve` 12→100 (each step
  ≤1.5× prior). Keep outbound ≤ inbound early, converging toward ~1:1 so reply_ratio ≥50%.
- **Days 10–30 (MATURING):** hold ~80–120 mixed events/day with natural variation; add
  occasional media/"voice" (typing `recording`) events. No spikes. At Day 25–30 with a
  clean record → GRADUATED (eligible for real campaigns, still capped at 200/day &
  20 new contacts/day).
- **Keep-warm (forever, all warmed numbers):** if idle > `keepwarm_max_idle_days` (10),
  send a light heartbeat (1–2 mesh messages) so no number ever approaches 14-day erosion
  or 30-day auto-logout.

### 4.4 AI-generated dynamic content (primary) + large fallback pool
- **Primary:** generate each mesh message with the existing AI key pool. Maintain a
  rotating **persona per number** and a short **running conversation history per edge**
  so exchanges are coherent, asymmetric, multi-turn Persian dialogues (greetings, small
  talk, home-appliance wholesale shop-talk, questions that invite replies). Ask for SHORT
  messages; address by name when natural.
- **Anti-repeat:** persist recent messages per edge; forbid exact repeats; run a
  similarity check (hash/embedding) and reject near-duplicates. Apply light
  synonym/punctuation variation as a second defense.
- **Fallback (AI unavailable/over budget/timeout):** draw from a LARGE curated Persian
  phrase pool — **target ≥500 entries** (the user wants a very large pool) across
  categories (greetings, follow-ups, confirmations, questions, small talk, emoji) with
  template slots (name, time-of-day, product) and randomized assembly so fallback output
  is also non-repeating. Track used phrases per edge. Ship the pool as seed data AND a
  hardcoded constant fallback (so it never depends on a DB seed succeeding — reuse the
  V16 lesson).
- Occasionally vary message TYPE (text, emoji-only, sticker, short "voice" via recording
  indicator) to diversify the behavioral fingerprint.

### 4.5 Typing + read behavior per human turn
Sequence: (optionally) mark inbound read after a randomized delay → show typing for a
jittered duration (PART 1 helper, or `autoTyping:2`) → send. Remember total latency =
`delaySendMessagesMilliseconds + typingTime`.

### 4.6 Tests
This is the biggest test surface. With Green API mocked and time simulated, assert:
- No two peers send within the same minute; no number exceeds 2 msgs/min or 6 active
  hours/day; nothing sends outside active hours.
- Daily counts track `ramp_curve` (12→100) with ≤1.5× steps; reply_ratio stays ≥0.50.
- Intervals are randomized (variance present; not constant).
- AI path produces non-duplicate messages; fallback path activates on AI failure and is
  also non-duplicate; the hardcoded constant works even with an empty DB pool.
- A number only ever messages a peer with both mutual-contact flags true (never a
  stranger).
Run full suite. Commit + push `V17 PART 4: automatic jittered AI mesh scheduler`.

---

## PART 5 — Kill-switch, chain-ban circuit breaker, reset detection

**Why:** Safety. One compromised number must never drag its peers down, and blocks must
auto-reset warm-up.

### 5.1 Per-number monitors (webhook-driven)
Consume `stateWebhook` and `incomingBlockWebhook`. Track delivery ratio from delivery
webhooks. On:
- **yellowCard** or a block spike on a number → immediately PAUSE that number (state
  `YELLOWCARD`/`PAUSED`), stop all its outbound, enter a rest period (≥48h), then resume
  at ~5% of prior volume and ramp +10%/week.
- **blocked / notAuthorized / logout** → state `BLOCKED_RESET`; on re-auth, restart the
  full schedule from Day 1 (Green API: block resets warm-up).
- **delivery ratio < ~60%** → treat as soft-ban; throttle and alert.

### 5.2 Chain-ban circuit breaker (mesh-wide)
If ≥2 numbers hit yellowCard/block within a rolling 24–48h window → HALT the entire mesh
(global pause), alert the operator, and quarantine the most-connected node first.

### 5.3 Reset/erosion detection
Detect app reinstall / account transfer / extra device linked / 14-day inactivity /
30-day inactivity and act (restart warm-up + notify). Use webhook/state signals where
available; otherwise infer from activity timestamps.

### 5.4 Alerts
When a number enters `notAuthorized`/`blocked`/`yellowCard`, or the circuit breaker
trips, raise a clear in-app alert (and, if the project already has a notification channel,
use it). Persian text.

### 5.5 Tests
Simulate webhooks: yellowCard pauses one number and triggers the rest/resume curve;
2 blocks in the window trip the global breaker; a block→re-auth restarts from Day 1;
low delivery throttles. Assert peers of a paused node keep operating unless the breaker
trips. Run full suite. Commit + push `V17 PART 5: kill-switch + chain-ban breaker + reset detection`.

---

## PART 6 — Warm-up dashboard (Persian, RTL)

**Why:** The user needs to SEE what the automatic system is doing.

### 6.1 Page «داشبورد گرم‌سازی»
For every enrolled number show: current state + day index, a progress bar to GRADUATED,
sent/received today vs. the day's target, reply ratio, mesh peers and per-edge activity,
next scheduled action time, and a status badge (COOLDOWN/RECEIVING/REPLYING/RAMPING/
MATURING/GRADUATED/PAUSED/YELLOWCARD/BLOCKED). Show a clear banner if a number is paused
or the global breaker tripped, and the insufficient-warm-peers notice when relevant.

### 6.2 Controls
Per number: pause/resume, force-restart, and view the recent `warmup_event_log`. A global
"stop all warm-up" and the batch **«شروع گرم‌سازی همه»** for many newly-added accounts.
All OFF by default.

### 6.3 Tests
Endpoint tests for the dashboard data (correct state/day/counts/ratio, peers, next
action). Run full suite. Commit + push `V17 PART 6: warm-up dashboard`.

---

## FINAL REPORT (after all parts)
Produce one summary with:
- Test count before → after and per-PART deltas; "zero regressions" confirmed.
- One line per PART (done / done-with-caveat) and what was built.
- **"NEEDS LIVE TEST"**: anything only verifiable with a real second warm instance
  (e.g. the actual mutual-contact handshake and real yellowCard/block webhooks).
- **"NEEDS USER ACTION"**: the user must add ≥1 extra warm account to actually mesh-warm
  a new number; and must keep numbers active (<10-day idle) so warm-up doesn't erode.
- Confirmation that: polling was never enabled; webhook/ngrok untouched; the send path is
  byte-identical when typing simulation is OFF; warm-up is OFF by default; and warming
  numbers only ever message mutual-contact peers (never strangers).
- The list of pushed commits.

Then STOP and await the user's review. Do not start further work.

---

### IMPORTANT REALITY NOTE (include a short version in the final report)
Warm-up REDUCES ban risk; it does NOT eliminate it. WhatsApp — not Green API — decides
bans, and the policy is hidden and constantly changing. A self-controlled mesh is
inherently a coordination pattern; its safety depends entirely on mutual contacts,
asymmetric graph, randomized timing, and varied AI content as specified. The user should
warm-test on LOW-VALUE numbers before trusting it with important ones.