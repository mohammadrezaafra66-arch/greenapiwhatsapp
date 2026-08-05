# V67.1 Phase 7.2 — Shadow Environment Inventory

**Mode:** Read-only discovery. No flags changed. No Secrets revealed.  
**Date:** 2026-08-05  
**Host evidence:** Docker containers on the machine running this repository checkout.

## Preflight note

Tracked git tree: clean. Pre-existing untracked research/prompt files present at repo root (not staged; unchanged by Phase 7.2).

## Environments discovered

### ENV-A — `claudegreenapi` full Compose stack

| Field | Evidence |
|---|---|
| Identifier | Docker Compose project containers named `claudegreenapi-*` |
| Classification | **PRODUCTION_LIKE** (live WhatsApp account rows; send/campaign workers present; public webhook base configured in Compose) |
| Compose file | `docker-compose.yml` |
| Deployment path | Repository root (volume `./backend:/app`) |
| Backend | `claudegreenapi-backend-1` (uvicorn reload, host port `8002→8000`) |
| Database | `claudegreenapi-db-1` (`postgres:15-alpine`, DB `whatsapp_sender`) |
| Redis | `claudegreenapi-redis-1` (`redis:7-alpine`, URL `redis://redis:6379/0`) |
| Celery workers | `claudegreenapi-worker-general-1`, `claudegreenapi-worker-webhooks-1` |
| Celery Beat | `claudegreenapi-beat-1` |
| Frontend | `claudegreenapi-frontend-1` (port `3002`) — no Shadow UI |
| Migration method | `alembic` inside Backend container (`/app`) |
| Flag source | `app.config.Settings` defaults + optional `.env` (`env_file: .env`) |
| Secret source | `.env` (not committed); Compose does not set Shadow token |
| Logs | `docker logs <container>` |
| Rollback | Disable Shadow flags (when later authorized); `alembic downgrade v67_06_fleet_plan_snapshots` drops Shadow table only |
| Real WhatsApp accounts | **YES** — read-only count `accounts=26` (21 active) |
| Real campaigns can run | **YES** — worker queues include `campaigns`, `sending` |
| Safe for future Shadow observation | **CONDITIONAL** — only after separate owner naming/approval; not isolated staging |

### ENV-B — `docker-compose.dev.yml` host-dev helper

| Field | Evidence |
|---|---|
| Identifier | Dev Compose: Postgres + Redis only |
| Classification | **LOCAL_TEST** / **DEVELOPMENT** |
| Compose file | `docker-compose.dev.yml` |
| Services | `db` (host `5432`), `redis` (host `6379`) |
| Backend/Celery/Beat | Intended to run on host (documented in file header) |
| Currently used as observation target | **No evidence it is the active full stack** |
| Safe for disposable rehearsal | **YES** (infrastructure-only; no send workers in this file) |

### ENV-C — Unrelated containers on same host

Observed running but **outside** this repository’s Compose project (e.g. `afrakala-lan-*`, `whatsapp-platform-*`).  
Classification: **UNKNOWN / OUT OF SCOPE** for V67 Shadow enablement. Not nominated.

### ENV-D — CI/CD

No `.github/workflows` found in this repository.  
Classification: **NOT_APPLICABLE** (no CI enablement path discovered).

## Templates

| File | Shadow flags |
|---|---|
| `.env.example` | No `V67_SHADOW_*` keys |
| `frontend/.env.example` | No Shadow keys |

## Blocker summary

- No dedicated isolated **STAGING** environment discovered in-repo.
- Only complete running candidate is ENV-A (**PRODUCTION_LIKE** with live accounts).
- ENV-A has `fleet_accounts=0` (read-only) — Shadow account evaluation requires a FleetAccount row (service returns `fleet_account_missing`).
