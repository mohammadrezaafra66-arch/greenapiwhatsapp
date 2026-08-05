# V67.1 Phase 7.2 — Shadow Celery / Scheduler Preflight

## ENV-A evidence

| Check | Result |
|---|---|
| Worker health | `celery inspect ping` → general + webhooks **OK** (2 nodes) |
| Beat container | `claudegreenapi-beat-1` Up |
| Shadow task name | `tasks.fleet_shadow_tick` registered |
| Beat schedule key | `fleet-shadow-tick` |
| Schedule interval | `300.0` seconds (code default) |
| Disabled no-op | Invoked → `skipped` / `shadow_flags_disabled` |
| Catch-up | Disabled path returns before account load |
| Batch size setting | `25` |
| Lock | Per-account when periodic path enabled |
| Routing to send queues | Task is standard Celery task; does not enqueue send/campaign |
| Green API path | Not invoked by disabled task; Shadow service uses read-only eligibility helpers only |
| Auto-enablement | None — both flags required |

## Worker queues (context)

`worker-general` consumes `campaigns,extraction,backfill,celery,sending` — **send capacity exists in the same environment**, independent of Shadow. This elevates ENV-A risk classification to PRODUCTION_LIKE.

## Phase 7.2 prohibitions honored

- Did not enable periodic Shadow
- Did not dispatch live Shadow against real accounts
- Only disabled-mode invocation + registration inspection

## Verdict

**Celery/Beat technically ready for controlled future observation after flags are explicitly authorized.**  
**Not enabled.**
