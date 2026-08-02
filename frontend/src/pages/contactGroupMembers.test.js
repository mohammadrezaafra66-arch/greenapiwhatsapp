// V62 — pins the GET /contacts/ response shape and the member-picker helpers.
//
// The live bug: the dialog stored the whole paginated object and branched on `results.length`.
// On an object that is `undefined`, so BOTH `=== 0` and `> 0` were false and nothing rendered —
// searching appeared to do nothing, and both contact groups stayed empty. These tests make the
// shape explicit so the same mistake cannot come back.
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  extractContacts, totalMatches, excludeExisting, toggleSelected, resultsSummary,
  membersButtonLabel, emptyGroupHint,
} from "./contactGroupMembers.js";

// exactly what GET /contacts/?search=… returns
const paginated = (contacts, total) => ({
  total: total ?? contacts.length, skip: 0, limit: 1000, contacts,
});
const c = (id, name) => ({ id, name, phone: "9890000" + id });

// ── the shape bug itself ────────────────────────────────────────────────────
test("the paginated object yields its contacts array", () => {
  const res = paginated([c(1, "الف"), c(2, "ب")]);
  assert.equal(extractContacts(res).length, 2);
});

test("a bare array still works, so a future API change cannot break the dialog", () => {
  assert.equal(extractContacts([c(1, "الف")]).length, 1);
});

test("junk yields an empty array instead of throwing", () => {
  for (const junk of [null, undefined, {}, 42, "x", { contacts: null }]) {
    assert.deepEqual(extractContacts(junk), []);
  }
});

test("the object itself has no usable length — the exact cause of the silent dialog", () => {
  const res = paginated([c(1, "الف")]);
  assert.equal(res.length, undefined);          // what the old code branched on
  assert.equal(extractContacts(res).length, 1); // what it should have branched on
});

// ── totals ──────────────────────────────────────────────────────────────────
test("total comes from the API when it reports one", () => {
  assert.equal(totalMatches(paginated([c(1, "a"), c(2, "b")], 57)), 57);
});

test("total falls back to the visible count", () => {
  assert.equal(totalMatches([c(1, "a")]), 1);
  assert.equal(totalMatches(null), 0);
});

// ── existing members are filtered out ──────────────────────────────────────
test("contacts already in the group are hidden from results", () => {
  const res = paginated([c(1, "الف"), c(2, "ب"), c(3, "ج")]);
  const fresh = excludeExisting(res, [{ id: 2 }]);
  assert.deepEqual(fresh.map((x) => x.id), [1, 3]);
});

test("id comparison survives string/number mismatch", () => {
  const res = paginated([c("7", "الف")]);
  assert.equal(excludeExisting(res, [{ id: 7 }]).length, 0);
});

test("no members yet means nothing is filtered", () => {
  const res = paginated([c(1, "الف")]);
  assert.equal(excludeExisting(res, []).length, 1);
  assert.equal(excludeExisting(res, null).length, 1);
});

// ── selection ───────────────────────────────────────────────────────────────
test("toggling adds then removes", () => {
  let sel = new Set();
  sel = toggleSelected(sel, "a");
  assert.ok(sel.has("a"));
  sel = toggleSelected(sel, "a");
  assert.ok(!sel.has("a"));
});

test("toggling returns a new Set so React sees the change", () => {
  const sel = new Set(["a"]);
  const next = toggleSelected(sel, "b");
  assert.notEqual(sel, next);
  assert.equal(sel.size, 1);
  assert.equal(next.size, 2);
});

// ── the summary line ────────────────────────────────────────────────────────
test("no matches says so plainly", () => {
  assert.match(resultsSummary(paginated([]), []), /مخاطبی یافت نشد/);
});

test("all matches already in the group is stated, not shown as an empty list", () => {
  const res = paginated([c(1, "الف")]);
  assert.match(resultsSummary(res, [{ id: 1 }]), /همه از قبل عضو/);
});

test("a partial overlap reports how many were hidden", () => {
  const res = paginated([c(1, "الف"), c(2, "ب"), c(3, "ج")]);
  const s = resultsSummary(res, [{ id: 2 }]);
  assert.match(s, /3 نتیجه/);
  assert.match(s, /1 مورد از قبل عضو/);
});

test("a truncated result set shows shown-of-total", () => {
  const res = paginated([c(1, "الف"), c(2, "ب")], 40);
  assert.match(resultsSummary(res, []), /2 از 40 نتیجه/);
});

// ── V63: the button has to name the ADD action ──────────────────────────────
// The dialog was never broken. The card button read «مشاهده اعضا» ("view members"), so an
// operator wanting to ADD members never opened it — they opened «ویرایش», found no search box,
// and reported that the search had vanished. Three times. These pin the wording.
test("the members button names adding, not only viewing", () => {
  const label = membersButtonLabel();
  assert.match(label, /افزودن/);            // the whole point
  assert.ok(!/^مشاهده اعضا$/.test(label));  // the old view-only label must not come back
});

test("an empty group tells the operator where to go next", () => {
  const hint = emptyGroupHint(0);
  assert.notEqual(hint, "");
  assert.ok(hint.includes(membersButtonLabel()),
    "the hint must name the exact button, or it sends people hunting again");
});

test("a group that already has members shows no hint", () => {
  assert.equal(emptyGroupHint(5), "");
  assert.equal(emptyGroupHint(995), "");
});

test("a missing or junk count is treated as empty, so the hint still shows", () => {
  for (const v of [undefined, null, "", NaN, "x"]) {
    assert.notEqual(emptyGroupHint(v), "");
  }
});

test("a string count from the API still counts as non-empty", () => {
  assert.equal(emptyGroupHint("7"), "");
});
