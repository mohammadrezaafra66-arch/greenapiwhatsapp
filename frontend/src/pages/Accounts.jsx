import React from "react";
import { Accounts as Api, ProxyApi } from "../api.js";
import { Badge, Spinner, Empty, Modal, useAsync } from "../ui.jsx";

export default function Accounts() {
  const { data, loading, error, reload } = useAsync(Api.list, []);
  const [showAdd, setShowAdd] = React.useState(false);
  const [qr, setQr] = React.useState(null);
  const [busy, setBusy] = React.useState(null);

  const act = async (fn, id) => {
    setBusy(id);
    try {
      await fn();
      await reload();
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    } finally {
      setBusy(null);
    }
  };

  const showQr = async (id) => {
    try {
      const r = await Api.qr(id);
      setQr(r || {});
    } catch (e) {
      alert("دریافت QR ناموفق بود");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">حساب‌ها</h2>
        <button className="btn-primary" onClick={() => setShowAdd(true)}>+ افزودن حساب</button>
      </div>

      {loading && <Spinner />}
      {error && <div className="card text-red-400">{error}</div>}
      {data && data.length === 0 && <Empty label="هیچ حسابی ثبت نشده است." />}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {data?.map((a) => (
          <div key={a.id} className="card space-y-3">
            <div className="flex items-center justify-between">
              <span className="font-bold">{a.name}</span>
              <Badge status={a.status} />
            </div>
            <div className="text-sm text-slate-400 space-y-0.5">
              <p>شماره واتس‌اپ: {a.instance_id}</p>
              <p>تلفن: {a.phone || "—"}</p>
              <p>ارسال امروز: {a.sent_today} / {a.daily_limit}</p>
              <p>دریافت امروز: {a.received_today}</p>
              <p>روزهای فعال: {a.days_active}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button className="btn-secondary" disabled={busy === a.id} onClick={() => act(() => Api.status(a.id), a.id)}>بررسی وضعیت</button>
              <button className="btn-secondary" onClick={() => showQr(a.id)}>QR</button>
              <button className="btn-secondary" disabled={busy === a.id} onClick={() => act(() => Api.reboot(a.id), a.id)}>ری‌بوت</button>
              <button className="btn-danger" disabled={busy === a.id} onClick={() => {
                if (confirm("حذف این حساب؟")) act(() => Api.remove(a.id), a.id);
              }}>حذف</button>
            </div>
            <ProxySection accountId={a.id} />
          </div>
        ))}
      </div>

      {showAdd && <AddAccountModal onClose={() => setShowAdd(false)} onDone={reload} />}
      {qr !== null && (
        <Modal title="کد QR" onClose={() => setQr(null)}>
          {qr.qr ? (
            <div className="space-y-2">
              <img
                alt="qr"
                className="mx-auto bg-white p-2 rounded"
                src={qr.qr.startsWith("data:") ? qr.qr : `data:image/png;base64,${qr.qr}`}
              />
              <p className="text-center text-xs text-slate-400">با واتس‌اپ گوشی این کد را اسکن کنید.</p>
            </div>
          ) : (
            <p className="text-slate-400 text-sm">
              {qr.type === "alreadyLogged"
                ? "این حساب هم‌اکنون متصل است؛ کد QR لازم نیست."
                : qr.message || "QR در دسترس نیست (احتمالاً حساب قبلاً متصل شده)."}
            </p>
          )}
        </Modal>
      )}
    </div>
  );
}

function ProxySection({ accountId }) {
  const [open, setOpen] = React.useState(false);
  const [f, setF] = React.useState({ proxy_host: "", proxy_port: 1080, proxy_login: "", proxy_password: "" });
  const [busy, setBusy] = React.useState(false);
  const [loaded, setLoaded] = React.useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const load = async () => {
    try {
      const r = await ProxyApi.get(accountId);
      setF((prev) => ({ ...prev, proxy_host: r.proxy_host || "", proxy_port: r.proxy_port || 1080 }));
    } catch { /* ignore */ }
    setLoaded(true);
  };

  const toggle = () => {
    const n = !open;
    setOpen(n);
    if (n && !loaded) load();
  };

  const saveProxy = async (enabled) => {
    setBusy(true);
    try {
      const r = await ProxyApi.set(accountId, {
        proxy_host: f.proxy_host,
        proxy_port: Number(f.proxy_port) || 1080,
        proxy_login: f.proxy_login,
        proxy_password: f.proxy_password,
        proxy_enabled: enabled,
      });
      alert(enabled ? (r.applied ? "پروکسی فعال شد" : "ذخیره شد (اعمال روی واتساپ ناموفق)") : "پروکسی غیرفعال شد");
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    } finally {
      setBusy(false);
    }
  };

  const syncBlocked = async () => {
    setBusy(true);
    try {
      const r = await ProxyApi.getBlocked(accountId);
      alert(`${r.count} مخاطب بلاک‌شده همگام‌سازی شد`);
    } catch (e) {
      alert(e?.response?.data?.detail || "دریافت لیست بلاک ناموفق بود");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border-t border-slate-700 pt-3">
      <button className="text-xs text-slate-400 hover:text-slate-200" onClick={toggle}>
        🌐 تنظیمات پروکسی {open ? "▲" : "▼"}
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          <p className="text-xs text-slate-500">برای پایداری اتصال از ایران می‌توانید یک پروکسی SOCKS5 تنظیم کنید.</p>
          <input className="input" placeholder="آدرس سرور (مثال: 1.2.3.4)" value={f.proxy_host} onChange={set("proxy_host")} />
          <input className="input" type="number" placeholder="پورت (مثال: 1080)" value={f.proxy_port} onChange={set("proxy_port")} />
          <input className="input" placeholder="نام کاربری (اختیاری)" value={f.proxy_login} onChange={set("proxy_login")} />
          <input className="input" type="password" placeholder="رمز عبور (اختیاری)" value={f.proxy_password} onChange={set("proxy_password")} />
          <div className="flex gap-2">
            <button className="btn-primary text-sm" disabled={busy} onClick={() => saveProxy(true)}>فعال کن</button>
            <button className="btn-secondary text-sm" disabled={busy} onClick={() => saveProxy(false)}>غیرفعال کن</button>
          </div>
          <button className="btn-secondary text-xs w-full" disabled={busy} onClick={syncBlocked}>
            همگام‌سازی مخاطبین بلاک‌شده
          </button>
        </div>
      )}
    </div>
  );
}

function AddAccountModal({ onClose, onDone }) {
  const [form, setForm] = React.useState({ name: "", instance_id: "", api_token: "" });
  const [saving, setSaving] = React.useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async () => {
    if (!form.name || !form.instance_id || !form.api_token) return alert("همه فیلدها لازم است");
    setSaving(true);
    try {
      await Api.create(form.name, form.instance_id, form.api_token);
      await onDone();
      onClose();
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title="افزودن حساب جدید" onClose={onClose}>
      <div className="space-y-3">
        <div>
          <label className="label">نام حساب</label>
          <input className="input" value={form.name} onChange={set("name")} />
        </div>
        <div>
          <label className="label">شناسه شماره واتس‌اپ</label>
          <input className="input" value={form.instance_id} onChange={set("instance_id")} />
        </div>
        <div>
          <label className="label">توکن اتصال</label>
          <input className="input" value={form.api_token} onChange={set("api_token")} />
        </div>
        <button className="btn-primary w-full" disabled={saving} onClick={submit}>
          {saving ? "در حال ذخیره..." : "ذخیره و تنظیم دریافت خودکار"}
        </button>
      </div>
    </Modal>
  );
}
