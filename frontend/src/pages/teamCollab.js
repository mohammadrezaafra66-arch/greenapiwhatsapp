// V30 PART 1 — pure, framework-free helpers for the «همکاری تیمی» (Team Collaboration)
// pages. Kept in a plain .js module (NOT .jsx) so `node --test` can import and unit-test them
// without a DOM/JSX loader — same pattern as src/data/qrAntibanRules.js.
//
// The React page (TeamCollaboration.jsx) imports these for every non-trivial data transform, so
// the transforms are verifiable in isolation (warmth badge mapping, log filtering, assignment
// ceiling, thread-status summary, per-contact ask counter).

// ── warmth badge (mirrors backend warmup_warmth level thresholds) ────────────
export const WARMTH_LEVEL_FA = { high: "بالا", mid: "متوسط", low: "کم" };

// The backend already returns a Persian level string («بالا»/«متوسط»/«کم») + a 0–100 score.
// warmthBadge maps EITHER the level string or a raw score to a {label, cls, level} display token.
export function warmthBadge({ level, score } = {}) {
  let lvl = level;
  if (!lvl && score != null) {
    lvl = score >= 70 ? "بالا" : score >= 40 ? "متوسط" : "کم";
  }
  lvl = lvl || "کم";
  const cls =
    lvl === "بالا"
      ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
      : lvl === "متوسط"
      ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
      : "bg-slate-600/30 text-slate-400 border-slate-600";
  const label = score != null ? `${lvl} (${score})` : lvl;
  return { label, cls, level: lvl };
}

// ── cold-account assignment ceiling (mirrors MAX_COLD_ACCOUNTS_PER_CONTACT = 2) ──
export const MAX_COLD_PER_CONTACT = 2;

export function canAssignCold(currentCount, max = MAX_COLD_PER_CONTACT) {
  return Number(currentCount || 0) < Number(max);
}

// ── client-side log filtering (server filters too; this keeps the UI responsive) ──
export function filterLogEvents(events, { senderInstanceId, coldInstanceId, helperId, eventType } = {}) {
  let out = Array.isArray(events) ? events.slice() : [];
  if (senderInstanceId) out = out.filter((e) => e.sender_instance_id === senderInstanceId);
  if (coldInstanceId) out = out.filter((e) => e.cold_instance_id === coldInstanceId);
  if (helperId) out = out.filter((e) => e.helper_id === helperId);
  if (eventType) out = out.filter((e) => e.event_type === eventType);
  return out;
}

// ── thread-status summary for a cold account (dashboard card) ────────────────
export function threadStatusSummary(cold) {
  const a = Number(cold?.threads_active || 0);
  const p = Number(cold?.threads_paused || 0);
  const d = Number(cold?.threads_done || 0);
  const parts = [];
  if (a) parts.push(`${a} فعال`);
  if (p) parts.push(`${p} متوقف`);
  if (d) parts.push(`${d} تکمیل`);
  return parts.length ? parts.join("، ") : "بدون گفتگو";
}

// ── day-in-cycle label (10-day team cycle) ───────────────────────────────────
export function dayInCycleLabel(dayIndex, cycleDays = 10) {
  const d = Number(dayIndex || 0);
  if (d >= cycleDays) return "دورهٔ ۱۰ روزه تکمیل شد";
  return `روز ${d + 1} از ${cycleDays}`;
}

// ── PART 7 — running ask-request counter, DERIVED from log rows (no stored column) ──
// Count "ask" events per contact (helper_id). Returns a Map-like plain object {helperId: n}.
export function askCountsByContact(events) {
  const out = {};
  for (const e of events || []) {
    if (e.event_type !== "ask") continue;
    const k = e.helper_id;
    if (!k) continue;
    out[k] = (out[k] || 0) + 1;
  }
  return out;
}

// Count "ask" events per sender instance.
export function askCountsBySender(events) {
  const out = {};
  for (const e of events || []) {
    if (e.event_type !== "ask") continue;
    const k = e.sender_instance_id;
    if (!k) continue;
    out[k] = (out[k] || 0) + 1;
  }
  return out;
}

// PART 7 — the Persian "this is ask #N for this contact" sentence.
export function askCountSentence(n) {
  const num = Number(n || 0);
  return `این درخواست شماره ${num} برای این مخاطب است`;
}
