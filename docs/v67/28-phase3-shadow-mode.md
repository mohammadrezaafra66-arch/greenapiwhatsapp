# V67.1 Phase 3 — Shadow Mode

## Modes

- `SIMULATION` — dry-run / optional persist of simulation journey + PLANNED actions  
- `SHADOW` — compare recommendations; no repair  

No `LIVE` mode.

## Comparison labels

| Label | Meaning |
|---|---|
| MATCH | Canonical / adapter / journey aligned |
| SAFE_MISMATCH | e.g. legacy GRADUATED vs canonical WARMUP_READY |
| DANGEROUS_MISMATCH | active vs live suspended; ready + major incident; unexpected CAMPAIGN_READY |
| INSUFFICIENT_EVIDENCE | incomplete sensors/evidence |

## Cutover

`fleet_accounts.cutover` remains **false**. Orchestrator refuses persist if cutover already true. Never writes cutover=true.

## send_gate

Unchanged. FleetState does not grant/deny real sends.
