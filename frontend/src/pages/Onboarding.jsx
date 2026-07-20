// V35 PART 4 — «راه‌اندازی»: guided, time-gated onboarding wizard for a brand-new phone number.
// Encodes the project's anti-ban discipline as an enforced sequence: record SIM insertion →
// wait 24h (Gate A) → activate WhatsApp → wait 24h (Gate B) → connect Green API + enroll in Team
// Collaboration. The backend derives locked/unlocked + next-unlock time; this page renders one
// clear next action at a time, with Shamsi date/time always visible. All step logic/content lives
// in the unit-tested pure module onboarding.js.
import React from "react";
import { Link } from "react-router-dom";
import { OnboardingApi } from "../api.js";
import { useAsync, Spinner, Empty } from "../ui.jsx";
import { toast, confirmDialog } from "../ui/toast.jsx";
import ShamsiDateTimePicker from "../components/ShamsiDateTimePicker.jsx";
import { phaseContent, faDigits, formatCountdown, STEP_ORDER } from "./onboarding.js";

const fa = faDigits;

// A live-updating clock so countdowns tick down without a manual refresh.
function useNow(intervalMs = 30000) {
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs]);
  return now;
}

// ── Step 1 — record SIM insertion ────────────────────────────────────────────
function NewOnboardingForm({ onCreated }) {
  const [phone, setPhone] = React.useState("");
  const [model, setModel] = React.useState("");
  const [simAt, setSimAt] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  async function submit() {
    if (!phone.trim()) return toast.error("شماره تلفن لازم است");
    if (!simAt) return toast.error("تاریخ و زمان واردکردن سیم‌کارت را انتخاب کنید");
    setBusy(true);
    try {
      await OnboardingApi.create({
        phone_number: phone.trim(),
        phone_make_model: model.trim() || null,
        sim_inserted_shamsi: simAt,
      });
      toast.success("راه‌اندازی جدید ثبت شد — دورهٔ ۲۴ ساعتهٔ اول آغاز شد");
      setPhone(""); setModel(""); setSimAt("");
      onCreated && onCreated();
    } catch (e) { toast.error(e?.response?.data?.detail || e.message); }
    finally { setBusy(false); }
  }

  return (
    <div className="card space-y-3">
      <h3 className="font-bold">مرحلهٔ ۱ — ثبت واردکردن سیم‌کارت</h3>
      <p className="text-xs text-slate-400">
        شماره، زمان دقیق واردکردن سیم‌کارت در گوشی و مدل گوشی را وارد کنید. از این لحظه دورهٔ
        ۲۴ ساعتهٔ اول شروع می‌شود. در این مدت با این سیم‌کارت تماس بگیرید و پیامک رد و بدل کنید —
        با شماره‌های واقعی، نه به‌صورت خودکار.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <input className="input" placeholder="شماره (مثل ۹۸۹۱۲…)" value={phone}
          onChange={(e) => setPhone(e.target.value)} />
        <input className="input" placeholder="مدل گوشی (مثلاً Samsung A14)" value={model}
          onChange={(e) => setModel(e.target.value)} />
        <div className="sm:col-span-2">
          <label className="text-xs text-slate-400 block mb-1">زمان واردکردن سیم‌کارت (شمسی):</label>
          <ShamsiDateTimePicker value={simAt} onChange={setSimAt}
            placeholder="تاریخ و ساعت واردکردن سیم‌کارت" />
        </div>
      </div>
      <button className="btn-primary" onClick={submit} disabled={busy}>
        {busy ? "در حال ثبت…" : "ثبت و شروع دورهٔ ۲۴ ساعتهٔ اول"}
      </button>
    </div>
  );
}

// ── 4-step progress tracker ──────────────────────────────────────────────────
function StepTracker({ step }) {
  const labels = { 1: "سیم‌کارت", 2: "واتساپ", 3: "انتظار", 4: "Green API" };
  return (
    <div className="flex items-center gap-1 text-[11px]">
      {STEP_ORDER.map((s, i) => (
        <React.Fragment key={s}>
          <span className={`px-2 py-0.5 rounded-full border ${s < step
            ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
            : s === step
              ? "bg-brand/15 text-brand border-brand font-bold"
              : "bg-slate-800 text-slate-500 border-slate-700"}`}>
            {fa(s)}. {labels[s]}
          </span>
          {i < STEP_ORDER.length - 1 && <span className="text-slate-600">—</span>}
        </React.Fragment>
      ))}
    </div>
  );
}

// ── one onboarding card ──────────────────────────────────────────────────────
function OnboardingCard({ item, now, onChange }) {
  const content = phaseContent(item.phase);
  const countdown = formatCountdown(item.next_unlock_at, now);
  const [busy, setBusy] = React.useState(false);

  async function confirm() {
    setBusy(true);
    try {
      if (item.phase === "activate_whatsapp") {
        await OnboardingApi.confirmWhatsapp(item.id);
        toast.success("واتساپ فعال شد — دورهٔ ۲۴ ساعتهٔ دوم آغاز شد");
      } else if (item.phase === "connect_green_api") {
        await OnboardingApi.confirmGreenApi(item.id);
        toast.success("اتصال Green API ثبت شد — راه‌اندازی کامل شد");
      }
      onChange && onChange();
    } catch (e) { toast.error(e?.response?.data?.detail || e.message); }
    finally { setBusy(false); }
  }

  async function del() {
    if (!(await confirmDialog(`راه‌اندازی «${item.phone_number}» حذف شود؟`))) return;
    try { await OnboardingApi.remove(item.id); toast.success("حذف شد"); onChange && onChange(); }
    catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }

  return (
    <div className={`card space-y-3 ${item.done ? "border-emerald-500/30" : ""}`}>
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="font-bold font-mono">{fa(item.phone_number)}</span>
          {item.phone_make_model && <span className="text-xs text-slate-400">{item.phone_make_model}</span>}
        </div>
        <StepTracker step={item.step} />
      </div>

      <div className={`rounded-lg p-3 ${content.locked ? "bg-amber-500/10 border border-amber-500/30" : "bg-slate-800/50 border border-slate-700"}`}>
        <h4 className="font-bold text-sm mb-1">{content.title}</h4>
        <p className="text-xs text-slate-300 whitespace-pre-wrap">{content.body}</p>

        {content.locked && item.next_unlock_shamsi && (
          <p className="text-xs text-amber-300 mt-2">
            هنوز زود است — تا ساعت <span className="font-mono">{fa(item.next_unlock_shamsi)}</span> صبر کنید
            {countdown && <> (تقریباً {countdown} دیگر)</>}
          </p>
        )}

        {!content.locked && content.action && (
          <button className="btn-primary text-sm mt-2" onClick={confirm} disabled={busy}>
            {busy ? "…" : content.action}
          </button>
        )}

        {item.phase === "connect_green_api" && (
          <div className="flex gap-2 mt-2 text-xs">
            <Link to="/accounts" className="btn-secondary">رفتن به اسکن QR (حساب‌ها)</Link>
            <Link to="/team-collaboration" className="btn-secondary">فعال‌سازی همکاری تیمی</Link>
          </div>
        )}
        {item.done && (
          <div className="flex gap-2 mt-2 text-xs">
            <Link to="/team-collaboration" className="btn-secondary">مدیریت همکاری تیمی</Link>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between text-[11px] text-slate-500">
        <span>واردکردن سیم‌کارت: {item.sim_inserted_shamsi ? fa(item.sim_inserted_shamsi) : "—"}</span>
        {item.whatsapp_activated_shamsi && <span>فعال‌سازی واتساپ: {fa(item.whatsapp_activated_shamsi)}</span>}
        <button className="btn-danger text-[11px]" onClick={del}>حذف</button>
      </div>
    </div>
  );
}

export default function Onboarding() {
  const { data, loading, reload } = useAsync(() => OnboardingApi.list(), []);
  const now = useNow();
  const items = data?.onboardings || [];
  const inProgress = items.filter((o) => !o.done);
  const completed = items.filter((o) => o.done);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">🚀 راه‌اندازی شمارهٔ جدید</h1>
        <p className="text-sm text-slate-400 mt-1">
          راهنمای گام‌به‌گام و زمان‌بندی‌شده برای راه‌اندازی امن یک شمارهٔ نو — از واردکردن سیم‌کارت تا
          اتصال به Green API و همکاری تیمی. دو دورهٔ ۲۴ ساعتهٔ اجباری برای کاهش ریسک مسدودشدن رعایت می‌شود.
        </p>
      </div>

      <NewOnboardingForm onCreated={reload} />

      <div className="space-y-2">
        <h3 className="font-bold">شماره‌های در حال راه‌اندازی ({fa(inProgress.length)})</h3>
        {loading ? <Spinner /> : inProgress.length === 0 ? (
          <Empty label="شماره‌ای در حال راه‌اندازی نیست." />
        ) : (
          <div className="space-y-3">
            {inProgress.map((o) => <OnboardingCard key={o.id} item={o} now={now} onChange={reload} />)}
          </div>
        )}
      </div>

      {completed.length > 0 && (
        <div className="space-y-2">
          <h3 className="font-bold text-slate-400">راه‌اندازی‌های کامل‌شده ({fa(completed.length)})</h3>
          <div className="space-y-3">
            {completed.map((o) => <OnboardingCard key={o.id} item={o} now={now} onChange={reload} />)}
          </div>
        </div>
      )}
    </div>
  );
}
