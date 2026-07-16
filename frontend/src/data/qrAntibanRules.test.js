// V22 — verifies the QR-screen anti-ban rules content (runs via `node --test`, no extra deps).
// The rules module is pure data, so it imports cleanly outside the Vite/React runtime.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  QR_ANTIBAN_TITLE, QR_ANTIBAN_HEADER, QR_ANTIBAN_RULES,
} from "./qrAntibanRules.js";

test("title mentions blocking prevention before scan", () => {
  assert.match(QR_ANTIBAN_TITLE, /قبل از اسکن/);
  assert.match(QR_ANTIBAN_TITLE, /بلاک/);
  assert.match(QR_ANTIBAN_HEADER, /قبل از اسکن/);
});

test("there are exactly 6 rules", () => {
  assert.equal(QR_ANTIBAN_RULES.length, 6);
});

test("rule ۱ is the 24-hour wait, present and emphasized", () => {
  const first = QR_ANTIBAN_RULES[0];
  assert.equal(first.n, "۱");
  assert.equal(first.emphasized, true);            // most-important rule is highlighted
  assert.match(first.title, /۲۴ ساعت/);
  assert.match(first.title, /مهم‌ترین قانون/);
  assert.match(first.body, /اتصال زودهنگام/);
  // exactly one rule is emphasized (the 24h rule)
  assert.equal(QR_ANTIBAN_RULES.filter((r) => r.emphasized).length, 1);
});

test("only pre-scan / scan-moment rules — no sending-behavior rules", () => {
  const blob = QR_ANTIBAN_RULES.map((r) => r.title + " " + r.body).join(" ");
  // pre-scan topics present
  assert.match(blob, /پروفایل/);          // complete profile
  assert.match(blob, /وب‌واتساپ|دسکتاپ/); // no extra devices
  assert.match(blob, /سیم‌کارت/);          // aged/non-sequential SIM
  // no post-connection sending-behavior topics leaked in
  assert.doesNotMatch(blob, /کمپین|ارسال انبوه|نرخ ارسال/);
});

test("rule ۵ text is complete (no truncated word)", () => {
  assert.match(QR_ANTIBAN_RULES[4].body, /بلاک می‌شوند/);
});
