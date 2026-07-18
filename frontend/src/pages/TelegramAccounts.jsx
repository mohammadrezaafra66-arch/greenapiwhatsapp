import React from "react";
import { Accounts, TelegramApi as Api } from "../api.js";
import { Spinner, Empty, Modal, useAsync } from "../ui.jsx";
import { toast } from "../ui/toast.jsx";

const STATUS_FA = {
  active: "متصل ✅", pending: "در انتظار اتصال", disconnected: "قطع",
  banned: "مسدود", suspended: "محدودشده (اسپم)", deleted: "حذف‌شده",
};

export default function TelegramAccounts() {
  const { data, loading, reload } = useAsync(() => Accounts.list(), []);
  const [creating, setCreating] = React.useState(false);
  const [authFor, setAuthFor] = React.useState(null);

  const telegramAccounts = (data || []).filter((a) => a.platform === "telegram");

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">اکانت‌های تلگرام ✈️</h2>
        <button className="btn-primary" onClick={() => setCreating(true)}>+ افزودن اکانت تلگرام</button>
      </div>

      <div className="card text-sm text-slate-300 bg-sky-500/10 border-sky-500/30 space-y-1">
        <div className="font-bold">نکات ضدمسدودی تلگرام (متفاوت با واتساپ):</div>
        <div>• در ۴۸ ساعت اول پس از اتصال، این اکانت به هیچ غریبه‌ای پیام نمی‌فرستد (محدودیت خودکار محافظتی).</div>
        <div>• فاصله‌ی هر ارسال حداقل ۱۰ تا ۱۵ ثانیه است.</div>
        <div>• روش اتصال با QR ترجیح دارد؛ روش کد+رمز ممکن است ناپایدار باشد.</div>
      </div>

      {loading && <Spinner />}
      {!loading && telegramAccounts.length === 0 && (
        <Empty label="هنوز اکانت تلگرامی اضافه نشده است." />
      )}
      {telegramAccounts.length > 0 && (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                <th className="text-right p-2">نام</th>
                <th className="text-right p-2">شناسه</th>
                <th className="text-right p-2">وضعیت</th>
                <th className="text-right p-2"></th>
              </tr>
            </thead>
            <tbody>
              {telegramAccounts.map((a) => (
                <tr key={a.id} className="border-b border-slate-800">
                  <td className="p-2 font-bold">{a.name}</td>
                  <td className="p-2 text-slate-400">{a.instance_id}</td>
                  <td className="p-2">{STATUS_FA[a.status] || a.status}</td>
                  <td className="p-2 text-left">
                    <button className="btn-ghost" onClick={() => setAuthFor(a)}>اتصال / QR</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {creating && (
        <CreateModal onClose={() => setCreating(false)} onDone={async () => { setCreating(false); await reload(); }} />
      )}
      {authFor && (
        <AuthModal account={authFor} onClose={() => { setAuthFor(null); reload(); }} />
      )}
    </div>
  );
}

function CreateModal({ onClose, onDone }) {
  const [f, setF] = React.useState({ name: "", instance_id: "", api_token: "", api_host: "" });
  const [busy, setBusy] = React.useState(false);
  const submit = async () => {
    if (!f.instance_id.trim() || !f.api_token.trim()) {
      toast.error("شناسه و توکن لازم است");
      return;
    }
    setBusy(true);
    try {
      await Api.create({ ...f, api_host: f.api_host.trim() || null });
      toast.success("اکانت تلگرام اضافه شد");
      await onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title="افزودن اکانت تلگرام" onClose={onClose}>
      <div className="space-y-3">
        <Field label="نام" value={f.name} onChange={(v) => setF({ ...f, name: v })} />
        <Field label="شناسه instance (از پروژه تلگرام Green API)" value={f.instance_id}
               onChange={(v) => setF({ ...f, instance_id: v })} />
        <Field label="توکن API" value={f.api_token} onChange={(v) => setF({ ...f, api_token: v })} />
        <Field label="آدرس API (اختیاری — پیش‌فرض میزبان پارتنر تلگرام)" value={f.api_host}
               onChange={(v) => setF({ ...f, api_host: v })} />
        <div className="text-xs text-amber-300">
          این اکانت با کلید پارتنر «تلگرام» ثبت می‌شود و هرگز با کلید واتساپ اشتباه نمی‌شود.
        </div>
        <button className="btn-primary w-full" disabled={busy} onClick={submit}>
          {busy ? "در حال افزودن…" : "افزودن"}
        </button>
      </div>
    </Modal>
  );
}

function AuthModal({ account, onClose }) {
  const [tab, setTab] = React.useState("qr");
  const { data: qr, reload: reloadQr, loading: qrLoading } = useAsync(() => Api.qr(account.id), [account.id]);
  const { data: notice } = useAsync(() => Api.qrNotice(), []);
  const [phone, setPhone] = React.useState("");
  const [code, setCode] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [state, setState] = React.useState(account.status);

  const poll = async () => {
    try {
      const s = await Api.state(account.id);
      setState(s.status);
      if (s.state === "authorized") toast.success("اکانت متصل شد ✅");
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  const run = async (fn, ok) => {
    try {
      await fn();
      toast.success(ok);
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  return (
    <Modal title={`اتصال تلگرام: ${account.name}`} onClose={onClose} wide>
      <div className="space-y-3">
        {notice?.notice && (
          <div className="card text-xs text-slate-300 bg-amber-500/10 border-amber-500/30 space-y-1">
            {notice.notice.map((n, i) => <div key={i}>{n}</div>)}
          </div>
        )}
        <div className="flex gap-2">
          <button className={tab === "qr" ? "btn-primary" : "btn-ghost"} onClick={() => setTab("qr")}>
            QR (پیشنهادی)
          </button>
          <button className={tab === "code" ? "btn-primary" : "btn-ghost"} onClick={() => setTab("code")}>
            کد + رمز (پشتیبان)
          </button>
        </div>

        {tab === "qr" && (
          <div className="text-center space-y-2">
            {qrLoading && <Spinner />}
            {qr?.qr ? (
              <img src={`data:image/png;base64,${qr.qr}`} alt="QR" className="mx-auto w-56 h-56" />
            ) : (
              <div className="text-slate-400 text-sm">{qr?.message || "QR در دسترس نیست"}</div>
            )}
            <div className="text-xs text-slate-400">{notice?.link_hint}</div>
            <button className="btn-ghost" onClick={reloadQr}>بارگذاری مجدد QR</button>
          </div>
        )}

        {tab === "code" && (
          <div className="space-y-2">
            <div className="text-xs text-amber-300">
              روش کد+رمز ممکن است طبق تلگرام ناپایدار باشد — در صورت امکان از QR استفاده کنید.
            </div>
            <Field label="شماره تلفن" value={phone} onChange={setPhone} />
            <button className="btn-ghost w-full"
                    onClick={() => run(() => Api.authStart(account.id, phone), "کد ارسال شد")}>
              ارسال کد
            </button>
            <Field label="کد دریافتی" value={code} onChange={setCode} />
            <button className="btn-ghost w-full"
                    onClick={() => run(() => Api.authCode(account.id, code), "کد ثبت شد")}>
              ثبت کد
            </button>
            <Field label="رمز دومرحله‌ای (در صورت وجود)" value={password} onChange={setPassword} />
            <button className="btn-ghost w-full"
                    onClick={() => run(() => Api.authPassword(account.id, password), "رمز ثبت شد")}>
              ثبت رمز
            </button>
          </div>
        )}

        <div className="flex items-center justify-between border-t border-slate-700 pt-2">
          <span className="text-sm text-slate-400">وضعیت: {STATUS_FA[state] || state}</span>
          <button className="btn-primary" onClick={poll}>بررسی وضعیت اتصال</button>
        </div>
      </div>
    </Modal>
  );
}

function Field({ label, value, onChange }) {
  return (
    <div>
      <label className="text-xs text-slate-400">{label}</label>
      <input className="input w-full" value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}
