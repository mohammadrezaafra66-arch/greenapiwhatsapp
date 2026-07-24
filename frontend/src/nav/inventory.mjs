// V47 PART 3/4 (THREAD C) — automated navigation inventory.
//
// Parses the ACTUAL source of the sidebar nav tree (components/Layout.jsx → `const NAV`) and the
// router (App.jsx → <Route> elements) into a structured inventory, so "which routes are reachable"
// is a repeatable, testable fact — not a manual reading. PART 3 snapshots this as a pre-reorg
// baseline; PART 4 re-runs it and diffs against that baseline to PROVE no route was lost.
//
// Pure string parsing (no bundler/JSX eval), deliberately simple and line-oriented to match the
// stable shape of these two files. Reused by the baseline builder, the diff, and their tests.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

/**
 * Parse the `const NAV = [ ... ]` tree from Layout.jsx source.
 * Returns { groups:[{label,icon,leaves:[{group,label,to}]}], leaves:[{group,label,to}] }.
 * A top-level leaf (e.g. Dashboard) has group=null. Separators are ignored.
 */
export function parseNavTree(src) {
  const lines = src.split(/\r?\n/);
  let inNav = false;
  let currentGroup = null;
  const groups = [];
  const leaves = [];
  for (const raw of lines) {
    const line = raw;
    if (!inNav) {
      if (line.includes("const NAV = [")) inNav = true;
      continue;
    }
    const trimmed = line.trim();
    if (trimmed === "];") break; // end of NAV

    // Group header: `label: "X", icon: "Y", children: [`
    const gh = line.match(/label:\s*"([^"]+)",\s*icon:\s*"([^"]*)",\s*children:/);
    if (gh) {
      currentGroup = gh[1];
      groups.push({ label: gh[1], icon: gh[2], leaves: [] });
      continue;
    }
    // End of a group's children array → back to top level.
    if (trimmed === "]," || trimmed === "]") {
      currentGroup = null;
      continue;
    }
    // A leaf: any object line carrying a `to: "..."`. Label may appear before or after `to`.
    const to = line.match(/to:\s*"([^"]+)"/);
    if (to) {
      const lbl = line.match(/label:\s*"([^"]+)"/);
      const leaf = { group: currentGroup, label: lbl ? lbl[1] : null, to: to[1] };
      leaves.push(leaf);
      if (currentGroup) {
        const g = groups[groups.length - 1];
        if (g && g.label === currentGroup) g.leaves.push(leaf);
      }
    }
  }
  return { groups, leaves };
}

/**
 * Parse every route path from App.jsx <Route> elements. The `index` route normalizes to "/";
 * the catch-all `path="*"` is excluded (it is not a real page). Returns an array of paths.
 */
export function parseRoutes(src) {
  const routes = [];
  if (/<Route\s+index\b/.test(src)) routes.push("/");
  const re = /<Route\s+path="([^"]+)"/g;
  let m;
  while ((m = re.exec(src)) !== null) {
    if (m[1] === "*") continue;
    routes.push("/" + m[1].replace(/^\//, ""));
  }
  return routes;
}

/** Build the full structured inventory from the two source strings. */
export function buildInventory(layoutSrc, appSrc) {
  const { groups, leaves } = parseNavTree(layoutSrc);
  const routerRoutes = [...new Set(parseRoutes(appSrc))].sort();
  const distinctNavRoutes = [...new Set(leaves.map((l) => l.to))].sort();

  // Routes referenced by more than one nav ENTRY: the intentional /wa-collections duplicate and the
  // phantom-alias leaves (extra labels pointing at an existing route's page).
  const byRoute = {};
  for (const l of leaves) (byRoute[l.to] ||= []).push(l.label);
  const duplicates = Object.entries(byRoute)
    .filter(([, ls]) => ls.length > 1)
    .map(([to, labels]) => ({ to, labels }))
    .sort((a, b) => a.to.localeCompare(b.to));

  const routesInNavNotRouter = distinctNavRoutes.filter((r) => !routerRoutes.includes(r));
  const routerRoutesNotInSidebar = routerRoutes.filter((r) => !distinctNavRoutes.includes(r));

  return {
    generatedFrom: "components/Layout.jsx (NAV) + App.jsx (routes)",
    groups,
    leaves,
    distinctNavRoutes,
    routerRoutes,
    duplicates,
    routesInNavNotRouter,
    routerRoutesNotInSidebar,
    counts: {
      distinctNavRoutes: distinctNavRoutes.length,
      routerRoutes: routerRoutes.length,
      navLeafEntries: leaves.length,
      duplicateRoutes: duplicates.length,
    },
  };
}

/** Read the two live source files (relative to this module) and return their text. */
export function loadSources() {
  const here = fileURLToPath(new URL(".", import.meta.url)); // .../src/nav/
  const layoutSrc = readFileSync(new URL("../components/Layout.jsx", import.meta.url), "utf8");
  const appSrc = readFileSync(new URL("../App.jsx", import.meta.url), "utf8");
  return { layoutSrc, appSrc, here };
}

/** Convenience: build the inventory straight from the live source files. */
export function currentInventory() {
  const { layoutSrc, appSrc } = loadSources();
  return buildInventory(layoutSrc, appSrc);
}
