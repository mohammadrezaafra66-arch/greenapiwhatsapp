// V43 — pure, testable filter options for the «جدول محصولات پر تکرار» (top-products) tab.
//
// Shared between Reporting.jsx (renders the <select> dropdowns) and reporting.test.js so the exact
// option lists + defaults are unit-tested without needing to parse JSX. UI labels are Persian/RTL;
// values are the numbers sent verbatim as the backend `days` / `limit` query params.

// V49 PART 2 — the product report is retained for 90 days (product_mention_logs is purged after 90
// days; see backend PRODUCT_MENTION_RETENTION_DAYS). The date-range («بازه») picker therefore stops
// at 90: the earlier V43 options of 180 / 365 / "all time" were removed because no window wider than
// 90 days can EVER return more real history — those options only implied history that has already
// been purged. The still-valid 7 / 14 / 30 / 60 / 90 options are kept as they were.
export const MAX_RANGE_DAYS = 90;

export const TOP_PRODUCTS_RANGE_OPTIONS = [
  { value: 7, label: "۷ روز" },
  { value: 14, label: "۱۴ روز" },
  { value: 30, label: "۳۰ روز" },
  { value: 60, label: "۶۰ روز" },
  { value: 90, label: "۹۰ روز" },
];

// The defaults the tab loads with — 30 days (the original V43 default), well within the 90-day window.
export const TOP_PRODUCTS_DEFAULT_DAYS = 30;
export const TOP_PRODUCTS_DEFAULT_LIMIT = 150;

// The maximum count the backend honors (its top-products clamp ceiling). Options never exceed it.
export const TOP_PRODUCTS_MAX_LIMIT = 1000;

// V43 PART 2 — product-count («تعداد») options, ascending. 50/100/150 are the previously-existing
// options (150 stays the default); 200…1000 in 100-unit steps are the additive new ones. Purely
// additive, capped at the backend's 1000 ceiling.
export const TOP_PRODUCTS_LIMIT_OPTIONS = [
  50, 100, 150, 200, 300, 400, 500, 600, 700, 800, 900, 1000,
];

export const TOP_PRODUCTS_FILTERS_STORAGE_KEY = "afrakala_reporting_top_products_filters";

const SOURCE_OPTIONS = new Set(["", "pv", "group", "status"]);

function normalizeNumber(value, allowed, fallback) {
  const n = Number(value);
  return allowed.includes(n) ? n : fallback;
}

export function normalizeTopProductsFilters(raw = {}) {
  const days = normalizeNumber(
    raw.days,
    TOP_PRODUCTS_RANGE_OPTIONS.map((o) => o.value),
    TOP_PRODUCTS_DEFAULT_DAYS,
  );
  const limit = normalizeNumber(raw.limit, TOP_PRODUCTS_LIMIT_OPTIONS, TOP_PRODUCTS_DEFAULT_LIMIT);
  const source = SOURCE_OPTIONS.has(raw.source) ? raw.source : "";
  const search = typeof raw.search === "string" ? raw.search : "";
  return { days, limit, source, search };
}

export function loadTopProductsFilters(storage = globalThis?.localStorage) {
  if (!storage) return normalizeTopProductsFilters();
  try {
    const raw = storage.getItem(TOP_PRODUCTS_FILTERS_STORAGE_KEY);
    return normalizeTopProductsFilters(raw ? JSON.parse(raw) : {});
  } catch {
    return normalizeTopProductsFilters();
  }
}

export function saveTopProductsFilters(filters, storage = globalThis?.localStorage) {
  if (!storage) return;
  try {
    storage.setItem(
      TOP_PRODUCTS_FILTERS_STORAGE_KEY,
      JSON.stringify(normalizeTopProductsFilters(filters)),
    );
  } catch {
    // Ignore private-mode/quota failures; filters can still work for the current session.
  }
}
