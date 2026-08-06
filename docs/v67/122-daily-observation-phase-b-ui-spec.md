# V67.1 — Phase B UI Spec

## Route

`/observation-report`

## Menu

`گزارش روزانه مشاهده` under گزارش‌ها و تحلیل

## Page

`DailyObservationReport.jsx` — Persian RTL read-only owner report.

## Dashboard card

Link: `مشاهده گزارش روزانه کامل` → `/observation-report`

## Sections

Header, owner action, summary cards, 14-day timeline (Day 0..14), snapshots, infrastructure, safety, mismatch/evidence, findings.

## Rules

- No recomputation of validity in UI
- Unknown stays نامشخص
- Day 14 never claims Phase 7 Fully Accepted
- Auto-refresh 60s with abort on unmount; pause when tab hidden
