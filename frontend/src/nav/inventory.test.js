// V47 PART 3 (THREAD C) — the automated navigation inventory is correct and matches the baseline.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { parseNavTree, parseRoutes, buildInventory, currentInventory } from "./inventory.mjs";

const baseline = JSON.parse(
  readFileSync(new URL("./nav-baseline.json", import.meta.url), "utf8"));

test("parseNavTree extracts groups and leaves with group association", () => {
  const src = `
const NAV = [
  { label: "داشبورد", to: "/", icon: "🏠", end: true },
  {
    label: "ارسال پیام", icon: "📤", children: [
      { to: "/campaigns", label: "کمپین‌ها" },
      { to: "/send-queue", label: "صف ارسال", badgeKey: "queue" },
    ],
  },
];
`;
  const { groups, leaves } = parseNavTree(src);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].label, "ارسال پیام");
  assert.equal(groups[0].leaves.length, 2);
  // top-level Dashboard leaf has no group
  const dash = leaves.find((l) => l.to === "/");
  assert.equal(dash.group, null);
  const camp = leaves.find((l) => l.to === "/campaigns");
  assert.equal(camp.group, "ارسال پیام");
});

test("parseRoutes captures index as '/' and excludes the catch-all", () => {
  const src = `
    <Route index element={<Dashboard />} />
    <Route path="accounts" element={<Accounts />} />
    <Route path="wa-collections" element={<WaCollections />} />
    <Route path="*" element={<div/>} />
  `;
  const routes = parseRoutes(src);
  assert.ok(routes.includes("/"));
  assert.ok(routes.includes("/accounts"));
  assert.ok(routes.includes("/wa-collections"));
  assert.ok(!routes.includes("/*"));
});

test("every current sidebar route maps to a router route and vice versa", () => {
  const inv = currentInventory();
  assert.deepEqual(inv.routesInNavNotRouter, [], "a sidebar leaf points at a non-existent route");
  assert.deepEqual(inv.routerRoutesNotInSidebar, [], "a router route is unreachable from the sidebar");
});

test("baseline snapshot records the confirmed structure (36 routes, 1 dup, 3 phantom aliases)", () => {
  // 34 from the research + own-numbers + active-contacts (V45) = 36 live distinct routes.
  assert.equal(baseline.counts.distinctNavRoutes, 36);
  assert.equal(baseline.counts.routerRoutes, 36);
  // Multi-label routes: /wa-collections (the duplicate) + /reporting & /campaigns (phantom aliases).
  const byRoute = Object.fromEntries(baseline.duplicates.map((d) => [d.to, d.labels]));
  assert.ok(byRoute["/wa-collections"] && byRoute["/wa-collections"].length === 2);   // 1 duplicate
  assert.ok(byRoute["/reporting"] && byRoute["/reporting"].length === 3);             // 2 phantom + primary
  assert.ok(byRoute["/campaigns"] && byRoute["/campaigns"].length === 2);             // 1 phantom + primary
  // Total extra entries beyond distinct routes = 1 dup + 3 phantom = 4.
  assert.equal(baseline.counts.navLeafEntries - baseline.counts.distinctNavRoutes, 4);
});

test("the saved baseline equals a freshly-built inventory (snapshot is current)", () => {
  const fresh = buildInventory(
    readFileSync(new URL("../components/Layout.jsx", import.meta.url), "utf8"),
    readFileSync(new URL("../App.jsx", import.meta.url), "utf8"));
  assert.deepEqual(fresh.distinctNavRoutes, baseline.distinctNavRoutes);
  assert.deepEqual(fresh.routerRoutes, baseline.routerRoutes);
});
