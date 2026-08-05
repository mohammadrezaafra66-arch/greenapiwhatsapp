import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const cardSrc = readFileSync(join(here, "ObservationCountdownCard.jsx"), "utf8");
const dashSrc = readFileSync(join(here, "..", "pages", "Dashboard.jsx"), "utf8");
const appSrc = readFileSync(join(here, "..", "App.jsx"), "utf8");

test("card source: testid, no actions, no mutating HTTP, no secrets", () => {
  assert.match(cardSrc, /Observation Window/);
  assert.match(cardSrc, /data-testid="observation-countdown-card"/);
  assert.match(cardSrc, /data-has-actions="false"/);
  assert.match(cardSrc, /observation-calendar-disclaimer/);
  assert.match(cardSrc, /Current FleetAccount Count|fleetAccountCountLabel/);
  assert.match(cardSrc, /useState\(null\)/);
  assert.match(cardSrc, /setAnyCutover\(null\)/);
  assert.match(cardSrc, /http\.get\(\s*["']\/fleet\/accounts["']/);
  assert.match(cardSrc, /60_000/);
  assert.match(cardSrc, /clearInterval/);
  assert.doesNotMatch(cardSrc, /<\s*button\b/i);
  assert.doesNotMatch(cardSrc, /\bonClick\s*=/);
  assert.doesNotMatch(cardSrc, /\.post\s*\(/);
  assert.doesNotMatch(cardSrc, /\.put\s*\(/);
  assert.doesNotMatch(cardSrc, /\.patch\s*\(/);
  assert.doesNotMatch(cardSrc, /\.delete\s*\(/);
  assert.doesNotMatch(cardSrc, /X-Fleet-Shadow-Token|operator.token|localStorage|sessionStorage/i);
  assert.doesNotMatch(cardSrc, /Current Cohort Count/);
  assert.doesNotMatch(cardSrc, /Phase 7 Fully Accepted/);
});

test("Dashboard mounts exactly one ObservationCountdownCard before live heading", () => {
  const importMatches = dashSrc.match(/ObservationCountdownCard/g) || [];
  assert.ok(importMatches.length >= 2, "import + JSX usage expected");
  assert.match(dashSrc, /import ObservationCountdownCard from ["'].*ObservationCountdownCard\.jsx["']/);
  const mountCount = (dashSrc.match(/<ObservationCountdownCard\s*\/>/g) || []).length;
  assert.equal(mountCount, 1);
  const cardIdx = dashSrc.indexOf("<ObservationCountdownCard");
  const headingIdx = dashSrc.indexOf("داشبورد زنده");
  assert.ok(cardIdx > 0 && headingIdx > cardIdx, "card must appear before داشبورد زنده");
});

test("App router index route renders Dashboard", () => {
  assert.match(appSrc, /import Dashboard from ["']\.\/pages\/Dashboard\.jsx["']/);
  assert.match(appSrc, /<Route\s+index\s+element=\{<Dashboard\s*\/>\}/);
});
