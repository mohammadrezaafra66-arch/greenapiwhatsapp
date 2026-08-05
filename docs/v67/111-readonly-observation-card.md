# V67.1 — Read-Only Observation Countdown Card (Owner Change)

**Mode:** Frontend-only reminder. Not Master Phase 11 Dashboard. Not Phase 8.

## Goal

Prevent forgetting that Session 2 Shadow observation is still running. Show Day X of 14, status, and read-only live labels on the existing home Dashboard.

## Exact route and mount

| Item | Value |
|------|--------|
| Routed component | `frontend/src/pages/Dashboard.jsx` |
| Router | `frontend/src/App.jsx` → `<Route index element={<Dashboard />} />` |
| User-facing path | `/` (application root under the authenticated layout) |
| Menu label | `داشبورد` |
| Live page heading | `داشبورد زنده` |
| Card mount | First child of Dashboard content: `<ObservationCountdownCard />` **before** red/yellow/queue banners and **before** the `داشبورد زنده` heading |
| Default UI port (compose) | `http://<host>:3002/` |

This remains outside Master Phase 11 (no fleet control plane, pools, timeline, or operator actions).

## Why this is not Phase 11

Master Phase 11 is an RTL fleet management Dashboard (pools, timeline, scores, capacity, incidents, decisions, simulations, cohort stats). This card is a single non-interactive reminder with no fleet management, no control plane, and no new product surface beyond an existing page slot.

## Why Owner Change

Independent owner request to reduce operational forgetfulness during the 14-day gate. Documented under `109` that Phase 8 stays blocked until Phase 7 completion audit; the card repeats that warning textually.

## Deployment / build requirement

Frontend is a **built Docker image** (no bind mount of source). Source changes are invisible until:

1. Commits are on the branch used for the image build
2. `docker compose build frontend && docker compose up -d frontend` (or equivalent) rebuilds and recreates **only** the frontend service
3. Owner hard-refreshes the browser if an old JS bundle is cached (`Ctrl+F5` / empty-cache reload)

Visibility remediation details: `docs/v67/112-observation-card-visibility-remediation.md`.

## Data limitations

- **Day counter:** client-side calendar progress from Session 2 official start in ops doc `107` (`SESSION_2_META`). Not proof of consecutive valid observation days. Disclaimer on card: *Elapsed calendar day only; final validity is determined by the Phase 7 Completion Audit.*
- **Current FleetAccount Count:** from existing `GET /api/v1/fleet/accounts` row length. This is **not** Session 2 cohort membership size.
- **Cutover:** fail-closed — `null` / Unknown until a valid array response is parsed; never treat missing evidence as `false`.
- Snapshot / Scheduler / Runtime / Shadow may show `Unknown` (no new public APIs; no operator token in frontend).

## Limits

- No buttons (Enable/Disable/Start/Stop/Restart/Retry/Run/Execute)
- No new Backend / API / Migration / Celery / Redis / Green API / feature-flag changes
- No Shadow control, Cutover control, Canary, Human Contacts, Graduation, or Maintenance UI
- Auto-refresh every 60 seconds only
- Never displays `Phase 7 Fully Accepted`
- API failure keeps the card visible with FleetAccount Count / Cutover as `Unknown`

## Files

- `frontend/src/observation/session2Meta.js` — pure logic
- `frontend/src/observation/session2Meta.test.js` — day/status/parse tests
- `frontend/src/components/ObservationCountdownCard.jsx` — read-only UI
- `frontend/src/components/ObservationCountdownCard.test.js` — mount/security guards
- `frontend/src/pages/Dashboard.jsx` — mount point only
- `docs/v67/112-observation-card-visibility-remediation.md` — deploy visibility fix
