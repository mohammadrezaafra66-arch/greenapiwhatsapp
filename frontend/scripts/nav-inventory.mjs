// V47 PART 3/4 (THREAD C) — nav-inventory CLI.
//
//   node scripts/nav-inventory.mjs               → print the current inventory as JSON
//   node scripts/nav-inventory.mjs --write-baseline  → write src/nav/nav-baseline.json (PART 3)
//   node scripts/nav-inventory.mjs --diff        → diff current vs the saved baseline (PART 4)
//
// The baseline is the pre-reorg snapshot. The diff asserts the "nothing lost" invariant: every
// route present in the baseline must still be reachable now. Exits non-zero if a route disappeared.
import { writeFileSync, readFileSync } from "node:fs";
import { currentInventory } from "../src/nav/inventory.mjs";
import { diffInventory, formatDiff } from "../src/nav/diff.mjs";

const BASELINE_URL = new URL("../src/nav/nav-baseline.json", import.meta.url);

const arg = process.argv[2] || "";

if (arg === "--write-baseline") {
  const inv = currentInventory();
  writeFileSync(BASELINE_URL, JSON.stringify(inv, null, 2) + "\n", "utf8");
  console.log(`baseline written: ${inv.counts.distinctNavRoutes} distinct sidebar routes, ` +
    `${inv.counts.routerRoutes} router routes, ${inv.counts.duplicateRoutes} multi-label routes.`);
} else if (arg === "--diff") {
  const baseline = JSON.parse(readFileSync(BASELINE_URL, "utf8"));
  const current = currentInventory();
  const d = diffInventory(baseline, current);
  console.log(formatDiff(d));
  process.exit(d.ok ? 0 : 1);
} else {
  console.log(JSON.stringify(currentInventory(), null, 2));
}
