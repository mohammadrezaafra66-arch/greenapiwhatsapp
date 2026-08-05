# V67.1 Phase 0.5 — Canonical FleetState Matrix

**Authority:** `fleet_accounts.fleet_state` is the single AFM decision truth.  
`AccountStatus`, `WarmupState`, and Green API live state are **sensors / legacy mirrors**, not competing authorities.

Legend for Green column: typical live `stateInstance` values (lower-cased in gate).

---

## 1. Master matrix

| FleetState | AccountStatus (typical) | WarmupState (legacy map) | GreenAPI live (typical) | Allowed actions | Blocked actions | Transition rules (enter) | Recovery rules |
|---|---|---|---|---|---|---|---|
| `NEW` | `pending` | none / not enrolled | unknown / notAuthorized | Register metadata, device, batch | Send, QR link, campaign | Account created in platform | — |
| `PRECHECK` | `pending` | none | any | Preflight checks, policy assign | Send, QR | Classifier + preflight start | Fail → `FAILED` / stay PRECHECK |
| `QR_WAITING` | `pending` | none | notAuthorized | Wait 24h clock; show wait UI | QR scan, send | Gate B / V67 24h post-WA | Timer complete → `READY_TO_LINK` |
| `READY_TO_LINK` | `pending` | none | notAuthorized | QR / auth code link | Campaign, warm send | 24h elapsed + preflight OK | Link success → observe authorized |
| `AUTHORIZED_QUIET` | `active` | `ENROLLED`/`COOLDOWN` | authorized | Receive only; stamp `connected_at` | Outbound (connect cooldown) | First authorized + healthy | Evidence → inbound build; danger → incident states |
| `INBOUND_BUILDING` | `active` | `RECEIVING` | authorized | Receive; schedule human/warmer inbound | Campaign; high outbound | Quiet done + journey selected | Low evidence stay; danger → risk/suspend |
| `BIDIRECTIONAL_BUILDING` | `active` | `REPLYING` | authorized | Limited real replies within Policy | Campaign; burst outbound | Inbound evidence met | Ratio fail → slow/AT_RISK |
| `CONTROLLED_RAMP` | `active` | `RAMPING` | authorized | total_daily_flow ramp per Policy | Full campaign | Bidirectional evidence | Spike/incident → AT_RISK/PAUSED |
| `WARMUP_READY` | `active` | `MATURING` or recovery “GRADUATED” | authorized | Graduation trial only | Full campaign pool | Base ramp complete (≈day 10 CONSERVATIVE) | Trial fail stay/rewarm path |
| `GRADUATION_TRIAL` | `active` | (none dedicated) | authorized | Tiny capacity campaign | Unbounded campaign | Owner/Autopilot trial start | Pass → CAMPAIGN_READY; fail → WARMUP_READY/AT_RISK |
| `CAMPAIGN_READY` | `active` | `GRADUATED` (general ≥25 grandfather) | authorized | Capacity-planned campaign | Bypass risk/STOP | Trial pass + certificate partial | Incident → AT_RISK/REWARM |
| `MATURE` | `active` | `GRADUATED` | authorized | Policy capacity | — | 25–30 healthy days | Drift → MAINTENANCE/AT_RISK |
| `MAINTENANCE` | `active` | `GRADUATED` | authorized | Few real daily interactions | Idle erosion ignore | Mature stable | Idle → AT_RISK; safety scan rules via Policy |
| `AT_RISK` | `active` (throttled) | `YELLOWCARD` / PAUSED-ish | authorized or yellowCard | Receive-only / SLOW budget | Normal campaign | RiskEngine threshold | Improve → prior; worsen → PAUSED |
| `PAUSED` | `active` or cooldown | `PAUSED` | any non-terminal | None outbound | All sends | Owner/breaker/kill | Owner resume → PRECHECK or prior safe |
| `SUSPENDED` | `suspended` | any → interrupt | suspended | None outbound; fetch suspendedUntil | All sends, QR spam | stateInstanceChanged / getWaSettings | Cooldown → verify → **REWARM_REQUIRED** (no direct resume) |
| `BLOCKED` | `banned` | `BLOCKED_RESET` | blocked | None | All; immediate relogin | blocked webhook | Incident → **REWARM_REQUIRED** |
| `FORCED_LOGOUT` | `disconnected` | `BLOCKED_RESET` | notAuthorized (forced) | None; no immediate relogin | Link until cooldown | logout / notAuthorized genuine | → REWARM_REQUIRED |
| `RECOVERY_COOLDOWN` | `suspended` lifting / disconnected resting | COOLDOWN-like | varies | Limited observe | Campaign / ramp | After suspend window | Verify healthy → REWARM_REQUIRED |
| `REWARM_REQUIRED` | any recoverable | `BLOCKED_RESET` / recovery reset | must re-precheck | Reset journey to PRECHECK path | Resume mid-ramp | Any major incident path | New journey; recovery_mode Policy |
| `FAILED` | any | PAUSED sticky | unknown/errors | Manual only | Autopilot | Repeated failures | Owner only |
| `RETIRED` | `deleted` / `green_api_deleted` | none | deleted | None | Everything | Owner retire / instance gone | Terminal |

---

## 2. Derivation priority (no duplicated truth)

When sensors disagree, apply in order:

1. **Terminal ops:** `green_api_deleted` / `deleted` → `RETIRED`
2. **Live danger:** `blocked` → `BLOCKED`; `suspended` → `SUSPENDED`; forced `notAuthorized` after session → `FORCED_LOGOUT`
3. **AccountStatus danger:** `banned` → `BLOCKED`; `suspended` → `SUSPENDED`; `disconnected` → may be `FORCED_LOGOUT` or quiet disconnect (classifier)
4. **Open critical incidents** (yellowCard unresolved) → at least `AT_RISK`/`PAUSED`
5. **Fleet journey progress** (evidence + Policy day) → building/ramp/ready states
6. **Legacy WarmupState** used only if Autopilot not cut over and no stronger signal

`send_gate` remains an **execution veto** even if FleetState is wrong (defense in depth).

---

## 3. Risk budget overlay (not a FleetState)

Independent axis on `fleet_accounts.risk_budget`:

`NORMAL → SLOW → RECEIVE_ONLY → PAUSED → REWARM_REQUIRED`

If budget is `RECEIVE_ONLY` while FleetState is `CAMPAIGN_READY`, **outbound campaign is blocked** until budget recovers. FleetState does not need to change for every throttle tick (reduces thrash); DecisionExplainer records overlay.

---

## 4. Day-10 freeze (glossary)

| Term | Meaning |
|---|---|
| Day 10 (CONSERVATIVE default) | Enter / remain `WARMUP_READY` |
| `فارغ‌التحصیلی` (legacy UI) | Must be relabeled: not full campaign; map carefully in Phase 11 |
| Campaign-ready | Only `CAMPAIGN_READY` / `MATURE` / `MAINTENANCE` with NORMAL/SLOW budget |

---

## 5. Incident → REWARM_REQUIRED (non-negotiable)

| Incident | Immediate FleetState | Then |
|---|---|---|
| Suspend | `SUSPENDED` | `RECOVERY_COOLDOWN` → `REWARM_REQUIRED` |
| Block | `BLOCKED` | `REWARM_REQUIRED` |
| Forced logout / device restriction | `FORCED_LOGOUT` | `REWARM_REQUIRED` |
| YellowCard | `AT_RISK`/`PAUSED` | Policy may escalate to REWARM on repeat |

Direct resume to CAMPAIGN_READY after these is **forbidden**.
