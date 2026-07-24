// V47 PART 4 (THREAD C) — the reorganized nav matches the APPROVED structure and loses nothing.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { currentInventory, parseRoutes } from "./inventory.mjs";
import { diffInventory } from "./diff.mjs";

const baseline = JSON.parse(readFileSync(new URL("./nav-baseline.json", import.meta.url), "utf8"));
const current = currentInventory();

// The approved grouping from the ui-research prototype (STEP 2), by group label → ordered routes.
const APPROVED = [
  ["ارسال و کمپین", ["/campaigns", "/wa-collections", "/send-queue", "/templates", "/button-auto-replies"]],
  ["مخاطبان و سرنخ‌ها", ["/contacts", "/contact-groups", "/groups", "/blacklist", "/active-contacts"]],
  ["گفتگوها", ["/inbox", "/journals", "/keyword-rules", "/group-monitoring", "/calls"]],
  ["استوری و محتوا", ["/statuses", "/status-scheduler", "/advertising-links", "/content", "/files"]],
  ["شماره‌ها", ["/onboarding", "/accounts", "/telegram-accounts", "/account-schedules", "/partner-instances"]],
  ["سلامت و ضدمسدودی", ["/protection", "/warmup", "/team-collaboration"]],
  ["گزارش‌ها و تحلیل", ["/reporting", "/products"]],
  ["تنظیمات", ["/ai-keys", "/ai-settings", "/own-numbers", "/join-links", "/capabilities"]],
];

test("every approved group renders exactly its expected items, in order", () => {
  const byLabel = Object.fromEntries(current.groups.map((g) => [g.label, g.leaves.map((l) => l.to)]));
  for (const [label, routes] of APPROVED) {
    assert.ok(byLabel[label], `missing group: ${label}`);
    assert.deepEqual(byLabel[label], routes, `group "${label}" items differ from approved`);
  }
  // No unexpected extra groups.
  assert.equal(current.groups.length, APPROVED.length);
});

test("NOTHING LOST — every baseline route is still reachable after the reorg", () => {
  const d = diffInventory(baseline, current);
  assert.ok(d.ok, "the nothing-lost invariant failed");
  assert.deepEqual(d.lostRoutes, []);
  assert.deepEqual(d.lostSidebarRoutes, []);
  // Every baseline router route is still a router route (no page dropped).
  for (const r of baseline.routerRoutes) assert.ok(current.routerRoutes.includes(r), `lost route ${r}`);
  // Route count is preserved (regroup/rename only).
  assert.equal(current.counts.distinctNavRoutes, baseline.counts.distinctNavRoutes);
  assert.equal(current.counts.routerRoutes, baseline.counts.routerRoutes);
});

test("the ONLY intentional entry changes are the dedup + the 3 phantom-alias removals", () => {
  const d = diffInventory(baseline, current);
  const removed = d.removedEntries.map((e) => `${e.to}::${e.label}`).sort();
  const added = d.addedEntries.map((e) => `${e.to}::${e.label}`).sort();
  assert.deepEqual(removed, [
    "/campaigns::بازده کمپین (ROI)",              // phantom alias → now a tab in /campaigns
    "/reporting::بهترین ساعت ارسال",              // phantom alias → already a tab in /reporting
    "/reporting::شماره‌های اضطراری",              // phantom alias → already a tab in /reporting
    "/wa-collections::ارسال گروهی",               // duplicate leaf (removed)
    "/wa-collections::مجموعه‌های گروهی",          // duplicate leaf (removed)
  ].sort());
  assert.deepEqual(added, ["/wa-collections::ارسال گروهی / مجموعه‌ها"]); // the single unified entry
});

test("the /wa-collections duplicate is gone (each route now appears once in the sidebar)", () => {
  assert.equal(current.counts.duplicateRoutes, 0);
  const counts = {};
  for (const l of current.leaves) counts[l.to] = (counts[l.to] || 0) + 1;
  assert.equal(counts["/wa-collections"], 1);
});

test("pinned/favorites rail points only at real, existing routes", () => {
  const src = readFileSync(new URL("../components/Layout.jsx", import.meta.url), "utf8");
  const block = src.slice(src.indexOf("const PINNED = ["));
  const pinnedBlock = block.slice(0, block.indexOf("];"));
  const routes = [...pinnedBlock.matchAll(/to:\s*"([^"]+)"/g)].map((m) => m[1]);
  assert.ok(routes.length >= 5, "expected a pinned rail with the approved favorites");
  const appSrc = readFileSync(new URL("../App.jsx", import.meta.url), "utf8");
  const router = new Set(parseRoutes(appSrc));
  for (const r of routes) assert.ok(router.has(r), `pinned route ${r} is not a real route`);
});
