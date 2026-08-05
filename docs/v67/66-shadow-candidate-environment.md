# V67.1 Phase 7.2 — Shadow Candidate Environment

## Selected candidate (provisional — pending D-SE-01)

**ENV-A — `claudegreenapi` Docker Compose stack** (`docker-compose.yml`)

This is the only discovered environment with Backend + Postgres + Redis + Celery workers + Beat currently healthy and serving this codebase.

## Why selected

- Complete runtime graph present and pingable
- Alembic head already includes `v67_07_fleet_shadow_snapshots`
- Shadow Beat task registered; disabled no-op proven
- Redis NX/Lua disposable preflight succeeded
- Logs accessible via Docker

## Why not auto-approved for enablement

| Risk | Detail |
|---|---|
| Live accounts | 26 accounts (21 active) — real WhatsApp connectivity possible |
| Send authority in same stack | Workers consume `campaigns` / `sending` queues |
| Not isolated staging | No separate staging Compose/project found |
| Fleet enrollment empty | `fleet_accounts=0` — cohort cannot run until Fleet rows exist |
| Operator token unset | Correct fail-closed today; provisioning needs D-SE-03 |
| Monitoring | Logs + SQL + in-process metrics only (see doc `72`) |

## Rejected / deferred alternatives

| Env | Decision | Reason |
|---|---|---|
| ENV-B `docker-compose.dev.yml` | Rejected as primary observation host | Incomplete stack (no workers/Beat in Compose); good for LOCAL_TEST only |
| ENV-C unrelated host stacks | Rejected | Out of repo scope; unknown ownership |
| Production-only “last resort” | Not nominated as distinct env | ENV-A already production-like; separate “production” name not evidenced |

## Unresolved facts (owner must answer)

1. Is ENV-A the intended approved observation environment name?
2. Should a new isolated staging stack be created before any flag enablement?
3. When will FleetAccount seeding/enrollment be completed for a cohort?
4. Who holds emergency stop authority (D-SE-10)?

## Snapshot persistence safety (future)

- Table exists and is empty (`shadow_rows=0`)
- Persistence is Shadow-table-only by design
- Still **not authorized** in Phase 7.2
- Disk headroom observed on DB volume mount (~891G available in `df` output) — not a storage blocker

## Separate owner approval required

**YES.** Phase 7.2 does not authorize enablement on ENV-A.
