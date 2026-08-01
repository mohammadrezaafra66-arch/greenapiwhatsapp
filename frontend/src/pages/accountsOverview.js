// V48 — pure transforms for the unified all-accounts overview page (sorting, filtering, and the
// Persian labels/badges/detail-links). Kept side-effect-free so it unit-tests under `node --test`.
// This module NEVER computes any score/eligibility itself — it only formats & arranges the rows the
// aggregation endpoint (GET /accounts/overview) already produced from the shared source functions.

// ── warmth badge (mirrors teamCollab.warmthBadge so the two pages read identically) ──
export function warmthBadge({ level, score } = {}) {
  let lvl = level;
  if (!lvl) {
    const s = Number(score || 0);
    lvl = s >= 70 ? "بالا" : s >= 40 ? "متوسط" : "کم";
  }
  const cls = lvl === "بالا"
    ? "bg-brand-light text-brand border-brand/30"
    : lvl === "متوسط"
      ? "bg-amber-50 text-amber-700 border-amber-200"
      : "bg-slate-100 text-slate-600 border-slate-300";
  return { level: lvl, cls, label: lvl };
}

// ── role labels + chips (each chip links to the existing detail page for that role) ──
export const MESH_ROLE_FA = {
  being_warmed: "در حال گرم‌سازی",
  peer_sender: "اکانت گرم مرجع / فرستنده",
  graduated_peer: "فارغ‌التحصیل (فرستنده)",
  none: "بدون نقش",
};

export const NO_ROLE_FA = "بدون نقش";

// The detail page each role/aspect deep-links to (this page is a map, not a replacement).
export const LINK_ACCOUNTS = "/accounts";
export const LINK_WARMUP = "/warmup";
export const LINK_TEAM = "/team-collaboration";
export const LINK_PROTECTION = "/protection";

/** Ordered role chips describing an account, each with the detail page it links to. */
export function roleChips(row) {
  const r = (row && row.role) || {};
  const chips = [];
  if (r.mesh && r.mesh !== "none") {
    chips.push({ key: "mesh", label: MESH_ROLE_FA[r.mesh] || r.mesh, to: LINK_WARMUP,
                 cls: "bg-sky-50 text-sky-700 border-sky-200" });
  }
  if (r.tc_sender) {
    chips.push({ key: "tc_sender",
                 label: `فرستندهٔ همکاری تیمی (${r.tc_contact_count || 0} مخاطب)`, to: LINK_TEAM,
                 cls: "bg-indigo-50 text-indigo-700 border-indigo-200" });
  }
  if (r.tc_cold) {
    chips.push({ key: "tc_cold", label: "اکانت سرد (همکاری تیمی)", to: LINK_TEAM,
                 cls: "bg-purple-50 text-purple-700 border-purple-200" });
  }
  if (r.in_mesh_recovery) {
    chips.push({ key: "recovery", label: "در حال بازیابی گرم‌سازی", to: LINK_WARMUP,
                 cls: "bg-amber-50 text-amber-700 border-amber-200" });
  }
  if (!chips.length) {
    chips.push({ key: "none", label: NO_ROLE_FA, to: LINK_ACCOUNTS,
                 cls: "bg-slate-100 text-slate-600 border-slate-300" });
  }
  return chips;
}

// ── eligibility label/badge (formats the reason slug the endpoint already decided) ──
export const ELIGIBILITY_REASON_FA = {
  ok: "واجد شرایط",
  too_young: "خیلی جدید (زیر ۱۴ روز)",
  recent_incident: "حادثهٔ اخیر (۱۴ روز)",
  in_mesh_recovery: "در حال بازیابی",
  not_found: "یافت نشد",
};

export function eligibilityInfo(row) {
  if (!row) return { label: "—", cls: "bg-slate-100 text-slate-600 border-slate-300", eligible: false };
  if (row.eligible) {
    return { label: "واجد شرایط", cls: "bg-brand-light text-brand border-brand/30", eligible: true };
  }
  const base = ELIGIBILITY_REASON_FA[row.eligibility_reason] || "واجد شرایط نیست";
  // An override lifts the 14-day/incident bar; show it so the row explains itself.
  if (row.eligibility_override) {
    return { label: `${base} — رد شرط ۱۴روزه`, cls: "bg-rose-50 text-rose-700 border-rose-200", eligible: false };
  }
  return { label: base, cls: "bg-slate-100 text-slate-600 border-slate-300", eligible: false };
}

// ── health badge (0..1 → percentage, colored like the protection page) ──
export function healthInfo(row) {
  const v = Number((row && row.health_score) || 0);
  const pct = Math.round(v * 100);
  const cls = v > 0.6 ? "text-brand" : v > 0.3 ? "text-amber-700" : "text-red-700";
  return { pct, cls };
}

// ── sorting ──
export const SORT_KEYS = {
  warmth: (r) => Number(r.warmth_score || 0),
  days_connected: (r) => (r.days_connected == null ? -1 : Number(r.days_connected)),
  health: (r) => Number(r.health_score || 0),
  name: (r) => (r.name || r.instance_id || "").toString(),
  incidents: (r) => Number(r.incident_total || 0),
};

/** Stable sort by one of SORT_KEYS, ascending or descending. Unknown key → unchanged copy. */
export function sortRows(rows, key = "warmth", dir = "desc") {
  const arr = [...(rows || [])];
  const fn = SORT_KEYS[key];
  if (!fn) return arr;
  const mul = dir === "asc" ? 1 : -1;
  return arr
    .map((r, i) => [r, i])
    .sort((a, b) => {
      const va = fn(a[0]);
      const vb = fn(b[0]);
      let c;
      if (typeof va === "string" || typeof vb === "string") {
        c = String(va).localeCompare(String(vb), "fa");
      } else {
        c = va < vb ? -1 : va > vb ? 1 : 0;
      }
      return c !== 0 ? c * mul : a[1] - b[1]; // stable tiebreak on original index
    })
    .map((p) => p[0]);
}

// ── filtering ──
export const ROLE_FILTERS = [
  { value: "", label: "همهٔ نقش‌ها" },
  { value: "mesh", label: "در شبکهٔ گرم‌سازی" },
  { value: "peer", label: "فرستندهٔ گرم (مرجع/فارغ‌التحصیل)" },
  { value: "tc_sender", label: "فرستندهٔ همکاری تیمی" },
  { value: "tc_cold", label: "اکانت سرد (همکاری تیمی)" },
  { value: "none", label: "بدون نقش" },
];

export const ELIG_FILTERS = [
  { value: "", label: "همهٔ وضعیت‌ها" },
  { value: "eligible", label: "واجد شرایط" },
  { value: "ineligible", label: "واجد شرایط نیست" },
  { value: "override", label: "رد شرط ۱۴روزه" },
];

export function roleMatches(row, role) {
  if (!role) return true;
  const r = (row && row.role) || {};
  switch (role) {
    case "mesh": return r.mesh === "being_warmed";
    case "peer": return r.mesh === "peer_sender" || r.mesh === "graduated_peer";
    case "tc_sender": return !!r.tc_sender;
    case "tc_cold": return !!r.tc_cold;
    case "none": return !!r.none;
    default: return true;
  }
}

export function eligMatches(row, elig) {
  if (!elig) return true;
  if (elig === "eligible") return !!row.eligible;
  if (elig === "ineligible") return !row.eligible;
  if (elig === "override") return !!row.eligibility_override;
  return true;
}

export function textMatches(row, q) {
  if (!q) return true;
  const needle = q.trim().toLowerCase();
  if (!needle) return true;
  return [row.name, row.instance_id, row.phone]
    .filter(Boolean)
    .some((v) => String(v).toLowerCase().includes(needle));
}

/** Apply role + eligibility + free-text filters together. */
export function filterRows(rows, { role = "", elig = "", q = "" } = {}) {
  return (rows || []).filter(
    (r) => roleMatches(r, role) && eligMatches(r, elig) && textMatches(r, q));
}

// ── V57: when a Green API spam restriction lifts ─────────────────────────────
// `suspended` reads like a dead end; the expiry is what makes it actionable ("wait N days",
// not "rescan the QR"). Green API supplies it as getWaSettings.suspendedUntil.
export function suspendedUntilFa(iso, now = new Date()) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const dateFa = d.toLocaleDateString("fa-IR", {
    year: "numeric", month: "long", day: "numeric", timeZone: "Asia/Tehran",
  });
  const timeFa = d.toLocaleTimeString("fa-IR", {
    hour: "2-digit", minute: "2-digit", timeZone: "Asia/Tehran",
  });
  const hours = (d.getTime() - now.getTime()) / 3600000;
  if (hours <= 0) return `${dateFa} ${timeFa} (سپری شده)`;
  const left = hours < 24
    ? `${Math.round(hours)} ساعت دیگر`
    : `${Math.round(hours / 24)} روز دیگر`;
  return `${dateFa} ${timeFa} — ${left}`;
}
