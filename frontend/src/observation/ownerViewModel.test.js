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
