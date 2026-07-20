// V30 PART 1 — «همکاری تیمی» (Team Collaboration) — the full navigable UI over the V29 API.
// Four panels: مدیریت (senders + contacts + cold-account assignment + brief), داشبورد
// (per-sender warmth / per-cold-account cycle & thread status), لاگ (Shamsi event log, filterable),
// هشدارها (safety-paused threads with manual review + resume). All data transforms live in the
// unit-tested pure module teamCollab.js.
import React from "react";
import { WarmupHelpersApi, Accounts } from "../api.js";
import { useAsync, Spinner, Empty } from "../ui.jsx";
import { toast, confirmDialog } from "../ui/toast.jsx";
import {
  warmthBadge, canAssignCold, filterLogEvents, threadStatusSummary,
  dayInCycleLabel, askRunningCounts, askCountSentence, MAX_COLD_PER_CONTACT,
  filterUnrespondedTasks, taskStatusFa,
} from "./teamCollab.js";

const fa = (n) => (n == null ? "" : String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]));

const TABS = [
  { key: "manage", label: "مدیریت فرستنده و مخاطبان" },
  { key: "dashboard", label: "داشبورد" },
  { key: "log", label: "لاگ رویدادها" },
  { key: "alerts", label: "هشدارهای ایمنی" },
];

const EMPTY_CONTACT = {
  name: "", phone: "", job_title: "", years_experience: "",
  personal_benefit_note: "", phone_secondary: "",
  // V35 PART 3 — relationship category + optional referral note.
  relationship: "", referral_note: "",
};

// V35 PART 3 — relationship categories (English code stored; Persian label shown).
const RELATIONSHIP_OPTIONS = [
  { value: "", label: "— نسبت (اختیاری) —" },
  { value: "friend", label: "دوست" },
  { value: "colleague", label: "همکار" },
  { value: "employee", label: "کارمند" },
  { value: "family", label: "فامیل" },
];
const RELATIONSHIP_FA = { friend: "دوست", colleague: "همکار", employee: "کارمند", family: "فامیل" };

// ── warmth badge lookup shared across panels ─────────────────────────────────
function WarmthBadge({ level, score }) {
  const b = warmthBadge({ level, score });
  return <span className={`badge ${b.cls}`} title="امتیاز گرمی فرستنده">{fa(b.label)}</span>;
}

// ── Panel 1: sender + contacts + cold-account assignment ─────────────────────
function ManagePanel() {
  const sendersAsync = useAsync(() => WarmupHelpersApi.senders(), []);
  const warmthAsync = useAsync(() => WarmupHelpersApi.warmth(), []);
  const [sender, setSender] = React.useState("");
  const senders = sendersAsync.data?.senders || [];
  const warmthBy = React.useMemo(() => {
    const m = {};
    for (const w of warmthAsync.data?.senders || []) m[w.instance_id] = w;
    return m;
  }, [warmthAsync.data]);

  React.useEffect(() => {
    if (!sender && senders.length) setSender(senders[0].instance_id);
  }, [senders, sender]);

  const current = senders.find((s) => s.instance_id === sender);

  async function toggleSender(s) {
    try {
      const r = await WarmupHelpersApi.senderToggle(s.instance_id, !s.team_enabled);
      toast.success(r.enabled ? "این فرستنده روشن شد" : "این فرستنده خاموش شد");
      sendersAsync.reload();
    } catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }

  return (
    <div className="space-y-4">
      <div className="card space-y-3">
        <h3 className="font-bold">انتخاب فرستنده</h3>
        <p className="text-xs text-slate-400">
          هر فرستنده مجموعهٔ مخاطبان و برنامهٔ گرم‌سازی مخصوص خود را دارد. امتیاز گرمی نشان می‌دهد
          این اکانت چقدر برای ارسال امن است (کم/متوسط/بالا).
        </p>
        {sendersAsync.loading ? <Spinner /> : (
          <div className="flex flex-wrap gap-2">
            {senders.map((s) => {
              const w = warmthBy[s.instance_id];
              const isSel = s.instance_id === sender;
              return (
                <button key={s.instance_id} onClick={() => setSender(s.instance_id)}
                  className={`px-3 py-2 rounded-lg border text-sm flex items-center gap-2 ${isSel
                    ? "bg-brand/15 border-brand text-brand font-bold"
                    : "bg-slate-800 border-slate-700 text-slate-300"}`}>
                  <span>{s.name || s.instance_id}</span>
                  <span className="text-xs opacity-70">({fa(s.contact_count)} مخاطب)</span>
                  {w && <WarmthBadge level={w.level} score={w.score} />}
                  {!s.team_enabled && <span className="badge bg-slate-600/30 text-slate-400 border-slate-600">خاموش</span>}
                </button>
              );
            })}
          </div>
        )}
        {current && (
          <div className="flex items-center gap-2">
            <button className={`text-sm px-3 py-1.5 rounded font-bold border ${current.team_enabled
              ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
              : "bg-slate-700 text-slate-300 border-slate-600"}`} onClick={() => toggleSender(current)}>
              {current.team_enabled ? "همکاری تیمی این فرستنده: روشن ✓" : "همکاری تیمی این فرستنده: خاموش"}
            </button>
          </div>
        )}
      </div>

      {sender && <BriefEditor senderInstanceId={sender} />}
      {sender && <ContactsEditor senderInstanceId={sender} onChange={() => sendersAsync.reload()} />}
      <ColdAccountRoster />
    </div>
  );
}

function BriefEditor({ senderInstanceId }) {
  const { data, reload } = useAsync(() => WarmupHelpersApi.getCurrentBrief(senderInstanceId), [senderInstanceId]);
  const [text, setText] = React.useState("");
  React.useEffect(() => { setText(data?.brief_text || ""); }, [data]);
  async function save() {
    try { await WarmupHelpersApi.setCurrentBrief(senderInstanceId, text.trim()); toast.success("خلاصهٔ فعال ذخیره شد"); reload(); }
    catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }
  return (
    <div className="card space-y-2">
      <h3 className="font-bold">خلاصهٔ فعال (Brief) این فرستنده</h3>
      <p className="text-xs text-slate-400">یک جملهٔ کوتاه که به هوش مصنوعی جهت می‌دهد چه پیامی برای مخاطبان ساخته شود.</p>
      <div className="flex gap-2">
        <input className="input flex-1" placeholder="مثلاً: به شماره‌های جدید ما یک سلام دوستانه بده" value={text}
          onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && save()} />
        <button className="btn-primary" onClick={save}>ذخیره</button>
      </div>
    </div>
  );
}

function ContactsEditor({ senderInstanceId, onChange }) {
  const { data, loading, reload } = useAsync(() => WarmupHelpersApi.list(senderInstanceId), [senderInstanceId]);
  const [form, setForm] = React.useState(EMPTY_CONTACT);
  const [showProfile, setShowProfile] = React.useState(false);
  const helpers = data?.helpers || [];
  const softWarning = data?.soft_warning;

  async function add() {
    if (!form.name.trim() || !form.phone.trim()) return toast.error("نام و شماره لازم است");
    try {
      await WarmupHelpersApi.create({
        name: form.name.trim(), phone: form.phone.trim(), sender_instance_id: senderInstanceId,
        job_title: form.job_title.trim() || null,
        years_experience: form.years_experience === "" ? null : Number(form.years_experience),
        personal_benefit_note: form.personal_benefit_note.trim() || null,
        phone_secondary: form.phone_secondary.trim() || null,
        relationship: form.relationship || null,
        referral_note: form.referral_note.trim() || null,
        require_full_name: true,
      });
      setForm(EMPTY_CONTACT); reload(); onChange && onChange();
    } catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }
  async function del(h) {
    if (!(await confirmDialog(`«${h.name}» حذف شود؟`))) return;
    try { await WarmupHelpersApi.remove(h.id); reload(); onChange && onChange(); }
    catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }
  async function toggleActive(h) {
    try { await WarmupHelpersApi.update(h.id, { is_active: !h.is_active }); reload(); }
    catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-bold">مخاطبان این فرستنده</h3>
        <span className="badge bg-slate-700 text-slate-300 border-slate-600">{fa(helpers.filter((h) => h.is_active).length)} فعال</span>
      </div>
      {softWarning && <p className="text-xs text-amber-300">{softWarning}</p>}

      <div className="space-y-2">
        <div className="flex gap-2 flex-wrap">
          <input className="input flex-1 min-w-[140px]" placeholder="نام و نام خانوادگی (اجباری)" value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input className="input flex-1 min-w-[140px]" placeholder="شماره (مثل ۹۸۹۱۲…)" value={form.phone}
            onChange={(e) => setForm({ ...form, phone: e.target.value })} onKeyDown={(e) => e.key === "Enter" && add()} />
          <button className="btn-secondary text-xs" onClick={() => setShowProfile((s) => !s)}>{showProfile ? "بستن مشخصات" : "مشخصات بیشتر"}</button>
          <button className="btn-primary" onClick={add}>افزودن</button>
        </div>
        {showProfile && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <input className="input" placeholder="سمت شغلی" value={form.job_title}
              onChange={(e) => setForm({ ...form, job_title: e.target.value })} />
            <input className="input" placeholder="سابقهٔ تخصصی (سال)" value={form.years_experience}
              onChange={(e) => setForm({ ...form, years_experience: e.target.value.replace(/[^0-9۰-۹]/g, "") })} />
            <input className="input" placeholder="شماره کاری (اختیاری)" value={form.phone_secondary}
              onChange={(e) => setForm({ ...form, phone_secondary: e.target.value })} />
            <input className="input" placeholder="این سیستم چه سودی برای او دارد؟" value={form.personal_benefit_note}
              onChange={(e) => setForm({ ...form, personal_benefit_note: e.target.value })} />
            <select className="input" value={form.relationship}
              onChange={(e) => setForm({ ...form, relationship: e.target.value })}>
              {RELATIONSHIP_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            <input className="input" placeholder="یادداشت معرف (مثلاً: شماره شما را آقای X داده)" value={form.referral_note}
              onChange={(e) => setForm({ ...form, referral_note: e.target.value })} />
          </div>
        )}
      </div>

      {loading ? <Spinner /> : helpers.length === 0 ? <Empty label="هنوز مخاطبی اضافه نشده." /> : (
        <div className="divide-y divide-slate-800">
          {helpers.map((h) => (
            <ContactRow key={h.id} helper={h} onDelete={() => del(h)} onToggle={() => toggleActive(h)} />
          ))}
        </div>
      )}
    </div>
  );
}

function ContactRow({ helper, onDelete, onToggle }) {
  const { data, reload } = useAsync(() => WarmupHelpersApi.coldAccounts(helper.id), [helper.id]);
  const accountsAsync = useAsync(() => Accounts.list(), []);
  const cold = data?.cold_accounts || [];
  const [pick, setPick] = React.useState("");
  const allAccounts = accountsAsync.data || [];
  const assignedIds = new Set(cold.map((c) => c.cold_instance_id));
  const candidates = allAccounts.filter((a) => a.instance_id && !assignedIds.has(a.instance_id));

  async function assign() {
    if (!pick) return;
    try { await WarmupHelpersApi.assignCold(helper.id, pick); setPick(""); reload(); }
    catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }
  async function unassign(cid) {
    try { await WarmupHelpersApi.unassignCold(helper.id, cid); reload(); }
    catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }

  return (
    <div className="py-2 text-sm space-y-1">
      <div className="flex items-center justify-between gap-2">
        <div>
          <span className={helper.is_active ? "font-bold" : "text-slate-500 line-through"}>{helper.name}</span>
          <span className="text-xs text-slate-500 font-mono mr-2">{fa(helper.phone)}</span>
          {helper.job_title && <span className="text-xs text-sky-300 mr-2">{helper.job_title}</span>}
          {helper.years_experience != null && <span className="text-xs text-slate-400 mr-1">({fa(helper.years_experience)} سال)</span>}
          {helper.relationship && RELATIONSHIP_FA[helper.relationship] && <span className="badge bg-indigo-500/20 text-indigo-300 border-indigo-500/40 mr-2">{RELATIONSHIP_FA[helper.relationship]}</span>}
          {helper.referral_note && <span className="text-xs text-amber-300/80 mr-1" title="یادداشت معرف">📇 {helper.referral_note}</span>}
        </div>
        <div className="flex gap-1">
          <button className={`badge ${helper.is_active ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40" : "bg-slate-600/30 text-slate-400 border-slate-600"}`} onClick={onToggle}>{helper.is_active ? "فعال" : "غیرفعال"}</button>
          <button className="btn-danger text-xs" onClick={onDelete}>حذف</button>
        </div>
      </div>
      <div className="flex items-center gap-2 flex-wrap pr-2">
        <span className="text-xs text-slate-400">اکانت‌های سرد ({fa(cold.length)}/{fa(MAX_COLD_PER_CONTACT)}):</span>
        {cold.map((c) => (
          <span key={c.cold_instance_id} className="badge bg-slate-700 text-slate-200 border-slate-600 flex items-center gap-1">
            {c.name || c.cold_instance_id}
            <button className="text-red-300 hover:text-red-200" onClick={() => unassign(c.cold_instance_id)}>×</button>
          </span>
        ))}
        {canAssignCold(cold.length) ? (
          <span className="flex items-center gap-1">
            <select className="input text-xs py-1" value={pick} onChange={(e) => setPick(e.target.value)}>
              <option value="">— افزودن اکانت سرد —</option>
              {candidates.map((a) => <option key={a.instance_id} value={a.instance_id}>{a.name || a.instance_id}</option>)}
            </select>
            <button className="btn-secondary text-xs" onClick={assign} disabled={!pick}>تخصیص</button>
          </span>
        ) : <span className="text-xs text-amber-300/80">به سقف ۲ اکانت رسیده</span>}
      </div>
    </div>
  );
}

function ColdAccountRoster() {
  const enrollAsync = useAsync(() => WarmupHelpersApi.teamEnrollments(), []);
  const accountsAsync = useAsync(() => Accounts.list(), []);
  const enrollments = enrollAsync.data?.enrollments || [];
  const enrollBy = React.useMemo(() => {
    const m = {}; for (const e of enrollments) m[e.cold_instance_id] = e; return m;
  }, [enrollments]);
  const accounts = accountsAsync.data || [];

  async function toggle(a) {
    const cur = enrollBy[a.instance_id];
    try {
      const r = await WarmupHelpersApi.teamEnroll(a.instance_id, !(cur && cur.enabled));
      toast.success(r.enabled ? "به همکاری تیمی افزوده شد (شروع دورهٔ ۱۰ روزه)" : "از همکاری تیمی خارج شد");
      enrollAsync.reload();
    } catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }

  return (
    <div className="card space-y-3">
      <h3 className="font-bold">اکانت‌های سرد (فهرست عضویت در همکاری تیمی)</h3>
      <p className="text-xs text-slate-400">هر اکانت سرد را می‌توانید در چرخهٔ خودکار ۱۰ روزه عضو کنید. ارسال‌ها فقط پس از گذشت دورهٔ ۲۴ ساعتهٔ اولیهٔ آن اکانت آغاز می‌شود.</p>
      {accountsAsync.loading ? <Spinner /> : (
        <div className="divide-y divide-slate-800">
          {accounts.map((a) => {
            const e = enrollBy[a.instance_id];
            const on = e && e.enabled;
            return (
              <div key={a.instance_id} className="flex items-center justify-between gap-2 py-2 text-sm">
                <div>
                  <span className={on ? "font-bold" : "text-slate-400"}>{a.name || a.instance_id}</span>
                  {on && <span className="text-xs text-sky-300 mr-2">{dayInCycleLabel(e.day_index, e.cycle_days)}</span>}
                </div>
                <button className={`badge ${on ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40" : "bg-slate-600/30 text-slate-400 border-slate-600"}`} onClick={() => toggle(a)}>
                  {on ? "عضو ✓" : "عضو کن"}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Panel 2: dashboard ───────────────────────────────────────────────────────
function DashboardPanel() {
  const { data, loading } = useAsync(() => WarmupHelpersApi.teamDashboard(), []);
  if (loading) return <Spinner />;
  const senders = data?.senders || [];
  const cold = data?.cold_accounts || [];
  return (
    <div className="space-y-4">
      <div className="card">
        <h3 className="font-bold mb-2">فرستنده‌ها</h3>
        {senders.length === 0 ? <Empty /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-slate-400 text-xs">
                <th className="text-right py-1">فرستنده</th><th>گرمی</th><th>مخاطبان</th><th className="text-right">خلاصهٔ فعال</th>
              </tr></thead>
              <tbody>
                {senders.map((s) => (
                  <tr key={s.instance_id} className="border-t border-slate-800">
                    <td className="py-2">{s.name || s.instance_id}{!s.team_enabled && <span className="badge bg-slate-600/30 text-slate-400 border-slate-600 mr-2">خاموش</span>}</td>
                    <td className="text-center"><WarmthBadge level={s.warmth_level} score={s.warmth_score} /></td>
                    <td className="text-center">{fa(s.contact_count)}</td>
                    <td className="text-slate-400 text-xs">{s.current_brief || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <div className="card">
        <h3 className="font-bold mb-2">اکانت‌های سرد</h3>
        {cold.length === 0 ? <Empty label="هنوز اکانت سردی عضو نشده." /> : (
          <div className="divide-y divide-slate-800">
            {cold.map((c) => (
              <div key={c.cold_instance_id} className="flex items-center justify-between gap-2 py-2 text-sm">
                <div>
                  <span className={c.enabled ? "font-bold" : "text-slate-400"}>{c.cold_name || c.cold_instance_id}</span>
                  {c.enabled && <span className="text-xs text-sky-300 mr-2">{dayInCycleLabel(c.day_index, c.cycle_days)}</span>}
                </div>
                <span className="text-xs text-slate-400">{threadStatusSummary(c)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Panel 3: log ──────────────────────────────────────────────────────────────
const EVENT_FA = { ask: "درخواست", reminder: "یادآوری", thank_you: "تشکر", cold_reply: "پاسخ اکانت سرد", incoming: "پیام دریافتی", safety_flag: "هشدار ایمنی" };

// V35 — sentinel dropdown value for the «درخواست‌های بی‌پاسخ» (unresponded requests) view.
// It is NOT an event_type; selecting it switches the panel from the event log to a task-status
// view (contacts who received an ask/reminder but have not completed the task).
const UNRESPONDED = "__unresponded__";

function LogPanel() {
  const { data, loading, reload } = useAsync(() => WarmupHelpersApi.teamLog({ limit: 300 }), []);
  // Tasks power the «درخواست‌های بی‌پاسخ» view (authoritative status: asked/reminded/no_response).
  const { data: taskData, loading: tasksLoading, reload: reloadTasks } =
    useAsync(() => WarmupHelpersApi.tasks(), []);
  const [eventType, setEventType] = React.useState("");
  const [senderInstanceId, setSender] = React.useState("");
  const events = data?.events || [];
  const tasks = taskData?.tasks || [];
  const unresponded = eventType === UNRESPONDED;

  // Sender options come from whichever dataset is active, so the filter stays meaningful in both views.
  const senders = React.useMemo(() => {
    const m = {};
    for (const e of events) if (e.sender_instance_id) m[e.sender_instance_id] = e.from_name || e.sender_instance_id;
    for (const t of tasks) if (t.sender_instance_id) m[t.sender_instance_id] = t.sender_name || t.sender_instance_id;
    return Object.entries(m);
  }, [events, tasks]);

  const filtered = filterLogEvents(events, { eventType: eventType || undefined, senderInstanceId: senderInstanceId || undefined });
  const running = askRunningCounts(events);   // PART 7 — running per-contact ask number per event

  // Unresponded task rows (apply the same sender filter).
  const unrespondedRows = React.useMemo(() => {
    let rows = filterUnrespondedTasks(tasks);
    if (senderInstanceId) rows = rows.filter((t) => t.sender_instance_id === senderInstanceId);
    return rows;
  }, [tasks, senderInstanceId]);

  const busy = unresponded ? tasksLoading : loading;
  const refresh = () => { reload(); reloadTasks(); };

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h3 className="font-bold">لاگ رویدادهای همکاری تیمی</h3>
        <div className="flex gap-2 flex-wrap">
          <select className="input text-xs py-1" value={eventType} onChange={(e) => setEventType(e.target.value)}>
            <option value="">همهٔ رویدادها</option>
            {Object.entries(EVENT_FA).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            <option value={UNRESPONDED}>درخواست‌های بی‌پاسخ</option>
          </select>
          <select className="input text-xs py-1" value={senderInstanceId} onChange={(e) => setSender(e.target.value)}>
            <option value="">همهٔ فرستنده‌ها</option>
            {senders.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
          </select>
          <button className="btn-secondary text-xs" onClick={refresh}>تازه‌سازی</button>
        </div>
      </div>

      {busy ? <Spinner /> : unresponded ? (
        unrespondedRows.length === 0 ? <Empty label="درخواست بی‌پاسخی وجود ندارد." /> : (
          <>
            <p className="text-xs text-slate-400">
              مخاطبانی که درخواست (و شاید یادآوری) دریافت کرده‌اند اما هنوز کار را کامل نکرده‌اند
              (وضعیت: درخواست ارسال شد / یادآوری شد / بدون پاسخ).
            </p>
            <div className="divide-y divide-slate-800 max-h-[70vh] overflow-y-auto">
              {unrespondedRows.map((t) => (
                <div key={t.id} className="py-2 text-sm">
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <span className="flex items-center gap-2 flex-wrap">
                      <span className={`badge ${
                        t.status === "no_response" ? "bg-red-500/20 text-red-300 border-red-500/40"
                        : t.status === "reminded" ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
                        : "bg-sky-500/20 text-sky-300 border-sky-500/40"}`}>
                        {taskStatusFa(t.status)}
                      </span>
                      <span>{t.sender_name || t.sender_instance_id || "—"} ← {t.helper_name || "—"}</span>
                      {t.cold_name && <span className="text-xs text-slate-500">(اکانت سرد: {t.cold_name})</span>}
                    </span>
                    <span className="text-xs text-slate-500">درخواست: {t.asked_shamsi || t.asked_at || "—"}</span>
                  </div>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    {t.reminded_shamsi
                      ? `یادآوری: ${t.reminded_shamsi}${t.reminder_count ? ` (${fa(t.reminder_count)} بار)` : ""}`
                      : "یادآوری: ارسال نشده"}
                  </p>
                </div>
              ))}
            </div>
          </>
        )
      ) : filtered.length === 0 ? <Empty label="رویدادی ثبت نشده." /> : (
        <div className="divide-y divide-slate-800 max-h-[70vh] overflow-y-auto">
          {filtered.map((e) => (
            <div key={e.id} className="py-2 text-sm">
              <div className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-2">
                  <span className="badge bg-slate-700 text-slate-200 border-slate-600">{e.event_fa || EVENT_FA[e.event_type] || e.event_type}</span>
                  <span>{e.from_name || e.from_instance_id || "—"} ← {e.helper_name || e.to_phone || "—"}</span>
                  {e.cold_name && <span className="text-xs text-slate-500">(اکانت سرد: {e.cold_name})</span>}
                </span>
                <span className="text-xs text-slate-500">{e.shamsi || e.created_at}</span>
              </div>
              {(e.message_sent || e.message_received) && (
                <p className="text-xs text-slate-400 mt-1 whitespace-pre-wrap">{e.message_sent || e.message_received}</p>
              )}
              {e.event_type === "ask" && running[e.id] != null && (
                <p className="text-[11px] text-sky-300/80 mt-0.5">{askCountSentence(fa(running[e.id]))}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Panel 4: alerts ───────────────────────────────────────────────────────────
function AlertsPanel() {
  const { data, loading, reload } = useAsync(() => WarmupHelpersApi.threadAlerts(), []);
  const alerts = data?.alerts || [];
  async function ack(a) {
    try { await WarmupHelpersApi.ackThreadAlert(a.id); toast.success("هشدار تأیید شد"); reload(); }
    catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }
  async function resume(a) {
    if (!(await confirmDialog("این گفتگو به‌عنوان مثبت کاذب دوباره فعال شود؟"))) return;
    try { const r = await WarmupHelpersApi.resumeThreadAlert(a.id); toast.success(r.resumed ? "گفتگو دوباره فعال شد" : "هشدار تأیید شد"); reload(); }
    catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }
  return (
    <div className="card space-y-3">
      <h3 className="font-bold">هشدارهای ایمنی (گفتگوهای متوقف‌شده)</h3>
      <p className="text-xs text-slate-400">اگر واژهٔ حساسی در یک گفتگو دیده شود، همان گفتگو متوقف و اینجا فهرست می‌شود. در صورت مثبت کاذب می‌توانید آن را دوباره فعال کنید.</p>
      {loading ? <Spinner /> : alerts.length === 0 ? <Empty label="هشدار بازی وجود ندارد." /> : (
        <div className="divide-y divide-slate-800">
          {alerts.map((a) => (
            <div key={a.id} className="py-2 text-sm flex items-center justify-between gap-2 flex-wrap">
              <div>
                <span className="badge bg-red-500/20 text-red-300 border-red-500/40 mr-2">{a.keyword || "واژهٔ حساس"}</span>
                <span>{a.helper_name || "—"}</span>
                {a.cold_instance_id && <span className="text-xs text-slate-500 mr-2">اکانت سرد: {a.cold_instance_id}</span>}
                {a.message_excerpt && <p className="text-xs text-slate-400 mt-1">{a.message_excerpt}</p>}
              </div>
              <div className="flex gap-1">
                <button className="btn-secondary text-xs" onClick={() => ack(a)}>تأیید</button>
                <button className="btn-primary text-xs" onClick={() => resume(a)}>فعال‌سازی مجدد</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function TeamCollaboration() {
  const [tab, setTab] = React.useState("manage");
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">🤝 همکاری تیمی</h1>
        <p className="text-sm text-slate-400 mt-1">گرم‌سازی اکانت‌های سرد با کمک افراد واقعی — مدیریت فرستنده‌ها، مخاطبان، چرخهٔ ۱۰ روزه، لاگ و هشدارها.</p>
      </div>
      <div className="flex gap-1 border-b border-slate-800 flex-wrap">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-3 py-2 text-sm border-b-2 -mb-px ${tab === t.key ? "border-brand text-brand font-bold" : "border-transparent text-slate-400 hover:text-slate-200"}`}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === "manage" && <ManagePanel />}
      {tab === "dashboard" && <DashboardPanel />}
      {tab === "log" && <LogPanel />}
      {tab === "alerts" && <AlertsPanel />}
    </div>
  );
}
