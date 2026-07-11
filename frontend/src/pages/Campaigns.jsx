import React from "react";
import { Campaigns as Api, FilesApi, Accounts, ContactGroupsApi, WaCollectionsApi, LabelsApi, Dashboard } from "../api.js";
import { Badge, Spinner, Empty, Modal, Progress, useAsync } from "../ui.jsx";
import { toast, confirmDialog } from "../ui/toast.jsx";

const fa = (n) => Number(n || 0).toLocaleString("fa-IR");

// V13.6 — render WhatsApp inline formatting markers (*bold* _italic_ ~strike~ ```mono```).
function renderWaInline(text) {
  const parts = [];
  const re = /(\*[^*\n]+\*|_[^_\n]+_|~[^~\n]+~|```[^`]+```)/g;
  let last = 0, m, i = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("```")) parts.push(<code key={i++} className="font-mono bg-black/20 px-1 rounded text-[0.9em]">{tok.slice(3, -3)}</code>);
    else if (tok[0] === "*") parts.push(<b key={i++}>{tok.slice(1, -1)}</b>);
    else if (tok[0] === "_") parts.push(<i key={i++}>{tok.slice(1, -1)}</i>);
    else if (tok[0] === "~") parts.push(<s key={i++}>{tok.slice(1, -1)}</s>);
    last = m.index + tok.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

function WhatsAppText({ text }) {
  const lines = (text || "").split("\n");
  return lines.map((line, i) => <div key={i}>{line ? renderWaInline(line) : <br />}</div>);
}

const TYPE_FA = {
  text: "متنی",
  image: "تصویری",
  poll: "نظرسنجی",
  interactive_buttons: "دکمه‌ای",
  status: "استوری",
};

export default function Campaigns() {
  const { data, loading, error, reload } = useAsync(Api.list, []);
  const [showAdd, setShowAdd] = React.useState(false);
  const [test, setTest] = React.useState(null);
  const [edit, setEdit] = React.useState(null); // { editId, initial }
  const [editLoading, setEditLoading] = React.useState(false);
  const [analytics, setAnalytics] = React.useState(null);

  const openAnalytics = async (c) => {
    try {
      const [data, ab] = await Promise.all([
        Api.analytics(c.id),
        Api.abResults(c.id).catch(() => null),
      ]);
      setAnalytics({ ...data, _ab: ab });
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  const [roi, setRoi] = React.useState(null);
  const openRoi = async (c) => {
    try {
      const d = await Api.roi(c.id);
      setRoi({ campaignId: c.id, name: c.name, ...d });
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  const act = async (fn) => {
    try {
      await fn();
      await reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  const openEdit = async (c) => {
    setEditLoading(true);
    try {
      const detail = await Api.get(c.id);
      setEdit({ editId: c.id, initial: detail });
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setEditLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">گروه‌های پیام</h2>
        <button className="btn-primary" onClick={() => setShowAdd(true)}>+ گروه پیام جدید</button>
      </div>

      {loading && <Spinner />}
      {error && <div className="card text-red-400">{error}</div>}
      {data && data.length === 0 && <Empty label="گروه پیامی وجود ندارد." />}

      <div className="space-y-3">
        {data?.map((c) => (
          <div key={c.id} className="card">
            <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
              <div className="flex items-center gap-2">
                <span className="font-bold">{c.name}</span>
                <Badge status={c.status} />
                <span className="badge bg-slate-700 text-slate-300 border-slate-600">{TYPE_FA[c.campaign_type] || c.campaign_type}</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {c.status === "running" ? (
                  <button className="btn-secondary" onClick={() => act(() => Api.pause(c.id))}>توقف</button>
                ) : (
                  <button className="btn-primary" onClick={() => act(() => (c.status === "paused" ? Api.resume(c.id) : Api.start(c.id)))}>شروع</button>
                )}
                <button className="btn-secondary" onClick={() => setTest(c)}>تست</button>
                <button className="btn-secondary text-xs" onClick={() => act(async () => {
                  const r = await Api.retryFailed(c.id);
                  if (r.requeued > 0) toast.success(`${fa(r.requeued)} پیام ناموفق دوباره در صف قرار گرفت`);
                  else toast.info("پیام ناموفقی برای تلاش مجدد نیست");
                })}>🔁 تلاش مجدد ناموفق‌ها</button>
                <button className="btn-secondary text-xs" onClick={() => openAnalytics(c)}>📊 آمار</button>
                <button className="btn-secondary text-xs" onClick={() => openRoi(c)}>💰 بازده</button>
                <button className="btn-secondary" disabled={editLoading} onClick={() => openEdit(c)}>✏️ ویرایش</button>
                <button className="btn-secondary" onClick={() => act(() => Api.toggleActive(c.id))}>
                  {c.is_active ? "⏸️ غیرفعال" : "▶️ فعال"}
                </button>
                <button className="btn-danger" onClick={async () => { if (await confirmDialog("این گروه پیام حذف شود؟")) act(() => Api.remove(c.id)); }}>حذف</button>
              </div>
            </div>
            <div className="flex justify-between text-sm mb-1 text-slate-400">
              <span>پیشرفت: {c.sent_count} / {c.total_contacts}</span>
              <span>تحویل: {c.delivered_count} · خوانده: {c.read_count} · ناموفق: {c.failed_count}</span>
            </div>
            {(c.schedule_start_shamsi || c.schedule_end_shamsi) && (
              <div className="text-xs text-slate-400">📅 {c.schedule_start_shamsi || "—"} تا {c.schedule_end_shamsi || "—"}</div>
            )}
            <Progress value={c.sent_count} max={c.total_contacts} />
            {(c.status === "running" || c.status === "paused") && <LiveLog campaignId={c.id} />}
          </div>
        ))}
      </div>

      {showAdd && <AddCampaignModal onClose={() => setShowAdd(false)} onDone={reload} />}
      {edit && (
        <AddCampaignModal
          editId={edit.editId}
          initial={edit.initial}
          onClose={() => setEdit(null)}
          onDone={reload}
        />
      )}
      {test && <TestModal campaign={test} onClose={() => setTest(null)} />}
      {analytics && <AnalyticsModal data={analytics} onClose={() => setAnalytics(null)} />}
      {roi && <RoiModal roi={roi} onClose={() => setRoi(null)} onChanged={() => openRoi({ id: roi.campaignId, name: roi.name })} />}
    </div>
  );
}

function AnalyticsModal({ data, onClose }) {
  const t = data?.totals || {};
  const r = data?.rates || {};
  const perAccount = data?.per_account || [];
  const title = data?.campaign?.name || data?.campaign || "آمار گروه پیام";

  const cells = [
    { label: "کل", value: t.total, cls: "text-slate-200" },
    { label: "ارسال‌شده", value: t.sent, cls: "text-emerald-300" },
    { label: "تحویل", value: t.delivered, cls: "text-sky-300" },
    { label: "خوانده", value: t.read, cls: "text-sky-300" },
    { label: "یلوکارت", value: t.yellow_card, cls: (t.yellow_card || 0) > 0 ? "text-red-300" : "text-amber-300" },
    { label: "ناموفق", value: t.failed, cls: "text-red-300" },
    { label: "در انتظار", value: t.pending, cls: "text-slate-300" },
  ];

  return (
    <Modal title={`آمار گروه پیام: ${title}`} onClose={onClose} wide>
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {cells.map((cell) => (
            <div key={cell.label} className="rounded-lg bg-slate-900 border border-slate-700 p-3 text-center">
              <div className={`text-2xl font-bold ${cell.cls}`}>{fa(cell.value)}</div>
              <div className="text-xs text-slate-400 mt-1">{cell.label}</div>
            </div>
          ))}
        </div>

        <div className="text-sm text-slate-300">
          نرخ ارسال {fa(r.sent_pct)}٪ · خوانده {fa(r.read_pct)}٪ ·{" "}
          <span className={(r.yellow_card_pct || 0) > 50 ? "text-red-400 font-bold" : ""}>
            یلوکارت {fa(r.yellow_card_pct)}٪
          </span>{" "}
          · ناموفق {fa(r.failed_pct)}٪
        </div>

        {perAccount.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-right">
              <thead>
                <tr className="text-slate-400 border-b border-slate-700">
                  <th className="py-2 px-2 font-medium">حساب</th>
                  <th className="py-2 px-2 font-medium">ارسال</th>
                  <th className="py-2 px-2 font-medium">خوانده</th>
                  <th className="py-2 px-2 font-medium">یلوکارت</th>
                </tr>
              </thead>
              <tbody>
                {perAccount.map((a) => (
                  <tr key={a.account_id} className="border-b border-slate-800">
                    <td className="py-2 px-2">{a.name}</td>
                    <td className="py-2 px-2 text-emerald-300">{fa(a.sent)}</td>
                    <td className="py-2 px-2 text-sky-300">{fa(a.read)}</td>
                    <td className={`py-2 px-2 ${(a.yellow_card || 0) > 0 ? "text-red-300" : "text-amber-300"}`}>{fa(a.yellow_card)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {data?._ab?.variants && Object.keys(data._ab.variants).length > 0 && (
          <div className="rounded-lg border border-slate-700 p-3 space-y-2">
            <h4 className="font-bold text-sm">نتایج تست A/B</h4>
            <div className="grid grid-cols-2 gap-3">
              {["A", "B"].map((v) => {
                const stat = data._ab.variants[v];
                if (!stat) return <div key={v} className="text-xs text-slate-500">نسخه {v}: بدون داده</div>;
                const win = data._ab.winner === v;
                return (
                  <div key={v} className={`rounded-lg p-3 border ${win ? "border-emerald-500/50 bg-emerald-500/10" : "border-slate-700 bg-slate-900"}`}>
                    <div className="flex items-center gap-2 font-bold">
                      نسخه {v} {win && <span title="برنده">🏆</span>}
                    </div>
                    <div className="text-xs text-slate-300 mt-1 space-y-0.5">
                      <div>تعداد: {fa(stat.total)}</div>
                      <div className="text-emerald-300">تحویل: {fa(stat.delivered_pct)}٪ ({fa(stat.delivered)})</div>
                      <div className="text-sky-300">خوانده: {fa(stat.read_pct)}٪ ({fa(stat.read)})</div>
                      <div className="text-red-300">ناموفق: {fa(stat.failed)}</div>
                    </div>
                  </div>
                );
              })}
            </div>
            {data._ab.winner && (
              <p className="text-xs text-emerald-300">برنده بر اساس نرخ خوانده‌شدن: نسخه {data._ab.winner} 🏆</p>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}

// V13.7 — campaign ROI: conversion funnel + per-contact outcome tagging.
const OUTCOMES = [
  { value: "interested", label: "علاقه‌مند", cls: "bg-sky-600" },
  { value: "purchased", label: "خرید کرد", cls: "bg-emerald-600" },
  { value: "not_interested", label: "علاقه‌مند نیست", cls: "bg-slate-600" },
];

function RoiModal({ roi, onClose, onChanged }) {
  const fn = roi.funnel || {};
  const steps = [
    { label: "ارسال", value: fn.sent },
    { label: "تحویل", value: fn.delivered },
    { label: "خوانده", value: fn.read },
    { label: "پاسخ", value: fn.replied },
    { label: "خرید", value: fn.purchased },
  ];
  const top = Math.max(1, fn.sent || 0);
  const tag = async (ccId, outcome) => {
    try {
      await Api.setOutcome(roi.campaignId, ccId, { outcome });
      onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };
  return (
    <Modal title={`گزارش بازده (ROI): ${roi.name || ""}`} onClose={onClose} wide>
      <div className="space-y-4">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="rounded-lg bg-slate-900 border border-slate-700 p-3 text-center">
            <div className="text-2xl font-bold text-sky-300">{fa(roi.reply_rate)}٪</div>
            <div className="text-xs text-slate-400 mt-1">نرخ پاسخ</div>
          </div>
          <div className="rounded-lg bg-slate-900 border border-slate-700 p-3 text-center">
            <div className="text-2xl font-bold text-emerald-300">{fa(roi.purchased)}</div>
            <div className="text-xs text-slate-400 mt-1">خرید</div>
          </div>
          <div className="rounded-lg bg-slate-900 border border-slate-700 p-3 text-center">
            <div className="text-2xl font-bold text-slate-200">{fa(roi.interested)}</div>
            <div className="text-xs text-slate-400 mt-1">علاقه‌مند</div>
          </div>
          <div className="rounded-lg bg-slate-900 border border-slate-700 p-3 text-center">
            <div className="text-2xl font-bold text-slate-200">{fa(fn.replied)}</div>
            <div className="text-xs text-slate-400 mt-1">پاسخ‌ها</div>
          </div>
        </div>

        {/* Funnel */}
        <div className="space-y-1">
          {steps.map((s) => (
            <div key={s.label} className="flex items-center gap-2">
              <span className="text-xs text-slate-400 w-14 shrink-0">{s.label}</span>
              <div className="flex-1 h-6 bg-slate-800 rounded overflow-hidden">
                <div className="h-full bg-emerald-600/70 flex items-center px-2 text-xs" style={{ width: `${((s.value || 0) / top) * 100}%` }}>
                  {fa(s.value)}
                </div>
              </div>
            </div>
          ))}
          <p className="text-xs text-slate-500">قیف تبدیل: ارسال → تحویل → خوانده → پاسخ → خرید</p>
        </div>

        {/* Replied contacts tagging */}
        <div>
          <h4 className="font-bold text-sm mb-2">مخاطبینی که پاسخ داده‌اند</h4>
          {(!roi.replied_contacts || roi.replied_contacts.length === 0) && (
            <p className="text-sm text-slate-500">هنوز پاسخی ثبت نشده.</p>
          )}
          <div className="space-y-2 max-h-72 overflow-y-auto">
            {(roi.replied_contacts || []).map((rc) => (
              <div key={rc.cc_id} className="flex items-center justify-between gap-2 border-b border-slate-800 pb-2">
                <div className="min-w-0">
                  <div className="text-sm truncate">{rc.name || rc.phone}</div>
                  <div className="font-mono text-xs text-slate-500">{rc.phone}</div>
                </div>
                <div className="flex gap-1 flex-wrap justify-end">
                  {OUTCOMES.map((o) => (
                    <button
                      key={o.value}
                      className={`text-xs px-2 py-1 rounded text-white ${rc.outcome === o.value ? o.cls : "bg-slate-700 hover:bg-slate-600"}`}
                      onClick={() => tag(rc.cc_id, o.value)}
                    >
                      {o.label}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Modal>
  );
}

function LiveLog({ campaignId }) {
  const [prog, setProg] = React.useState(null);
  const [failed, setFailed] = React.useState([]);
  const [err, setErr] = React.useState(null);
  const [tick, setTick] = React.useState(null);

  React.useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const [p, f] = await Promise.all([
          Api.progress(campaignId),
          Api.contacts(campaignId, "failed"),
        ]);
        if (!alive) return;
        setProg(p);
        setFailed(f);
        setErr(null);
        setTick(new Date());
      } catch (e) {
        if (alive) setErr(e?.response?.data?.detail || e.message);
      }
    };
    poll();
    const t = setInterval(poll, 3000);
    return () => { alive = false; clearInterval(t); };
  }, [campaignId]);

  return (
    <div className="mt-3 rounded-lg bg-slate-900 border border-slate-700 p-3 text-sm space-y-2">
      <div className="flex items-center justify-between">
        <span className="font-bold text-slate-300">گزارش زنده</span>
        <span className="flex items-center gap-2 text-xs text-slate-500">
          <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          {tick ? `به‌روزرسانی: ${tick.toLocaleTimeString("fa-IR")}` : "در حال اتصال..."}
        </span>
      </div>

      {err && <div className="text-red-400 text-xs">خطا در دریافت گزارش: {err}</div>}

      {prog?.pause_reason && (
        <div className="rounded bg-amber-500/10 border border-amber-500/40 text-amber-300 p-2 text-xs">
          ⏸️ {prog.pause_reason}
        </div>
      )}

      {prog && (
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="badge bg-slate-700 text-slate-300 border-slate-600">وضعیت: {prog.status}</span>
          <span className="badge bg-amber-500/20 text-amber-300 border-amber-500/40">در انتظار: {prog.pending}</span>
          <span className="badge bg-emerald-500/20 text-emerald-300 border-emerald-500/40">ارسال‌شده: {prog.sent}</span>
          <span className="badge bg-red-500/20 text-red-300 border-red-500/40">ناموفق: {prog.failed}</span>
          <span className="badge bg-sky-500/20 text-sky-300 border-sky-500/40">پیشرفت: {prog.progress_pct}%</span>
        </div>
      )}

      {failed.length === 0 ? (
        <p className="text-xs text-slate-500">هیچ خطای ارسالی ثبت نشده است.</p>
      ) : (
        <div className="space-y-1 max-h-52 overflow-y-auto">
          <p className="text-xs text-red-300 font-bold">پیام‌های خطا ({failed.length}):</p>
          {failed.map((f) => (
            <div key={f.id} className="rounded bg-red-500/10 border border-red-500/30 p-2 text-xs">
              <div className="flex justify-between text-slate-400">
                <span className="font-mono">{f.phone}</span>
                <span>تلاش: {f.retry_count}</span>
              </div>
              <div className="text-red-300 mt-1 break-words whitespace-pre-wrap font-mono">
                {f.error_message || "بدون پیام خطا"}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const EMOJI_LEVELS = [
  { code: "none", label: "بدون ایموجی" },
  { code: "low", label: "کم" },
  { code: "medium", label: "متوسط" },
  { code: "high", label: "زیاد" },
];

const CAMPAIGN_DEFAULTS = {
  name: "", campaign_type: "text", use_gpt: true, gpt_prompt: "",
  message_template: "", include_products: false, product_count: 3, image_url: "",
  poll_question: "", poll_options: "", buttons: "", footer_text: "",
  campaign_scope: "pv", group_ids: "",
  description: "", contact_group_id: "", wa_collection_id: "", product_label_filter: "",
  emoji_level: "medium",
  append_seller_name: false, seller_name: "",
  append_seller_phone: false, seller_phone: "", seller_phone2: "",
  append_date: false,
  schedule_start_shamsi: "", schedule_end_shamsi: "",
  parallel_accounts: false, show_product_prices: true,
  // Message customization
  opening_mode: "ai", opening_line: "", opening_variants: "",
  product_variation_mode: "same", products_per_group: 3, product_weights: "",
  include_opt_out: true, opt_out_text: "",
  ab_test_enabled: false, variant_b_prompt: "", variant_b_template: "",
  use_rich_formatting: false, smart_rotation: false,
};

// Parse a "name=weight" per-line textarea into {name: number}. Blank → null.
function parseWeights(text) {
  if (!text || !text.trim()) return null;
  const out = {};
  for (const line of text.split("\n")) {
    const idx = line.lastIndexOf("=");
    if (idx < 0) continue;
    const name = line.slice(0, idx).trim();
    const w = Number(line.slice(idx + 1).trim());
    if (name && Number.isFinite(w) && w > 0) out[name] = w;
  }
  return Object.keys(out).length ? out : null;
}

function seedCampaignForm(d) {
  const join = (v) => (Array.isArray(v) ? v.join("\n") : (v || ""));
  return {
    name: d.name || "",
    campaign_type: d.campaign_type || "text",
    use_gpt: d.use_gpt ?? true,
    gpt_prompt: d.gpt_prompt || "",
    message_template: d.message_template || "",
    include_products: d.include_products || false,
    product_count: d.product_count || 3,
    image_url: d.image_url || "",
    poll_question: d.poll_question || "",
    poll_options: join(d.poll_options),
    buttons: join(d.buttons),
    footer_text: d.footer_text || "",
    campaign_scope: d.campaign_scope || "pv",
    group_ids: join(d.group_ids),
    description: d.description || "",
    contact_group_id: d.contact_group_id || "",
    wa_collection_id: d.wa_collection_id || "",
    product_label_filter: d.product_label_filter || "",
    emoji_level: d.emoji_level || "medium",
    append_seller_name: d.append_seller_name || false,
    seller_name: d.seller_name || "",
    append_seller_phone: d.append_seller_phone || false,
    seller_phone: d.seller_phone || "",
    seller_phone2: d.seller_phone2 || "",
    append_date: d.append_date || false,
    schedule_start_shamsi: d.schedule_start_shamsi || "",
    schedule_end_shamsi: d.schedule_end_shamsi || "",
    parallel_accounts: d.parallel_accounts || false,
    show_product_prices: d.show_product_prices !== false,
    opening_mode: d.opening_mode || "ai",
    opening_line: d.opening_line || "",
    opening_variants: join(d.opening_variants),
    product_variation_mode: d.product_variation_mode || "same",
    products_per_group: d.products_per_group || 3,
    product_weights: d.product_weights
      ? Object.entries(d.product_weights).map(([k, v]) => `${k}=${v}`).join("\n")
      : "",
    include_opt_out: d.include_opt_out !== false,
    opt_out_text: d.opt_out_text || "",
    ab_test_enabled: d.ab_test_enabled || false,
    variant_b_prompt: d.variant_b_prompt || "",
    variant_b_template: d.variant_b_template || "",
    use_rich_formatting: d.use_rich_formatting || false,
    smart_rotation: d.smart_rotation || false,
  };
}

function AddCampaignModal({ onClose, onDone, editId = null, initial = null }) {
  const [f, setF] = React.useState(() => (initial ? seedCampaignForm(initial) : { ...CAMPAIGN_DEFAULTS }));
  const [saving, setSaving] = React.useState(false);
  const [uploading, setUploading] = React.useState(false);
  const [contactGroups, setContactGroups] = React.useState([]);
  const [waCollections, setWaCollections] = React.useState([]);
  const [labels, setLabels] = React.useState([]);
  const [feasContactCount, setFeasContactCount] = React.useState(100);
  const [feasResult, setFeasResult] = React.useState(null);
  const [feasLoading, setFeasLoading] = React.useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  // V13.5 — WhatsApp formatting toolbar: wrap the selected text in the template editor.
  const templateRef = React.useRef(null);
  const wrapTemplate = (marker, endMarker) => {
    const ta = templateRef.current;
    const em = endMarker ?? marker;
    const val = f.message_template || "";
    const start = ta ? ta.selectionStart : val.length;
    const end = ta ? ta.selectionEnd : val.length;
    const sel = val.slice(start, end) || "متن";
    const next = val.slice(0, start) + marker + sel + em + val.slice(end);
    setF((prev) => ({ ...prev, message_template: next }));
    requestAnimationFrame(() => {
      if (!ta) return;
      ta.focus();
      ta.setSelectionRange(start + marker.length, start + marker.length + sel.length);
    });
  };
  const bulletTemplate = () => {
    const val = f.message_template || "";
    const out = val
      .split("\n")
      .map((l) => (l.trim() ? (l.startsWith("• ") ? l : "• " + l) : l))
      .join("\n");
    setF((prev) => ({ ...prev, message_template: out }));
  };

  // V13.6 — live preview
  const [preview, setPreview] = React.useState(null);
  const [previewing, setPreviewing] = React.useState(false);
  const buildPreviewBody = () => ({
    use_gpt: f.use_gpt,
    gpt_prompt: f.gpt_prompt || null,
    message_template: f.message_template || null,
    include_products: f.include_products,
    product_count: Number(f.product_count) || 3,
    product_label_filter: f.include_products && f.product_label_filter ? f.product_label_filter : null,
    show_product_prices: f.show_product_prices !== false,
    emoji_level: f.emoji_level,
    opening_mode: f.opening_mode,
    opening_line: f.opening_mode === "fixed" ? (f.opening_line || null) : null,
    opening_variants:
      f.opening_mode === "random" && f.opening_variants
        ? f.opening_variants.split("\n").map((s) => s.trim()).filter(Boolean)
        : null,
    include_opt_out: f.include_opt_out !== false,
    opt_out_text: f.include_opt_out && f.opt_out_text ? f.opt_out_text : null,
    use_rich_formatting: f.use_rich_formatting,
    append_seller_name: f.append_seller_name,
    seller_name: f.append_seller_name ? (f.seller_name || null) : null,
    append_seller_phone: f.append_seller_phone,
    seller_phone: f.append_seller_phone ? (f.seller_phone || null) : null,
    seller_phone2: f.append_seller_phone ? (f.seller_phone2 || null) : null,
    append_date: f.append_date,
  });
  const doPreview = async () => {
    setPreviewing(true);
    try {
      const r = await Api.preview(buildPreviewBody());
      setPreview(r?.preview || "");
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setPreviewing(false);
    }
  };

  const runFeasibility = async () => {
    setFeasLoading(true);
    setFeasResult(null);
    try {
      const accs = await Accounts.list();
      const account_ids = accs.filter((a) => a.status === "active").map((a) => a.id);
      const r = await Dashboard.validateCampaign({
        contact_count: Number(feasContactCount) || 0,
        account_ids,
        min_delay: 45,
        max_delay: 110,
      });
      setFeasResult(r);
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setFeasLoading(false);
    }
  };

  // Load dropdown data once
  React.useEffect(() => {
    ContactGroupsApi.list().then(setContactGroups).catch(() => {});
    WaCollectionsApi.list().then(setWaCollections).catch(() => {});
    LabelsApi.list().then(setLabels).catch(() => {});
  }, []);

  // Prefill image_url + campaign type from a file chosen on the Files page (create mode only)
  React.useEffect(() => {
    if (editId) return;
    const pre = typeof localStorage !== "undefined" ? localStorage.getItem("afrakala_prefill_image_url") : "";
    if (pre) {
      setF((prev) => ({ ...prev, image_url: pre, campaign_type: "image" }));
      localStorage.removeItem("afrakala_prefill_image_url");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const uploadImage = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const accs = await Accounts.list();
      const active = accs.find((a) => a.status === "active") || accs[0];
      if (!active) return toast.error("حسابی برای آپلود موجود نیست");
      const fd = new FormData();
      fd.append("file", file);
      const r = await FilesApi.upload(active.id, fd);
      setF((prev) => ({ ...prev, image_url: r.url }));
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setUploading(false);
    }
  };

  const submit = async () => {
    if (!f.name) return toast.error("لطفاً نام گروه پیام را وارد کنید");
    setSaving(true);
    try {
      const body = {
        name: f.name,
        campaign_type: f.campaign_type,
        use_gpt: f.use_gpt,
        gpt_prompt: f.gpt_prompt || null,
        message_template: f.message_template || null,
        include_products: f.include_products,
        product_count: Number(f.product_count) || 3,
        image_url: f.image_url || null,
        poll_question: f.poll_question || null,
        poll_options: f.poll_options ? f.poll_options.split("\n").map((s) => s.trim()).filter(Boolean) : null,
        buttons: f.buttons ? f.buttons.split("\n").map((s) => s.trim()).filter(Boolean) : null,
        footer_text: f.footer_text || null,
        campaign_scope: f.campaign_scope,
        group_ids:
          f.campaign_scope === "group" && f.group_ids
            ? f.group_ids.split("\n").map((s) => s.trim()).filter(Boolean)
            : null,
        description: f.description || null,
        contact_group_id: f.contact_group_id || null,
        wa_collection_id: f.wa_collection_id || null,
        product_label_filter: f.include_products && f.product_label_filter ? f.product_label_filter : null,
        emoji_level: f.emoji_level,
        append_seller_name: f.append_seller_name,
        seller_name: f.append_seller_name ? (f.seller_name || null) : null,
        append_seller_phone: f.append_seller_phone,
        seller_phone: f.append_seller_phone ? (f.seller_phone || null) : null,
        seller_phone2: f.append_seller_phone ? (f.seller_phone2 || null) : null,
        append_date: f.append_date,
        schedule_start_shamsi: f.schedule_start_shamsi || null,
        schedule_end_shamsi: f.schedule_end_shamsi || null,
        parallel_accounts: f.parallel_accounts,
        show_product_prices: f.show_product_prices !== false,
        // Message customization
        opening_mode: f.opening_mode || "ai",
        opening_line: f.opening_mode === "fixed" ? (f.opening_line || null) : null,
        opening_variants:
          f.opening_mode === "random" && f.opening_variants
            ? f.opening_variants.split("\n").map((s) => s.trim()).filter(Boolean)
            : null,
        product_variation_mode: f.product_variation_mode || "same",
        products_per_group: Number(f.products_per_group) || 3,
        product_weights: parseWeights(f.product_weights),
        include_opt_out: f.include_opt_out !== false,
        opt_out_text: f.include_opt_out && f.opt_out_text ? f.opt_out_text : null,
        ab_test_enabled: f.ab_test_enabled,
        variant_b_prompt: f.ab_test_enabled ? (f.variant_b_prompt || null) : null,
        variant_b_template: f.ab_test_enabled ? (f.variant_b_template || null) : null,
        use_rich_formatting: f.use_rich_formatting,
        smart_rotation: f.smart_rotation,
      };
      if (editId) {
        await Api.update(editId, body);
      } else {
        await Api.create(body);
      }
      await onDone();
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title={editId ? "ویرایش کمپین" : "گروه پیام جدید"} onClose={onClose} wide>
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">نام گروه پیام</label>
            <input className="input" value={f.name} onChange={set("name")} />
          </div>
          <div>
            <label className="label">نوع پیام</label>
            <select className="input" value={f.campaign_type} onChange={set("campaign_type")}>
              {Object.entries(TYPE_FA).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
        </div>

        <div>
          <label className="label">توضیحات کمپین (اختیاری)</label>
          <textarea className="input h-16" value={f.description} onChange={set("description")} />
        </div>

        <div>
          <label className="label">نوع ارسال</label>
          <select className="input" value={f.campaign_scope} onChange={set("campaign_scope")}>
            <option value="pv">ارسال به افراد</option>
            <option value="group">ارسال به گروه‌ها</option>
          </select>
        </div>

        {f.campaign_scope === "pv" && (
          <div>
            <label className="label">گروه مخاطبین (جایگزین افزودن دستی مخاطبین)</label>
            <select className="input" value={f.contact_group_id} onChange={set("contact_group_id")}>
              <option value="">— انتخاب نشده —</option>
              {contactGroups.map((g) => (
                <option key={g.id} value={g.id}>{g.name}{g.member_count != null ? ` (${g.member_count})` : ""}</option>
              ))}
            </select>
          </div>
        )}

        {f.campaign_scope === "group" && (
          <>
            <div>
              <label className="label">مجموعه گروه‌های واتساپ</label>
              <select className="input" value={f.wa_collection_id} onChange={set("wa_collection_id")}>
                <option value="">— انتخاب نشده —</option>
                {waCollections.map((w) => (
                  <option key={w.id} value={w.id}>{w.name}{w.group_count != null ? ` (${w.group_count})` : ""}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">شناسه گروه‌ها (هر خط یک گروه)</label>
              <textarea className="input h-20" value={f.group_ids} onChange={set("group_ids")} placeholder="120363xxxxxxxx@g.us" />
            </div>
          </>
        )}

        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={f.use_gpt} onChange={set("use_gpt")} />
          نوشتن پیام با هوش مصنوعی
        </label>
        <p className="text-xs text-slate-500 -mt-1">سیستم با هوش مصنوعی یک پیام منحصربه‌فرد برای هر مخاطب می‌نویسد</p>

        {f.use_gpt ? (
          <div>
            <label className="label">توضیح برای هوش مصنوعی</label>
            <textarea className="input h-20" value={f.gpt_prompt} onChange={set("gpt_prompt")} placeholder="مثال: یک پیام صمیمی و کوتاه برای مشتری عمده‌فروش لوازم خانگی بنویس که از خرید از افراکالا تشکر کند" />
            <label className="flex items-center gap-2 text-sm mt-2">
              <input type="checkbox" checked={f.use_rich_formatting} onChange={set("use_rich_formatting")} />
              قالب‌بندی هوشمند با هوش مصنوعی (پررنگ کردن نام محصولات و نکات مهم)
            </label>
          </div>
        ) : (
          <div>
            <label className="label">قالب پیام (می‌توانید از {"{{first_name}}"} استفاده کنید)</label>
            {/* V13.5 — WhatsApp formatting toolbar */}
            <div className="flex flex-wrap gap-1 mb-1">
              <button type="button" className="btn-secondary text-xs font-bold" title="پررنگ" onClick={() => wrapTemplate("*")}>B</button>
              <button type="button" className="btn-secondary text-xs italic" title="کج" onClick={() => wrapTemplate("_")}>I</button>
              <button type="button" className="btn-secondary text-xs line-through" title="خط‌خورده" onClick={() => wrapTemplate("~")}>S</button>
              <button type="button" className="btn-secondary text-xs font-mono" title="تک‌فاصله" onClick={() => wrapTemplate("```")}>{"</>"}</button>
              <button type="button" className="btn-secondary text-xs" title="فهرست" onClick={bulletTemplate}>• لیست</button>
            </div>
            <textarea ref={templateRef} className="input h-20" value={f.message_template} onChange={set("message_template")} />
            <p className="text-xs text-slate-500 mt-1">
              راهنما: <span className="font-bold">*پررنگ*</span> · <span className="italic">_کج_</span> ·{" "}
              <span className="line-through">~خط‌خورده~</span> · <span className="font-mono">```تک‌فاصله```</span>
            </p>
          </div>
        )}

        {/* V13.6 — live message preview */}
        <div className="border-t border-slate-700 pt-3">
          <div className="flex items-center gap-2">
            <button type="button" className="btn-secondary text-sm" disabled={previewing} onClick={doPreview}>
              {previewing ? "در حال ساخت..." : "👁 پیش‌نمایش پیام"}
            </button>
            {preview !== null && (
              <button type="button" className="btn-secondary text-xs" disabled={previewing} onClick={doPreview}>🔄 به‌روزرسانی</button>
            )}
          </div>
          {preview !== null && (
            <div className="mt-2 flex justify-end" dir="rtl">
              <div className="max-w-sm rounded-2xl rounded-tr-sm bg-emerald-700/90 text-white p-3 text-sm leading-relaxed shadow break-words">
                {preview ? <WhatsAppText text={preview} /> : <span className="text-white/70">—</span>}
                <div className="text-[10px] text-white/60 text-left mt-1">پیش‌نمایش ✓✓</div>
              </div>
            </div>
          )}
          <p className="text-xs text-slate-500 mt-1">پیش‌نمایش دقیقاً از همان مسیر ساخت پیام واقعی تولید می‌شود (نمونه مخاطب: اولین مخاطب یا «دوست»).</p>
        </div>

        {/* V13.1 — A/B testing */}
        <div className="border-t border-slate-700 pt-3">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={f.ab_test_enabled} onChange={set("ab_test_enabled")} />
            تست A/B (دو نسخه پیام، تقسیم ۵۰/۵۰)
          </label>
          <p className="text-xs text-slate-500 -mt-0.5">نیمی از مخاطبین نسخه A و نیمی نسخه B را دریافت می‌کنند؛ نتایج در «آمار» مقایسه می‌شود.</p>
          {f.ab_test_enabled && (
            <div className="mt-2">
              {f.use_gpt ? (
                <>
                  <label className="label">پرامپت نسخه B</label>
                  <textarea
                    className="input h-20"
                    value={f.variant_b_prompt}
                    onChange={set("variant_b_prompt")}
                    placeholder="توضیح متفاوت برای هوش مصنوعی (نسخه B). خالی = مثل نسخه A"
                  />
                </>
              ) : (
                <>
                  <label className="label">قالب نسخه B</label>
                  <textarea
                    className="input h-20"
                    value={f.variant_b_template}
                    onChange={set("variant_b_template")}
                    placeholder="متن قالب نسخه B (می‌توانید از {{first_name}} استفاده کنید)"
                  />
                </>
              )}
            </div>
          )}
        </div>

        {/* Phase 2 — opening line control */}
        <div className="border-t border-slate-700 pt-3">
          <label className="label">عبارت آغازین</label>
          <select className="input" value={f.opening_mode} onChange={set("opening_mode")}>
            <option value="ai">هوش مصنوعی بنویسد</option>
            <option value="fixed">متن ثابت</option>
            <option value="none">بدون سلام</option>
            <option value="random">چند حالت تصادفی</option>
          </select>
          {f.opening_mode === "fixed" && (
            <input
              className="input mt-2"
              value={f.opening_line}
              onChange={set("opening_line")}
              placeholder="مثال: سلام دوستان عزیز 🌟"
            />
          )}
          {f.opening_mode === "random" && (
            <>
              <textarea
                className="input h-20 mt-2"
                value={f.opening_variants}
                onChange={set("opening_variants")}
                placeholder={"هر خط یک عبارت آغازین:\nسلام دوستان 🌟\nوقت بخیر همراهان عزیز\nدرود بر شما"}
              />
              <p className="text-xs text-slate-500 mt-1">در هر ارسال یکی به‌صورت تصادفی انتخاب می‌شود (تنوع بین گروه‌ها).</p>
            </>
          )}
        </div>

        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={f.include_products} onChange={set("include_products")} />
          افزودن محصولات روز افراکالا
        </label>
        <p className="text-xs text-slate-500 -mt-1">قیمت لحظه‌ای محصولات افراکالا در پیام درج می‌شود</p>

        {f.include_products && (
          <>
            <div>
              <label className="label">تعداد محصول (اندازه مخزن)</label>
              <input
                type="number"
                className="input"
                min={1}
                max={30}
                value={f.product_count}
                onChange={set("product_count")}
              />
              <p className="text-xs text-slate-500 mt-1">در حالت تنوع، مخزن باید بزرگ‌تر از «تعداد در هر گروه» باشد.</p>
            </div>

            {/* Phase 3 — per-group product variation */}
            <div>
              <label className="label">تنوع محصولات بین گروه‌ها</label>
              <select className="input" value={f.product_variation_mode} onChange={set("product_variation_mode")}>
                <option value="same">یکسان برای همه</option>
                <option value="per_group_random">تصادفی برای هر گروه</option>
                <option value="rotate">چرخشی</option>
              </select>
              <p className="text-xs text-slate-500 mt-1">تنوع بین گروه‌ها باعث می‌شود پیام‌ها شبیه هم نباشند (کاهش ریسک شناسایی توسط متا).</p>
            </div>
            {f.product_variation_mode !== "same" && (
              <div>
                <label className="label">تعداد محصول در هر گروه</label>
                <input
                  type="number"
                  className="input"
                  min={1}
                  max={10}
                  value={f.products_per_group}
                  onChange={set("products_per_group")}
                />
              </div>
            )}
            {/* Phase 4 — weighted selection (only meaningful with random variation) */}
            {f.product_variation_mode === "per_group_random" && (
              <div>
                <label className="label">وزن محصولات (اختیاری)</label>
                <textarea
                  className="input h-20"
                  value={f.product_weights}
                  onChange={set("product_weights")}
                  placeholder={"نام محصول=وزن (هر خط یکی):\nساید ال جی X24=8\nیخچال دوو=3"}
                />
                <p className="text-xs text-slate-500 mt-1">وزن (اهمیت): هرچه بیشتر، در گروه‌های بیشتری و با تکرار بیشتری تبلیغ می‌شود. پیش‌فرض ۱.</p>
              </div>
            )}

            <div>
              <label className="label">فیلتر بر اساس برچسب (اختیاری)</label>
              <select className="input" value={f.product_label_filter} onChange={set("product_label_filter")}>
                <option value="">— همه محصولات —</option>
                {labels.map((l) => (
                  <option key={l.id} value={l.id}>{l.title}</option>
                ))}
              </select>
              {f.product_label_filter && (() => {
                const sel = labels.find((l) => String(l.id) === String(f.product_label_filter));
                return sel?.color ? (
                  <span className="inline-flex items-center gap-2 mt-1 text-xs text-slate-400">
                    <span className="inline-block w-3 h-3 rounded-full" style={{ backgroundColor: sel.color }} />
                    {sel.title}
                  </span>
                ) : null;
              })()}
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={f.show_product_prices !== false} onChange={set("show_product_prices")} />
              نمایش قیمت در پیام
            </label>
          </>
        )}

        {/* Phase 5 — optional opt-out line */}
        <div className="border-t border-slate-700 pt-3">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={f.include_opt_out !== false} onChange={set("include_opt_out")} />
            افزودن عبارت لغو اشتراک
          </label>
          {f.include_opt_out !== false && (
            <input
              className="input mt-2"
              value={f.opt_out_text}
              onChange={set("opt_out_text")}
              placeholder="برای لغو عدد ۱۱ ارسال کنید"
            />
          )}
          <p className="text-xs text-slate-500 mt-1">اگر خاموش باشد، هیچ عبارت لغوی به انتهای پیام اضافه نمی‌شود.</p>
        </div>

        {/* V13.2 — smart account rotation */}
        <div className="border-t border-slate-700 pt-3">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={f.smart_rotation} onChange={set("smart_rotation")} />
            چرخش هوشمند حساب‌ها (اولویت با حساب سالم‌تر)
          </label>
          <p className="text-xs text-slate-500 -mt-0.5">به‌جای چرخش ساده، حساب‌های سالم‌تر (یلوکارت کمتر، ظرفیت روزانه بیشتر) پیام بیشتری می‌فرستند.</p>
        </div>

        {f.campaign_type === "image" && (
          <div>
            <label className="label">آدرس تصویر</label>
            <div className="flex gap-2">
              <input className="input flex-1" value={f.image_url} onChange={set("image_url")} />
              <label className="btn-secondary cursor-pointer whitespace-nowrap">
                {uploading ? "در حال آپلود..." : "آپلود فایل"}
                <input type="file" className="hidden" onChange={(e) => uploadImage(e.target.files?.[0])} />
              </label>
            </div>
          </div>
        )}
        {f.campaign_type === "poll" && (
          <>
            <div>
              <label className="label">سؤال نظرسنجی</label>
              <input className="input" value={f.poll_question} onChange={set("poll_question")} />
            </div>
            <div>
              <label className="label">گزینه‌ها (هر خط یک گزینه)</label>
              <textarea className="input h-20" value={f.poll_options} onChange={set("poll_options")} />
            </div>
          </>
        )}
        {f.campaign_type === "interactive_buttons" && (
          <>
            <div>
              <label className="label">دکمه‌ها (هر خط یک دکمه، حداکثر ۳)</label>
              <textarea className="input h-16" value={f.buttons} onChange={set("buttons")} />
            </div>
            <div>
              <label className="label">متن پاورقی</label>
              <input className="input" value={f.footer_text} onChange={set("footer_text")} />
            </div>
          </>
        )}

        <div>
          <label className="label">سطح ایموجی</label>
          <select className="input" value={f.emoji_level} onChange={set("emoji_level")}>
            {EMOJI_LEVELS.map((e) => <option key={e.code} value={e.code}>{e.label}</option>)}
          </select>
        </div>

        <div className="rounded-lg border border-slate-700 p-3 space-y-2">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={f.append_seller_name} onChange={set("append_seller_name")} />
            نام فروشنده اضافه شود
          </label>
          {f.append_seller_name && (
            <div>
              <label className="label">نام فروشنده</label>
              <input className="input" value={f.seller_name} onChange={set("seller_name")} />
            </div>
          )}

          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={f.append_seller_phone} onChange={set("append_seller_phone")} />
            شماره فروشنده اضافه شود
          </label>
          {f.append_seller_phone && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">موبایل</label>
                <input className="input" value={f.seller_phone} onChange={set("seller_phone")} />
              </div>
              <div>
                <label className="label">تلفن ثابت</label>
                <input className="input" value={f.seller_phone2} onChange={set("seller_phone2")} />
              </div>
            </div>
          )}

          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={f.append_date} onChange={set("append_date")} />
            تاریخ امروز (شمسی) آخر پیام اضافه شود
          </label>
        </div>

        <div className="border-t border-slate-700 pt-3 mt-3">
          <p className="font-bold text-sm mb-2">⏰ زمان‌بندی ارسال</p>
          <div className="grid grid-cols-2 gap-2">
            <input
              className="input"
              dir="ltr"
              value={f.schedule_start_shamsi}
              onChange={set("schedule_start_shamsi")}
              placeholder="۱۴۰۳/۰۱/۱۵ ۰۸:۰۰"
            />
            <input
              className="input"
              dir="ltr"
              value={f.schedule_end_shamsi}
              onChange={set("schedule_end_shamsi")}
              placeholder="۱۴۰۳/۰۱/۲۰ ۲۲:۰۰"
            />
          </div>
          <p className="text-xs text-slate-500">فرمت: YYYY/MM/DD HH:MM</p>
        </div>

        <div className="border-t border-slate-700 pt-3 mt-3">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={f.parallel_accounts} onChange={set("parallel_accounts")} />
            ارسال موازی با چند حساب
          </label>
          {f.parallel_accounts && (
            <p className="text-xs text-sky-300">💡 مخاطبین به‌صورت مساوی بین حساب‌های فعال تقسیم می‌شوند</p>
          )}
        </div>

        <div className="border-t border-slate-700 pt-3 mt-3">
          <p className="font-bold text-sm mb-2">امکان‌سنجی ارسال</p>
          <div className="flex gap-2 items-end">
            <div className="flex-1">
              <label className="label">تعداد مخاطبین</label>
              <input
                type="number"
                className="input"
                min={1}
                value={feasContactCount}
                onChange={(e) => setFeasContactCount(e.target.value)}
              />
            </div>
            <button className="btn-secondary whitespace-nowrap" disabled={feasLoading} onClick={runFeasibility}>
              🔍 بررسی امکان‌سنجی
            </button>
          </div>
          {feasLoading && <p className="text-xs text-slate-400 mt-2">در حال بررسی...</p>}
          {!feasLoading && feasResult && (
            <div
              className={`card mt-2 border ${
                feasResult.color === "green"
                  ? "border-emerald-500 bg-emerald-500/10"
                  : feasResult.color === "amber"
                  ? "border-amber-500 bg-amber-500/10"
                  : "border-red-500 bg-red-500/10"
              }`}
            >
              <p className="font-bold text-sm">{feasResult.status}</p>
              {feasResult.summary && (
                <div className="grid grid-cols-2 gap-1 text-xs text-slate-300 mt-2">
                  <span>مخاطبین: {feasResult.summary.contact_count}</span>
                  <span>حساب‌های فعال: {feasResult.summary.active_accounts}</span>
                  <span>ظرفیت روزانه کل: {feasResult.summary.total_daily_capacity}</span>
                  <span>تخمین زمان: {feasResult.summary.estimated_days} روز</span>
                </div>
              )}
              {feasResult.warnings?.map((w, i) => (
                <p key={`w${i}`} className="text-xs text-amber-300 mt-1">⚠️ {w}</p>
              ))}
              {feasResult.recommendations?.map((r, i) => (
                <p key={`r${i}`} className="text-xs text-sky-300 mt-1">💡 {r}</p>
              ))}
            </div>
          )}
        </div>

        <button className="btn-primary w-full" disabled={saving} onClick={submit}>
          {saving ? (editId ? "در حال ذخیره..." : "در حال ساخت...") : (editId ? "ذخیره تغییرات" : "ساخت گروه پیام")}
        </button>
        {!editId && <p className="text-xs text-slate-500">پس از ساخت، مخاطبین را از صفحه مخاطبین اضافه کنید و سپس گروه پیام را شروع کنید.</p>}
      </div>
    </Modal>
  );
}

function TestModal({ campaign, onClose }) {
  const [phone, setPhone] = React.useState("");
  const [message, setMessage] = React.useState("");
  const [sending, setSending] = React.useState(false);

  const send = async () => {
    if (!phone) return toast.error("لطفاً شماره را وارد کنید");
    setSending(true);
    try {
      const r = await Api.test(campaign.id, phone, message || null);
      toast.info(r.sent ? `ارسال شد (از ${r.via})` : "ارسال ناموفق");
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setSending(false);
    }
  };

  return (
    <Modal title={`تست گروه پیام: ${campaign.name}`} onClose={onClose}>
      <div className="space-y-3">
        <div>
          <label className="label">شماره تست</label>
          <input className="input" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="09123456789" />
        </div>
        <div>
          <label className="label">پیام دلخواه (اختیاری)</label>
          <textarea className="input h-20" value={message} onChange={(e) => setMessage(e.target.value)} />
        </div>
        <p className="text-xs text-slate-500">پیام آزمایشی با همین تنظیمات GPT و محصولات ارسال می‌شود</p>
        <button className="btn-primary w-full" disabled={sending} onClick={send}>
          {sending ? "در حال ارسال..." : "ارسال تست"}
        </button>
      </div>
    </Modal>
  );
}
