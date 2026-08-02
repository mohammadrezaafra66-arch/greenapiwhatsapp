// V60 STEP 1 (PART C-3) — the capacity maths shown to the operator must match the backend's
// real per-account cap. If these drift, the page confidently tells the user the wrong number of
// days, which is how a list gets rushed and a number gets suspended.
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  accountDailyCap, campaignCapacity, capacitySentence, youngAccountNotice,
  YOUNG_ACCOUNT_CAP, YOUNG_ACCOUNT_DAYS,
  accountAgeDays, accountAgeLabel, accountAgeAndCap, capExplanation, neverSentNotice,
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

// ── V60 STEP 2: capacity shared with Team Collaboration ─────────────────────
import { capacityWithTeamCollab, teamCollabNotice } from "./campaignCapacity.js";

const tc = (over = {}) => ({ instance_id: "tc-1", days_active: 0, max_daily_absolute: 200, ...over });

test("an account that is also a TC sender loses that share of its daily cap", () => {
  const cap = capacityWithTeamCollab([tc()], 100, ["tc-1"], 1);
  assert.equal(cap.perAccount[0].cap, 5);
  assert.equal(cap.perAccount[0].remaining, 4);
  assert.equal(cap.perDay, 4);
  assert.equal(cap.anyTeamCollab, true);
});

test("an account not in Team Collaboration keeps its whole cap", () => {
  const cap = capacityWithTeamCollab([tc({ instance_id: "plain" })], 100, ["tc-1"], 1);
  assert.equal(cap.perAccount[0].remaining, 5);
  assert.equal(cap.anyTeamCollab, false);
});

test("the reserved share can never push remaining below zero", () => {
  const cap = capacityWithTeamCollab([tc()], 100, ["tc-1"], 99);
  assert.equal(cap.perAccount[0].remaining, 0);
  assert.equal(cap.perDay, 0);
  assert.equal(cap.days, null);
});

test("days are recomputed from the REMAINING capacity, not the raw cap", () => {
  // three young TC senders: raw would be 15/day → 14 days; real is 12/day → 17 days
  const rows = [tc({ instance_id: "a" }), tc({ instance_id: "b" }), tc({ instance_id: "c" })];
  const cap = capacityWithTeamCollab(rows, 200, ["a", "b", "c"], 1);
  assert.equal(cap.perDay, 12);
  assert.equal(cap.days, 17);
});

test("the TC notice names the accounts and shows remaining out of total", () => {
  const cap = capacityWithTeamCollab([tc({ instance_id: "a", phone: "9048249526" })], 100, ["a"], 1);
  const notice = teamCollabNotice(cap);
  assert.match(notice, /همکاری تیمی/);
  assert.match(notice, /9048249526/);
  assert.match(notice, /4 از 5/);
});

test("no TC notice when no chosen account is a warm-up sender", () => {
  assert.equal(teamCollabNotice(capacityWithTeamCollab([tc()], 100, [], 1)), "");
});

// ── V64: age and cap are two different numbers and must both be named ───────
// The live confusion: the chip showed only «(۵/روز)» — the daily message cap — and it was read
// as "5 days old", while accounts-overview showed 18 days for the very same account. Both were
// right; nothing said which was which. These pin that the chip now carries BOTH, labelled, and
// that the age never leaks into the cap.
const aged = (over = {}) => ({
  instance_id: "770022683809", phone: "9048249526",
  age_days: 18.2, days_active: 0, daily_limit: 5, ever_sent: false, ...over,
});

test("age comes from the API field accounts-overview is built on", () => {
  assert.equal(accountAgeDays(aged()), 18.2);
  assert.equal(accountAgeLabel(aged()), "18 روز");
});

test("an unknown age renders as a dash, never as zero days", () => {
  assert.equal(accountAgeDays(aged({ age_days: null })), null);
  assert.equal(accountAgeLabel(aged({ age_days: null })), "—");
  assert.equal(accountAgeLabel(aged({ age_days: undefined })), "—");
  assert.equal(accountAgeLabel(null), "—");
});

test("the chip names both numbers, so neither can be read as the other", () => {
  const s = accountAgeAndCap(aged());
  assert.match(s, /18 روز/);
  assert.match(s, /5 پیام در روز/);
});

test("the real age NEVER raises the cap — the young-account brake is untouched", () => {
  // 18 days old, but the warm-up counter is 0, so the backend cap of 5 must stand.
  assert.equal(accountDailyCap(aged()), YOUNG_ACCOUNT_CAP);
  assert.equal(accountDailyCap(aged({ age_days: 400 })), YOUNG_ACCOUNT_CAP);
});

test("the contradiction is explained on screen, naming both numbers", () => {
  const msg = capExplanation(aged());
  assert.match(msg, /18 روز/);          // the overview's number
  assert.match(msg, /گرم‌سازی/);         // why the counter is stuck
  assert.match(msg, /5 پیام در روز/);   // the cap that still applies
});

test("a genuinely young account gets the plain young explanation instead", () => {
  const msg = capExplanation(aged({ age_days: 3 }));
  assert.match(msg, new RegExp(`زیر ${YOUNG_ACCOUNT_DAYS} روز`));
});

test("no explanation when the counter has actually advanced past the window", () => {
  assert.equal(capExplanation(aged({ days_active: 30, daily_limit: 30 })), "");
});

test("no explanation when the age is unknown — never invent a reason", () => {
  assert.equal(capExplanation(aged({ age_days: null })), "");
  assert.equal(capExplanation(null), "");
});

test("an instance that has never sent is flagged, whatever its age", () => {
  assert.equal(neverSentNotice(aged({ ever_sent: false })), "بدون سابقه‌ی ارسال");
  assert.equal(neverSentNotice(aged({ ever_sent: true })), "");
});

test("an API that omits ever_sent shows no flag rather than a false one", () => {
  assert.equal(neverSentNotice({ instance_id: "x" }), "");
});
