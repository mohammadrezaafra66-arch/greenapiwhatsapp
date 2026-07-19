import { test } from "node:test";
import assert from "node:assert";
import {
  warmthBadge, canAssignCold, filterLogEvents, threadStatusSummary,
  dayInCycleLabel, askCountsByContact, askCountsBySender, askCountSentence,
  askRunningCounts, MAX_COLD_PER_CONTACT,
} from "./teamCollab.js";

test("warmthBadge maps level string to class", () => {
  assert.equal(warmthBadge({ level: "بالا" }).level, "بالا");
  assert.match(warmthBadge({ level: "بالا" }).cls, /emerald/);
  assert.match(warmthBadge({ level: "متوسط" }).cls, /amber/);
  assert.match(warmthBadge({ level: "کم" }).cls, /slate/);
});

test("warmthBadge derives level from score when level missing", () => {
  assert.equal(warmthBadge({ score: 100 }).level, "بالا");
  assert.equal(warmthBadge({ score: 64 }).level, "متوسط");
  assert.equal(warmthBadge({ score: 18 }).level, "کم");
  assert.equal(warmthBadge({ score: 70 }).level, "بالا"); // threshold
  assert.equal(warmthBadge({ score: 40 }).level, "متوسط"); // threshold
});

test("warmthBadge label includes score when present", () => {
  assert.equal(warmthBadge({ level: "بالا", score: 88 }).label, "بالا (88)");
  assert.equal(warmthBadge({ level: "کم" }).label, "کم");
});

test("canAssignCold respects the ceiling of 2", () => {
  assert.equal(MAX_COLD_PER_CONTACT, 2);
  assert.equal(canAssignCold(0), true);
  assert.equal(canAssignCold(1), true);
  assert.equal(canAssignCold(2), false);
  assert.equal(canAssignCold(3), false);
});

const LOG = [
  { event_type: "ask", sender_instance_id: "S1", cold_instance_id: "C1", helper_id: "H1" },
  { event_type: "ask", sender_instance_id: "S1", cold_instance_id: "C2", helper_id: "H1" },
  { event_type: "reminder", sender_instance_id: "S1", cold_instance_id: "C1", helper_id: "H2" },
  { event_type: "ask", sender_instance_id: "S2", cold_instance_id: "C1", helper_id: "H3" },
  { event_type: "thank_you", sender_instance_id: "S1", cold_instance_id: "C1", helper_id: "H1" },
];

test("filterLogEvents filters by each dimension", () => {
  assert.equal(filterLogEvents(LOG, { senderInstanceId: "S1" }).length, 4);
  assert.equal(filterLogEvents(LOG, { coldInstanceId: "C1" }).length, 4);
  assert.equal(filterLogEvents(LOG, { helperId: "H1" }).length, 3);
  assert.equal(filterLogEvents(LOG, { eventType: "ask" }).length, 3);
  assert.equal(filterLogEvents(LOG, { senderInstanceId: "S1", eventType: "ask" }).length, 2);
  assert.equal(filterLogEvents(LOG, {}).length, 5);
});

test("threadStatusSummary formats counts", () => {
  assert.equal(threadStatusSummary({ threads_active: 3, threads_paused: 1, threads_done: 2 }), "3 فعال، 1 متوقف، 2 تکمیل");
  assert.equal(threadStatusSummary({ threads_active: 0, threads_paused: 0, threads_done: 0 }), "بدون گفتگو");
  assert.equal(threadStatusSummary({ threads_active: 2 }), "2 فعال");
});

test("dayInCycleLabel", () => {
  assert.equal(dayInCycleLabel(0), "روز 1 از 10");
  assert.equal(dayInCycleLabel(9), "روز 10 از 10");
  assert.equal(dayInCycleLabel(10), "دورهٔ ۱۰ روزه تکمیل شد");
  assert.equal(dayInCycleLabel(12), "دورهٔ ۱۰ روزه تکمیل شد");
});

test("askCountsByContact counts only ask events per helper", () => {
  const c = askCountsByContact(LOG);
  assert.equal(c.H1, 2);
  assert.equal(c.H3, 1);
  assert.equal(c.H2, undefined); // reminder is not an ask
});

test("askCountsBySender counts asks per sender", () => {
  const c = askCountsBySender(LOG);
  assert.equal(c.S1, 2);
  assert.equal(c.S2, 1);
});

test("askCountSentence", () => {
  assert.equal(askCountSentence(5), "این درخواست شماره 5 برای این مخاطب است");
});

test("askRunningCounts numbers a contact's asks in chronological order", () => {
  // Provided newest-first; running number must still be 1,2,3 chronologically.
  const evs = [
    { id: "e3", event_type: "ask", helper_id: "H1", created_at: "2026-05-04T12:00:00" },
    { id: "e2", event_type: "ask", helper_id: "H1", created_at: "2026-05-04T11:00:00" },
    { id: "rem", event_type: "reminder", helper_id: "H1", created_at: "2026-05-04T10:30:00" },
    { id: "e1", event_type: "ask", helper_id: "H1", created_at: "2026-05-04T10:00:00" },
    { id: "x1", event_type: "ask", helper_id: "H2", created_at: "2026-05-04T10:15:00" },
  ];
  const r = askRunningCounts(evs);
  assert.equal(r.e1, 1);
  assert.equal(r.e2, 2);
  assert.equal(r.e3, 3);
  assert.equal(r.x1, 1);       // per-contact, independent of H1
  assert.equal(r.rem, undefined); // reminders are not counted
});
