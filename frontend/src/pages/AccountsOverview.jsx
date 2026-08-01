// V48 — «نمای کلی حساب‌ها»: ONE row per account pulling together what today is scattered across
// /accounts (connection + activity), /warmup (warmth + role), /protection (health + incidents) and
// /team-collaboration (TC role + sender eligibility). This page is a MAP/overview: every cell links
// out to the relevant detail page; it never duplicates deep functionality. All data comes from the
// GET /accounts/overview aggregation endpoint (which reuses the shared source functions), so nothing
// here recomputes any score/eligibility/incident.
import React from "react";
import { Link } from "react-router-dom";
import { Accounts } from "../api.js";
import { useAsync, Spinner, Empty } from "../ui.jsx";
import {
  warmthBadge, roleChips, eligibilityInfo, healthInfo, sortRows, filterRows,
  ROLE_FILTERS, ELIG_FILTERS, LINK_TEAM, LINK_PROTECTION,
} from "./accountsOverview.js";
import HelpTooltip from "../components/HelpTooltip.jsx";
import { OVERVIEW_TIPS } from "./teamCollabHelp.js";

const fa = (n) => (n == null ? "" : String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]));

const STATUS_FA = {
  active: "فعال", banned: "مسدود", disconnected: "قطع", pending: "در انتظار",
  suspended: "محدود", green_api_deleted: "حذف‌شده در سرویس",
};
const STATUS_CLS = {
  active: "bg-brand-light text-brand border-brand/30",
  banned: "bg-red-50 text-red-700 border-red-200",
  disconnected: "bg-amber-50 text-amber-700 border-amber-200",
  pending: "bg-slate-100 text-slate-600 border-slate-300",
};

const SORT_COLS = [
  { key: "name", label: "حساب", help: OVERVIEW_TIPS.account },
  { key: "warmth", label: "گرمی", help: OVERVIEW_TIPS.warmth },
  { key: "days_connected", label: "روزهای اتصال", help: OVERVIEW_TIPS.days_connected },
  { key: "health", label: "سلامت", help: OVERVIEW_TIPS.health },
  { key: "incidents", label: "حوادث", help: OVERVIEW_TIPS.incidents },
];

function Th({ col, sort, setSort }) {
  const active = sort.key === col.key;
  const arrow = active ? (sort.dir === "asc" ? " ▲" : " ▼") : "";
  return (
    <th
      className={`py-2 px-2 cursor-pointer select-none whitespace-nowrap ${active ? "text-brand font-bold" : "text-muted"}`}
      onClick={() => setSort({ key: col.key, dir: active && sort.dir === "desc" ? "asc" : "desc" })}
      title="برای مرتب‌سازی کلیک کنید">
      {col.label}{arrow}
      {/* V54 — the icon stops its own click, so tapping «؟» never re-sorts the table. */}
      {col.help && <HelpTooltip text={col.help} />}
    </th>
  );
}

export default function AccountsOverview() {
  const { data, loading, reload } = useAsync(() => Accounts.overview(), []);
  const [sort, setSort] = React.useState({ key: "warmth", dir: "desc" });
  const [role, setRole] = React.useState("");
  const [elig, setElig] = React.useState("");
  const [q, setQ] = React.useState("");

  const all = data?.accounts || [];
  const rows = React.useMemo(
    () => sortRows(filterRows(all, { role, elig, q }), sort.key, sort.dir),
    [all, role, elig, q, sort]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">🗂️ نمای کلی حساب‌ها</h1>
        <p className="text-sm text-muted mt-1">
          وضعیت کامل هر حساب در یک نگاه — اتصال، امتیاز گرمی، روزهای اتصال، حوادث، نقش، واجد‌شرایط‌بودن
          فرستنده و فعالیت امروز. برای جزئیات هر بخش، روی نقش یا مقدار مربوطه بزنید.
        </p>
      </div>

      <div className="card space-y-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <span className="badge bg-slate-100 text-slate-600 border-slate-300">
            {fa(rows.length)} از {fa(all.length)} حساب
          </span>
          <div className="flex gap-2 flex-wrap">
            <input className="input text-xs py-1" placeholder="جستجوی نام/شماره/آی‌دی…"
              value={q} onChange={(e) => setQ(e.target.value)} />
            <select className="input text-xs py-1" value={role} onChange={(e) => setRole(e.target.value)}>
              {ROLE_FILTERS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            <select className="input text-xs py-1" value={elig} onChange={(e) => setElig(e.target.value)}>
              {ELIG_FILTERS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            <button className="btn-secondary btn-sm" onClick={reload}>تازه‌سازی</button>
          </div>
        </div>

        {loading ? <Spinner /> : rows.length === 0 ? <Empty label="حسابی مطابق فیلترها یافت نشد." /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs border-b border-line">
                  {SORT_COLS.map((c) => <Th key={c.key} col={c} sort={sort} setSort={setSort} />)}
                  <th className="py-2 px-2 text-muted whitespace-nowrap">اتصال<HelpTooltip text={OVERVIEW_TIPS.connection} /></th>
                  <th className="py-2 px-2 text-muted whitespace-nowrap">نقش<HelpTooltip text={OVERVIEW_TIPS.role} /></th>
                  <th className="py-2 px-2 text-muted whitespace-nowrap">واجد شرایط فرستنده<HelpTooltip text={OVERVIEW_TIPS.eligible} /></th>
                  <th className="py-2 px-2 text-muted whitespace-nowrap">فعالیت امروز<HelpTooltip text={OVERVIEW_TIPS.activity_today} /></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => <Row key={r.instance_id} row={r} />)}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function Row({ row }) {
  const w = warmthBadge({ level: row.warmth_level, score: row.warmth_score });
  const chips = roleChips(row);
  const ei = eligibilityInfo(row);
  const hi = healthInfo(row);
  return (
    <tr className="border-b border-line align-top">
      {/* account (links to /accounts) */}
      <td className="py-2 px-2">
        <Link to="/accounts" className="hover:text-brand font-medium">{row.name || row.instance_id}</Link>
        <div className="text-[11px] text-muted font-mono">{fa(row.phone || row.instance_id)}</div>
      </td>
      {/* warmth (links to team-collaboration where the warmth badge lives) */}
      <td className="py-2 px-2">
        <Link to={LINK_TEAM} title="امتیاز گرمی فرستنده">
          <span className={`badge ${w.cls}`}>{fa(w.label)}</span>
          <span className="text-[11px] text-muted mr-1">{fa(row.warmth_score)}</span>
        </Link>
      </td>
      {/* days connected */}
      <td className="py-2 px-2 whitespace-nowrap">
        {row.days_connected == null ? "—" : `${fa(row.days_connected)} روز`}
        {row.incident_free_14d
          ? <div className="text-[11px] text-brand">۱۴ روز بدون حادثه</div>
          : <div className="text-[11px] text-amber-700">{fa(row.recent_incidents_14d)} حادثه در ۱۴ روز</div>}
      </td>
      {/* health (links to /protection) */}
      <td className="py-2 px-2 whitespace-nowrap">
        <Link to={LINK_PROTECTION} className={`font-bold ${hi.cls}`} title="امتیاز سلامت">{fa(hi.pct)}٪</Link>
        {row.in_cooldown && <div className="text-[11px] text-red-700">در خنک‌سازی</div>}
      </td>
      {/* incidents (links to /protection) */}
      <td className="py-2 px-2 whitespace-nowrap">
        <Link to={LINK_PROTECTION} className="hover:text-brand">{fa(row.incident_total)}</Link>
        {row.last_incident_type && (
          <div className="text-[11px] text-muted">{row.last_incident_type}</div>
        )}
      </td>
      {/* connection status */}
      <td className="py-2 px-2">
        <span className={`badge ${STATUS_CLS[row.status] || "bg-slate-100 text-slate-600 border-slate-300"}`}>
          {STATUS_FA[row.status] || row.status}
        </span>
      </td>
      {/* role chips (each links to its detail page) */}
      <td className="py-2 px-2">
        <div className="flex flex-wrap gap-1">
          {chips.map((c) => (
            <Link key={c.key} to={c.to}>
              <span className={`badge ${c.cls}`}>{c.label}</span>
            </Link>
          ))}
        </div>
      </td>
      {/* sender eligibility (links to team-collaboration) */}
      <td className="py-2 px-2">
        <Link to={LINK_TEAM}><span className={`badge ${ei.cls}`}>{ei.label}</span></Link>
      </td>
      {/* activity today */}
      <td className="py-2 px-2 whitespace-nowrap text-ink">
        <span className="text-sky-700">↑{fa(row.sent_today)}</span>
        {" / "}
        <span className="text-brand">↓{fa(row.received_today)}</span>
        <div className="text-[11px] text-muted">سقف {fa(row.daily_cap)}</div>
      </td>
    </tr>
  );
}
