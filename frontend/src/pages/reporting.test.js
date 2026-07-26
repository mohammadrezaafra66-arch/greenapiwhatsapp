import { test } from "node:test";
import assert from "node:assert";
import {
  TOP_PRODUCTS_RANGE_OPTIONS, MAX_RANGE_DAYS,
  TOP_PRODUCTS_LIMIT_OPTIONS, TOP_PRODUCTS_MAX_LIMIT,
  TOP_PRODUCTS_DEFAULT_DAYS, TOP_PRODUCTS_DEFAULT_LIMIT,
  TOP_PRODUCTS_FILTERS_STORAGE_KEY,
  loadTopProductsFilters,
  normalizeTopProductsFilters,
  saveTopProductsFilters,
} from "./reporting.js";

// ── V49 PART 2 — date-range options honor the real 90-day retention ceiling ───
test("defaults use 30 days / 150 limit", () => {
  assert.equal(TOP_PRODUCTS_DEFAULT_DAYS, 30);
  assert.equal(TOP_PRODUCTS_DEFAULT_LIMIT, 150);
});

test("range options are ascending and each carries a numeric days value + Persian label", () => {
  const values = TOP_PRODUCTS_RANGE_OPTIONS.map((o) => o.value);
  assert.deepEqual(values, [...values].sort((a, b) => a - b)); // strictly ascending
  for (const o of TOP_PRODUCTS_RANGE_OPTIONS) {
    assert.equal(typeof o.value, "number");
    assert.ok(o.value >= 1);
    assert.ok(typeof o.label === "string" && o.label.length > 0);
  }
});

test("range options are exactly 7/14/30/60/90 — the still-valid windows within 90-day retention", () => {
  const values = TOP_PRODUCTS_RANGE_OPTIONS.map((o) => o.value);
  assert.deepEqual(values, [7, 14, 30, 60, 90]);
});

test("no range option exceeds the 90-day retention ceiling (180/365/all-time removed)", () => {
  assert.equal(MAX_RANGE_DAYS, 90);
  for (const o of TOP_PRODUCTS_RANGE_OPTIONS) {
    assert.ok(o.value <= MAX_RANGE_DAYS, `option ${o.value} exceeds ${MAX_RANGE_DAYS}`);
  }
  const values = TOP_PRODUCTS_RANGE_OPTIONS.map((o) => o.value);
  for (const gone of [180, 365, 36500]) {
    assert.ok(!values.includes(gone), `stale option ${gone} must be removed`);
  }
  assert.equal(Math.max(...values), MAX_RANGE_DAYS); // the widest option IS the ceiling
});

test("the default day value is one of the selectable options", () => {
  const values = TOP_PRODUCTS_RANGE_OPTIONS.map((o) => o.value);
  assert.ok(values.includes(TOP_PRODUCTS_DEFAULT_DAYS));
});

// ── V43 PART 2 — product-count limit options (unchanged) ─────────────────────
test("limit options are ascending, keep 50/100/150, and add 100-steps up to 1000", () => {
  assert.deepEqual(TOP_PRODUCTS_LIMIT_OPTIONS,
    [...TOP_PRODUCTS_LIMIT_OPTIONS].sort((a, b) => a - b)); // strictly ascending
  for (const existing of [50, 100, 150]) {
    assert.ok(TOP_PRODUCTS_LIMIT_OPTIONS.includes(existing), `missing existing ${existing}`);
  }
  for (const added of [200, 300, 400, 500, 600, 700, 800, 900, 1000]) {
    assert.ok(TOP_PRODUCTS_LIMIT_OPTIONS.includes(added), `missing added ${added}`);
  }
});

test("no limit option exceeds the backend ceiling of 1000, and the max option IS 1000", () => {
  assert.equal(TOP_PRODUCTS_MAX_LIMIT, 1000);
  for (const n of TOP_PRODUCTS_LIMIT_OPTIONS) {
    assert.ok(n >= 1 && n <= TOP_PRODUCTS_MAX_LIMIT, `option ${n} out of range`);
  }
  assert.equal(Math.max(...TOP_PRODUCTS_LIMIT_OPTIONS), 1000);
});

test("the default limit (150) is one of the selectable options", () => {
  assert.ok(TOP_PRODUCTS_LIMIT_OPTIONS.includes(TOP_PRODUCTS_DEFAULT_LIMIT));
});

// ── persisted top-products filters ───────────────────────────────────────────
function fakeStorage() {
  const data = new Map();
  return {
    getItem: (key) => data.has(key) ? data.get(key) : null,
    setItem: (key, value) => data.set(key, String(value)),
  };
}

test("top-products filters persist and reload from storage", () => {
  const storage = fakeStorage();
  saveTopProductsFilters({ days: 90, limit: 500, source: "group", search: "کولر" }, storage);
  assert.deepEqual(loadTopProductsFilters(storage), {
    days: 90,
    limit: 500,
    source: "group",
    search: "کولر",
  });
  assert.ok(storage.getItem(TOP_PRODUCTS_FILTERS_STORAGE_KEY));
});

test("a persisted range beyond the 90-day options falls back to the default", () => {
  // 365 was a valid option before V49; a stale saved value must no longer be honored.
  assert.deepEqual(normalizeTopProductsFilters({
    days: 365,
    limit: 5000,
    source: "bad",
    search: 123,
  }), {
    days: TOP_PRODUCTS_DEFAULT_DAYS,
    limit: TOP_PRODUCTS_DEFAULT_LIMIT,
    source: "",
    search: "",
  });
});
