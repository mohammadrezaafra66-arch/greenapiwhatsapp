import { test } from "node:test";
import assert from "node:assert/strict";
import {
  SESSION_2_META,
  CALENDAR_DAY_DISCLAIMER,
  DAILY_ACTION_TITLE,
  OWNER_DAILY_DUTY,
  OWNER_NO_CHANGE,
  computeObservationDay,
  isBeforeObservationStart,
  resolveObservationStatus,
  statusColor,
  statusLabelFa,
  dayLabel,
  faNum,
  observationWarning,
  buildObservationCardModel,
  parseFleetAccountsHint,
} from "./session2Meta.js";

const START = SESSION_2_META.startedAtUtc;
const T0 = Date.parse(START);

test("Day Unknown when start missing", () => {
  assert.equal(computeObservationDay(null), null);
  assert.equal(dayLabel(null), "روز فعلی نامشخص است");
  assert.equal(resolveObservationStatus({ day: null }), "WAITING");
  assert.equal(statusColor("WAITING"), "gray");
  assert.equal(statusLabelFa("WAITING"), "در انتظار شروع");
});

test("invalid start timestamp yields Unknown day", () => {
  assert.equal(computeObservationDay("not-a-date"), null);
  assert.equal(dayLabel(computeObservationDay("not-a-date")), "روز فعلی نامشخص است");
});

test("before-start is not a positive day and shows not-started label", () => {
  assert.equal(isBeforeObservationStart(START, T0 - 60_000), true);
  assert.equal(computeObservationDay(START, T0 - 60_000), null);
  assert.equal(dayLabel(null, { beforeStart: true }), "دوره مشاهده هنوز شروع نشده است");
  assert.equal(
    resolveObservationStatus({ day: null, beforeStart: true }),
    "WAITING"
  );
});

test("Day 0 within first 24h", () => {
  const day = computeObservationDay(START, T0 + 3_600_000);
  assert.equal(day, 0);
  assert.equal(dayLabel(0), `روز ${faNum(0)} از ۱۴`);
  assert.equal(resolveObservationStatus({ day: 0 }), "RUNNING");
  assert.equal(statusLabelFa("RUNNING"), "در حال مشاهده");
  assert.equal(statusColor("RUNNING"), "blue");
  assert.match(observationWarning(0), /این دوره هنوز ادامه دارد/);
  assert.match(observationWarning(0), /Phase 8 نباید شروع شود/);
});

test("Day 1 after one full UTC day", () => {
  const day = computeObservationDay(START, T0 + 86_400_000 + 1);
  assert.equal(day, 1);
  assert.equal(dayLabel(1), `روز ${faNum(1)} از ۱۴`);
  assert.equal(resolveObservationStatus({ day: 1 }), "RUNNING");
});

test("Day 13 still RUNNING", () => {
  const day = computeObservationDay(START, T0 + 13 * 86_400_000);
  assert.equal(day, 13);
  assert.equal(dayLabel(13), `روز ${faNum(13)} از ۱۴`);
  assert.equal(resolveObservationStatus({ day: 13 }), "RUNNING");
});

test("Day 14 COMPLETED ready for audit only", () => {
  const day = computeObservationDay(START, T0 + 14 * 86_400_000);
  assert.equal(day, 14);
  assert.equal(dayLabel(14), `روز ${faNum(14)} از ۱۴`);
  assert.equal(resolveObservationStatus({ day: 14 }), "COMPLETED");
  assert.equal(statusLabelFa("COMPLETED"), "آماده ممیزی نهایی");
  assert.equal(statusColor("COMPLETED"), "green");
  assert.match(observationWarning(14), /ممیزی نهایی/);
  assert.doesNotMatch(observationWarning(14), /Fully Accepted/i);
  assert.doesNotMatch(observationWarning(14), /فاز ۷ کامل شد/);
});

test("Day 20 still COMPLETED (audit phrase only)", () => {
  const day = computeObservationDay(START, T0 + 20 * 86_400_000);
  assert.equal(day, 20);
  assert.equal(resolveObservationStatus({ day: 20 }), "COMPLETED");
  assert.doesNotMatch(observationWarning(20), /Fully Accepted/i);
  assert.doesNotMatch(observationWarning(20), /فاز ۷ کامل شد/);
  const model = buildObservationCardModel({ now: T0 + 20 * 86_400_000 });
  assert.doesNotMatch(model.warning, /Fully Accepted/i);
  assert.match(model.progressHeadline, /آماده ممیزی نهایی/);
});

test("INVALID and RESTART_REQUIRED Persian labels", () => {
  assert.equal(resolveObservationStatus({ day: 2, invalid: true }), "INVALID");
  assert.equal(statusLabelFa("INVALID"), "نامعتبر");
  assert.equal(statusColor("INVALID"), "red");
  assert.equal(resolveObservationStatus({ day: 2, restartRequired: true }), "RESTART_REQUIRED");
  assert.equal(statusLabelFa("RESTART_REQUIRED"), "نیازمند شروع مجدد");
  assert.equal(statusColor("RESTART_REQUIRED"), "orange");
});

test("parseFleetAccountsHint success zero rows", () => {
  assert.deepEqual(parseFleetAccountsHint([]), { fleetAccountCount: 0, anyCutover: false });
});

test("parseFleetAccountsHint one row cutover false", () => {
  assert.deepEqual(parseFleetAccountsHint([{ cutover: false }]), {
    fleetAccountCount: 1,
    anyCutover: false,
  });
});

test("parseFleetAccountsHint one row cutover true", () => {
  assert.deepEqual(parseFleetAccountsHint([{ cutover: true }]), {
    fleetAccountCount: 1,
    anyCutover: true,
  });
});

test("parseFleetAccountsHint malformed -> nulls", () => {
  assert.deepEqual(parseFleetAccountsHint({ rows: [] }), {
    fleetAccountCount: null,
    anyCutover: null,
  });
  assert.deepEqual(parseFleetAccountsHint(null), {
    fleetAccountCount: null,
    anyCutover: null,
  });
});

test("Persian card model: fail-closed, labels, owner guide, no English UI leftovers", () => {
  const unknown = buildObservationCardModel({
    now: T0 + 1000,
    cutover: null,
    fleetAccountCount: null,
  });
  assert.equal(unknown.title, "دوره مشاهده ۱۴ روزه");
  assert.equal(unknown.simulationBadge, "فقط شبیه‌سازی و مشاهده");
  assert.equal(unknown.dayLabel, `روز ${faNum(0)} از ۱۴`);
  assert.equal(unknown.statusLabel, "در حال مشاهده");
  assert.equal(unknown.live.cutover, "نامشخص");
  assert.equal(unknown.fleetAccountCount, "نامشخص");
  assert.equal(unknown.fleetAccountCountLabel, "تعداد حساب‌های ناوگان");
  assert.equal(unknown.disclaimer, CALENDAR_DAY_DISCLAIMER);
  assert.equal(unknown.dailyActionTitle, DAILY_ACTION_TITLE);
  assert.match(unknown.ownerDailyDuty, /۰۹:۳۰/);
  assert.equal(unknown.ownerNoChange, OWNER_NO_CHANGE);
  assert.match(OWNER_DAILY_DUTY, /۰۹:۳۰/);
  assert.deepEqual(unknown.actions, []);
  assert.doesNotMatch(JSON.stringify(unknown), /Observation Window/);
  assert.doesNotMatch(JSON.stringify(unknown), /Day \d+ of 14/);
  assert.doesNotMatch(JSON.stringify(unknown), /Simulation Only/);
  assert.doesNotMatch(JSON.stringify(unknown), /\bUnknown\b/);
  assert.doesNotMatch(JSON.stringify(unknown), /Phase 7 Fully Accepted/);

  const off = buildObservationCardModel({ now: T0 + 1000, cutover: false, fleetAccountCount: 0 });
  assert.equal(off.live.cutover, "خاموش");
  assert.equal(off.fleetAccountCount, faNum(0));
  assert.equal(off.live.canary, "شروع نشده");
  assert.equal(off.live.humanContacts, "شروع نشده");

  const on = buildObservationCardModel({ now: T0 + 1000, cutover: true, fleetAccountCount: 1 });
  assert.equal(on.live.cutover, "روشن — هشدار");
  assert.equal(on.fleetAccountCount, faNum(1));
});
