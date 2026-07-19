# V21 MASTER PROMPT — Afrakala WhatsApp Sender
## Enforce warm:cold ratio, exclude unconnected accounts, smarter chain-ban breaker

> **MODE: FULLY AUTONOMOUS.** Execute every PART end-to-end WITHOUT asking the user
> questions and WITHOUT waiting for approval. After each PART: run a heavy test suite and
> verify it works; only advance once every test passes. Commit and push each PART
> separately. Produce a final report at the end.

---

## 0. CONTEXT (read first)

Project: `C:\Users\AFRA\Desktop\bots\claudegreenapi`
(GitHub: `mohammadrezaafra66-arch/greenapiwhatsapp`). Baseline: **V20**, all tests
passing, `origin/main` clean.

A real chain-ban breaker trip revealed design gaps. Diagnosis findings (ground truth):
- The chain-ban breaker tripped and paused the whole mesh after 2 cold numbers
  (`770022682882`, `770022683837`) hit yellowCard. Root cause was **low-trust/fresh
  numbers carding on their own** (even at rest), NOT the mesh send logic. V21 CANNOT fix
  number quality — but it can make the system safer and give the user control.
- **Design gap 1:** the breaker counts INCIDENTS, not DISTINCT numbers — so one flaky
  number tripping repeatedly halts the entire mesh.
- **Design gap 2:** a pending / never-connected number (`770022683837`) was allowed into
  the mesh and enrolled. Unconnected numbers must never enter the mesh.
- **Design gap 3:** no warm:cold ratio cap — one warm peer was serving 4+ cold numbers,
  which itself is a suspicious pattern for the sender.

**User decisions (build to these EXACTLY):**
1. **Warm:cold ratio cap = 1 warm peer : at most 2 cold numbers.** A single warm peer may
   warm AT MOST 2 cold numbers at a time. (Conservative; ship 2 as the value.)
2. **Automatic peer assignment**, but it MUST respect the ratio cap. The system picks peers
   automatically; it must never assign more than 2 cold numbers to one warm peer. (No manual
   peer→cold mapping UI required in this version.)
3. Recovery of the currently-paused/yellowCard numbers is handled MANUALLY by the user —
   V21 does NOT need to auto-reset the breaker or auto-resume numbers.

**Stack:** FastAPI + PostgreSQL + Redis + Celery + React/Vite, Green API gateway, AI key
pool. Backend 8002, frontend 3002. Webhook-only.

### NON-NEGOTIABLE GUARDRAILS
1. **NEVER enable Green API polling.** Webhook-only.
2. **Do NOT touch ngrok / webhook wiring. Do NOT weaken the send path, the message mesh
   core, or the V19 group track** beyond the specific changes below.
3. **Mesh only messages the user's own instances over mutual-contact edges. Never a
   stranger. Warm-up OFF by default. A warm peer is never enrolled/warmed.**
4. **All UI strings Persian (Farsi), RTL.** Code/vars/comments English.
5. **Commit + push each PART separately** (`V21 PART N: ...`).

### WORKFLOW PER PART
Explore existing code first → implement → write/extend tests → run FULL `pytest` → verify →
commit + push → next PART.

---

## PART 1 — Enforce the warm:cold ratio cap (1 warm peer : max 2 cold)

**Why:** A warm peer serving many cold numbers is a suspicious pattern and overloads the
sender. Cap it.

### 1.1 Ratio logic
- Add a configurable constant `MAX_COLD_PER_WARM_PEER = 2` (shipped value 2).
- In the peer-selection / edge-building logic (`ensure_mesh_edges` and the peer eligibility
  function), enforce: a given warm peer may have AT MOST `MAX_COLD_PER_WARM_PEER` ACTIVE
  cold numbers assigned to it (active = enrolled, not GRADUATED, not
  PAUSED/blocked). When building an edge for a cold number, only pick a warm peer that is
  currently below the cap. Count existing active edges per peer to decide.
- If NO eligible warm peer is below the cap, the cold number gets NO peer yet: leave it
  without an edge, set a clear status, and surface a Persian notice on the dashboard, e.g.
  **«ظرفیت اکانت‌های گرم پر است — برای گرم‌کردن این شماره، یک اکانت گرم دیگر به‌عنوان فرستنده اضافه کنید (هر اکانت گرم حداکثر ۲ شماره).»**
  Do NOT overload a peer past the cap.

### 1.2 Distribute across peers
- When multiple warm peers exist, distribute cold numbers to balance load (fill peers
  evenly up to the cap) rather than piling onto one peer.

### 1.3 Tests
- One warm peer + 3 cold enrolled → only 2 get an edge to it; the 3rd gets the "capacity
  full" notice and no edge.
- Two warm peers + 4 cold → 2 each (balanced), none over cap.
- Adding a 2nd warm peer frees capacity so a waiting cold number then gets an edge.
- A peer never exceeds 2 active cold assignments under any tick/retry.
Run full suite. Commit + push `V21 PART 1: enforce 1:2 warm-to-cold ratio cap`.

---

## PART 2 — Exclude pending / never-connected numbers from the mesh

**Why:** A number that isn't authorized on Green API (pending) was enrolled and given a
mesh slot. Unconnected numbers must never enter the mesh.

### 2.1 Gate enrollment + ticking on connection state
- At enrollment (toggle ON) AND on every mesh tick, verify the instance is actually
  authorized/connected on Green API (its state = authorized). If a number is
  pending / notAuthorized / never-connected:
  - Do NOT create an enrollment / do NOT build edges / do NOT count it as an active cold
    number for ratio purposes.
  - Surface a clear Persian status on its card, e.g.
    **«این شماره هنوز به واتساپ متصل نشده — ابتدا با اسکن QR وصل کنید تا گرم‌سازی شروع شود.»**
- If a number was already enrolled while pending (like `770022683837`), the tick must skip
  it and show the not-connected notice until it authorizes; once it authorizes, it can
  proceed normally.

### 2.2 Tests
- Toggling warm-up on a pending instance does NOT create an active enrollment/edges and
  shows the not-connected notice.
- A pending enrolled number is skipped by the tick and does not consume a warm peer's ratio
  slot; when it becomes authorized, it proceeds.
Run full suite. Commit + push `V21 PART 2: exclude pending/unconnected numbers from mesh`.

---

## PART 3 — Smarter chain-ban breaker (count DISTINCT numbers, not incidents)

**Why:** The breaker halts the whole mesh when ONE flaky number cards repeatedly, because
it counts incidents. It should count DISTINCT numbers.

### 3.1 Breaker logic
- Change the chain-ban trip condition to count **distinct instances** that hit
  yellowCard/blocked within the rolling window (keep the existing ~24–48h window), NOT the
  raw number of incidents. Trip only when **≥2 DISTINCT numbers** are affected in the
  window. Repeated cards from the SAME single number must NOT trip the global breaker;
  instead, that single number should be paused/quarantined on its own (per-number
  kill-switch, which already exists) without halting everyone else.
- Keep the existing per-number kill-switch (yellowCard → pause that number → rest → reduced
  resume) unchanged.
- Keep the manual breaker reset endpoint and the "بازنشانی بریکر" button. Keep PAUSED
  sticky (numbers require explicit resume) — do not auto-resume.

### 3.2 Dashboard clarity
- When the breaker trips, show WHICH distinct numbers caused it and when. When only a single
  number is quarantined (not a global trip), make that clear too («این شماره به‌دلیل کارت زرد
  قرنطینه شد — بقیهٔ شبکه فعال است»).

### 3.3 Tests
- 3 incidents from ONE number in the window → global breaker does NOT trip; that number is
  quarantined; other numbers keep running.
- 2 DISTINCT numbers carded in the window → global breaker trips (as before).
- Manual reset still works; PAUSED numbers still require explicit resume.
Run full suite. Commit + push `V21 PART 3: breaker counts distinct numbers, not incidents`.

---

## PART 4 — Dashboard: ratio + capacity + peer load visibility

**Why:** The user needs to see the ratio state and why a number may be waiting.

### 4.1 Dashboard
- Show, per warm peer, how many cold numbers it's currently warming (e.g. «۲ از ۲ ظرفیت»)
  so the user can see when peers are full.
- Show, per cold number, which warm peer it's assigned to (or the "capacity full — add
  another warm peer" notice if none).
- Show the breaker state clearly: tripped (with the distinct numbers that caused it) vs.
  a single quarantined number vs. healthy.

### 4.2 Tests
- Dashboard reports correct peer load (n/2), cold→peer assignment, capacity-full notice,
  and breaker/quarantine state. Run full suite. Commit + push
  `V21 PART 4: dashboard ratio + capacity + breaker visibility`.

---

## FINAL REPORT (after all parts)
Produce one summary with:
- Test count before → after, per-PART deltas, "zero regressions" confirmed.
- PART 1: the 1:2 ratio cap and how peers are balanced; what happens when capacity is full.
- PART 2: pending numbers are now excluded from the mesh and shown a connect notice.
- PART 3: the breaker now trips on ≥2 DISTINCT numbers, not repeated incidents from one;
  single flaky numbers are quarantined without halting the mesh.
- PART 4: dashboard now shows peer capacity (n/2), assignments, and precise breaker state.
- **Plain guidance for the user:** with the 1:2 cap, to warm N cold numbers the user needs
  at least ceil(N/2) warm peers. State this explicitly.
- **Reality note:** V21 does NOT fix number quality — the carding root cause was low-trust
  fresh numbers, which will keep tripping safety regardless of send logic. Use higher-quality
  numbers, warm on low-value numbers first, and keep the 24h cooldown / waking-hours / slow
  pace. Frontend needs a redeploy for the new dashboard bits.
- Confirmation: polling never enabled; ngrok/webhook untouched; mesh core + group track
  otherwise unchanged; warm-up OFF by default; peers never warmed; no strangers messaged.
- The list of pushed commits, and a reminder to redeploy the frontend + restart worker/beat
  so the new logic and UI take effect (`docker compose build frontend && docker compose up
  -d frontend` and `docker compose up -d --force-recreate worker-general worker-webhooks
  beat`).

Then STOP and await the user's review.