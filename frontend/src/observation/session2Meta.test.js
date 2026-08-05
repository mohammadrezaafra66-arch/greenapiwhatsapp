import { test } from "node:test";
import assert from "node:assert/strict";
import {
  SESSION_2_META,
  computeObservationDay,
  resolveObservationStatus,
  statusColor,
  dayLabel,
  observationWarning,
  buildObservationCardModel,
} from "./session2Meta.js";

const START = SESSION_2_META.startedAtUtc;
const T0 = Date.parse(START);

test("Day Unknown when start missing", () => {
  assert.equal(computeObservationDay(null), null);
  assert.equal(dayLabel(null), "Unknown");
  assert.equal(resolveObservationStatus({ day: null }), "WAITING");
  assert.equal(statusColor("WAITING"), "gray");
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
  assert.match(observationWarning(13), /still in progress/);
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
  assert.equal(observationWarning(20), "Observation ready for Completion Audit.");
});

test("INVALID and RESTART_REQUIRED colors", () => {
  assert.equal(resolveObservationStatus({ day: 2, invalid: true }), "INVALID");
  assert.equal(statusColor("INVALID"), "red");
  assert.equal(resolveObservationStatus({ day: 2, restartRequired: true }), "RESTART_REQUIRED");
  assert.equal(statusColor("RESTART_REQUIRED"), "orange");
});

test("card model has no actions and simulation badge", () => {
  const m = buildObservationCardModel({ now: T0 + 1000, cohortCount: 1, snapshotCount: null });
  assert.deepEqual(m.actions, []);
  assert.equal(m.simulationOnly, true);
  assert.equal(m.subtitle, "Session 2");
  assert.equal(m.title, "Observation Window");
  assert.equal(m.cohortCount, 1);
  assert.equal(m.snapshotCount, "Unknown");
  assert.equal(m.live.cutover, "OFF");
  assert.equal(m.live.canary, "OFF");
  assert.equal(m.live.humanContacts, "OFF");
  assert.equal(m.live.scheduler, "Unknown");
});
