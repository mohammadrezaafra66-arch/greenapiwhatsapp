import React from "react";
import { WarmupApi } from "../api.js";
import { useAsync, Spinner, Empty, Progress } from "../ui.jsx";
import { toast, confirmDialog } from "../ui/toast.jsx";

const fa = (n) => (n == null ? "—" : String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]));

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
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="text-2xl font-bold">گرم‌سازی هوشمند</h2>
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={startAll}>🔥 شروع گرم‌سازی همه</button>
          <button className="btn-secondary" onClick={stopAll}>⏹ توقف همه</button>
        </div>
      </div>
      <div className="card bg-sky-500/10 border-sky-500/30 text-sky-200 text-xs">
        ۱۰ روز اول پس از اتصال، سامانه به‌آرامی و انسانی با شماره کار می‌کند: روز ۱ تا ۳ فقط دریافت، روز ۴ تا ۷ حداکثر ۳ پاسخ در روز، روز ۸ تا ۱۰ حداکثر ۱۰ پاسخ. ارسال‌ها در طول روز پخش می‌شوند و فقط به کسانی که قبلاً پیام داده‌اند فرستاده می‌شود.
      </div>

      {/* Accounts in warm-up */}
      {dash.loading ? <Spinner /> : accounts.length === 0 ? (
        <Empty label="هیچ شماره‌ای در حال گرم‌سازی نیست. با «شروع گرم‌سازی همه» یا تیک «گرم‌سازی خودکار» در صفحه حساب‌ها فعال کنید." />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {accounts.map((a) => (
            <div key={a.account_id} className="card space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-bold">{a.name}</span>
                {a.completed
                  ? <span className="badge bg-emerald-500/20 text-emerald-300 border-emerald-500/40">آماده ✅</span>
                  : <span className="badge bg-amber-500/20 text-amber-300 border-amber-500/40">{a.phase}</span>}
              </div>
              {!a.completed && (
                <>
                  <p className="text-xs text-slate-400">روز {fa(a.day)} از {fa(a.total_days)}</p>
                  <Progress value={Math.min(a.day, a.total_days)} max={a.total_days} color="bg-amber-500" />
                  <p className="text-xs text-slate-400">
                    پاسخ‌های امروز: {fa(a.sent_today)} از {a.daily_cap ? fa(a.daily_cap) : "۰ (فقط دریافت)"}
                  </p>
                </>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Phrase pool editor */}
      <div>
        <h3 className="text-lg font-bold mb-2">عبارت‌های گرم‌سازی</h3>
        <p className="text-sm text-slate-400 mb-2">پیام‌های کوتاه و طبیعی که به‌صورت تصادفی هنگام گرم‌سازی فرستاده می‌شوند.</p>
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
