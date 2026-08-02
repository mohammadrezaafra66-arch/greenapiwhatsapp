// V63 — pins the product-pool picker helpers.
//
// The trap this guards: ticking N products while «تعداد محصول در هر پیام» is also N produces
// NO variety at all — every recipient still gets an identical message. That is a silent no-op
// of the whole feature, so it has to be said on screen, not discovered after a send.
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  extractProducts, totalProducts, brandOptions, togglePooled, isPooled,
  priceLabel, poolSummary, poolVarietyWarning,
} from "./productPool.js";

// exactly what GET /reporting/products-table returns
const paged = (items, total, brands) => ({
  total: total ?? items.length, skip: 0, limit: 20, items,
  brands: brands ?? ["یونیوا", "سامسونگ"],
});
const p = (id, name, price) => ({ id, name, price, price_formatted: price?.toLocaleString("en-US") });

// ── response shape ──────────────────────────────────────────────────────────
test("the paginated object yields its items", () => {
  assert.equal(extractProducts(paged([p("1", "الف", 100), p("2", "ب", 200)])).length, 2);
});

test("a bare array still works", () => {
  assert.equal(extractProducts([p("1", "الف", 100)]).length, 1);
});

test("junk yields an empty list instead of throwing", () => {
  for (const junk of [null, undefined, {}, 42, "x", { items: null }]) {
    assert.deepEqual(extractProducts(junk), []);
  }
});

test("total comes from the API, else from what we can see", () => {
  assert.equal(totalProducts(paged([p("1", "a", 1)], 109)), 109);
  assert.equal(totalProducts([p("1", "a", 1)]), 1);
  assert.equal(totalProducts(null), 0);
});

test("brands are read for the filter, and missing brands are not fatal", () => {
  assert.deepEqual(brandOptions(paged([], 0, ["یونیوا"])), ["یونیوا"]);
  assert.deepEqual(brandOptions({}), []);
  assert.deepEqual(brandOptions(null), []);
});

// ── selection ───────────────────────────────────────────────────────────────
test("toggling adds then removes", () => {
  let pool = togglePooled([], "a");
  assert.deepEqual(pool, ["a"]);
  pool = togglePooled(pool, "a");
  assert.deepEqual(pool, []);
});

test("toggling returns a new array so React sees the change", () => {
  const pool = ["a"];
  const next = togglePooled(pool, "b");
  assert.notEqual(pool, next);
  assert.equal(pool.length, 1);
  assert.equal(next.length, 2);
});

test("selection order is preserved, because the backend draws in caller order", () => {
  let pool = [];
  for (const id of ["c", "a", "b"]) pool = togglePooled(pool, id);
  assert.deepEqual(pool, ["c", "a", "b"]);
});

test("id comparison survives string/number mismatch", () => {
  assert.ok(isPooled(["7"], 7));
  assert.ok(isPooled([7], "7"));
  assert.deepEqual(togglePooled([7], "7"), []);
});

// ── price rendering ─────────────────────────────────────────────────────────
test("a formatted price from the API is used as-is", () => {
  assert.match(priceLabel({ price_formatted: "82,400,000" }), /82,400,000 تومان/);
});

test("a raw number is formatted", () => {
  assert.match(priceLabel({ price: 82400000 }), /82,400,000 تومان/);
});

test("no price says so rather than rendering zero tomans", () => {
  assert.equal(priceLabel({ price: null }), "بدون قیمت");
  assert.equal(priceLabel({ price: 0 }), "بدون قیمت");
  assert.equal(priceLabel({}), "بدون قیمت");
});

// ── the summary sentence ────────────────────────────────────────────────────
test("an empty pool states plainly that nothing changes", () => {
  const s = poolSummary([], 3);
  assert.match(s, /هیچ محصولی انتخاب نشده/);
  assert.match(s, /مثل قبل/);
});

test("a real pool explains BOTH variety and per-contact stability", () => {
  const s = poolSummary(["a", "b", "c", "d", "e"], 2);
  assert.match(s, /5 محصول/);
  assert.match(s, /2 محصول تصادفی/);
  assert.match(s, /همان مخاطب همیشه همان محصولات/);
});

// ── the silent no-op this feature can fall into ─────────────────────────────
test("a pool no bigger than the per-message count is called out as producing no variety", () => {
  assert.match(poolSummary(["a", "b", "c"], 3), /تنوعی ایجاد نمی‌شود/);
  assert.notEqual(poolVarietyWarning(["a", "b", "c"], 3), "");
  assert.notEqual(poolVarietyWarning(["a", "b"], 3), "");
});

test("a pool larger than the per-message count raises no warning", () => {
  assert.equal(poolVarietyWarning(["a", "b", "c", "d"], 3), "");
});

test("an empty pool is not warned about — it is the documented default", () => {
  assert.equal(poolVarietyWarning([], 3), "");
});

test("the warning names both numbers so the fix is obvious", () => {
  const w = poolVarietyWarning(["a", "b"], 4);
  assert.match(w, /4/);
  assert.match(w, /2 محصول/);
});

test("a junk per-message count does not produce a nonsense sentence", () => {
  for (const bad of [null, undefined, 0, -3, "x"]) {
    assert.doesNotThrow(() => poolSummary(["a", "b"], bad));
    assert.doesNotThrow(() => poolVarietyWarning(["a", "b"], bad));
  }
});
