# V67.1 — Read-Only Observation Countdown Card (Owner Change)

**Mode:** Frontend-only reminder. Not Master Phase 11 Dashboard. Not Phase 8.

## Goal

Prevent forgetting that Session 2 Shadow observation is still running. Show Persian Day X of 14, status, daily owner guidance, and read-only live labels on the existing home Dashboard.

## Exact route and mount

| Item | Value |
|------|--------|
| Routed component | `frontend/src/pages/Dashboard.jsx` |
| Router | `frontend/src/App.jsx` → `<Route index element={<Dashboard />} />` |
| User-facing path | `/` |
| Menu label | `داشبورد` |
| Live page heading | `داشبورد زنده` |
| Card mount | First child: `<ObservationCountdownCard />` before banners and before `داشبورد زنده` |
| Default UI port | `http://<host>:3002/` |

## Persian UI (summary)

Full owner-facing copy is Persian. See `docs/v67/113-observation-card-persian-owner-guide.md`.

- Title: `دوره مشاهده ۱۴ روزه`
- Badge: `فقط شبیه‌سازی و مشاهده`
- Day: `روز X از ۱۴` / unknown / not-started variants
- Fail-closed unknowns: `نامشخص`
- Fleet count label: `تعداد حساب‌های ناوگان` (not Session 2 cohort size)
- Daily guidance + escalate sections are read-only text only

## Why this is not Phase 11

Master Phase 11 is an RTL fleet management Dashboard. This card is a single non-interactive reminder.

## Deployment / build requirement

Frontend is a built Docker image (no source bind mount). After UI changes:

1. Commit/push Frontend + docs
2. `docker compose build frontend && docker compose up -d frontend`
3. Owner hard-refresh if needed (`Ctrl+F5`)

## Data limitations

- Day counter = client calendar progress from Session 2 start in ops doc `107`
- Snapshot / Scheduler / Runtime / Shadow may show `نامشخص` (no new public APIs; no operator token)
- Cutover fail-closed: missing evidence → `نامشخص`, never unsafe false
- Never displays `Phase 7 Fully Accepted` / `فاز ۷ کامل شد`

## Limits

- No buttons / forms / mutating HTTP
- No Backend / API / Migration / Celery / Redis / Green API / feature-flag changes
- Auto-refresh every 60 seconds only
- API failure keeps the card visible

## Related docs

- `docs/v67/112-observation-card-visibility-remediation.md`
- `docs/v67/113-observation-card-persian-owner-guide.md`

## Files

- `frontend/src/observation/session2Meta.js`
- `frontend/src/observation/session2Meta.test.js`
- `frontend/src/components/ObservationCountdownCard.jsx`
- `frontend/src/components/ObservationCountdownCard.test.js`
- `frontend/src/pages/Dashboard.jsx` — mount point only
