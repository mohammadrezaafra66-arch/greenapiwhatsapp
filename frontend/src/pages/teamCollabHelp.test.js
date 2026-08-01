// V54 — guards the help copy itself. The tooltips are the only documentation a new operator
// sees, so an empty/placeholder/English string is a real defect: it silently leaves an element
// unexplained. These run under `node --test` like the other pure-module tests.
import { test } from "node:test";
import assert from "node:assert/strict";

import { TC_TIPS, OVERVIEW_TIPS, TC_OVERVIEW_HELP } from "./teamCollabHelp.js";

const PERSIAN = /[؀-ۿ]/;

function checkMap(name, map) {
  const keys = Object.keys(map);
  assert.ok(keys.length > 0, `${name} must not be empty`);
  for (const k of keys) {
    const v = map[k];
    assert.equal(typeof v, "string", `${name}.${k} must be a string`);
    assert.ok(v.trim().length >= 20, `${name}.${k} is too short to explain anything`);
    assert.ok(PERSIAN.test(v), `${name}.${k} must be Persian`);
    assert.ok(!/TODO|FIXME|lorem/i.test(v), `${name}.${k} still has placeholder text`);
  }
}

test("every team-collaboration tip is real Persian copy", () => {
  checkMap("TC_TIPS", TC_TIPS);
});

test("every accounts-overview column tip is real Persian copy", () => {
  checkMap("OVERVIEW_TIPS", OVERVIEW_TIPS);
});

test("tips are unique — a duplicated string usually means a wrong key was reused", () => {
  const seen = new Map();
  for (const [k, v] of Object.entries(TC_TIPS)) {
    if (seen.has(v)) {
      assert.fail(`TC_TIPS.${k} duplicates TC_TIPS.${seen.get(v)}`);
    }
    seen.set(v, k);
  }
});

test("the overview help panel covers roles, both step lists and the common mistakes", () => {
  assert.ok(PERSIAN.test(TC_OVERVIEW_HELP.title));
  assert.ok(PERSIAN.test(TC_OVERVIEW_HELP.goal));
  assert.equal(TC_OVERVIEW_HELP.roles.length, 3);
  assert.equal(TC_OVERVIEW_HELP.onceSteps.length, 5);
  assert.equal(TC_OVERVIEW_HELP.autoSteps.length, 2);
  assert.equal(TC_OVERVIEW_HELP.mistakes.length, 3);
  for (const list of [TC_OVERVIEW_HELP.roles, TC_OVERVIEW_HELP.onceSteps,
                      TC_OVERVIEW_HELP.autoSteps, TC_OVERVIEW_HELP.mistakes]) {
    for (const item of list) assert.ok(PERSIAN.test(item), `"${item}" must be Persian`);
  }
});

test("the eligibility tip keeps the «can» vs «is working» distinction", () => {
  // This is the single most misread thing on the overview page — the copy must keep saying it.
  assert.match(OVERVIEW_TIPS.eligible, /می‌تواند/);
  assert.match(OVERVIEW_TIPS.eligible, /کلید/);
});

test("the cold-roster tip keeps the assignment-vs-enrollment distinction", () => {
  assert.match(TC_TIPS.coldRosterSection, /فرق دارد/);
  assert.match(TC_TIPS.coldRosterSection, /عضو/);
});
