# V18 MASTER PROMPT — Afrakala WhatsApp Sender
## Fix silent multi-account fan-out + wire the "smart warm-up" toggle to the V17 mesh

> **MODE: FULLY AUTONOMOUS.** Execute every PART below end-to-end WITHOUT asking the user
> questions and WITHOUT waiting for approval. After each PART: run a heavy test suite and
> verify it works; only advance once every test passes. Commit and push each PART
> separately. Produce a final report at the end.

---

## 0. CONTEXT (read first)

Project: `C:\Users\AFRA\Desktop\bots\claudegreenapi`
(GitHub: `mohammadrezaafra66-arch/greenapiwhatsapp`). Baseline: **V17**, all tests
passing, `origin/main` clean.

A diagnostic of a real yellowCard incident revealed TWO latent bugs (they did NOT cause
that incident, but both are dangerous and must be fixed):

1. **Silent fan-out fallback** at `campaign_runner.py` (around line 303): a `if chosen:`
   fallback can send from ALL accounts if the user's selected account is ever filtered
   out of the eligible set. This risks the exact disaster the user fears — a campaign the
   user intended to send from ONE account silently blasting from every account.
2. **Warm-up flag mismatch:** the "smart warm-up" toggle and the campaign-exclusion logic
   still key off the OLD `auto_warmup` flag, NOT the V17 `warmup_enrollment` system. As a
   result: (a) flipping the toggle does NOT actually start the V17 mesh (diagnostic showed
   zero enrollments/edges/events — the mesh has never run), and (b) a number that IS being
   mesh-warmed would not be excluded from real campaigns, so it could be pulled into a
   campaign and get banned.

**Stack:** FastAPI + PostgreSQL + Redis + Celery + React/Vite, Green API gateway,
AI key pool. Backend 8002, frontend 3002.

### NON-NEGOTIABLE GUARDRAILS
1. **NEVER enable Green API polling / `receiveNotification`.** Webhook-only deployment.
2. **Do NOT touch ngrok / webhook wiring.**
3. **Preserve existing correct behavior.** When a single account is selected and it is
   eligible, the campaign MUST send from only that account (this already works — keep it).
4. **Warm-up / mesh only messages the user's own instances, only after mutual-contact
   handshake. Never message a stranger. Warm-up is OFF by default.**
5. **All UI strings Persian (Farsi), RTL. Code/vars/comments English.**
6. **Commit + push each PART separately** (`V18 PART N: ...`). No uncommitted work between.

### WORKFLOW PER PART
Explore existing code first → implement → write/extend tests → run FULL `pytest` (not
just new tests) → verify → commit + push → next PART.

---

## PART 1 — Fix the silent multi-account fan-out (SAFETY-CRITICAL)

**Why:** A campaign must NEVER send from accounts the user didn't choose. The current
fallback can fan out to all accounts if the chosen account is filtered out.

### 1.1 Investigate
Read `campaign_runner.py` around the account-selection logic (~line 303) and any
`group_campaign_runner.py` equivalent. Identify the exact `if chosen:` / fallback branch
and every path where the set of sending instances is decided. Report (in the final
report) the precise before-behavior.

### 1.2 Fix
Rewrite the selection so it is **fail-closed, never fail-open**:
- If the user selected specific account(s): send from EXACTLY those, intersected with the
  eligible/healthy set. If one or more selected accounts are filtered out (e.g. cooldown,
  yellowCard, not authorized), send only from the remaining selected-and-eligible ones.
- If NONE of the selected accounts are eligible: **do NOT fall back to all accounts.**
  Instead, ABORT the send for that batch, mark the campaign/run with a clear status, and
  surface a Persian error to the user, e.g.
  **«اکانت انتخاب‌شده در دسترس نیست (استراحت/کارت زرد/عدم اتصال). کمپین ارسال نشد — یک اکانت سالم انتخاب کنید.»**
- Only when the user explicitly chose "all accounts" / parallel mode should multiple
  accounts be used. Selecting one account must never expand to many under any fallback.

Add a hard invariant/assertion: the final sending-instance set is always a SUBSET of what
the user explicitly selected (or the explicit "all/parallel" choice). Never a superset.

### 1.3 Tests
- Single account selected + eligible → sends from only that one (regression).
- Single account selected + that account filtered out → send ABORTS with the Persian
  error; sends from NOTHING; does NOT fan out.
- Multiple selected, some filtered → sends only from the eligible selected subset.
- Explicit all/parallel mode → unchanged behavior.
- Assertion catches any attempt to send from a non-selected instance.
Run full suite. Commit + push `V18 PART 1: fail-closed account selection (no silent fan-out)`.

---

## PART 2 — Unify warm-up on `warmup_enrollment`; wire the toggle to the V17 mesh

**Why:** The "smart warm-up" toggle must actually start the V17 mesh, and mesh-warming
numbers must be excluded from real campaigns. Today both still use the old `auto_warmup`
flag, so the mesh never runs and warming numbers aren't protected.

### 2.1 Make the toggle drive V17
Find where the "🔥 گرم‌سازی خودکار / گرم‌سازی هوشمند" toggle is handled (frontend action +
backend endpoint). Rewire it so turning it ON for an account:
- Creates/activates a `warmup_enrollment` for that instance (the V17 pre-flight from PART
  3 of V17: apply warming SetSettings, enforce 24h cooldown, build the mutual-contact
  mesh with eligible warm peers) — i.e. actually starts the V17 state machine.
- Turning it OFF pauses/disables that enrollment (stops all mesh activity for the number).

If a legacy `auto_warmup` boolean still exists, treat enrollment as the single source of
truth: either map the old flag onto enrollment or migrate it, but the toggle's effect must
be a real `warmup_enrollment`, not just a boolean.

### 2.2 Fix campaign exclusion to key off enrollment
Wherever campaigns exclude warming accounts, change the check from the old `auto_warmup`
flag to: **exclude any instance whose `warmup_enrollment` is active and not yet
GRADUATED.** A number that is COOLDOWN/RECEIVING/REPLYING/RAMPING/MATURING must NOT be
selectable/used in a real campaign. Only GRADUATED (or never-enrolled, known-good) numbers
are campaign-eligible. Combine this with PART 1: the eligible set excludes non-graduated
warming numbers.

### 2.3 Verify the mesh actually activates
After wiring, confirm (in code/tests, with Green API mocked) that flipping the toggle on a
new account with ≥1 eligible warm peer results in: an enrollment row, mesh edges created,
mutual-contact handshake attempted, and the scheduler beginning to drive state — i.e. the
V17 mesh genuinely runs (fixing the "zero enrollments/edges/events" finding). If there are
not enough warm peers, it must surface the existing Persian "اکانت گرم کافی نیست" notice
and send nothing (not silently do nothing with no explanation).

### 2.4 Tests
- Toggle ON creates an active `warmup_enrollment` (not just a boolean) and kicks off
  pre-flight; toggle OFF disables it and stops mesh activity.
- A non-graduated warming instance is EXCLUDED from campaign account selection (cannot be
  chosen; if somehow selected, PART 1's fail-closed logic drops it).
- A GRADUATED instance IS campaign-eligible again.
- With ≥1 warm peer, toggling ON produces enrollment + edges + handshake attempt (mesh
  activates); with 0 warm peers, the Persian insufficient-peers notice is surfaced and
  nothing is sent.
- No stranger is ever messaged; warm-up still OFF by default.
Run full suite. Commit + push `V18 PART 2: wire smart-warmup toggle to V17 mesh + enrollment-based campaign exclusion`.

---

## FINAL REPORT (after both parts)
Produce one summary with:
- Test count before → after, per-PART deltas, "zero regressions" confirmed.
- PART 1: the exact old fan-out behavior found, and the new fail-closed behavior, with the
  invariant that the sending set is always a subset of the user's selection.
- PART 2: confirmation that the toggle now creates a real `warmup_enrollment` and starts
  the V17 mesh, and that non-graduated warming numbers are now excluded from campaigns.
- Direct answer to the user's question, stated plainly: **"After V18, when you enable smart
  warm-up on an account, does the system automatically send messages FROM your warm
  accounts TO the new one?"** — describe the actual post-V18 behavior (yes, via the V17
  mesh, provided there is ≥1 eligible GRADUATED/known-good warm peer and the 24h cooldown
  has passed; otherwise it holds and shows the insufficient-peers notice).
- Confirmation: polling never enabled; ngrok/webhook untouched; single-account selection
  still sends from only that account; warm-up OFF by default; strangers never messaged.
- The list of pushed commits.

Then STOP and await the user's review.

---
### REALITY NOTE (short version in the report)
Warm-up reduces ban risk, never eliminates it. A brand-new number can be carded by
WhatsApp within minutes of connecting, before we send anything (this already happened) —
so always let a new number sit through the 24h cooldown + warm-up before using it, and
warm-test on low-value numbers first.