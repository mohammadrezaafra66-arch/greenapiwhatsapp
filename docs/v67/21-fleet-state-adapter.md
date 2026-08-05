# V67.1 Phase 2 — FleetState Adapter

## Authority

`fleet_accounts.fleet_state` is canonical AFM decision truth.

Sensors only: AccountStatus, WarmupState, Green live state, AccountIncident, fleet breaker, activity hints.

`send_gate` remains **execution veto** — Phase 2 does **not** cut over eligibility to FleetState.

## Precedence (07 matrix)

1. Terminal → RETIRED  
2. Live/account danger → BLOCKED / SUSPENDED / FORCED_LOGOUT  
3. Major open incidents → observable danger / REWARM path  
4. yellowCard / auth_churn → AT_RISK  
5. Fleet breaker → PAUSED  
6. Warmup progress / conservative defaults  

## Seed mapping (critical)

| Legacy | Seed FleetState |
|---|---|
| MATURING (day-10-ish) | **WARMUP_READY** |
| GRADUATED (any, including ≥25) | **WARMUP_READY** (never auto CAMPAIGN_READY in Phase 2 seed) |
| RAMPING | CONTROLLED_RAMP |
| REPLYING | BIDIRECTIONAL_BUILDING |
| RECEIVING | INBOUND_BUILDING |
| ENROLLED / COOLDOWN | AUTHORIZED_QUIET |
| BLOCKED_RESET | REWARM_REQUIRED |

D-H2 grandfather CAMPAIGN_READY for clean GRADUATED≥25 is **not** automatic seed — later explicit attestation/cutover.

## Module

`app.services.fleet_state_adapter.FleetStateAdapter`

CLI seed: `python -m app.scripts.fleet_seed --dry-run` (default) / `--apply`

## Phase 3 relationship

- Adapter remains **sensor → recommended state** (no journey execution).
- Journey engine (`evaluate_transition`) is a separate pure recommender for SIMULATION/SHADOW.
- Shadow diagnostics compare: canonical FleetState, adapter recommendation, journey recommendation, legacy AccountStatus/WarmupState, live Green state, incidents.
- Neither adapter nor journey engine cuts over `send_gate`. See `28-phase3-shadow-mode.md`.
