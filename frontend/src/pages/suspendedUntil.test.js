// V57 — the «آزاد می‌شود» label. A `suspended` badge alone reads like a dead end; the expiry is
// what turns it into "wait N days" instead of "rescan the QR". Green API supplies it as
// getWaSettings.suspendedUntil (epoch); the real observed value was 2026-08-08T14:37:35Z.
import { test } from "node:test";
import assert from "node:assert/strict";

import { suspendedUntilFa } from "./accountsOverview.js";

const REAL = "2026-08-08T14:37:35";      // the live value from instance 770022695753
const NOW = new Date("2026-08-01T15:00:00Z");

test("empty input renders nothing rather than a broken label", () => {
  assert.equal(suspendedUntilFa(null), "");
  assert.equal(suspendedUntilFa(undefined), "");
  assert.equal(suspendedUntilFa(""), "");
});

test("garbage renders nothing rather than Invalid Date", () => {
  assert.equal(suspendedUntilFa("not-a-date"), "");
});

test("a future expiry shows days remaining", () => {
  const s = suspendedUntilFa(REAL, NOW);
  assert.match(s, /روز دیگر/);
  assert.ok(!s.includes("Invalid"));
});

test("under a day switches to hours so it never rounds to «0 روز دیگر»", () => {
  const soon = new Date(NOW.getTime() + 5 * 3600000).toISOString();
  assert.match(suspendedUntilFa(soon, NOW), /ساعت دیگر/);
});

test("a past expiry is labelled as elapsed, not as negative time", () => {
  const past = new Date(NOW.getTime() - 3600000).toISOString();
  const s = suspendedUntilFa(past, NOW);
  assert.match(s, /سپری شده/);
  assert.ok(!s.includes("-"));
});

test("the label carries a Persian date, not a raw ISO string", () => {
  const s = suspendedUntilFa(REAL, NOW);
  assert.ok(!s.includes("2026-08-08"));
  assert.match(s, /[۰-۹0-9]/);
});
