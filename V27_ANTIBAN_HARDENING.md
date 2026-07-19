# V27 MASTER PROMPT — Afrakala WhatsApp Sender
## Anti-ban hardening: peer-health gating, peer-level rate limits, minimum peer age, and 7 additional safeguards

> **MODE: FULLY AUTONOMOUS.** Execute every PART end-to-end WITHOUT asking questions and
> WITHOUT waiting for approval. After each PART: run a heavy test suite and verify it
> works; only advance once every test passes. Commit and push each PART separately.
> Produce a final report.

---

## 0. CONTEXT (read first)

Project: `C:\Users\AFRA\Desktop\bots\claudegreenapi`
(GitHub: `mohammadrezaafra66-arch/greenapiwhatsapp`). Baseline: latest main (V25 confirmed
deployed, 532 tests passing; V26/group-monitoring was never executed — this prompt does
NOT depend on V26 and must not assume it exists). Stack: FastAPI + PostgreSQL + Redis +
Celery + React/Vite, Green API gateway (webhook-only), multi-provider AI key pool.
Backend 8002, frontend 3002.

**Why this prompt exists:** A live incident diagnosis found the warm peer `770022682898`
(صالحی) got yellowCarded while serving the mesh, and the engine kept sending through it
anyway. Root-cause analysis found **THREE concrete engine gaps**, confirmed by direct
investigation of `run_warmup_tick` / `eligible_peer_accounts`:

1. **No peer-health gate.** `run_warmup_tick`/`eligible_peer_accounts` only checks
   `status = active` for a peer — it NEVER checks the peer's own `cooldown_until`,
   `throttle_until`, or live yellowCard/blocked state before using it to send. Result: the
   carded peer sent **19 more messages** after being carded, including sends after its
   `cooldown_until` had already been set to a future date.
2. **No peer-level rate limit.** Jitter/spacing was enforced per COLD-NUMBER enrollment
   only. When one peer serves 2 cold numbers, the combined send stream from that ONE peer
   came out **2.6–9 seconds apart** — under the required 10–15s floor — because each cold
   number's schedule was paced independently with no awareness of the shared sender.
3. **Peer eligibility has no minimum real age.** Any instance can be manually flagged
   `is_warm_peer=true` regardless of how long it's actually been authorized/healthy. In the
   incident, a genuinely fresh (0-day) batch-mate number was flagged as the peer and used to
   warm OTHER batch-mates, while an actually well-established ~14-day number sat unused.

A follow-up deep-research audit found **7 additional gaps** (Green API's own official
recommendations plus general WhatsApp anti-ban practice) that are covered in PARTS 4–10
below. **All 10 items must be built in this run.**

### NON-NEGOTIABLE GUARDRAILS
1. **NEVER enable Green API polling.** Webhook-only stays intact.
2. **Do NOT touch ngrok/webhook wiring.** Do not weaken the existing send path.
3. **Warm-up stays OFF by default.** These are safety/hardening changes to the EXISTING
   mesh, campaign, and group-reply send paths — not new user-facing toggles, except where
   explicitly noted (e.g. an admin-visible quality-score dashard is fine; it doesn't need to
   be a toggle).
4. **Do not weaken any existing protection** (V17–V25: mesh, ratio cap, breaker, helper
   assist, group-warmup). This PART set is strictly additive hardening.
5. **All UI strings Persian (Farsi), RTL.** Code/vars/comments English.
6. **Commit + push each PART separately** (`V27 PART N: ...`).

### WORKFLOW PER PART
Explore existing code first (especially `run_warmup_tick`, `eligible_peer_accounts`, the
campaign send-queue, and any breaker/kill-switch logic) → implement → write/extend tests →
run the FULL existing test suite (not just new tests) → verify zero regressions → commit +
push → next PART.

---

## PART 1 — Live pre-send health gate (fixes incident gap #1) 🔴 HIGHEST PRIORITY

**Why:** The engine must never send through an instance that is currently unhealthy, and
must check this at the moment of sending, not just periodically.

### 1.1 One central gate function
- Implement a SINGLE function, e.g. `can_send_now(instance) -> (bool, reason)`, that is the
  ONE source of truth for "is this instance allowed to send right this moment." It must
  check, in order: `status == active`, `cooldown_until` is not in the future,
  `throttle_until` is not in the future, and the instance's LIVE Green API state (see 1.2)
  is not `yellowCard`/`blocked`/`notAuthorized`.
- **Every single send call-site must call this function immediately before calling
  `sendMessage`** — the mesh tick, the campaign send-queue worker, any group auto-reply
  path, and the helper-assist sender (V25). Do not just check at scheduling time; check
  again right before the actual API call, since state can change between scheduling and
  execution.
- If the gate returns false, the send must be skipped/deferred (not silently dropped —
  log it), and if the reason is a live yellowCard/blocked signal, immediately trigger the
  existing per-instance kill-switch (set `cooldown_until`/`throttle_until` forward) so
  nothing else tries to use that instance either.

### 1.2 Live state source
- Prefer a recently-cached `GetStateInstance` result (see PART 4 for the polling/webhook
  mechanism that keeps this cache fresh) over calling `GetStateInstance` synchronously on
  every single send (to avoid hammering the API) — but the cache must be fresh enough
  (≤60–90 seconds old, matching PART 4's polling interval) that a just-carded instance is
  caught within roughly a minute, not left to send 19 more messages like the incident.

### 1.3 Tests
- A peer with `cooldown_until` in the future is correctly refused by `can_send_now` and no
  send call reaches Green API for it.
- Simulate the exact incident: a peer gets yellow-carded mid-tick → the NEXT scheduled send
  attempt (mesh, campaign, or group-reply) is blocked, not silently allowed through.
- Every existing send call-site (mesh, campaign, group-reply if present, helper-assist) is
  verified to call the gate — write a test that asserts the gate is invoked before any
  `sendMessage` call in each of these paths (e.g. via a mock that fails the test if
  `sendMessage` is called without a preceding gate check).
- A healthy instance passes the gate and sends normally (no regression).
Run full suite. Commit + push `V27 PART 1: live pre-send health gate for every send path`.

---

## PART 2 — Peer-level rate limiting (fixes incident gap #2) 🔴 HIGHEST PRIORITY

**Why:** Pacing must be enforced across ALL sends from one peer combined, not per cold
number independently.

### 2.1 Shared per-peer pacer
- Implement a per-INSTANCE (not per-edge) last-send timestamp / lock, e.g.
  `peer_last_send_at[instance_id]`. Before any send FROM a given instance (regardless of
  which cold number or campaign it's for), enforce a minimum gap since that instance's last
  send: **≥10–15 seconds, jittered**, matching the existing anti-ban pacing constant. If two
  scheduled sends from the same peer would land closer together than that, delay the later
  one.
- This must apply across the mesh AND campaign sending AND any other feature using that
  instance as a sender — the gap is per SENDING INSTANCE, full stop.

### 2.2 Tests
- One peer serving 2 (or more) cold numbers: simulate both wanting to send at nearly the
  same tick; assert the actual send timestamps are ≥10s apart (reproduce and fix the
  2.6–9s-apart incident pattern).
- Two DIFFERENT peers sending at the same time are NOT rate-limited against each other
  (the gate is per-instance, not global).
- Existing single-cold-number-per-peer scenarios are unaffected (no regression in normal
  low-load cases).
Run full suite. Commit + push `V27 PART 2: peer-level rate limiting across all cold numbers`.

---

## PART 3 — Minimum real age for warm-peer eligibility (fixes incident gap #3) 🔴 HIGHEST PRIORITY

**Why:** A peer must be genuinely established, not just manually flagged.

### 3.1 Hard age/health requirement
- When an instance is flagged `is_warm_peer=true` (via the existing UI/endpoint), validate:
  its `authorized_at` (or equivalent "connected since" timestamp) is **at least 14 real
  days in the past**, AND it has no recent (rolling 14-day) yellowCard/blocked incident.
  Reject the flag-set with a clear Persian error if not met, e.g. «این اکانت هنوز به‌اندازه‌ی
  کافی قدیمی/سالم نیست تا بتواند فرستنده‌ی گرم‌سازی باشد (حداقل ۱۴ روز سابقه‌ی سالم لازم
  است).» Prefer, where feasible, sourcing eligibility from having actually reached
  GRADUATED through the mesh state machine itself rather than only a manual flag + age
  check — but at minimum enforce the 14-day + clean-history gate on the manual flag path.
- Also RETROACTIVELY re-validate existing `is_warm_peer=true` instances against this rule
  once, and report (do not silently auto-unflag) any that fail it, so the user can decide.

### 3.2 Tests
- Flagging a <14-day-old instance as a peer is rejected with the Persian error.
- Flagging an instance with a yellowCard in the last 14 days is rejected.
- A genuinely 14+ day, clean-history instance can be flagged successfully.
- The retroactive check correctly reports (without auto-changing) any existing peers that
  wouldn't meet the bar today.
Run full suite. Commit + push `V27 PART 3: minimum real age + clean history for warm-peer eligibility`.

---

## PART 4 — Real-time instance-state monitoring (Green API's own official recommendation)

**Why:** Green API's own docs recommend polling `GetStateInstance` every ~1 minute AND
subscribing to the state-change webhook, acting immediately on `blocked`/`notAuthorized`.

### 4.1 Polling + webhook
- Add a scheduled Celery task that calls `GetStateInstance` for every active instance on a
  ~60-second cadence (batched/staggered to avoid a thundering herd), updating a cached
  "live state" column used by PART 1's gate.
- If the instance-authorization-state-change webhook/notification setting isn't already
  enabled, enable it (`SetSettings`) and handle the incoming notification to update the same
  cached state immediately (push, faster than the 60s poll) — this is IN ADDITION to
  polling, not instead of it (Green API recommends both).
- On receiving/polling a `blocked` or a restrictive state, immediately trigger the
  per-instance kill-switch (as in PART 1.1) so `can_send_now` reflects it right away.

### 4.2 Tests
- The poll task runs on the expected cadence and updates cached state.
- A simulated state-change webhook updates the cache faster than waiting for the next poll.
- A `blocked` state immediately trips the kill-switch for that instance.
Run full suite. Commit + push `V27 PART 4: real-time instance-state monitoring (poll + webhook)`.

---

## PART 5 — Safer number-existence validation (avoid CheckWhatsapp abuse)

**Why:** Green API's own blog warns that calling `CheckWhatsapp` too often *without* then
messaging the number is itself a block risk. Messaging invalid/non-existent numbers is
also a documented spam trigger. Both must be handled carefully.

### 5.1 Lazy, cached validation
- Before adding a number to a campaign, if its WhatsApp-existence hasn't been checked
  recently (cache per number, e.g. 30+ days), do ONE `CheckWhatsapp` call and cache the
  result; do NOT re-check a number repeatedly. Prefer relying on actual send-status feedback
  (a message's delivery status) as the ongoing signal of validity for numbers already
  messaged before, rather than re-querying `CheckWhatsapp`.
- Numbers that fail existence check are excluded from the campaign with a clear reason
  logged (not sent to).

### 5.2 Tests
- A number checked within the cache window is not re-checked (assert no duplicate
  `CheckWhatsapp` call).
- A nonexistent number is excluded from sending with a logged reason.
- Cache expiry after the window triggers a fresh (single) check.
Run full suite. Commit + push `V27 PART 5: lazy cached number-existence validation`.

---

## PART 6 — Media-fingerprint reuse tracking for campaign images

**Why:** Sending the identical image/video file to many recipients is a separately-tracked
spam signal, parallel to (but distinct from) the existing text-similarity protection.

### 6.1 Fingerprint tracking
- Compute a content hash (e.g. SHA-256) of any image/media sent in a campaign. Track, per
  sending instance, how many distinct recipients received the SAME media hash within a
  rolling window (e.g. 1 hour / 1 day — mirror whatever window the existing text-similarity
  check already uses for consistency).
- If a media file is about to be sent to more than a conservative threshold of distinct
  recipients in that window (pick a sensible conservative default, e.g. 10, consistent with
  the documented "10+ contacts within an hour" text-similarity signal), surface a Persian
  warning in the campaign UI/report (e.g. «این تصویر به تعداد زیادی از مخاطبان با فایل
  کاملاً یکسان ارسال شده — ریسک تشخیص اسپم را افزایش می‌دهد») rather than silently blocking
  — this is a warning/report signal, not a hard block, since product photos are often
  legitimately reused; make the threshold/behavior easy to find in code for future tuning.

### 6.2 Tests
- Sending the same media hash to many recipients within the window triggers the warning/
  report entry; different media or a longer time gap does not.
Run full suite. Commit + push `V27 PART 6: media-fingerprint reuse tracking for campaigns`.

---

## PART 7 — Volume-spike guard for ALL sending instances (not just warm-up-phase numbers)

**Why:** A sudden week-over-week or day-over-day volume jump is flagged independent of
absolute daily caps — and this risk applies to GRADUATED/established numbers too, not just
numbers formally inside the warm-up state machine.

### 7.1 Guard
- For every sending instance (whether or not currently enrolled in warm-up), track recent
  daily send volume (e.g. trailing 7-day average) and compare against today's planned
  volume. If today's planned volume would represent a large jump versus the recent average
  (pick a conservative multiplier, e.g. >3–5x the trailing average, with a sensible minimum
  floor so a quiet number sending a first small batch isn't flagged), do not silently allow
  it — cap today's send to a smoother ramp and log/report the deferral, so a long-quiet
  GRADUATED number can't suddenly be asked to blast a big campaign in one day.

### 7.2 Tests
- A graduated/established instance with a big new campaign queued after a quiet week is
  smoothed/ramped rather than sent all at once; a small first batch on a previously-unused
  but properly warmed number is NOT incorrectly blocked by the floor.
Run full suite. Commit + push `V27 PART 7: volume-spike guard for all sending instances`.

---

## PART 8 — Live per-instance quality score (reply-rate + failure-rate auto-throttle)

**Why:** WhatsApp's own trust assessment reportedly weighs engagement (opens/replies), not
just send volume. This needs to apply continuously to active campaign-sending instances,
not just be a warm-up-phase-only metric.

### 8.1 Quality score
- Compute a rolling per-instance score from: recent reply rate (replies received / messages
  sent, trailing window) and recent failed-delivery rate (from Green API send-status
  webhooks). Reuse the existing "نسبت پاسخ" tracking/plumbing already built for the
  warm-up mesh — extend it to also apply to instances actively sending campaigns
  (GRADUATED or otherwise), not only numbers formally inside a warm-up enrollment.
- If the score drops below a conservative threshold (pick a sensible default informed by
  the ~40% reply-rate "good" benchmark noted in research, adapted conservatively since a
  cold sales campaign will have a lower natural reply rate than person-to-person chat —
  document the chosen threshold clearly in code/comments so it's easy to tune), automatically
  throttle (slow the send rate further) or pause that instance's OUTBOUND campaign sending,
  and surface this clearly on the dashboard, e.g. «کیفیت این اکانت افت کرده — ارسال آن
  به‌صورت خودکار کند/متوقف شد.»

### 8.2 Tests
- A simulated drop in reply rate / rise in failure rate triggers the throttle/pause and the
  Persian dashboard notice; healthy engagement does not trigger it.
Run full suite. Commit + push `V27 PART 8: live quality-score auto-throttle`.

---

## PART 9 — Minimum-2-distinct-peers requirement + staggered cold-number starts

**Why:** The incident showed a single-peer, single-point-of-failure design: one peer with
its 2 slots both filled meant BOTH cold numbers lost their sender simultaneously when it
was carded.

### 9.1 Guard
- Before allowing more than a small number of cold numbers (e.g. >2) to be actively enrolled
  and assigned peers at once, require at least **2 distinct healthy `is_warm_peer=true`**
  instances to exist; otherwise surface the existing "ظرفیت پر است، یک فرستنده‌ی دیگر اضافه
  کنید" notice rather than concentrating everything on one peer.
- When a peer serves multiple cold numbers, **stagger their first-contact/start times**
  (e.g. do not let two cold numbers under the same peer both enter RECEIVING on the exact
  same day/hour — offset by at least a day where the schedule allows) so a single peer
  incident doesn't take down a whole cohort's warm-up progress at the same instant.

### 9.2 Tests
- Enrolling a 3rd+ cold number with only 1 healthy peer available surfaces the
  capacity-full notice instead of silently concentrating risk.
- Two cold numbers assigned to the same peer have staggered (not simultaneous) start times
  in their schedule.
Run full suite. Commit + push `V27 PART 9: minimum-2-peers requirement + staggered cold-number starts`.

---

## PART 10 — Tariff/quota monitoring (466 errors)

**Why:** If the account tariff or monthly quota is ever exceeded, Green API silently queues
messages (466 `QUOTE_EXCEEDED`/`QUOTE_ALLOWED`-restricted responses) — same visible symptom
as a ban ("nothing is sending") but a completely different cause, and currently invisible.

### 10.1 Detection + alert
- Detect 466-style quota/tariff-limit responses from any Green API call and surface a clear
  Persian admin alert distinguishing this from a ban/health issue, e.g. «سهمیه یا تعرفه‌ی
  حساب محدود شده — این ربطی به بن‌شدن ندارد، لطفاً تعرفه یا سهمیه را در Green API بررسی
  کنید.» so the user doesn't waste time debugging warm-up/peer logic when the real cause is
  billing/quota.

### 10.2 Tests
- A simulated 466 quota-exceeded response is detected and produces the distinct Persian
  alert (not confused with a yellowCard/blocked incident).
Run full suite. Commit + push `V27 PART 10: tariff/quota (466) monitoring and alerting`.

---

## FINAL REPORT (after all parts)
- Test count before → after, per-PART deltas, "zero regressions" confirmed (re-run the FULL
  pre-existing suite, not just new tests).
- Explicitly confirm, one line each, that the THREE incident-derived gaps are fixed:
  (1) live pre-send health gate exists and is used by every send path, (2) peer-level rate
  limiting is enforced across all cold numbers sharing a peer, (3) a 14-day minimum-age +
  clean-history gate blocks fresh numbers from becoming peers, including the retroactive
  check result for existing peers.
- One line per PART 4–10 confirming what was built.
- Confirm: polling never enabled; ngrok/webhook untouched; warm-up stays OFF by default;
  no existing protection (V17–V25) was weakened; all new UI text is Persian/RTL.
- The list of pushed commits, and the redeploy reminder:
  `docker compose build frontend && docker compose up -d frontend` and
  `docker compose up -d --force-recreate worker-general worker-webhooks beat backend`.
- **Flag clearly:** any existing `is_warm_peer=true` instance that fails the new PART 3
  retroactive age/health check (report, do not auto-unflag) — the user needs to decide what
  to do about each one (e.g. whether صالحی itself, once recovered, would even still qualify).

Then STOP and await review.

---
### REALITY NOTE (short version in the report)
These ten changes close real, diagnosed gaps and follow Green API's own official
recommendations, but no amount of engine hardening changes the underlying number-quality
problem (sequential/bulk-issued SIMs) identified earlier. Keep testing with low-value
numbers, keep the 24h post-registration wait, and keep pursuing the non-sequential/aged-SIM
triage strategy in parallel — this prompt makes the engine safer, it does not make bulk
messaging risk-free.