import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(here, "ObservationCountdownCard.jsx"), "utf8");

test("card source has no action buttons or mutating HTTP verbs", () => {
  assert.match(src, /Observation Window/);
  assert.match(src, /data-has-actions="false"/);
  assert.doesNotMatch(src, /<\s*button\b/i);
  assert.doesNotMatch(src, /\bonClick\s*=/);
  assert.doesNotMatch(src, /\.post\s*\(/);
  assert.doesNotMatch(src, /\.put\s*\(/);
  assert.doesNotMatch(src, /\.patch\s*\(/);
  assert.doesNotMatch(src, /\.delete\s*\(/);
  assert.doesNotMatch(src, /Enable|Disable|Restart|Retry|Execute/);
  assert.match(src, /http\.get\(\s*["']\/fleet\/accounts["']/);
  assert.match(src, /60_000/);
});
