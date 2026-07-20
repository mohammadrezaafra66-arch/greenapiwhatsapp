import React from "react";
import { IncidentsApi, Accounts as AccountsApi } from "../api.js";
import { useAsync, Spinner, Empty, Progress } from "../ui.jsx";
import { toast, confirmDialog } from "../ui/toast.jsx";
import HelpTip, { TIPS } from "../components/HelpTip.jsx";

const fa = (n) => (n == null ? "—" : String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]));
const pct = (r) => (r == null ? "—" : `${fa(Math.round(r * 100))}٪`);

const INCIDENT_FA = {
  yellowCard: "کارت زرد", blockSpike: "هجوم بلاک", lowReplyRate: "نرخ پاسخ پایین",
  blocked: "مسدود", notAuthorized: "قطع اتصال", quotaExceeded: "پایان سهمیه",
};

export default function Protection() {
  const prot = useAsync(() => IncidentsApi.protection(), []);
  const inc = useAsync(() => IncidentsApi.list(), []);

  const reload = () => { prot.reload(); inc.reload(); };

  if (prot.loading) return <Spinner />;

  return (
    <div className="space-y-5">
      <h2 className="text-2xl font-bold">محافظت و سلامت</h2>
      <div className="card bg-amber-500/10 border-amber-500/30 text-amber-200 text-xs">
        سامانه به‌طور خودکار کارت زرد را تشخیص می‌دهد و ارسال را متوقف، صف را پاک، سرعت را نصف و شماره را ۳ روز خنک می‌کند.
        اقدامات پرخطر (ری‌بوت/ادامه ارسال) فقط دستی و پس از پایان دوره خنک‌سازی فعال می‌شوند.
        {prot.data?.auto_failover === false && " · فِیل‌اوور خودکار: خاموش (پیش‌فرض) — با AUTO_FAILOVER_ON_YELLOW_CARD در .env روشن می‌شود."}
      </div>

      {/* Per-account health cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {(prot.data?.accounts || []).map((a) => (
          <div key={a.account_id} className={`card space-y-2 ${a.green_api_deleted ? "border-red-500/50 bg-red-500/10" : a.in_cooldown ? "border-red-500/50 bg-red-500/5" : ""}`}>
            <div className="flex items-center justify-between">
              <span className="font-bold">{a.name}</span>
              {a.green_api_deleted
                ? <span className="badge bg-red-500/20 text-red-300 border-red-500/40">حذف‌شده در Green API 🗑️</span>
                : a.in_cooldown ? <span className="badge bg-red-500/20 text-red-300 border-red-500/40">در خنک‌سازی تا {a.cooldown_until}</span>
                : a.throttle_factor < 1 ? <span className="badge bg-amber-500/20 text-amber-300 border-amber-500/40">کاهش سرعت ({pct(a.throttle_factor)})</span>
                : null}
            </div>
            {/* V36 — instance deleted upstream: terminal state + remove action ONLY (no health widgets) */}
            {a.green_api_deleted ? (
              <div className="space-y-2 text-sm">
                <p className="text-red-200 text-xs">{a.green_api_deleted_message || "این اینستنس در Green API دیگر وجود ندارد"} — دیگر بررسی/اتصال ممکن نیست.</p>
                <button className="btn-danger text-xs" onClick={async () => {
                  if (await confirmDialog("این حساب از پلتفرم حذف شود؟ (در Green API از قبل حذف شده است)")) {
                    try { await AccountsApi.remove(a.account_id); toast.success("حذف شد"); reload(); }
                    catch (e) { toast.error(e?.response?.data?.detail || e.message); }
                  }
                }}>حذف از پلتفرم</button>
              </div>
            ) : (
              <>
                <div className="text-xs text-slate-400">امتیاز سلامت<HelpTip text={TIPS.health} /></div>
                <Progress value={Math.round((a.health_score || 0) * 100)} max={100} color={a.health_score > 0.6 ? "bg-emerald-500" : a.health_score > 0.3 ? "bg-amber-500" : "bg-red-500"} />
                <div className="grid grid-cols-2 gap-1 text-xs text-slate-400">
                  <span>ارسال امروز: {fa(a.sent_today)} / {fa(a.effective_cap)}</span>
                  <span>کارت زرد ۷ روز: {pct(a.yellow_card_rate_7d)}</span>
                  <span>نرخ پاسخ ۷ روز: {pct(a.reply_rate_7d)}</span>
                  <span>رویداد ۷ روز: {fa(a.incident_count_7d)}</span>
                </div>
                {a.reply_rate_7d != null && a.reply_rate_7d < 0.2 && (
                  <p className="text-xs text-amber-300">⚠️ نرخ پاسخ پایین است — خطر مسدود شدن بالا می‌رود، حجم ارسال را کم کنید.</p>
                )}
                <div className="flex flex-wrap gap-1 pt-1">
                  <button className="btn-secondary text-xs" disabled={a.in_cooldown}
                    title={a.in_cooldown ? "در دوره خنک‌سازی غیرفعال است" : ""}
                    onClick={async () => { if (await confirmDialog("⚠️ ری‌بوت، صف را از سر می‌گیرد ولی کارت زرد را پاک نمی‌کند. اگر بلافاصله دوباره ارسال کنید، کارت زرد برمی‌گردد.")) { try { await IncidentsApi.reboot(a.account_id); toast.success("ری‌بوت شد"); } catch (e) { toast.error(e?.response?.data?.detail || e.message); } } }}>
                    ری‌بوت شماره
                  </button>
                  <button className="btn-secondary text-xs" disabled={a.in_cooldown}
                    onClick={async () => { try { const r = await IncidentsApi.resume(a.account_id); toast.success(`${fa(r.resumed)} کمپین ادامه یافت — ${r.note || ""}`); reload(); } catch (e) { toast.error(e?.response?.data?.detail || e.message); } }}>
                    ادامه ارسال
                  </button>
                  <button className="btn-secondary text-xs"
                    onClick={async () => { if (await confirmDialog("خروج از حساب برای اتصال مجدد با QR؟")) { try { await IncidentsApi.reconnect(a.account_id); toast.success("خارج شد — از صفحه حساب‌ها QR بگیرید"); reload(); } catch (e) { toast.error(e?.response?.data?.detail || e.message); } } }}>
                    اتصال مجدد
                  </button>
                </div>
              </>
            )}
          </div>
        ))}
      </div>

      {/* Incident timeline */}
      <h3 className="text-lg font-bold">تاریخچه رویدادها</h3>
      {inc.loading ? <Spinner /> : (!inc.data || inc.data.length === 0) ? <Empty label="رویدادی ثبت نشده." /> : (
        <div className="space-y-2">
          {inc.data.map((i) => (
            <div key={i.id} className={`card text-sm ${i.severity === "critical" ? "border-red-500/40" : "border-amber-500/40"}`}>
              <div className="flex items-center justify-between flex-wrap gap-2">
                <span className="font-bold">
                  {i.severity === "critical" ? "🔴" : "🟡"} {INCIDENT_FA[i.incident_type] || i.incident_type} — {i.account_name}
                </span>
                <span className="text-xs text-slate-500">{i.created_at} · {i.detected_via}</span>
              </div>
              <div className="text-xs text-slate-400 mt-1 space-y-0.5">
                {i.campaigns_paused?.length > 0 && <div>✅ {fa(i.campaigns_paused.length)} کمپین متوقف شد</div>}
                {i.queue_snapshot_count > 0 && <div>✅ {fa(i.queue_snapshot_count)} پیام از صف حذف شد</div>}
                {i.auto_actions?.throttle_factor && <div>✅ سرعت به {pct(i.auto_actions.throttle_factor)} کاهش یافت</div>}
                {i.auto_actions?.cooldown_until && <div>✅ دوره خنک‌سازی فعال شد</div>}
              </div>
              {!i.resolved && (
                <button className="btn-secondary text-xs mt-2" onClick={async () => { try { await IncidentsApi.resolve(i.id); toast.success("حل شد"); inc.reload(); } catch (e) { toast.error(e?.response?.data?.detail || e.message); } }}>
                  ✓ حل شد
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
