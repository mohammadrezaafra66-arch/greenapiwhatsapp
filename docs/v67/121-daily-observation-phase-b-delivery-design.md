# V67.1 — Phase B Delivery Design

## Choice

Sanitized unauthenticated GET adapter (same pattern as Dashboard stats / fleet accounts list):

`GET /api/v1/fleet/observation/report?date=YYYY-MM-DD&session=session-2&include_timeline=true`

## Why

- App has no app-wide login; Dashboard already uses unauthenticated GETs.
- Shadow operator APIs require `X-Fleet-Shadow-Token` — **forbidden** in browser.
- Adapter calls `DailyObservationReportService.build_owner_payload` only — no parallel validator/aggregator.

## Security

- GET only
- No token in response
- No phone / raw message / secrets
- Account ids masked (8 chars) when present
- Date bounded to Session 2 window / not future
- Errors sanitized (`report_unavailable`, `invalid_date`)
- `phase7_fully_accepted` / `phase8_allowed` forced false

## Not

Product Control Plane API. Not Phase 11. Not Shadow operator surface.
