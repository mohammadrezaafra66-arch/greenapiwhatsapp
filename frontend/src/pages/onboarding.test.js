import { test } from "node:test";
import assert from "node:assert";
import {
  GATE_A_HOURS, GATE_B_HOURS, PHASE_CONTENT, phaseContent, faDigits, formatCountdown, STEP_ORDER,
} from "./onboarding.js";

test("gate constants are 24h", () => {
  assert.equal(GATE_A_HOURS, 24);
  assert.equal(GATE_B_HOURS, 24);
});

test("phaseContent maps each phase to its step number and lock state", () => {
  assert.equal(phaseContent("gate_a_wait").step, 1);
  assert.equal(phaseContent("gate_a_wait").locked, true);
  assert.equal(phaseContent("activate_whatsapp").step, 2);
  assert.equal(phaseContent("activate_whatsapp").locked, false);
  assert.equal(phaseContent("gate_b_wait").step, 3);
  assert.equal(phaseContent("gate_b_wait").locked, true);
  assert.equal(phaseContent("connect_green_api").step, 4);
  assert.equal(phaseContent("connect_green_api").locked, false);
  assert.equal(phaseContent("done").step, 4);
});

test("phaseContent unlocked steps carry a single next-action label", () => {
  assert.ok(PHASE_CONTENT.activate_whatsapp.action);
  assert.ok(PHASE_CONTENT.connect_green_api.action);
  // Locked/wait phases expose no action button.
  assert.equal(PHASE_CONTENT.gate_a_wait.action, undefined);
  assert.equal(PHASE_CONTENT.gate_b_wait.action, undefined);
});

test("phaseContent step 4 body hands off to QR + Team Collaboration", () => {
  assert.match(PHASE_CONTENT.connect_green_api.body, /Green API/);
  assert.match(PHASE_CONTENT.connect_green_api.body, /QR/);
  assert.match(PHASE_CONTENT.connect_green_api.body, /همکاری تیمی/);
});

test("phaseContent step 1 body carries the anti-ban real-usage guidance", () => {
  assert.match(PHASE_CONTENT.gate_a_wait.body, /شماره‌های واقعی/);
  assert.match(PHASE_CONTENT.gate_a_wait.body, /خودکار/);
});

test("faDigits converts to Persian numerals", () => {
  assert.equal(faDigits("2026/03/01"), "۲۰۲۶/۰۳/۰۱");
  assert.equal(faDigits(24), "۲۴");
  assert.equal(faDigits(null), "");
});

test("formatCountdown returns empty when unlocked/absent/past", () => {
  assert.equal(formatCountdown(null), "");
  assert.equal(formatCountdown(""), "");
  const past = new Date(Date.UTC(2020, 0, 1)).toISOString();
  assert.equal(formatCountdown(past, Date.UTC(2026, 0, 1)), "");
});

test("formatCountdown shows hours and minutes remaining", () => {
  // now = 2026-03-01T09:00:00Z; unlock 25h30m later.
  const now = Date.UTC(2026, 2, 1, 9, 0, 0);
  const unlock = new Date(now + (25 * 3600 + 30 * 60) * 1000).toISOString();
  const out = formatCountdown(unlock, now);
  assert.match(out, /ساعت/);
  assert.match(out, /دقیقه/);
  assert.match(out, /۲۵/); // 25 hours, Persian digits
});

test("STEP_ORDER is 1..4", () => {
  assert.deepEqual(STEP_ORDER, [1, 2, 3, 4]);
});
