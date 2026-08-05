/**
 * V67.1 — Session 2 observation reminder metadata (frontend-only).
 * Source of start/run_id: ops docs 107 (not a new backend API).
 * Day index = full UTC days elapsed since official CELERY start (Day 0 until 24h elapses).
 */

export const SESSION_2_META = Object.freeze({
  sessionLabel: "Session 2",
  startedAtUtc: "2026-08-05T19:13:46.331651Z",
  runId: "9197e53f-4a25-404f-92b8-ad8a8d5e6acf",
  targetDays: 14,
  simulationOnly: true,
});

/** @typedef {"WAITING"|"RUNNING"|"COMPLETED"|"INVALID"|"RESTART_REQUIRED"} ObservationStatus */

export const STATUS_COLORS = Object.freeze({
  WAITING: "gray",
  RUNNING: "blue",
  COMPLETED: "green",
  INVALID: "red",
  RESTART_REQUIRED: "orange",
});

/**
 * @param {string|null|undefined} startedAtUtc ISO timestamp
 * @param {Date|number|string} [now]
 * @returns {number|null} day index (0..) or null if unknown
 */
export function computeObservationDay(startedAtUtc, now = Date.now()) {
  if (!startedAtUtc) return null;
  const startMs = Date.parse(startedAtUtc);
  if (Number.isNaN(startMs)) return null;
  const nowMs = typeof now === "number" ? now : Date.parse(now);
  if (Number.isNaN(nowMs)) return null;
  if (nowMs < startMs) return 0;
  return Math.floor((nowMs - startMs) / 86_400_000);
}

/**
 * @param {{ day: number|null, sessionActive?: boolean, invalid?: boolean, restartRequired?: boolean }} p
 * @returns {ObservationStatus}
 */
export function resolveObservationStatus({
  day,
  sessionActive = true,
  invalid = false,
  restartRequired = false,
}) {
  if (restartRequired) return "RESTART_REQUIRED";
  if (invalid) return "INVALID";
  if (!sessionActive || day == null) return "WAITING";
  if (day >= 14) return "COMPLETED";
  return "RUNNING";
}

/**
 * @param {ObservationStatus} status
 * @returns {"gray"|"blue"|"green"|"red"|"orange"}
 */
export function statusColor(status) {
  return STATUS_COLORS[status] || "gray";
}

/**
 * @param {number|null} day
 * @returns {string}
 */
export function dayLabel(day) {
  if (day == null || Number.isNaN(day)) return "Unknown";
  return `Day ${day} of 14`;
}

/**
 * Warning copy — never claims Phase 7 Fully Accepted.
 * @param {number|null} day
 * @returns {string}
 */
export function observationWarning(day) {
  if (day == null || Number.isNaN(day)) {
    return "Observation day is unknown. Phase 8 is blocked.";
  }
  if (day < 14) {
    return "Observation is still in progress. Phase 8 is blocked.";
  }
  return "Observation ready for Completion Audit.";
}

/**
 * @param {string} isoUtc
 * @returns {string}
 */
export function formatTehranFromUtc(isoUtc) {
  if (!isoUtc) return "Unknown";
  const d = new Date(isoUtc);
  if (Number.isNaN(d.getTime())) return "Unknown";
  try {
    return new Intl.DateTimeFormat("en-GB", {
      timeZone: "Asia/Tehran",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(d) + " IRST";
  } catch {
    return "Unknown";
  }
}

/**
 * Build card view-model (pure; no network).
 * @param {object} opts
 */
export function buildObservationCardModel(opts = {}) {
  const {
    startedAtUtc = SESSION_2_META.startedAtUtc,
    runId = SESSION_2_META.runId,
    now = Date.now(),
    sessionActive = true,
    invalid = false,
    restartRequired = false,
    cohortCount = null,
    snapshotCount = null,
    scheduler = null,
    runtime = null,
    shadow = null,
    cutover = false,
    canary = false,
    humanContacts = false,
  } = opts;

  const day = computeObservationDay(startedAtUtc, now);
  const status = resolveObservationStatus({ day, sessionActive, invalid, restartRequired });
  const display = (v) => (v == null || v === "" ? "Unknown" : v);

  return {
    title: "Observation Window",
    subtitle: SESSION_2_META.sessionLabel,
    day,
    dayLabel: dayLabel(day),
    status,
    statusColor: statusColor(status),
    warning: observationWarning(day),
    simulationOnly: true,
    currentSession: SESSION_2_META.sessionLabel,
    currentDay: day == null ? "Unknown" : String(day),
    startedAtUtc: startedAtUtc || "Unknown",
    startedAtTehran: formatTehranFromUtc(startedAtUtc),
    runId: runId || "Unknown",
    cohortCount: display(cohortCount),
    snapshotCount: display(snapshotCount),
    live: {
      scheduler: display(scheduler === true ? "ON" : scheduler === false ? "OFF" : null),
      runtime: display(runtime === true ? "ON" : runtime === false ? "OFF" : null),
      shadow: display(shadow === true ? "ON" : shadow === false ? "OFF" : null),
      cutover: cutover === true ? "ON" : "OFF",
      canary: canary === true ? "ON" : "OFF",
      humanContacts: humanContacts === true ? "ON" : "OFF",
    },
    // Explicit: no action affordances in the model
    actions: [],
  };
}
