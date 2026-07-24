// V48 — re-run the V47 automated nothing-lost diff to prove the new unified overview page is an
// INTENTIONAL ADDITION and not a regression: nothing that was reachable before is lost, and the
// only newly-reachable route is `/accounts-overview`.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { currentInventory } from "./inventory.mjs";
import { diffInventory } from "./diff.mjs";

const baseline = JSON.parse(readFileSync(new URL("./nav-baseline.json", import.meta.url), "utf8"));
const current = currentInventory();

test("nothing lost — every pre-existing route is still reachable after adding the overview", () => {
  const d = diffInventory(baseline, current);
  assert.ok(d.ok, "the nothing-lost invariant must still hold");
  assert.deepEqual(d.lostRoutes, []);
  assert.deepEqual(d.lostSidebarRoutes, []);
  for (const r of baseline.routerRoutes) {
    assert.ok(current.routerRoutes.includes(r), `route disappeared: ${r}`);
  }
});

test("the overview is counted as the single intentional new route", () => {
  const d = diffInventory(baseline, current);
  assert.deepEqual(d.addedRoutes, ["/accounts-overview"]);
});

test("the overview route is both a real router route and a sidebar leaf", () => {
  assert.ok(current.routerRoutes.includes("/accounts-overview"), "missing router route");
  assert.ok(current.distinctNavRoutes.includes("/accounts-overview"), "missing sidebar leaf");
  // and it introduces no dangling links (sidebar↔router stay fully consistent).
  assert.deepEqual(current.routesInNavNotRouter, []);
  assert.deepEqual(current.routerRoutesNotInSidebar, []);
});
