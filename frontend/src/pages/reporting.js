// V43 — pure, testable filter options for the «جدول محصولات پر تکرار» (top-products) tab.
//
// Shared between Reporting.jsx (renders the <select> dropdowns) and reporting.test.js so the exact
// option lists + defaults are unit-tested without needing to parse JSX. UI labels are Persian/RTL;
// values are the numbers sent verbatim as the backend `days` / `limit` query params.

// "All time" sentinel for the date-range («بازه») picker. The backend cutoff is
// `now - timedelta(days=days)` with no upper clamp, so a very large day count is an effectively
// unbounded window — no special backend sentinel handling is required.
export const ALL_TIME_DAYS = 36500; // ~100 years

// V43 PART 1 — date-range options, ascending. 30 stays the default (unchanged). 7/30/90 are the
// previously-existing options; 14/60/180/365 + "all time" are the additive new ones.
export const TOP_PRODUCTS_RANGE_OPTIONS = [
  { value: 7, label: "۷ روز" },
  { value: 14, label: "۱۴ روز" },
  { value: 30, label: "۳۰ روز" },
  { value: 60, label: "۶۰ روز" },
  { value: 90, label: "۹۰ روز" },
  { value: 180, label: "۱۸۰ روز" },
  { value: 365, label: "۳۶۵ روز" },
  { value: ALL_TIME_DAYS, label: "همه‌ی زمان‌ها" },
];

// The defaults the tab loads with — MUST stay unchanged (guardrail 2).
export const TOP_PRODUCTS_DEFAULT_DAYS = 30;
export const TOP_PRODUCTS_DEFAULT_LIMIT = 150;
