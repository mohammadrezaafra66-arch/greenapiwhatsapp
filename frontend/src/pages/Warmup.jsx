import React from "react";
import { WarmupApi, WarmupHelpersApi, Accounts } from "../api.js";
import { useAsync, Spinner, Empty, Progress } from "../ui.jsx";
import { toast, confirmDialog } from "../ui/toast.jsx";

const fa = (n) => (n == null ? "—" : String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]));
const timeFa = (iso) => {
  if (!iso) return "—";
  try { return fa(new Date(iso).toLocaleString("fa-IR", { hour: "2-digit", minute: "2-digit", month: "short", day: "numeric" })); }
  catch { return "—"; }
};

const BADGE_CLASS = {
  COOLDOWN: "bg-slate-100 text-slate-600 border-slate-300",
  RECEIVING: "bg-sky-50 text-sky-700 border-sky-200",
  REPLYING: "bg-indigo-50 text-indigo-700 border-indigo-200",
  RAMPING: "bg-amber-50 text-amber-700 border-amber-200",
  MATURING: "bg-violet-50 text-violet-700 border-violet-200",
  GRADUATED: "bg-brand-light text-brand border-brand/30",
  PAUSED: "bg-slate-100 text-slate-600 border-slate-300",
  YELLOWCARD: "bg-yellow-50 text-yellow-700 border-yellow-200",
  BLOCKED_RESET: "bg-red-50 text-red-700 border-red-200",
  ENROLLED: "bg-slate-100 text-slate-600 border-slate-300",
};
const BANNER_CLASS = {
  paused: "bg-slate-100 border-slate-300 text-slate-600",
  yellowcard: "bg-yellow-50 border-yellow-200 text-yellow-700",
  blocked: "bg-red-50 border-red-200 text-red-700",
  insufficient_peers: "bg-amber-50 border-amber-200 text-amber-700",
  no_peer: "bg-amber-50 border-amber-200 text-amber-700",
  // V21 — capacity full (all warm peers at 1:2 cap) + not-connected (pending) notices.
  capacity_full: "bg-amber-50 border-amber-200 text-amber-700",
  not_connected: "bg-orange-50 border-orange-200 text-orange-700",
  breaker: "bg-red-50 border-red-200 text-red-700",
};
// V20 PART 3 — Persian labels for account roles.
const ROLE_LABELS = {
  being_warmed: "در حال گرم‌سازی",
  peer_sender: "فرستندهٔ گرم",
  graduated_peer: "فارغ‌التحصیل (فرستنده)",
  none: "—",
};

// ── V23 — actual warm-up message texts (from warmup_event_log), AI vs fallback ──
function RecentMessages() {
  const [open, setOpen] = React.useState(false);
  const { data, loading, reload } = useAsync(
    () => (open ? WarmupApi.messages(10) : Promise.resolve({ messages: [] })), [open]);
  const msgs = data?.messages || [];

  return (
    <div className="card space-y-2">
      <div className="flex items-center justify-between gap-2">
        <span className="font-bold text-sm">💬 متن پیام‌های گرم‌سازی اخیر</span>
        <div className="flex gap-2">
          {open && <button className="btn-secondary btn-sm" onClick={reload} disabled={loading}>بازخوانی</button>}
          <button className="btn-secondary btn-sm" onClick={() => setOpen((o) => !o)}>
            {open ? "بستن" : "نمایش متن پیام‌ها"}
          </button>
        </div>
      </div>
      {open && (loading ? <Spinner /> : msgs.length === 0 ? (
        <Empty label="هنوز پیام گرم‌سازی‌ای ارسال نشده." />
      ) : (
        <div className="table-wrap">
          <table className="w-full text-xs">
            <thead className="text-muted"><tr>
              <th className="text-right p-1">زمان</th>
              <th className="text-right p-1">از → به</th>
              <th className="text-right p-1">متن</th>
              <th className="text-right p-1">منبع</th>
            </tr></thead>
            <tbody>
              {msgs.map((m, i) => (
                <tr key={i} className="border-t border-line align-top">
                  <td className="p-1 whitespace-nowrap text-muted">{timeFa(m.at)}</td>
                  <td className="p-1 whitespace-nowrap text-muted">{m.from_name} ← {m.to_name}</td>
                  <td className="p-1 text-ink">{m.text || "—"}</td>
                  <td className="p-1 whitespace-nowrap">
                    <span className={`badge text-[10px] ${m.source === "ai"
                      ? "bg-brand-light text-brand border-brand/30"
                      : "bg-slate-100 text-slate-600 border-slate-300"}`}>
                      {m.source === "ai" ? "🤖 هوش مصنوعی" : "📝 مخزن"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}

// ── V17 — mesh warm-up dashboard (automatic, AI-driven, mesh-based) ──────────
function MeshDashboard() {
  const dash = useAsync(() => WarmupApi.meshDashboard(), []);
  const accs = useAsync(() => Accounts.list(), []);
  const [eventsFor, setEventsFor] = React.useState(null);
  const ev = useAsync(() => (eventsFor ? WarmupApi.events(eventsFor) : Promise.resolve({ events: [] })), [eventsFor]);

  const byInstance = React.useMemo(() => {
    const m = {};
    (accs.data || []).forEach((a) => { m[a.instance_id] = a; });
    return m;
  }, [accs.data]);

  const numbers = dash.data?.numbers || [];
  const gday = dash.data?.graduate_day || 25;

  async function ctl(fnName, instanceId, confirmMsg) {
    const acc = byInstance[instanceId];
    if (!acc) return toast.error("اکانت متناظر یافت نشد");
    if (confirmMsg && !(await confirmDialog(confirmMsg))) return;
    try { await WarmupApi[fnName](acc.id); toast.success("انجام شد"); dash.reload(); }
    catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }
  async function startAllMesh() {
    if (!(await confirmDialog("گرم‌سازی مش برای همهٔ اکانت‌های فعال ثبت‌نشده آغاز شود؟"))) return;
    try { const r = await WarmupApi.meshStartAll(); toast.success(`${fa(r.started)} شماره وارد گرم‌سازی شد`); dash.reload(); }
    catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }
  async function stopAllMesh() {
    if (!(await confirmDialog("گرم‌سازی مش برای همهٔ شماره‌ها متوقف شود؟"))) return;
    try { const r = await WarmupApi.meshStopAll(); toast.success(`${fa(r.stopped)} شماره متوقف شد`); dash.reload(); }
    catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }
  async function resetBreaker() {
    try { await WarmupApi.resetBreaker(); toast.success("بریکر بازنشانی شد"); dash.reload(); }
    catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="text-2xl font-bold">🔥 گرم‌سازی خودکار (مش)</h2>
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={startAllMesh}>شروع گرم‌سازی همه</button>
          <button className="btn-secondary" onClick={stopAllMesh}>⏹ توقف همه</button>
        </div>
      </div>

      {dash.data?.global_banner && (
        <div className={`card text-sm ${BANNER_CLASS.breaker}`}>
          <div className="flex items-center justify-between gap-2">
            <span>⛔ {dash.data.global_banner.message}</span>
            <button className="btn-danger btn-sm" onClick={resetBreaker}>بازنشانی بریکر</button>
          </div>
        </div>
      )}

      {/* V41 Path B — pending auto-apply status for the recovery target (shown until it is
          enrolled in recovery mode; reflects the last daily recheck, no action taken here). */}
      {dash.data?.recovery_pending?.waiting && (
        <div className="card text-sm bg-amber-50 border-amber-200 text-amber-700">
          <div className="font-medium">⏳ {dash.data.recovery_pending.title}</div>
          <div className="text-xs mt-1">{dash.data.recovery_pending.message}</div>
        </div>
      )}

      {/* V20 PART 3 — no-peer notice + warm-sender roster */}
      {!dash.loading && dash.data?.has_eligible_peer === false && numbers.length > 0 && (
        <div className={`card text-sm ${BANNER_CLASS.no_peer}`}>
          ⚠️ {dash.data.no_peer_notice}
        </div>
      )}
      {(dash.data?.roles || []).some((r) => r.role === "peer_sender" || r.role === "graduated_peer") && (
        <div className="card text-xs">
          <span className="text-muted">فرستنده‌های گرم: </span>
          {dash.data.roles.filter((r) => r.role === "peer_sender" || r.role === "graduated_peer").map((r) => (
            <span key={r.instance_id} className="badge bg-sky-50 text-sky-700 border-sky-200 mx-1">
              📤 {r.name}
            </span>
          ))}
        </div>
      )}

      {/* V21 PART 4 — per-warm-peer capacity roster (n از cap ظرفیت) */}
      {(dash.data?.peer_load || []).length > 0 && (
        <div className="card text-xs space-y-1">
          <div className="text-muted">
            ظرفیت اکانت‌های گرم (هر اکانت گرم حداکثر {fa(dash.data?.max_cold_per_warm_peer || 2)} شمارهٔ سرد):
          </div>
          <div className="flex flex-wrap gap-2">
            {dash.data.peer_load.map((p) => (
              <span key={p.instance_id}
                className={`badge ${p.full ? "bg-amber-50 text-amber-700 border-amber-200"
                  : "bg-brand-light text-brand border-brand/30"}`}>
                {p.full ? "🟠" : "🟢"} {byInstance[p.instance_id]?.name || p.name}: {fa(p.cold_count)} از {fa(p.cap)} ظرفیت
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="card bg-sky-50 border-sky-200 text-sky-700 text-xs">
        هر شمارهٔ جدید به‌صورت خودکار و انسانی گرم می‌شود: ۲۴ساعت آماده‌سازی، سپس دریافت پیام از اکانت‌های گرم شما، سپس پاسخ‌دهی و افزایش تدریجی تا فارغ‌التحصیلی (حدود روز {fa(gday)}). فقط با اکانت‌های خودتان که مخاطب دوطرفه شده‌اند پیام رد و بدل می‌شود — هرگز با غریبه.
      </div>

      <RecentMessages />

      {dash.loading ? <Spinner /> : numbers.length === 0 ? (
        <Empty label="هیچ شماره‌ای در گرم‌سازی مش نیست. در صفحهٔ حساب‌ها گرم‌سازی خودکار را روشن کنید یا «شروع گرم‌سازی همه» را بزنید." />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {numbers.map((n) => (
            <div key={n.instance_id} className="card space-y-2">
              <div className="flex items-center justify-between gap-2">
                <span className="font-bold">
                  {byInstance[n.instance_id]?.name || n.phone || n.instance_id}
                  <span className="badge bg-slate-100 text-slate-600 border-slate-300 mx-1 text-[10px]">
                    {n.role === "graduated_peer" ? ROLE_LABELS.graduated_peer : ROLE_LABELS.being_warmed}
                  </span>
                </span>
                <span className="flex items-center gap-1">
                  {/* V41 PART 5 — distinct badge for a mesh-recovery re-warm (Green API's 10-day sequence) */}
                  {n.recovery_mode && (
                    <span className="badge bg-purple-50 text-purple-700 border-purple-200 text-[10px]">
                      {n.recovery_badge}
                    </span>
                  )}
                  <span className={`badge ${BADGE_CLASS[n.state] || ""}`}>{n.badge}</span>
                </span>
              </div>

              {n.banner && (
                <div className={`rounded-lg border px-2 py-1 text-xs ${BANNER_CLASS[n.banner.type] || ""}`}>
                  {n.banner.message}
                </div>
              )}

              <p className="text-xs text-muted">روز {fa(n.day_index)} — پیشرفت تا فارغ‌التحصیلی</p>
              <Progress value={n.progress_pct} max={100} color="bg-brand" />

              {/* V41 PART 5 — restart-on-disruption counter: how many times the recovery cycle was
                  reset to Day 1, with the last reason. Only shown for a recovery number that reset. */}
              {n.recovery_mode && n.recovery_reset_count > 0 && (
                <p className="text-xs text-amber-700">
                  {n.recovery_reset_label}: {fa(n.recovery_reset_count)}
                  {n.recovery_last_reset_reason ? ` (${n.recovery_last_reset_reason})` : ""}
                </p>
              )}

              <div className="grid grid-cols-2 gap-2 text-xs text-muted">
                <span>ارسال امروز: {fa(n.sent_today)}{n.day_target ? ` / ${fa(n.day_target)}` : ""}</span>
                <span>دریافت امروز: {fa(n.received_today)}</span>
                <span className={n.reply_ratio_ok ? "text-brand" : "text-amber-700"}>
                  نسبت پاسخ: {fa(Math.round((n.reply_ratio || 0) * 100))}٪
                </span>
                <span>اقدام بعدی: {timeFa(n.next_action_at)}</span>
              </div>

              <p className="text-xs text-muted">
                همتاهای مش: {fa(n.messageable_peer_count)} فعال از {fa(n.peer_count)}
                {/* V21 PART 4 — which warm peer warms this number, or waiting-for-capacity */}
                {n.assigned_peer
                  ? <span className="text-sky-700"> · فرستنده: {byInstance[n.assigned_peer]?.name || n.assigned_peer}</span>
                  : n.capacity_full
                    ? <span className="text-amber-700"> · در انتظار ظرفیت اکانت گرم</span>
                    : null}
              </p>

              {/* V19 — group-based warm-up placements (additive track) */}
              {n.group_warmup && (n.group_warmup.placements?.length > 0 || n.group_warmup.counts) && (
                <div className="text-xs text-muted border-t border-line pt-1">
                  <div className="flex items-center justify-between">
                    <span>گروه‌ها:
                      {" "}<span className="text-brand">{fa(n.group_warmup.counts?.added || 0)} افزوده</span>
                      {(n.group_warmup.counts?.pending || 0) > 0 && <span className="text-amber-700"> · {fa(n.group_warmup.counts.pending)} در انتظار</span>}
                      {(n.group_warmup.counts?.failed || 0) > 0 && <span className="text-red-700"> · {fa(n.group_warmup.counts.failed)} ناموفق</span>}
                    </span>
                    {n.group_warmup.next_action_at && <span>گروه بعدی: {timeFa(n.group_warmup.next_action_at)}</span>}
                  </div>
                  {(n.group_warmup.placements || []).slice(0, 4).map((p, i) => (
                    <div key={i} className="flex justify-between gap-2 text-[11px] text-muted">
                      <span className="truncate">{p.group_id}</span>
                      <span className={p.status === "added" ? "text-brand" : p.status === "failed" ? "text-red-700" : "text-amber-700"}>{p.status}</span>
                    </div>
                  ))}
                </div>
              )}

              <div className="flex flex-wrap gap-1 pt-1">
                {n.is_enabled && n.state !== "PAUSED"
                  ? <button className="btn-secondary btn-sm" onClick={() => ctl("pause", n.instance_id, "این شماره موقتاً متوقف شود؟")}>توقف</button>
                  : <button className="btn-secondary btn-sm" onClick={() => ctl("resume", n.instance_id)}>ادامه</button>}
                <button className="btn-secondary btn-sm" onClick={() => ctl("restart", n.instance_id, "گرم‌سازی این شماره از روز اول شروع شود؟")}>شروع مجدد</button>
                <button className="btn-secondary btn-sm" onClick={() => {
                  const accId = byInstance[n.instance_id]?.id;
                  setEventsFor(eventsFor === accId ? null : accId);
                }}>رویدادها</button>
              </div>

              {eventsFor && byInstance[n.instance_id]?.id === eventsFor && (
                <div className="mt-2 max-h-40 overflow-auto text-xs bg-canvas rounded p-2 space-y-1">
                  {ev.loading ? <Spinner /> : (ev.data?.events || []).length === 0
                    ? <span className="text-muted">رویدادی ثبت نشده</span>
                    : ev.data.events.map((e, i) => (
                      <div key={i} className="flex justify-between gap-2 border-b border-line pb-1">
                        <span className="text-ink">{e.event_type}</span>
                        <span className="text-muted">{timeFa(e.created_at)}</span>
                      </div>
                    ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── V19 — group-based warm-up: pick a warm account's admin groups as targets ──
function GroupTargets() {
  const wa = useAsync(() => WarmupApi.warmAccounts(), []);
  const [acctId, setAcctId] = React.useState("");
  const groups = useAsync(() => (acctId ? WarmupApi.adminGroups(acctId) : Promise.resolve({ groups: [] })), [acctId]);
  const targets = useAsync(() => (acctId ? WarmupApi.groupTargets(acctId) : Promise.resolve({ targets: [] })), [acctId]);

  const selected = React.useMemo(() => {
    const m = {};
    (targets.data?.targets || []).forEach((t) => { m[t.group_id] = t.is_selected; });
    return m;
  }, [targets.data]);

  async function toggle(g, checked) {
    try {
      await WarmupApi.setGroupTarget(acctId, { group_id: g.group_id, group_subject: g.subject, is_selected: checked });
      targets.reload();
      toast.success(checked ? "گروه به مقصدها اضافه شد" : "گروه حذف شد");
    } catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }

  const accts = wa.data?.accounts || [];
  return (
    <div className="space-y-3">
      <h3 className="text-lg font-bold">افزودن به گروه‌های اکانت گرم</h3>
      <p className="text-xs text-muted">
        یک اکانت گرم را انتخاب کنید تا گروه‌هایی که در آن‌ها ادمین است نمایش داده شود. گروه‌های انتخاب‌شده به‌صورت خودکار و آهسته
        (طبق زمان‌بندی ضدبن) برای قراردادن شماره‌های جدید در آن‌ها استفاده می‌شوند — فقط پس از روشن‌بودن «گرم‌سازی هوشمند».
      </p>
      <select className="input" value={acctId} onChange={(e) => setAcctId(e.target.value)}>
        <option value="">— انتخاب اکانت گرم —</option>
        {accts.map((a) => (
          <option key={a.id} value={a.id}>{a.name}{a.is_warm ? " ✅" : ""}</option>
        ))}
      </select>
      {acctId && (groups.loading ? <Spinner /> : (groups.data?.groups || []).length === 0 ? (
        <Empty label="این اکانت در هیچ گروهی ادمین نیست" />
      ) : (
        <div className="card divide-y divide-line">
          {groups.data.groups.map((g) => (
            <label key={g.group_id} className="flex items-center justify-between gap-2 py-2 text-sm cursor-pointer">
              <span className="flex items-center gap-2">
                <input type="checkbox" checked={!!selected[g.group_id]} onChange={(e) => toggle(g, e.target.checked)} />
                {g.subject || g.group_id}
              </span>
              <span className="text-xs text-muted">{fa(g.size)} عضو</span>
            </label>
          ))}
        </div>
      ))}
    </div>
  );
}

// ── V19 — manual link vault (Green API cannot auto-join by invite link) ──────
function LinkVault() {
  const v = useAsync(() => WarmupApi.linkVault(), []);
  const [form, setForm] = React.useState({ group_name: "", invite_link: "", notes: "" });

  async function add() {
    if (!form.invite_link.trim()) return toast.error("لینک دعوت لازم است");
    try { await WarmupApi.addLink(form); setForm({ group_name: "", invite_link: "", notes: "" }); v.reload(); }
    catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }
  async function del(id) {
    if (!(await confirmDialog("این لینک حذف شود؟"))) return;
    try { await WarmupApi.deleteLink(id); v.reload(); } catch (e) { toast.error(e.message); }
  }

  return (
    <div className="space-y-3">
      <h3 className="text-lg font-bold">مخزن لینک گروه‌ها (عضویت دستی)</h3>
      <div className="card bg-amber-50 border-amber-200 text-amber-700 text-xs">
        {v.data?.notice || "توجه: عضویت در این گروه‌ها فقط به‌صورت دستی روی گوشی ممکن است — سرویس اجازه‌ی عضویت خودکار با لینک را نمی‌دهد. این لینک‌ها اینجا ذخیره می‌شوند تا پرسنل دستی عضو شوند."}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        <input className="input" placeholder="نام گروه" value={form.group_name} onChange={(e) => setForm({ ...form, group_name: e.target.value })} />
        <input className="input" placeholder="لینک دعوت (chat.whatsapp.com/…)" value={form.invite_link} onChange={(e) => setForm({ ...form, invite_link: e.target.value })} />
        <div className="flex gap-2">
          <input className="input flex-1" placeholder="یادداشت" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          <button className="btn-primary" onClick={add}>افزودن</button>
        </div>
      </div>
      {v.loading ? <Spinner /> : (v.data?.links || []).length === 0 ? (
        <Empty label="هنوز لینکی ذخیره نشده است." />
      ) : (
        <div className="card divide-y divide-line">
          {v.data.links.map((l) => (
            <div key={l.id} className="flex items-center justify-between gap-2 py-2 text-sm">
              <div className="min-w-0">
                <div className="font-bold truncate">{l.group_name || "—"}</div>
                <a href={l.invite_link} target="_blank" rel="noreferrer" className="text-sky-700 text-xs break-all">{l.invite_link}</a>
                {l.notes && <div className="text-xs text-muted">{l.notes}</div>}
              </div>
              <button className="btn-danger btn-sm shrink-0" onClick={() => del(l.id)}>حذف</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// V16 PART 5 — smart warm-up dashboard + phrase pool + batch controls.
// ── V25 PART 1 — "human helpers" warm-up assist (≤25 known people) ──────────
const HELPER_STATUS_FA = {
  pending: { fa: "در انتظار", cls: "bg-slate-100 text-slate-600 border-slate-300" },
  asked: { fa: "درخواست‌شده", cls: "bg-sky-50 text-sky-700 border-sky-200" },
  reminded: { fa: "یادآوری‌شده", cls: "bg-amber-50 text-amber-700 border-amber-200" },
  done: { fa: "انجام‌شد ✓", cls: "bg-brand-light text-brand border-brand/30" },
  skipped: { fa: "رد‌شده", cls: "bg-slate-100 text-slate-600 border-slate-300" },
};

const EMPTY_HELPER_FORM = {
  name: "", phone: "", job_title: "", years_experience: "",
  personal_benefit_note: "", phone_secondary: "",
};

function HumanHelpers() {
  const { data, loading, reload } = useAsync(() => WarmupHelpersApi.list(), []);
  const tasksAsync = useAsync(() => WarmupHelpersApi.tasks(), []);
  const [form, setForm] = React.useState(EMPTY_HELPER_FORM);
  const [showTasks, setShowTasks] = React.useState(false);
  const [showProfile, setShowProfile] = React.useState(false);

  const enabled = data?.enabled;
  const active = data?.active_count ?? 0;
  const softWarning = data?.soft_warning;   // V28 non-blocking banner (no hard cap in V29)
  const helpers = data?.helpers || [];

  async function toggle() {
    try {
      const r = await WarmupHelpersApi.toggle(!enabled);
      toast.success(r.enabled ? "«همکاری تیمی» روشن شد" : "خاموش شد");
      reload();
    } catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }
  async function add() {
    if (!form.name.trim() || !form.phone.trim()) return toast.error("نام و شماره لازم است");
    try {
      await WarmupHelpersApi.create({
        name: form.name.trim(), phone: form.phone.trim(),
        job_title: form.job_title.trim() || null,
        years_experience: form.years_experience === "" ? null : Number(form.years_experience),
        personal_benefit_note: form.personal_benefit_note.trim() || null,
        phone_secondary: form.phone_secondary.trim() || null,
        require_full_name: true,   // V29 «همکاری تیمی» — full name (first + last) mandatory
      });
      setForm(EMPTY_HELPER_FORM);
      reload();
    } catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }
  async function del(h) {
    if (!(await confirmDialog(`«${h.name}» حذف شود؟`))) return;
    try { await WarmupHelpersApi.remove(h.id); reload(); }
    catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }
  async function toggleActive(h) {
    try { await WarmupHelpersApi.update(h.id, { is_active: !h.is_active }); reload(); }
    catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h3 className="text-lg font-bold">🤝 همکاری تیمی (گرم‌سازی با افراد واقعی)</h3>
          <p className="text-xs text-muted mt-1">
            هر فرستنده مجموعه‌ی مخاطبان مخصوص خودش را دارد. برای هر مخاطب نام کامل (اجباری) و در صورت تمایل
            سمت شغلی، سابقهٔ تخصصی و توضیح «چه سودی برایش دارد» را ثبت کنید تا پیام‌ها شخصی‌سازی شوند.
            ارسال‌ها آهسته و کنترل‌شده است (بدون سقف تعداد، اما با محدودیت سرعت).
          </p>
        </div>
        <button className={`text-sm px-3 py-1.5 rounded font-bold border ${enabled
          ? "bg-brand-light text-brand border-brand/30"
          : "bg-slate-100 text-slate-600 border-slate-300"}`} onClick={toggle} disabled={loading}>
          {enabled ? "روشن ✓" : "خاموش"}
        </button>
      </div>

      <div className="flex items-center gap-2 text-sm flex-wrap">
        <span className="badge bg-slate-100 text-slate-600 border-slate-300">{fa(active)} مخاطب فعال</span>
        {softWarning && <span className="text-xs text-amber-700">{softWarning}</span>}
      </div>

      <div className="space-y-2">
        <div className="flex gap-2 flex-wrap">
          <input className="input flex-1 min-w-[140px]" placeholder="نام و نام خانوادگی (اجباری)" value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input className="input flex-1 min-w-[140px]" placeholder="شماره (مثل ۹۸۹۱۲…)" value={form.phone}
            onChange={(e) => setForm({ ...form, phone: e.target.value })}
            onKeyDown={(e) => e.key === "Enter" && add()} />
          <button className="btn-secondary btn-sm" onClick={() => setShowProfile((s) => !s)}>
            {showProfile ? "بستن مشخصات" : "مشخصات بیشتر"}
          </button>
          <button className="btn-primary" onClick={add}>افزودن</button>
        </div>
        {showProfile && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <input className="input" placeholder="سمت در آفراکالا" value={form.job_title}
              onChange={(e) => setForm({ ...form, job_title: e.target.value })} />
            <input className="input" placeholder="سابقهٔ تخصصی (سال)" value={form.years_experience}
              onChange={(e) => setForm({ ...form, years_experience: e.target.value.replace(/[^0-9۰-۹]/g, "") })} />
            <input className="input" placeholder="شماره کاری (اختیاری)" value={form.phone_secondary}
              onChange={(e) => setForm({ ...form, phone_secondary: e.target.value })} />
            <input className="input" placeholder="این سیستم چه سودی برای او دارد؟" value={form.personal_benefit_note}
              onChange={(e) => setForm({ ...form, personal_benefit_note: e.target.value })} />
          </div>
        )}
      </div>

      {loading ? <Spinner /> : helpers.length === 0 ? (
        <Empty label="هنوز مخاطبی اضافه نشده." />
      ) : (
        <div className="divide-y divide-line">
          {helpers.map((h) => (
            <div key={h.id} className="flex items-center justify-between gap-2 py-2 text-sm">
              <div>
                <span className={h.is_active ? "font-bold" : "text-muted line-through"}>{h.name}</span>
                <span className="text-xs text-muted font-mono mr-2">{fa(h.phone)}</span>
                {h.job_title && <span className="text-xs text-sky-700 mr-2">{h.job_title}</span>}
                {h.years_experience != null && <span className="text-xs text-muted mr-1">({fa(h.years_experience)} سال)</span>}
                {h.phone_secondary && <span className="text-xs text-muted font-mono mr-2">کاری: {fa(h.phone_secondary)}</span>}
              </div>
              <div className="flex gap-1">
                <button className={`badge ${h.is_active ? "bg-brand-light text-brand border-brand/30" : "bg-slate-100 text-slate-600 border-slate-300"}`}
                  onClick={() => toggleActive(h)}>{h.is_active ? "فعال" : "غیرفعال"}</button>
                <button className="btn-danger btn-sm" onClick={() => del(h)}>حذف</button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div>
        <button className="btn-secondary btn-sm" onClick={() => { setShowTasks((s) => !s); if (!showTasks) tasksAsync.reload(); }}>
          {showTasks ? "بستن وضعیت درخواست‌ها" : "نمایش وضعیت درخواست‌ها (چه کسی سلام کرد)"}
        </button>
        {showTasks && (
          <div className="mt-2">
            {tasksAsync.loading ? <Spinner /> : (tasksAsync.data?.tasks || []).length === 0 ? (
              <Empty label="هنوز درخواستی ثبت نشده." />
            ) : (
              <div className="card divide-y divide-line max-h-72 overflow-y-auto">
                {(tasksAsync.data.tasks || []).map((t) => {
                  const s = HELPER_STATUS_FA[t.status] || HELPER_STATUS_FA.pending;
                  return (
                    <div key={t.id} className="flex items-center justify-between gap-2 py-2 text-xs">
                      <span>{t.helper_name || "—"} → <span className="text-muted">{t.cold_name || t.cold_instance_id}</span></span>
                      <span className={`badge ${s.cls}`}>{s.fa}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function Warmup() {
  const dash = useAsync(() => WarmupApi.dashboard(), []);
  const ph = useAsync(() => WarmupApi.phrases(), []);
  const [newPhrase, setNewPhrase] = React.useState("");

  async function startAll() {
    if (!(await confirmDialog("گرم‌سازی خودکار برای همه شماره‌های جدید روشن شود؟"))) return;
    try { const r = await WarmupApi.startAll(); toast.success(`گرم‌سازی برای ${fa(r.started)} شماره روشن شد`); dash.reload(); }
    catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }
  async function stopAll() {
    if (!(await confirmDialog("گرم‌سازی خودکار برای همه شماره‌ها خاموش شود؟"))) return;
    try { const r = await WarmupApi.stopAll(); toast.success(`گرم‌سازی ${fa(r.stopped)} شماره خاموش شد`); dash.reload(); }
    catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }
  async function addPhrase() {
    if (!newPhrase.trim()) return;
    try { await WarmupApi.createPhrase({ text: newPhrase.trim() }); setNewPhrase(""); ph.reload(); }
    catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }

  const accounts = dash.data?.accounts || [];

  return (
    <div className="space-y-6">
      {/* V17 — automatic AI-driven mesh warm-up */}
      <MeshDashboard />

      {/* V25 PART 1 — automatic "human helpers" warm-up assist (≤25 known people) */}
      <HumanHelpers />

      {/* V19 — group-based warm-up (additive to the mesh) */}
      <GroupTargets />
      <LinkVault />

      {/* Phrase pool editor (shared by both warm-up engines) */}
      <div>
        <h3 className="text-lg font-bold mb-2">عبارت‌های گرم‌سازی</h3>
        <p className="text-sm text-muted mb-2">پیام‌های کوتاه و طبیعی که هنگام گرم‌سازی به‌صورت تصادفی استفاده می‌شوند (علاوه بر تولید هوش مصنوعی و مخزن آمادهٔ داخلی).</p>
        <div className="flex gap-2 mb-3">
          <input className="input flex-1" placeholder="عبارت جدید…" value={newPhrase} onChange={(e) => setNewPhrase(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addPhrase()} />
          <button className="btn-primary" onClick={addPhrase}>افزودن</button>
        </div>
        {ph.loading ? <Spinner /> : (
          <div className="card divide-y divide-line">
            {(ph.data || []).map((p) => (
              <div key={p.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                <span className={p.is_active ? "" : "text-muted line-through"}>{p.text}</span>
                <div className="flex gap-1">
                  <button className={`badge ${p.is_active ? "bg-brand-light text-brand border-brand/30" : "bg-slate-100 text-slate-600 border-slate-300"}`}
                    onClick={async () => { await WarmupApi.updatePhrase(p.id, { text: p.text, is_active: !p.is_active }); ph.reload(); }}>
                    {p.is_active ? "فعال" : "غیرفعال"}
                  </button>
                  <button className="btn-danger btn-sm" onClick={async () => { if (await confirmDialog("این عبارت حذف شود؟")) { await WarmupApi.deletePhrase(p.id); ph.reload(); } }}>حذف</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
