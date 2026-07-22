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

// ── V39 PART 4 — sender-eligibility override (14-day rule) ────────────────────
// The «رد شرط ۱۴روزه» badge label shown next to a sender running on a deliberate override.
export const OVERRIDE_BADGE_FA = "رد شرط ۱۴روزه";

// The required confirmation-checkbox label in the warning dialog.
export const OVERRIDE_CONFIRM_LABEL_FA =
  "می‌دانم این اکانت هنوز آماده نیست و مسئولیت ریسک را می‌پذیرم";

// ── V41 PART 3 — mesh-recovery sender pause (distinct from the 14-day override) ──
// The «در حال بازیابی گرم‌سازی» badge shown next to a sender that is mid mesh-recovery re-warm and
// therefore cannot send as a Team Collaboration sender until it graduates.
export const RECOVERY_BADGE_FA = "در حال بازیابی گرم‌سازی";

// Whether to show the mesh-recovery badge next to a sender in the picker (from GET /senders).
export function senderInMeshRecovery(sender) {
  return !!(sender && sender.in_mesh_recovery);
}

// True when the chosen sender is ineligible AND not already overridden → the warning/confirmation
// dialog must be shown before the assignment can proceed. `elig` is the GET /sender-eligibility body.
// A mesh-recovery pause is a HARD block that no override can lift, so it never opens the override
// dialog (the backend rejects a recovery sender's sends regardless of any override).
export function needsOverridePrompt(elig) {
  if (!elig) return false;                       // unknown → don't block the UI (backend still gates)
  if (elig.reason === "in_mesh_recovery") return false;
  return elig.eligible === false && elig.override_active !== true;
}

// The override can only be submitted once the user BOTH ticks the confirmation checkbox AND writes a
// short (non-empty) note. Mirrors the backend's mandatory-note rule.
export function overrideConfirmValid({ confirmed, note } = {}) {
  return confirmed === true && typeof note === "string" && note.trim().length > 0;
}

// The exact Persian warning sentence for the dialog: prefer the backend's specific message; else fall
// back to a days-remaining phrasing; else a generic line.
export function eligibilityWarningText(elig) {
  if (!elig) return "";
  if (elig.message) return elig.message;
  if (elig.reason === "in_mesh_recovery") {
    return "این اکانت در حال بازیابی گرم‌سازی است و تا پایان دوره نمی‌تواند فرستنده باشد.";
  }
  if (elig.reason === "too_young" && elig.days_remaining != null) {
    return `این اکانت هنوز ${elig.days_remaining} روز تا کامل‌شدن شرط ۱۴روزه فاصله دارد.`;
  }
  if (elig.reason === "recent_incident") {
    return "این اکانت در ۱۴ روز اخیر حادثه داشته است.";
  }
  return "این اکانت هنوز واجد شرایط فرستنده‌ی همکاری تیمی نیست.";
}

// Whether to show the override badge next to a sender in the picker (from GET /senders).
export function senderHasOverride(sender) {
  return !!(sender && sender.eligibility_overridden);
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

// ── V35 — «درخواست‌های بی‌پاسخ» (unresponded requests) task filter ───────────────
// A task represents one (contact × cold-account) ask. Its status lifecycle is
// pending → asked → reminded → no_response | done | skipped.
// "Unresponded" = the contact RECEIVED an ask (and possibly a reminder) but has NOT completed
// it — i.e. status is exactly one of asked / reminded / no_response. `pending` (never asked)
// and `skipped` (abandoned) are deliberately excluded; `done` is the completed case we drop.
export const UNRESPONDED_STATUSES = ["asked", "reminded", "no_response"];

export const TASK_STATUS_FA = {
  pending: "در صف",
  asked: "درخواست ارسال شد",
  reminded: "یادآوری شد",
  no_response: "بدون پاسخ",
  done: "تکمیل شد",
  skipped: "رها شده",
};

export function taskStatusFa(status) {
  return TASK_STATUS_FA[status] || status || "—";
}

// Filter task rows to the unresponded set (status ∈ {asked, reminded, no_response}).
// Newest asks first: sort by asked_at desc (rows without asked_at fall to the end).
export function filterUnrespondedTasks(tasks) {
  const rows = (Array.isArray(tasks) ? tasks : []).filter((t) =>
    UNRESPONDED_STATUSES.includes(t.status)
  );
  rows.sort((a, b) => {
    const ta = a.asked_at || "", tb = b.asked_at || "";
    if (ta === tb) return 0;
    if (!ta) return 1;        // no ask time → bottom
    if (!tb) return -1;
    return ta < tb ? 1 : -1;  // newest first
  });
  return rows;
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

// PART 7 — the RUNNING per-contact ask number for each ask event (1 for the contact's first ask,
// 2 for the second, …). Returns { eventId: runningNumber }. Events may arrive newest-first; we
// number them in chronological (created_at) order so each row shows its true position in sequence.
export function askRunningCounts(events) {
  const withIdx = (events || []).map((e, i) => ({ e, i }));
  withIdx.sort((a, b) => {
    const ta = a.e.created_at || "", tb = b.e.created_at || "";
    if (ta < tb) return -1;
    if (ta > tb) return 1;
    return a.i - b.i;   // stable tiebreak on original order
  });
  const perContact = {};
  const out = {};
  for (const { e } of withIdx) {
    if (e.event_type !== "ask" || !e.helper_id) continue;
    perContact[e.helper_id] = (perContact[e.helper_id] || 0) + 1;
    out[e.id] = perContact[e.helper_id];
  }
  return out;
}
