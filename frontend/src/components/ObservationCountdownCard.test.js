import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  buildObservationCardModel,
  SESSION_2_META,
  DAILY_ACTION_TITLE,
  OWNER_NO_CHANGE,
  CALENDAR_DAY_DISCLAIMER,
} from "../observation/session2Meta.js";

const here = dirname(fileURLToPath(import.meta.url));
const cardSrc = readFileSync(join(here, "ObservationCountdownCard.jsx"), "utf8");
const dashSrc = readFileSync(join(here, "..", "pages", "Dashboard.jsx"), "utf8");
const appSrc = readFileSync(join(here, "..", "App.jsx"), "utf8");
const metaSrc = readFileSync(join(here, "..", "observation", "session2Meta.js"), "utf8");

const T0 = Date.parse(SESSION_2_META.startedAtUtc);

test("card source: Persian titles, no actions, no mutating HTTP, no secrets", () => {
  assert.match(cardSrc, /دوره مشاهده ۱۴ روزه/);
  assert.match(cardSrc, /data-testid="observation-countdown-card"/);
  assert.match(cardSrc, /data-has-actions="false"/);
  assert.match(cardSrc, /observation-calendar-disclaimer/);
  assert.match(cardSrc, /observation-daily-action/);
  assert.match(cardSrc, /observation-owner-duty/);
  assert.match(cardSrc, /observation-owner-no-change/);
  assert.match(cardSrc, /fleetAccountCountLabel/);
  assert.match(cardSrc, /useState\(null\)/);
  assert.match(cardSrc, /setAnyCutover\(null\)/);
  assert.match(cardSrc, /http\.get\(\s*["']\/fleet\/accounts["']/);
  assert.match(cardSrc, /60_000/);
  assert.match(cardSrc, /clearInterval/);
  assert.equal((cardSrc.match(/setInterval/g) || []).length, 1);
  assert.doesNotMatch(cardSrc, /<\s*button\b/i);
  assert.doesNotMatch(cardSrc, /\bonClick\s*=/);
  assert.doesNotMatch(cardSrc, /\.post\s*\(/);
  assert.doesNotMatch(cardSrc, /\.put\s*\(/);
  assert.doesNotMatch(cardSrc, /\.patch\s*\(/);
  assert.doesNotMatch(cardSrc, /\.delete\s*\(/);
  assert.doesNotMatch(cardSrc, /X-Fleet-Shadow-Token|operator.token|localStorage|sessionStorage/i);
  assert.doesNotMatch(cardSrc, /Observation Window/);
  assert.doesNotMatch(cardSrc, /Simulation Only/);
  assert.doesNotMatch(cardSrc, /\bUnknown\b/);
  assert.doesNotMatch(cardSrc, /Day \d+ of 14/);
  assert.doesNotMatch(cardSrc, /Phase 7 Fully Accepted/);
  assert.doesNotMatch(cardSrc, /Current Cohort Count/);
});

test("card model Persian UX strings required by owner guide", () => {
  const m = buildObservationCardModel({ now: T0 + 1000, cutover: null, fleetAccountCount: null });
  assert.equal(m.title, "دوره مشاهده ۱۴ روزه");
  assert.equal(m.dailyActionTitle, DAILY_ACTION_TITLE);
  assert.match(m.ownerDailyDuty, /۰۹:۳۰/);
  assert.equal(m.ownerNoChange, OWNER_NO_CHANGE);
  assert.equal(m.disclaimer, CALENDAR_DAY_DISCLAIMER);
  assert.match(m.warning, /Phase 8 نباید شروع شود/);
  assert.equal(m.live.cutover, "نامشخص");
  assert.equal(m.fleetAccountCount, "نامشخص");
  assert.doesNotMatch(m.dayLabel, /Day /);
  assert.doesNotMatch(JSON.stringify(m), /\bUnknown\b/);
});

test("meta source keeps Persian unknown and session meta", () => {
  assert.match(metaSrc, /SESSION_2_META/);
  assert.match(metaSrc, /نامشخص/);
  assert.doesNotMatch(metaSrc, /["'`]Phase 7 Fully Accepted["'`]/);
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
