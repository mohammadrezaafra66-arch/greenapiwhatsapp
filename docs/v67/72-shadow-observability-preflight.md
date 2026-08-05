# V67.1 Phase 7.2 — Shadow Observability Preflight

## Required visibility vs available mechanisms

| Signal | Available now | Mechanism |
|---|---|---|
| Task starts/finishes | PARTIAL | Celery/worker Docker logs; disabled path returns immediately |
| Duration | PARTIAL | Log timestamps; no dedicated histogram |
| Skipped-disabled | YES | Task return + in-process `shadow_skipped_disabled` counter |
| Account count / failures | PARTIAL | Periodic result dict when enabled; logs |
| Lock / Redis failure | YES | Metrics counters + service error fields |
| DB unavailable | PARTIAL | Exception logs |
| Policy / stale / runtime unknown | YES | Snapshot columns + comparison JSON (when persisted) |
| Mismatch / severity distribution | YES | SQL on `fleet_shadow_snapshots` + summary API |
| Persist / idempotent skip | YES | Metrics + row uniqueness |
| Auth failures | PARTIAL | HTTP status + app logs (no token) |
| Rate-limit | YES | HTTP 429 on run-once |

## Mechanisms present

- Application / Docker logs
- In-process `shadow_metrics` (best-effort, **not** fleet-global across workers)
- Authenticated read APIs: `/fleet/shadow/summary`, `/drift`, `/status`
- Direct SQL (see query catalog)

## Mechanisms absent

- Dedicated Prometheus Shadow dashboards
- Cross-worker aggregated metrics
- Automated paging/alerts for Shadow

## Classification

**PARTIALLY_SUFFICIENT** for a small controlled Stage A/B observation **if**:

- daily SQL + log review is staffed (D-SE-11)
- cohort is small
- operators accept per-process metrics limits

**Not** sufficient to claim fleet-global automated observability.

## Minimal pre-observation remediation (optional; not implemented in 7.2)

1. Document daily review checklist (included in observation plan)
2. Ensure operator access to `docker logs` for backend/worker/beat
3. Keep query catalog handy
4. Do **not** require a full observability platform before Stage A dry-runs
