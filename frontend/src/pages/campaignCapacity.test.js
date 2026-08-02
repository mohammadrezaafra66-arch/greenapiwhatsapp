// V60 STEP 1 (PART C-3) — the capacity maths shown to the operator must match the backend's
// real per-account cap. If these drift, the page confidently tells the user the wrong number of
// days, which is how a list gets rushed and a number gets suspended.
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  accountDailyCap, campaignCapacity, capacitySentence, youngAccountNotice,
  YOUNG_ACCOUNT_CAP, YOUNG_ACCOUNT_DAYS,
} from "./campaignCapacity.js";

const young = (over = {}) => ({ instance_id: "y", days_active: 0, max_daily_absolute: 200, ...over });
const mature = (over = {}) => ({ instance_id: "m", days_active: 30, max_daily_absolute: 200, ...over });

test("an account under 10 days is capped at 5 whatever its configured maximum", () => {
  for (const d of [0, 1, 5, 9]) {
    assert.equal(accountDailyCap(young({ days_active: d })), YOUNG_ACCOUNT_CAP);
  }
});

test("the cap opens up at exactly 10 days", () => {
  assert.equal(accountDailyCap(young({ days_active: 9 })), 5);
  assert.ok(accountDailyCap(young({ days_active: 10 })) > 5);
});

test("max_daily_absolute can lower the young cap but never raise it", () => {
  assert.equal(accountDailyCap(young({ max_daily_absolute: 3 })), 3);
  assert.equal(accountDailyCap(young({ max_daily_absolute: 9999 })), 5);
});

test("a mature account earns capacity from real engagement", () => {
  const quiet = accountDailyCap(mature());
  const engaged = accountDailyCap(mature({ received_yesterday: 20, quick_replies_yesterday: 4 }));
  assert.ok(engaged > quiet);
});

test("nothing exceeds the absolute maximum", () => {
  const a = mature({ days_active: 365, received_yesterday: 9999, quick_replies_yesterday: 9999, max_daily_absolute: 40 });
  assert.equal(accountDailyCap(a), 40);
});

test("missing or malformed rows do not throw or produce NaN", () => {
  assert.equal(accountDailyCap(null), 0);
  assert.equal(accountDailyCap({}), YOUNG_ACCOUNT_CAP);
  assert.ok(Number.isFinite(accountDailyCap({ days_active: "x", max_daily_absolute: "y" })));
});

test("the live fleet: three young senders give 15/day and 200 contacts take 14 days", () => {
  const cap = campaignCapacity([young(), young(), young()], 200);
  assert.equal(cap.accounts, 3);
  assert.equal(cap.perDay, 15);
  assert.equal(cap.days, 14);
  assert.equal(cap.anyYoung, true);
});

test("days rounds UP — a partial day still needs a whole day", () => {
  assert.equal(campaignCapacity([young()], 6).days, 2);   // 6 / 5 → 2
  assert.equal(campaignCapacity([young()], 5).days, 1);
});

test("zero capacity reports null days, never Infinity", () => {
  const cap = campaignCapacity([young({ max_daily_absolute: 0 })], 30);
  assert.equal(cap.perDay, 0);
  assert.equal(cap.days, null);
  assert.match(capacitySentence(cap, 30), /ارسال انجام نمی‌شود/);
});

test("no accounts selected says so plainly", () => {
  assert.match(capacitySentence(campaignCapacity([], 30), 30), /هنوز حسابی انتخاب نشده/);
});

test("the sentence states accounts, per-day and total days", () => {
  const s = capacitySentence(campaignCapacity([young(), young(), young()], 200), 200);
  assert.match(s, /3 حساب/);
  assert.match(s, /15 پیام در روز/);
  assert.match(s, /14 روز/);
});

test("with no contact count the sentence still reports daily capacity", () => {
  const s = capacitySentence(campaignCapacity([young()], 0), 0);
  assert.match(s, /5 پیام در روز/);
  assert.ok(!s.includes("روز تمام"));
});

test("an authoritative daily_limit from the API wins over the local formula", () => {
  // GET /accounts/ returns computed_daily_limit as `daily_limit`; trusting it keeps the page
  // and the backend from ever disagreeing about how many messages an account may send.
  assert.equal(accountDailyCap({ daily_limit: 5, days_active: 365 }), 5);
  assert.equal(accountDailyCap({ daily_limit: 42, days_active: 0 }), 42);
  assert.equal(accountDailyCap({ daily_limit: 0, days_active: 365 }), 0);
});

test("the local formula is used only when daily_limit is absent", () => {
  assert.equal(accountDailyCap({ days_active: 0 }), YOUNG_ACCOUNT_CAP);
  assert.equal(accountDailyCap({ daily_limit: null, days_active: 0 }), YOUNG_ACCOUNT_CAP);
});

test("the young-account notice explains the cap cannot be raised by settings", () => {
  const notice = youngAccountNotice(campaignCapacity([young(), mature()], 50));
  assert.match(notice, new RegExp(`${YOUNG_ACCOUNT_DAYS} روز`));
  assert.match(notice, /سقف روزانه/);
  assert.match(notice, /برداشته نمی‌شود/);
});

test("no notice when every chosen account is mature", () => {
  assert.equal(youngAccountNotice(campaignCapacity([mature(), mature()], 50)), "");
});
