import { test } from "node:test";
import assert from "node:assert";
import {
  TOP_PRODUCTS_RANGE_OPTIONS, ALL_TIME_DAYS,
  TOP_PRODUCTS_LIMIT_OPTIONS, TOP_PRODUCTS_MAX_LIMIT,
  TOP_PRODUCTS_DEFAULT_DAYS, TOP_PRODUCTS_DEFAULT_LIMIT,
} from "./reporting.js";

// ── V43 PART 1 — date-range options ──────────────────────────────────────────
test("defaults are unchanged (30 days / 150 limit)", () => {
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

test("range options keep the previously-existing 7/30/90 and add 14/60/180/365 + all-time", () => {
  const values = TOP_PRODUCTS_RANGE_OPTIONS.map((o) => o.value);
  for (const existing of [7, 30, 90]) assert.ok(values.includes(existing), `missing existing ${existing}`);
  for (const added of [14, 60, 180, 365]) assert.ok(values.includes(added), `missing added ${added}`);
  assert.ok(values.includes(ALL_TIME_DAYS), "missing all-time option");
});

test("all-time sentinel is a large day count the backend treats as unbounded", () => {
  assert.equal(ALL_TIME_DAYS, 36500);
  // it is the last (largest) option, and its label is the Persian «all time».
  const last = TOP_PRODUCTS_RANGE_OPTIONS[TOP_PRODUCTS_RANGE_OPTIONS.length - 1];
  assert.equal(last.value, ALL_TIME_DAYS);
  assert.equal(last.label, "همه‌ی زمان‌ها");
});

test("the default day value is one of the selectable options", () => {
  const values = TOP_PRODUCTS_RANGE_OPTIONS.map((o) => o.value);
  assert.ok(values.includes(TOP_PRODUCTS_DEFAULT_DAYS));
});

// ── V43 PART 2 — product-count limit options ─────────────────────────────────
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
