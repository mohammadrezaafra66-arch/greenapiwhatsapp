// V48 — unit tests for the unified accounts-overview pure transforms (node --test).
import { test } from "node:test";
import assert from "node:assert";
import {
  warmthBadge, roleChips, eligibilityInfo, healthInfo, sortRows, filterRows,
  roleMatches, eligMatches, textMatches,
  LINK_WARMUP, LINK_TEAM, LINK_ACCOUNTS,
} from "./accountsOverview.js";

// ── fixtures: one row per role/state combination ──
const HEALTHY = {
  name: "healthy", instance_id: "A1", phone: "9891",
  warmth_score: 80, warmth_level: "بالا", days_connected: 30, incident_total: 0,
  eligible: true, eligibility_reason: "ok", eligibility_override: false, health_score: 1.0,
  role: { mesh: "peer_sender", tc_sender: true, tc_contact_count: 2, tc_cold: false, none: false, in_mesh_recovery: false },
};
const YOUNG = {
  name: "young", instance_id: "B2", phone: "9892",
  warmth_score: 69, warmth_level: "متوسط", days_connected: 9, incident_total: 0,
  eligible: false, eligibility_reason: "too_young", eligibility_override: false, health_score: 1.0,
  role: { mesh: "being_warmed", tc_sender: false, tc_contact_count: 0, tc_cold: false, none: false, in_mesh_recovery: false },
};
const CARDED = {
  name: "carded", instance_id: "C3", phone: "9893",
  warmth_score: 60, warmth_level: "متوسط", days_connected: 21, incident_total: 1,
  eligible: false, eligibility_reason: "recent_incident", eligibility_override: false, health_score: 0.0,
  role: { mesh: "none", tc_sender: false, tc_contact_count: 0, tc_cold: false, none: true, in_mesh_recovery: false },
};
const COLD = {
  name: "cold", instance_id: "D4", phone: "9894",
  warmth_score: 69, warmth_level: "متوسط", days_connected: 30, incident_total: 0,
  eligible: true, eligibility_reason: "ok", eligibility_override: false, health_score: 1.0,
  role: { mesh: "none", tc_sender: false, tc_contact_count: 0, tc_cold: true, none: false, in_mesh_recovery: false },
};
const NONE = {
  name: "none", instance_id: "E5", phone: "9895",
  warmth_score: 37, warmth_level: "کم", days_connected: 2, incident_total: 0,
  eligible: false, eligibility_reason: "too_young", eligibility_override: false, health_score: 1.0,
  role: { mesh: "none", tc_sender: false, tc_contact_count: 0, tc_cold: false, none: true, in_mesh_recovery: false },
};
const OVERRIDE = {
  name: "override", instance_id: "F6", phone: "9896",
  warmth_score: 41, warmth_level: "متوسط", days_connected: 2, incident_total: 0,
  eligible: false, eligibility_reason: "too_young", eligibility_override: true, health_score: 1.0,
  role: { mesh: "none", tc_sender: false, tc_contact_count: 0, tc_cold: false, none: true, in_mesh_recovery: false },
};
const ALL = [HEALTHY, YOUNG, CARDED, COLD, NONE, OVERRIDE];

test("warmthBadge maps level and derives it from score when missing", () => {
  assert.match(warmthBadge({ level: "بالا" }).cls, /brand/);
  assert.match(warmthBadge({ level: "متوسط" }).cls, /amber/);
  assert.match(warmthBadge({ level: "کم" }).cls, /slate/);
  assert.equal(warmthBadge({ score: 85 }).level, "بالا");
  assert.equal(warmthBadge({ score: 50 }).level, "متوسط");
  assert.equal(warmthBadge({ score: 10 }).level, "کم");
});

test("roleChips: peer+TC-sender links to warmup and team pages", () => {
  const chips = roleChips(HEALTHY);
  const keys = chips.map((c) => c.key);
  assert.ok(keys.includes("mesh"));
  assert.ok(keys.includes("tc_sender"));
  assert.equal(chips.find((c) => c.key === "mesh").to, LINK_WARMUP);
  assert.equal(chips.find((c) => c.key === "tc_sender").to, LINK_TEAM);
  assert.match(chips.find((c) => c.key === "tc_sender").label, /2 مخاطب/);
});

test("roleChips: a no-role account shows a single 'no role' chip linking to /accounts", () => {
  const chips = roleChips(NONE);
  assert.equal(chips.length, 1);
  assert.equal(chips[0].key, "none");
  assert.equal(chips[0].to, LINK_ACCOUNTS);
});

test("roleChips: cold account links to team page", () => {
  const chips = roleChips(COLD);
  assert.equal(chips[0].key, "tc_cold");
  assert.equal(chips[0].to, LINK_TEAM);
});

test("eligibilityInfo formats each reason and the override", () => {
  assert.equal(eligibilityInfo(HEALTHY).eligible, true);
  assert.match(eligibilityInfo(HEALTHY).cls, /brand/);
  assert.match(eligibilityInfo(YOUNG).label, /خیلی جدید/);
  assert.match(eligibilityInfo(CARDED).label, /حادثهٔ اخیر/);
  assert.match(eligibilityInfo(OVERRIDE).label, /رد شرط ۱۴روزه/);
  assert.match(eligibilityInfo(OVERRIDE).cls, /rose/);
});

test("healthInfo converts 0..1 to percent with color bands", () => {
  assert.deepEqual({ ...healthInfo(HEALTHY) }, { pct: 100, cls: "text-brand" });
  assert.equal(healthInfo(CARDED).pct, 0);
  assert.match(healthInfo(CARDED).cls, /red/);
});

test("sortRows by warmth descending/ascending is stable and correct", () => {
  const desc = sortRows(ALL, "warmth", "desc").map((r) => r.warmth_score);
  assert.deepEqual(desc, [80, 69, 69, 60, 41, 37]);
  const asc = sortRows(ALL, "warmth", "asc").map((r) => r.warmth_score);
  assert.deepEqual(asc, [37, 41, 60, 69, 69, 80]);
  // stable tie: the two 69s keep their original relative order (YOUNG before COLD).
  const ties = sortRows(ALL, "warmth", "desc").filter((r) => r.warmth_score === 69).map((r) => r.instance_id);
  assert.deepEqual(ties, ["B2", "D4"]);
});

test("sortRows by name and incidents", () => {
  const byInc = sortRows(ALL, "incidents", "desc").map((r) => r.incident_total);
  assert.equal(byInc[0], 1);
  const names = sortRows(ALL, "name", "asc").map((r) => r.name);
  assert.equal(names.length, ALL.length);
});

test("roleMatches classifies each category", () => {
  assert.ok(roleMatches(YOUNG, "mesh"));
  assert.ok(!roleMatches(HEALTHY, "mesh"));
  assert.ok(roleMatches(HEALTHY, "peer"));
  assert.ok(roleMatches(HEALTHY, "tc_sender"));
  assert.ok(roleMatches(COLD, "tc_cold"));
  assert.ok(roleMatches(NONE, "none"));
  assert.ok(roleMatches(HEALTHY, "")); // empty → all
});

test("eligMatches filters eligible / ineligible / override", () => {
  assert.ok(eligMatches(HEALTHY, "eligible"));
  assert.ok(!eligMatches(YOUNG, "eligible"));
  assert.ok(eligMatches(YOUNG, "ineligible"));
  assert.ok(eligMatches(OVERRIDE, "override"));
  assert.ok(!eligMatches(YOUNG, "override"));
});

test("textMatches searches name, instance_id and phone", () => {
  assert.ok(textMatches(HEALTHY, "healthy"));
  assert.ok(textMatches(HEALTHY, "A1"));
  assert.ok(textMatches(HEALTHY, "9891"));
  assert.ok(!textMatches(HEALTHY, "zzz"));
  assert.ok(textMatches(HEALTHY, "")); // empty → all
});

test("filterRows combines role + eligibility + text", () => {
  assert.equal(filterRows(ALL, { role: "peer" }).length, 1);
  assert.equal(filterRows(ALL, { elig: "ineligible" }).length, 4);
  assert.equal(filterRows(ALL, { elig: "override" }).length, 1);
  assert.equal(filterRows(ALL, { role: "tc_cold", elig: "eligible" }).length, 1);
  assert.equal(filterRows(ALL, { q: "carded" }).length, 1);
  assert.equal(filterRows(ALL, {}).length, ALL.length);
});
