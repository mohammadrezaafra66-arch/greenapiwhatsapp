import { test } from "node:test";
import assert from "node:assert";
import { filterByPlatform } from "./platformSwitcherUtils.js";

const items = [
  { id: 1, platform: "whatsapp" },
  { id: 2, platform: "telegram" },
  { id: 3 }, // no platform → treated as whatsapp
];

test("all returns everything", () => {
  assert.equal(filterByPlatform(items, "all").length, 3);
  assert.equal(filterByPlatform(items, null).length, 3);
});

test("whatsapp includes items with no platform", () => {
  const r = filterByPlatform(items, "whatsapp");
  assert.deepEqual(r.map((x) => x.id), [1, 3]);
});

test("telegram only", () => {
  const r = filterByPlatform(items, "telegram");
  assert.deepEqual(r.map((x) => x.id), [2]);
});

test("empty input safe", () => {
  assert.deepEqual(filterByPlatform(null, "telegram"), []);
});
