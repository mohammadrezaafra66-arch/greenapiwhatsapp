# V67.1 — Read-Only Observation Countdown Card (Owner Change)

**Mode:** Frontend-only reminder. Not Master Phase 11 Dashboard. Not Phase 8.

## Goal

Prevent forgetting that Session 2 Shadow observation is still running. Show Day X of 14, status, and read-only live labels on the existing home Dashboard.

## Why this is not Phase 11

Master Phase 11 is an RTL fleet management Dashboard (pools, timeline, scores, capacity, incidents, decisions, simulations, cohort stats). This card is a single non-interactive reminder with no fleet management, no control plane, and no new product surface beyond an existing page slot.

## Why Owner Change

Independent owner request to reduce operational forgetfulness during the 14-day gate. Documented under `109` that Phase 8 stays blocked until Phase 7 completion audit; the card repeats that warning textually.

## Limits

- No buttons (Enable/Disable/Start/Stop/Restart/Retry/Run/Execute)
- No new Backend / API / Migration / Celery / Redis / Green API / feature-flag changes
- No Shadow control, Cutover control, Canary, Human Contacts, Graduation, or Maintenance UI
- Snapshot count may show `Unknown` because authenticated Shadow summary endpoints are not used (no new public API; no operator token in frontend)
- Scheduler / Runtime / Shadow flags show `Unknown` without inventing unauthenticated flag endpoints
- Cohort count uses existing `GET /api/v1/fleet/accounts` only
- Day index computed client-side from Session 2 official start in ops doc `107` (`SESSION_2_META`)
- Auto-refresh every 60 seconds only
- Never displays `Phase 7 Fully Accepted`

## Files

- `frontend/src/observation/session2Meta.js` — pure logic
- `frontend/src/observation/session2Meta.test.js` — day/status tests
- `frontend/src/components/ObservationCountdownCard.jsx` — read-only UI
- `frontend/src/pages/Dashboard.jsx` — mount point only
