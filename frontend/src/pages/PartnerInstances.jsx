import React from "react";
import { PartnerApi } from "../api.js";
import { Modal, useAsync, Spinner, Empty } from "../ui.jsx";
import { toast, confirmDialog } from "../ui/toast.jsx";
import HelpTip, { TIPS } from "../components/HelpTip.jsx";

// Persian digit helper
const fa = (n) => (n == null ? "" : String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]));

const STATUS_FA = {
  active: "متصل ✅",
  pending: "در انتظار اتصال ⏳",
  disconnected: "قطع 🔌",
  banned: "مسدود 🚫",
  deleted: "حذف‌شده",
};

export default function PartnerInstances() {
  const { data, loading, error, reload } = useAsync(() => PartnerApi.instances(), []);
  const [showCreate, setShowCreate] = React.useState(false);
  const [qrFor, setQrFor] = React.useState(null);
  const [codeFor, setCodeFor] = React.useState(null);
  const [syncing, setSyncing] = React.useState(false);

  const configured = data?.configured;

  async function doSync() {
    setSyncing(true);
    try {
      const r = await PartnerApi.sync();
      toast.success(`همگام‌سازی شد: ${fa(r.created)} جدید، ${fa(r.updated)} بروزرسانی، ${fa(r.orphaned)} یافت‌نشده`);
      reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setSyncing(false);
    }
  }

  async function doDelete(inst) {
    const typed = window.prompt(
      `⚠️ حذف instance، دستگاه متصل را logout نمی‌کند و نشست فعال در گوشی باقی می‌ماند.\n` +
      `توصیه: ابتدا «خروج از حساب» را بزنید، سپس حذف کنید.\n\n` +
      `برای تأیید، شماره یا کلمه «حذف» را تایپ کنید:`
    );
    if (typed == null) return;
    if (typed.trim() !== "حذف" && typed.trim() !== (inst.instance_id || "")) {
      return toast.error("تأیید نامعتبر — حذف انجام نشد");
    }
    try {
      await PartnerApi.remove(inst.instance_id);
      toast.success("شماره حذف شد — صورتحساب روزانه این شماره متوقف می‌شود");
      reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  }

  if (loading) return <Spinner />;
  if (error) return <p className="text-red-400 text-sm">{error}</p>;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="text-xl font-bold">مدیریت پارتنر (شماره‌ها)</h2>
        <div className="flex gap-2">
          <button className="btn" onClick={doSync} disabled={syncing || !configured}>
            {syncing ? "در حال همگام‌سازی…" : "🔄 همگام‌سازی"}
          </button>
          <button className="btn btn-primary" onClick={() => setShowCreate(true)} disabled={!configured}>
            ➕ افزودن شماره جدید
          </button>
        </div>
      </div>

      {!configured && (
        <div className="card border-amber-500/40 bg-amber-500/10 text-amber-200 text-sm">
          توکن پارتنر تنظیم نشده است — آن را در فایل <code>.env</code> قرار دهید
          (<code>GREEN_PARTNER_TOKEN</code>). تا آن زمان، قابلیت‌های پارتنر غیرفعال هستند.
        </div>
      )}

      {/* Billing summary */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="card">
          <p className="text-slate-400 text-xs">تعداد شماره‌های متصل</p>
          <p className="text-2xl font-bold">{fa(data?.summary?.active_count ?? 0)}</p>
        </div>
        <div className="card">
          <p className="text-slate-400 text-xs">مجموع روزهای فعال این ماه</p>
          <p className="text-2xl font-bold">{fa(data?.summary?.total_days_this_month ?? 0)}</p>
        </div>
        <div className="card">
          <p className="text-slate-400 text-xs">هزینه تخمینی این ماه</p>
          <p className="text-2xl font-bold">
            {data?.summary?.estimated_month_cost != null
              ? fa(data.summary.estimated_month_cost)
              : "—"}
          </p>
        </div>
      </div>
      <p className="text-xs text-slate-500">
        صورتحساب پارتنر روزانه است و ساعت ۰۰:۰۰ (UTC+3) کسر می‌شود. با موجودی منفی هم instanceها کار می‌کنند.
        {data?.summary?.daily_rate ? "" : " (نرخ روزانه تنظیم نشده — فقط تعداد روز نمایش داده می‌شود.)"}
      </p>

      {/* Instances table */}
      <div className="card overflow-x-auto">
        {(!data?.instances || data.instances.length === 0) ? (
          <Empty label="هیچ شماره‌ای ثبت نشده است." />
        ) : (
          <table className="w-full text-sm">
            <thead className="text-slate-400 text-xs">
              <tr>
                <th className="text-right p-2">نام<HelpTip text={TIPS.name} /></th>
                <th className="text-right p-2">idInstance<HelpTip text={TIPS.idInstance} /></th>
                <th className="text-right p-2">وضعیت</th>
                <th className="text-right p-2">تعرفه<HelpTip text={TIPS.tariff} /></th>
                <th className="text-right p-2">تاریخ ساخت</th>
                <th className="text-right p-2">روزهای فعال<HelpTip text={TIPS.daysActive} /></th>
                <th className="text-right p-2">اقدامات</th>
              </tr>
            </thead>
            <tbody>
              {data.instances.map((a) => (
                <tr key={a.id} className="border-t border-slate-800">
                  <td className="p-2">
                    {a.name}
                    {a.is_orphaned && (
                      <span className="mr-1 badge bg-amber-500/20 text-amber-300 border-amber-500/40">
                        در Green API یافت نشد
                      </span>
                    )}
                  </td>
                  <td className="p-2 font-mono text-xs">{a.instance_id}</td>
                  <td className="p-2">{STATUS_FA[a.status] || a.status}</td>
                  <td className="p-2">{a.tariff || "—"}</td>
                  <td className="p-2">{a.partner_created_at || "—"}</td>
                  <td className="p-2">{fa(a.days_active)}</td>
                  <td className="p-2">
                    <div className="flex gap-1 flex-wrap">
                      <button className="btn btn-xs" onClick={() => setQrFor(a)}>QR</button>
                      <button className="btn btn-xs" onClick={() => setCodeFor(a)}>اتصال با کد</button>
                      <button className="btn btn-xs text-red-300" onClick={() => doDelete(a)}>حذف</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showCreate && <CreateModal onClose={() => setShowCreate(false)} onDone={reload} />}
      {qrFor && <QrModal inst={qrFor} onClose={() => setQrFor(null)} onConnected={reload} />}
      {codeFor && <CodeModal inst={codeFor} onClose={() => setCodeFor(null)} onConnected={reload} />}
    </div>
  );
}

function CreateModal({ onClose, onDone }) {
  const [name, setName] = React.useState("");
  const [delay, setDelay] = React.useState(15000);
  const [busy, setBusy] = React.useState(false);
  const [qrUrl, setQrUrl] = React.useState(null);

  async function submit() {
    if (!name.trim()) return toast.error("نام شماره لازم است");
    setBusy(true);
    try {
      const r = await PartnerApi.create(name.trim(), Number(delay) || 15000);
      toast.success("شماره ساخته شد — برای اتصال، QR را اسکن کنید");
      setQrUrl(r.qr_url);
      onDone && onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="افزودن شماره جدید" onClose={onClose}>
      {qrUrl ? (
        <div className="space-y-3 text-sm">
          <p className="text-slate-300">شماره ساخته شد. برای اتصال، این QR را در واتساپ اسکن کنید:</p>
          <iframe title="qr" src={qrUrl} className="w-full h-72 bg-white rounded" />
          <p className="text-amber-300 text-xs">⚠️ ساخت کد QR تا ۲ دقیقه پس از ساخت شماره ممکن است طول بکشد.</p>
          <button className="btn w-full" onClick={onClose}>بستن</button>
        </div>
      ) : (
        <div className="space-y-3">
          <label className="block text-sm">
            نام شماره
            <input className="input mt-1" value={name} onChange={(e) => setName(e.target.value)} placeholder="مثلاً: فروش تهران" />
          </label>
          <label className="block text-sm">
            تأخیر ضدمسدودی بین پیام‌ها (میلی‌ثانیه)
            <input type="number" className="input mt-1" value={delay} onChange={(e) => setDelay(e.target.value)} />
          </label>
          <button className="btn btn-primary w-full" onClick={submit} disabled={busy}>
            {busy ? "در حال ساخت…" : "ساخت شماره"}
          </button>
        </div>
      )}
    </Modal>
  );
}

function QrModal({ inst, onClose, onConnected }) {
  const [qrUrl, setQrUrl] = React.useState(null);
  const [tick, setTick] = React.useState(0);

  React.useEffect(() => {
    PartnerApi.qr(inst.id).then((r) => setQrUrl(r.qr_url)).catch(() => {});
  }, [inst.id]);

  // refresh iframe every 2s; poll state every 3s
  React.useEffect(() => {
    const r = setInterval(() => setTick((t) => t + 1), 2000);
    const p = setInterval(async () => {
      try {
        const s = await PartnerApi.state(inst.id);
        if (s.state === "authorized") {
          toast.success("✅ شماره با موفقیت متصل شد");
          onConnected && onConnected();
          onClose();
        }
      } catch { /* ignore */ }
    }, 3000);
    return () => { clearInterval(r); clearInterval(p); };
  }, [inst.id, onClose, onConnected]);

  return (
    <Modal title={`اتصال با QR — ${inst.name}`} onClose={onClose}>
      <div className="space-y-3 text-sm">
        {qrUrl ? (
          <iframe key={tick} title="qr" src={qrUrl} className="w-full h-72 bg-white rounded" />
        ) : (
          <Spinner label="در حال دریافت کد…" />
        )}
        <ol className="text-slate-300 text-xs space-y-1 list-decimal pr-4">
          <li>در گوشی، واتساپ را باز کنید</li>
          <li>تنظیمات ← دستگاه‌های متصل ← اتصال دستگاه</li>
          <li>این کد QR را اسکن کنید</li>
        </ol>
        <p className="text-amber-300 text-xs">⚠️ ساخت کد QR تا ۲ دقیقه پس از ساخت شماره ممکن است طول بکشد.</p>
      </div>
    </Modal>
  );
}

function CodeModal({ inst, onClose, onConnected }) {
  const [phone, setPhone] = React.useState(inst.phone || "");
  const [code, setCode] = React.useState(null);
  const [left, setLeft] = React.useState(0);
  const [busy, setBusy] = React.useState(false);

  async function requestCode() {
    setBusy(true);
    try {
      const r = await PartnerApi.authCode(inst.id, phone.trim());
      setCode(r.code);
      setLeft(r.expires_in_seconds || 150);
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setBusy(false);
    }
  }

  // countdown
  React.useEffect(() => {
    if (left <= 0) return;
    const t = setInterval(() => setLeft((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(t);
  }, [left]);

  // poll for authorized while a code is live
  React.useEffect(() => {
    if (!code) return;
    const p = setInterval(async () => {
      try {
        const s = await PartnerApi.state(inst.id);
        if (s.state === "authorized") {
          toast.success("✅ شماره با موفقیت متصل شد");
          onConnected && onConnected();
          onClose();
        }
      } catch { /* ignore */ }
    }, 3000);
    return () => clearInterval(p);
  }, [code, inst.id, onClose, onConnected]);

  const mm = String(Math.floor(left / 60)).padStart(2, "0");
  const ss = String(left % 60).padStart(2, "0");

  return (
    <Modal title={`اتصال با کد تلفن — ${inst.name}`} onClose={onClose}>
      <div className="space-y-3 text-sm">
        <label className="block">
          شماره (بین‌المللی، بدون + یا ۰۰ — مثال: 989122270261)
          <input className="input mt-1" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="989122270261" />
        </label>
        <button className="btn btn-primary w-full" onClick={requestCode} disabled={busy}>
          {busy ? "در حال دریافت…" : code ? "دریافت کد جدید" : "دریافت کد"}
        </button>
        {code && (
          <div className="text-center space-y-2">
            <div className="text-3xl font-mono tracking-[0.4em] select-all bg-slate-800 rounded py-3">{code}</div>
            <p className={`text-xs ${left > 0 ? "text-slate-400" : "text-red-400"}`}>
              {left > 0 ? `⏳ ${fa(mm)}:${fa(ss)} تا انقضای کد` : "کد منقضی شد — «دریافت کد جدید» را بزنید"}
            </p>
            <ol className="text-slate-300 text-xs space-y-1 list-decimal pr-4 text-right">
              <li>در گوشی: واتساپ ← تنظیمات ← دستگاه‌های متصل ← اتصال دستگاه</li>
              <li>«اتصال با شماره تلفن» را انتخاب کنید</li>
              <li>کد بالا را وارد کنید</li>
            </ol>
          </div>
        )}
      </div>
    </Modal>
  );
}
