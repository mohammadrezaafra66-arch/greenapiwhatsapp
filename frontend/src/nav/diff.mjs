// V47 PART 4 (THREAD C) — the "nothing lost" diff between a baseline inventory and the current one.
//
// The hard invariant: every route reachable in the baseline must still be reachable now. A route is
// "reachable" if it is a router route (a real page) — whether it appears as a sidebar leaf, inside a
// pinned/favorites area, or as an in-page TAB on its parent page. A route that leaves the SIDEBAR
// but is still a router route (e.g. a phantom-alias leaf converted to an in-page tab) is allowed and
// reported separately; a route that disappears from the router entirely is a HARD failure.

/** Diff two inventories (baseline, current). Returns a structured result with `ok`. */
export function diffInventory(baseline, current) {
  const bRouter = new Set(baseline.routerRoutes);
  const cRouter = new Set(current.routerRoutes);
  const bNav = new Set(baseline.distinctNavRoutes);
  const cNav = new Set(current.distinctNavRoutes);

  // Router-level: a page that no longer has a route at all is lost.
  const lostRoutes = [...bRouter].filter((r) => !cRouter.has(r)).sort();
  const addedRoutes = [...cRouter].filter((r) => !bRouter.has(r)).sort();

  // Sidebar-level: a route that used to be in the sidebar and is now gone from it.
  const goneFromSidebar = [...bNav].filter((r) => !cNav.has(r)).sort();
  // …split into truly lost (not a router route anymore → HARD failure) vs still-reachable
  // (converted to an in-page tab / folded into a parent page → allowed intentional change).
  const lostSidebarRoutes = goneFromSidebar.filter((r) => !cRouter.has(r));
  const movedOutOfSidebar = goneFromSidebar.filter((r) => cRouter.has(r));

  // Entry-level (label+route): what nav entries were removed / added (renames + dedup + regroup).
  const entryKey = (l) => `${l.to}::${l.label}`;
  const bEntries = new Set(baseline.leaves.map(entryKey));
  const cEntries = new Set(current.leaves.map(entryKey));
  const removedEntries = baseline.leaves.filter((l) => !cEntries.has(entryKey(l)));
  const addedEntries = current.leaves.filter((l) => !bEntries.has(entryKey(l)));

  const ok = lostRoutes.length === 0 && lostSidebarRoutes.length === 0;
  return {
    ok,
    lostRoutes,
    lostSidebarRoutes,
    movedOutOfSidebar,
    addedRoutes,
    removedEntries,
    addedEntries,
  };
}

/** Human-readable diff summary with a PASS/FAIL headline. */
export function formatDiff(d) {
  const lines = [];
  lines.push(d.ok ? "✅ NOTHING LOST — every baseline route is still reachable."
                  : "❌ ROUTE(S) LOST — see below.");
  if (d.lostRoutes.length) lines.push(`  LOST router routes: ${d.lostRoutes.join(", ")}`);
  if (d.lostSidebarRoutes.length)
    lines.push(`  LOST sidebar routes (gone entirely): ${d.lostSidebarRoutes.join(", ")}`);
  if (d.movedOutOfSidebar.length)
    lines.push(`  Moved out of sidebar (now reachable as in-page tab / parent page): ` +
      d.movedOutOfSidebar.join(", "));
  if (d.addedRoutes.length) lines.push(`  New router routes: ${d.addedRoutes.join(", ")}`);
  lines.push(`  Removed nav entries: ${d.removedEntries.length}, added nav entries: ${d.addedEntries.length}`);
  return lines.join("\n");
}
