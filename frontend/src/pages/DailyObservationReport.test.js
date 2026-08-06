import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const pageSrc = readFileSync(join(here, "DailyObservationReport.jsx"), "utf8");
const appSrc = readFileSync(join(here, "..", "App.jsx"), "utf8");
const layoutSrc = readFileSync(join(here, "..", "components", "Layout.jsx"), "utf8");
const cardSrc = readFileSync(join(here, "..", "components", "ObservationCountdownCard.jsx"), "utf8");
const apiSrc = readFileSync(join(here, "..", "api.js"), "utf8");

test("page has Persian title and owner action", () => {
  assert.match(pageSrc, /گزارش روزانه دوره مشاهده/);
  assert.match(pageSrc, /امروز چه کاری باید انجام دهم؟/);
  assert.match(pageSrc, /Phase 8 همچنان مسدود/);
  assert.doesNotMatch(pageSrc, /Phase 7 Fully Accepted/);
  assert.doesNotMatch(pageSrc, /فاز ۷ کامل شد/);
});

test("page uses ObservationApi GET only and 60s refresh", () => {
  assert.match(pageSrc, /ObservationApi\.report/);
  assert.match(pageSrc, /60_000/);
  assert.match(pageSrc, /abort/);
  assert.match(pageSrc, /document\.hidden/);
  assert.doesNotMatch(pageSrc, /\.post\s*\(/);
  assert.doesNotMatch(pageSrc, /\.put\s*\(/);
  assert.doesNotMatch(pageSrc, /\.patch\s*\(/);
  assert.doesNotMatch(pageSrc, /\.delete\s*\(/);
  assert.doesNotMatch(pageSrc, /X-Fleet-Shadow-Token/);
  assert.doesNotMatch(pageSrc, /localStorage|sessionStorage/);
});

test("timeline and sections exist", () => {
  assert.match(pageSrc, /observation-timeline/);
  assert.match(pageSrc, /snapshot-section/);
  assert.match(pageSrc, /infra-section/);
  assert.match(pageSrc, /safety-section/);
  assert.match(pageSrc, /mismatch-section/);
  assert.match(pageSrc, /findings-section/);
  assert.match(pageSrc, /summary-cards/);
  assert.match(pageSrc, /runtime-evidence-section/);
  assert.match(pageSrc, /static-evidence-section/);
  assert.match(pageSrc, /stop-conditions-section/);
  assert.match(pageSrc, /automated-report-section/);
});

test("route and menu wired", () => {
  assert.match(appSrc, /observation-report/);
  assert.match(appSrc, /DailyObservationReport/);
  assert.match(layoutSrc, /گزارش روزانه مشاهده/);
  assert.match(layoutSrc, /\/observation-report/);
});

test("dashboard card links to full report", () => {
  assert.match(cardSrc, /observation-full-report-link/);
  assert.match(cardSrc, /to="\/observation-report"/);
  assert.match(cardSrc, /مشاهده گزارش روزانه کامل/);
});

test("api client has no shadow token", () => {
  assert.match(apiSrc, /ObservationApi/);
  assert.match(apiSrc, /\/fleet\/observation\/report/);
  assert.doesNotMatch(apiSrc, /X-Fleet-Shadow-Token/);
});
