import React from "react";
import { WarmupApi, Accounts } from "../api.js";
import { useAsync, Spinner, Empty, Progress } from "../ui.jsx";
import { toast, confirmDialog } from "../ui/toast.jsx";

const fa = (n) => (n == null ? "—" : String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]));
const timeFa = (iso) => {
  if (!iso) return "—";
  try { return fa(new Date(iso).toLocaleString("fa-IR", { hour: "2-digit", minute: "2-digit", month: "short", day: "numeric" })); }
  catch { return "—"; }
};

const BADGE_CLASS = {
  COOLDOWN: "bg-slate-500/20 text-slate-300 border-slate-500/40",
  RECEIVING: "bg-sky-500/20 text-sky-300 border-sky-500/40",
  REPLYING: "bg-indigo-500/20 text-indigo-300 border-indigo-500/40",
  RAMPING: "bg-amber-500/20 text-amber-300 border-amber-500/40",
  MATURING: "bg-violet-500/20 text-violet-300 border-violet-500/40",
  GRADUATED: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  PAUSED: "bg-slate-600/30 text-slate-400 border-slate-600",
  YELLOWCARD: "bg-yellow-500/20 text-yellow-300 border-yellow-500/40",
  BLOCKED_RESET: "bg-rose-500/20 text-rose-300 border-rose-500/40",
  ENROLLED: "bg-slate-500/20 text-slate-300 border-slate-500/40",
};
const BANNER_CLASS = {
  paused: "bg-slate-600/20 border-slate-600/40 text-slate-300",
  yellowcard: "bg-yellow-500/10 border-yellow-500/30 text-yellow-200",
  blocked: "bg-rose-500/10 border-rose-500/30 text-rose-200",
  insufficient_peers: "bg-amber-500/10 border-amber-500/30 text-amber-200",
  no_peer: "bg-amber-500/10 border-amber-500/30 text-amber-200",
  // V21 — capacity full (all warm peers at 1:2 cap) + not-connected (pending) notices.
  capacity_full: "bg-amber-500/10 border-amber-500/30 text-amber-200",
  not_connected: "bg-orange-500/10 border-orange-500/30 text-orange-200",
  breaker: "bg-rose-600/15 border-rose-600/40 text-rose-200",
};
// V20 PART 3 — Persian labels for account roles.
const ROLE_LABELS = {
  being_warmed: "در حال گرم‌سازی",
  peer_sender: "فرستندهٔ گرم",
  graduated_peer: "فارغ‌التحصیل (فرستنده)",
  none: "—",
};

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
            <button className="btn-danger text-xs" onClick={resetBreaker}>بازنشانی بریکر</button>
          </div>
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
          <span className="text-slate-400">فرستنده‌های گرم: </span>
          {dash.data.roles.filter((r) => r.role === "peer_sender" || r.role === "graduated_peer").map((r) => (
            <span key={r.instance_id} className="badge bg-sky-500/20 text-sky-300 border-sky-500/40 mx-1">
              📤 {r.name}
            </span>
          ))}
        </div>
      )}

      {/* V21 PART 4 — per-warm-peer capacity roster (n از cap ظرفیت) */}
      {(dash.data?.peer_load || []).length > 0 && (
        <div className="card text-xs space-y-1">
          <div className="text-slate-400">
            ظرفیت اکانت‌های گرم (هر اکانت گرم حداکثر {fa(dash.data?.max_cold_per_warm_peer || 2)} شمارهٔ سرد):
          </div>
          <div className="flex flex-wrap gap-2">
            {dash.data.peer_load.map((p) => (
              <span key={p.instance_id}
                className={`badge ${p.full ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
                  : "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"}`}>
                {p.full ? "🟠" : "🟢"} {byInstance[p.instance_id]?.name || p.name}: {fa(p.cold_count)} از {fa(p.cap)} ظرفیت
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="card bg-sky-500/10 border-sky-500/30 text-sky-200 text-xs">
        هر شمارهٔ جدید به‌صورت خودکار و انسانی گرم می‌شود: ۲۴ساعت آماده‌سازی، سپس دریافت پیام از اکانت‌های گرم شما، سپس پاسخ‌دهی و افزایش تدریجی تا فارغ‌التحصیلی (حدود روز {fa(gday)}). فقط با اکانت‌های خودتان که مخاطب دوطرفه شده‌اند پیام رد و بدل می‌شود — هرگز با غریبه.
      </div>

      {dash.loading ? <Spinner /> : numbers.length === 0 ? (
        <Empty label="هیچ شماره‌ای در گرم‌سازی مش نیست. در صفحهٔ حساب‌ها گرم‌سازی خودکار را روشن کنید یا «شروع گرم‌سازی همه» را بزنید." />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {numbers.map((n) => (
            <div key={n.instance_id} className="card space-y-2">
              <div className="flex items-center justify-between gap-2">
                <span className="font-bold">
                  {byInstance[n.instance_id]?.name || n.phone || n.instance_id}
                  <span className="badge bg-slate-500/20 text-slate-300 border-slate-500/40 mx-1 text-[10px]">
                    {n.role === "graduated_peer" ? ROLE_LABELS.graduated_peer : ROLE_LABELS.being_warmed}
                  </span>
                </span>
                <span className={`badge ${BADGE_CLASS[n.state] || ""}`}>{n.badge}</span>
              </div>

              {n.banner && (
                <div className={`rounded-lg border px-2 py-1 text-xs ${BANNER_CLASS[n.banner.type] || ""}`}>
                  {n.banner.message}
                </div>
              )}

              <p className="text-xs text-slate-400">روز {fa(n.day_index)} — پیشرفت تا فارغ‌التحصیلی</p>
              <Progress value={n.progress_pct} max={100} color="bg-emerald-500" />

              <div className="grid grid-cols-2 gap-2 text-xs text-slate-400">
                <span>ارسال امروز: {fa(n.sent_today)}{n.day_target ? ` / ${fa(n.day_target)}` : ""}</span>
                <span>دریافت امروز: {fa(n.received_today)}</span>
                <span className={n.reply_ratio_ok ? "text-emerald-300" : "text-amber-300"}>
                  نسبت پاسخ: {fa(Math.round((n.reply_ratio || 0) * 100))}٪
                </span>
                <span>اقدام بعدی: {timeFa(n.next_action_at)}</span>
              </div>

              <p className="text-xs text-slate-400">
                همتاهای مش: {fa(n.messageable_peer_count)} فعال از {fa(n.peer_count)}
                {/* V21 PART 4 — which warm peer warms this number, or waiting-for-capacity */}
                {n.assigned_peer
                  ? <span className="text-sky-300"> · فرستنده: {byInstance[n.assigned_peer]?.name || n.assigned_peer}</span>
                  : n.capacity_full
                    ? <span className="text-amber-300"> · در انتظار ظرفیت اکانت گرم</span>
                    : null}
              </p>

              {/* V19 — group-based warm-up placements (additive track) */}
              {n.group_warmup && (n.group_warmup.placements?.length > 0 || n.group_warmup.counts) && (
                <div className="text-xs text-slate-400 border-t border-slate-800 pt-1">
                  <div className="flex items-center justify-between">
                    <span>گروه‌ها:
                      {" "}<span className="text-emerald-300">{fa(n.group_warmup.counts?.added || 0)} افزوده</span>
                      {(n.group_warmup.counts?.pending || 0) > 0 && <span className="text-amber-300"> · {fa(n.group_warmup.counts.pending)} در انتظار</span>}
                      {(n.group_warmup.counts?.failed || 0) > 0 && <span className="text-rose-300"> · {fa(n.group_warmup.counts.failed)} ناموفق</span>}
                    </span>
                    {n.group_warmup.next_action_at && <span>گروه بعدی: {timeFa(n.group_warmup.next_action_at)}</span>}
                  </div>
                  {(n.group_warmup.placements || []).slice(0, 4).map((p, i) => (
                    <div key={i} className="flex justify-between gap-2 text-[11px] text-slate-500">
                      <span className="truncate">{p.group_id}</span>
                      <span className={p.status === "added" ? "text-emerald-400" : p.status === "failed" ? "text-rose-400" : "text-amber-400"}>{p.status}</span>
                    </div>
                  ))}
                </div>
              )}

              <div className="flex flex-wrap gap-1 pt-1">
                {n.is_enabled && n.state !== "PAUSED"
                  ? <button className="btn-secondary text-xs" onClick={() => ctl("pause", n.instance_id, "این شماره موقتاً متوقف شود؟")}>توقف</button>
                  : <button className="btn-secondary text-xs" onClick={() => ctl("resume", n.instance_id)}>ادامه</button>}
                <button className="btn-secondary text-xs" onClick={() => ctl("restart", n.instance_id, "گرم‌سازی این شماره از روز اول شروع شود؟")}>شروع مجدد</button>
                <button className="btn-secondary text-xs" onClick={() => {
                  const accId = byInstance[n.instance_id]?.id;
                  setEventsFor(eventsFor === accId ? null : accId);
                }}>رویدادها</button>
              </div>

              {eventsFor && byInstance[n.instance_id]?.id === eventsFor && (
                <div className="mt-2 max-h-40 overflow-auto text-xs bg-slate-900/50 rounded p-2 space-y-1">
                  {ev.loading ? <Spinner /> : (ev.data?.events || []).length === 0
                    ? <span className="text-slate-500">رویدادی ثبت نشده</span>
                    : ev.data.events.map((e, i) => (
                      <div key={i} className="flex justify-between gap-2 border-b border-slate-800 pb-1">
                        <span className="text-slate-300">{e.event_type}</span>
                        <span className="text-slate-500">{timeFa(e.created_at)}</span>
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
      <p className="text-xs text-slate-400">
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
        <div className="card divide-y divide-slate-800">
          {groups.data.groups.map((g) => (
            <label key={g.group_id} className="flex items-center justify-between gap-2 py-2 text-sm cursor-pointer">
              <span className="flex items-center gap-2">
                <input type="checkbox" checked={!!selected[g.group_id]} onChange={(e) => toggle(g, e.target.checked)} />
                {g.subject || g.group_id}
              </span>
              <span className="text-xs text-slate-400">{fa(g.size)} عضو</span>
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
      <div className="card bg-amber-500/10 border-amber-500/30 text-amber-200 text-xs">
        {v.data?.notice || "توجه: عضویت در این گروه‌ها فقط به‌صورت دستی روی گوشی ممکن است — Green API اجازه‌ی عضویت خودکار با لینک را نمی‌دهد. این لینک‌ها اینجا ذخیره می‌شوند تا پرسنل دستی عضو شوند."}
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
        <div className="card divide-y divide-slate-800">
          {v.data.links.map((l) => (
            <div key={l.id} className="flex items-center justify-between gap-2 py-2 text-sm">
              <div className="min-w-0">
                <div className="font-bold truncate">{l.group_name || "—"}</div>
                <a href={l.invite_link} target="_blank" rel="noreferrer" className="text-sky-400 text-xs break-all">{l.invite_link}</a>
                {l.notes && <div className="text-xs text-slate-500">{l.notes}</div>}
              </div>
              <button className="btn-danger text-xs shrink-0" onClick={() => del(l.id)}>حذف</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// V16 PART 5 — smart warm-up dashboard + phrase pool + batch controls.
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

      {/* V19 — group-based warm-up (additive to the mesh) */}
      <GroupTargets />
      <LinkVault />

      {/* Phrase pool editor (shared by both warm-up engines) */}
      <div>
        <h3 className="text-lg font-bold mb-2">عبارت‌های گرم‌سازی</h3>
        <p className="text-sm text-slate-400 mb-2">پیام‌های کوتاه و طبیعی که هنگام گرم‌سازی به‌صورت تصادفی استفاده می‌شوند (علاوه بر تولید هوش مصنوعی و مخزن آمادهٔ داخلی).</p>
        <div className="flex gap-2 mb-3">
          <input className="input flex-1" placeholder="عبارت جدید…" value={newPhrase} onChange={(e) => setNewPhrase(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addPhrase()} />
          <button className="btn-primary" onClick={addPhrase}>افزودن</button>
        </div>
        {ph.loading ? <Spinner /> : (
          <div className="card divide-y divide-slate-800">
            {(ph.data || []).map((p) => (
              <div key={p.id} className="flex items-center justify-between gap-2 py-2 text-sm">
                <span className={p.is_active ? "" : "text-slate-500 line-through"}>{p.text}</span>
                <div className="flex gap-1">
                  <button className={`badge ${p.is_active ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40" : "bg-slate-600/30 text-slate-400 border-slate-600"}`}
                    onClick={async () => { await WarmupApi.updatePhrase(p.id, { text: p.text, is_active: !p.is_active }); ph.reload(); }}>
                    {p.is_active ? "فعال" : "غیرفعال"}
                  </button>
                  <button className="btn-danger text-xs" onClick={async () => { if (await confirmDialog("این عبارت حذف شود؟")) { await WarmupApi.deletePhrase(p.id); ph.reload(); } }}>حذف</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
