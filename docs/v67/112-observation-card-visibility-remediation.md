# V67.1 — Observation Card Visibility Remediation

**Mode:** Frontend-only Owner Change remediation. Not Phase 8. Not Master Phase 11.

## Root cause

The card was correctly mounted in `frontend/src/pages/Dashboard.jsx` and present in local commits `b1e079d` / `2061071`, but the owner could not see it because:

1. Those commits were **local-only** (`ahead 2` of `origin/feature/v67-autonomous-fleet-manager`) until this remediation push.
2. Running `claudegreenapi-frontend-1` was a **production nginx image built earlier** (created ~2026-08-02, Up multiple days) with **no source bind mount**.
3. The active browser-served bundle therefore contained **no** `Observation Window` / `observation-countdown-card` strings (`NO_OBSERVATION_IN_BUNDLE`).

Route was not wrong: index `/` renders `Dashboard.jsx`. Cache can amplify stale bundles after deploy; hard refresh is recommended.

## Fixes applied

| Fix | Behavior |
|-----|----------|
| A — Cutover fail-closed | `anyCutover` initial `null`; failed/malformed `GET /fleet/accounts` → count and cutover `null` → UI `Unknown` (never unsafe `false`) |
| B — Count label | Display `Current FleetAccount Count` (not cohort count) |
| Disclaimer | Calendar-day disclaimer on the card |
| Deploy | Push commits + rebuild/restart **frontend only** |

## Tests

- `frontend` node test suite for `session2Meta` + card source/mount guards (day 0/1/13/14/20, Unknown, fail-closed cutover, FleetAccount label, no buttons/tokens/mutating HTTP, Dashboard before heading, App index route).

## Deployment

Repository-approved narrow command (from `docker-compose.yml` service `frontend`):

```bash
docker compose build frontend
docker compose up -d frontend
```

Do **not** restart backend, PostgreSQL, Redis, Celery, or Green API for this change.

## Owner access

1. Open `http://<host>:3002/` (LAN IP or localhost as used for this stack).
2. Menu: `داشبورد` (landing index route `/`).
3. Card location: top of live dashboard content, before critical/warning banners and before heading `داشبورد زنده`.
4. Title: `Observation Window`; day from Session 2 start metadata.
5. After deploy: hard refresh (`Ctrl+F5`) if the old bundle persists.

## Proof of non-scope

- No Backend / API / Database / Migration / Redis / Celery / Green API / feature-flag / Shadow control changes.
- Session 2 observation continues uninterrupted.
- Master Phase 8 and Master Phase 11 not started.
