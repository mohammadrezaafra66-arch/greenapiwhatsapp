# V67.1 — Daily Observation UI/UX Acceptance

## Route / navigation

- Route `/observation-report` wired in App  
- Menu label `گزارش روزانه مشاهده`  
- Dashboard card link `مشاهده گزارش روزانه کامل`  
- Nav inventory tests updated for intentional route  

## Owner workflow

- Persian RTL page with status shell (not color-only; technical code shown)  
- Owner Action card near top  
- Summary cards, Timeline 0..14, Snapshot/Infra/Safety/Mismatch/Findings  
- Phase C sections: Runtime evidence, Static Manifest, Stop Conditions, Automated report meta  
- Refresh GET only; 60s interval; abort + skip when tab hidden  
- Malformed / unsafe acceptance flags → Persian fail-closed error  
- No Start/Stop/Restart/Run/POST controls  
- Never displays Phase 7 Fully Accepted  

## Accessibility / responsive

- `dir="rtl"`, aria labels on date/refresh/timeline buttons  
- Responsive grids; sections readable on narrow widths  
- Light/dark utility classes present on status shells  

## Automated report visibility

- Schedule UTC 06:00 / Tehran 09:30 shown  
- Explains no notification and GET-only reconstruction  

## Verdict

UI/UX acceptance **PASS** for Owner Change (non-technical owner can use the page without CLI).
