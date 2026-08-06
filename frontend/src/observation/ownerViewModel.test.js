import { test } from "node:test";
import assert from "node:assert/strict";
import {
  mapOwnerReport,
  STATUS_FA,
  faNum,
  reasonLabel,
  shiftDateUtc,
} from "./ownerViewModel.js";

test("maps PASS FAIL REVIEW INSUFFICIENT Persian labels", () => {
  for (const s of ["PASS", "FAIL", "REVIEW_REQUIRED", "INSUFFICIENT_EVIDENCE"]) {
    const v = mapOwnerReport({
      report: {
        overall_status: s,
        phase7_fully_accepted: false,
        phase8_allowed: false,
        calendar_day_index: 1,
        expected_total_days: 14,
        owner_action_fa: "x",
      },
      timeline: [],
    });
    assert.equal(v.error, null);
    assert.equal(v.report.statusFa, STATUS_FA[s]);
  }
});

test("malformed and unsafe flags rejected", () => {
  assert.equal(mapOwnerReport(null).error, "malformed");
  assert.equal(
    mapOwnerReport({
      report: { overall_status: "PASS", phase7_fully_accepted: true, phase8_allowed: false },
    }).error,
    "unsafe_flags"
  );
});

test("faNum unknown and reason label", () => {
  assert.equal(faNum(null), "نامشخص");
  assert.match(reasonLabel("live_state_missing"), /live_state_missing/);
});

test("shiftDateUtc", () => {
  assert.equal(shiftDateUtc("2026-08-06", -1), "2026-08-05");
});

test("maps evidence bundle and stop conditions without recomputing status", () => {
  const v = mapOwnerReport({
    report: {
      overall_status: "INSUFFICIENT_EVIDENCE",
      phase7_fully_accepted: false,
      phase8_allowed: false,
      evidence_bundle: {
        evidence_version: "v67.owner.daily-observation.evidence.1",
        can_support_daily_pass: false,
        correlation_status: "HEALTHY",
        runtime_items: [],
      },
      static_manifest_status: "MATCH",
      deployed_git_sha: "abc123def456",
      stop_conditions: [{ key: "cutover_true", title_fa: "Cutover", state: "فعال نشده" }],
      automated_report_meta: { schedule_utc: "06:00", schedule_tehran: "09:30" },
    },
    timeline: [],
  });
  assert.equal(v.error, null);
  assert.equal(v.report.overall_status, "INSUFFICIENT_EVIDENCE");
  assert.equal(v.report.evidenceBundle.can_support_daily_pass, false);
  assert.equal(v.report.staticManifestStatus, "MATCH");
  assert.equal(v.report.stopConditions.length, 1);
  assert.equal(v.report.automatedReportMeta.schedule_utc, "06:00");
});
