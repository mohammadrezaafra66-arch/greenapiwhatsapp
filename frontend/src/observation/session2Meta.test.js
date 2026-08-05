import { test } from "node:test";
import assert from "node:assert/strict";
import {
  SESSION_2_META,
  CALENDAR_DAY_DISCLAIMER,
  computeObservationDay,
  resolveObservationStatus,
  statusColor,
  dayLabel,
  observationWarning,
  buildObservationCardModel,
  parseFleetAccountsHint,
} from "./session2Meta.js";

const START = SESSION_2_META.startedAtUtc;
const T0 = Date.parse(START);

test("Day Unknown when start missing", () => {
  assert.equal(computeObservationDay(null), null);
  assert.equal(dayLabel(null), "Unknown");
  assert.equal(resolveObservationStatus({ day: null }), "WAITING");
  assert.equal(statusColor("WAITING"), "gray");
});

test("invalid start timestamp yields Unknown day", () => {
  assert.equal(computeObservationDay("not-a-date"), null);
  assert.equal(dayLabel(computeObservationDay("not-a-date")), "Unknown");
});

test("before-start timestamp stays Day 0 not negative", () => {
  assert.equal(computeObservationDay(START, T0 - 60_000), 0);
});

test("Day 0 within first 24h", () => {
  const day = computeObservationDay(START, T0 + 3_600_000);
  assert.equal(day, 0);
  assert.equal(dayLabel(0), "Day 0 of 14");
  assert.equal(resolveObservationStatus({ day: 0 }), "RUNNING");
  assert.equal(statusColor("RUNNING"), "blue");
  assert.match(observationWarning(0), /still in progress/);
  assert.match(observationWarning(0), /Phase 8 is blocked/);
});

test("Day 1 after one full UTC day", () => {
  const day = computeObservationDay(START, T0 + 86_400_000 + 1);
  assert.equal(day, 1);
  assert.equal(dayLabel(1), "Day 1 of 14");
  assert.equal(resolveObservationStatus({ day: 1 }), "RUNNING");
});

test("Day 13 still RUNNING", () => {
  const day = computeObservationDay(START, T0 + 13 * 86_400_000);
  assert.equal(day, 13);
  assert.equal(resolveObservationStatus({ day: 13 }), "RUNNING");
});

test("Day 14 COMPLETED ready for audit only", () => {
  const day = computeObservationDay(START, T0 + 14 * 86_400_000);
  assert.equal(day, 14);
  assert.equal(resolveObservationStatus({ day: 14 }), "COMPLETED");
  assert.equal(statusColor("COMPLETED"), "green");
  assert.equal(observationWarning(14), "Observation ready for Completion Audit.");
  assert.doesNotMatch(observationWarning(14), /Fully Accepted/i);
});

test("Day 20 still COMPLETED (audit phrase only)", () => {
  const day = computeObservationDay(START, T0 + 20 * 86_400_000);
  assert.equal(day, 20);
  assert.equal(resolveObservationStatus({ day: 20 }), "COMPLETED");
  assert.doesNotMatch(observationWarning(20), /Fully Accepted/i);
});

test("INVALID and RESTART_REQUIRED colors", () => {
  assert.equal(resolveObservationStatus({ day: 2, invalid: true }), "INVALID");
  assert.equal(statusColor("INVALID"), "red");
  assert.equal(resolveObservationStatus({ day: 2, restartRequired: true }), "RESTART_REQUIRED");
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

test("card model fail-closed cutover and FleetAccount label", () => {
  const unknown = buildObservationCardModel({ now: T0 + 1000, cutover: null, fleetAccountCount: null });
  assert.equal(unknown.live.cutover, "Unknown");
  assert.equal(unknown.fleetAccountCount, "Unknown");
  assert.equal(unknown.fleetAccountCountLabel, "Current FleetAccount Count");
  assert.equal(unknown.disclaimer, CALENDAR_DAY_DISCLAIMER);
  assert.deepEqual(unknown.actions, []);

  const off = buildObservationCardModel({ now: T0 + 1000, cutover: false, fleetAccountCount: 0 });
  assert.equal(off.live.cutover, "OFF");
  assert.equal(off.fleetAccountCount, 0);

  const on = buildObservationCardModel({ now: T0 + 1000, cutover: true, fleetAccountCount: 1 });
  assert.equal(on.live.cutover, "ON");
  assert.equal(on.fleetAccountCount, 1);
});
