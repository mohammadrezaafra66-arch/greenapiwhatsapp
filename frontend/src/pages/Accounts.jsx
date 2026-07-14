import React from "react";
import { Accounts as Api, ProxyApi } from "../api.js";
import { Badge, Spinner, Empty, Modal, useAsync } from "../ui.jsx";
import { toast, confirmDialog } from "../ui/toast.jsx";

const fa = (n) => Number(n || 0).toLocaleString("fa-IR");

// V13.2 — per-account health bar (green/amber/red by score).
function HealthSection({ accountId }) {
  const [h, setH] = React.useState(null);
  React.useEffect(() => {
    let alive = true;
    Api.health(accountId).then((d) => alive && setH(d)).catch(() => {});
    return () => { alive = false; };
  }, [accountId]);
  if (!h) return null;
  const pct = Math.round((h.score || 0) * 100);
  const color = pct >= 66 ? "bg-emerald-500" : pct >= 33 ? "bg-amber-500" : "bg-red-500";
  const label = pct >= 66 ? "سالم" : pct >= 33 ? "متوسط" : "ضعیف";
  return (
    <div className="border-t border-slate-700 pt-3">
      <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
        <span>سلامت حساب: {fa(pct)}٪ ({label})</span>
        <span>یلوکارت ۷روز: {fa(h.yellow_card_7d)}/{fa(h.sends_7d)}</span>
      </div>
      <div className="h-2 rounded bg-slate-800 overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default function Accounts() {
  const { data, loading, error, reload } = useAsync(Api.list, []);
  const [showAdd, setShowAdd] = React.useState(false);
  const [qr, setQr] = React.useState(null);
  const [busy, setBusy] = React.useState(null);
  const [renaming, setRenaming] = React.useState(null); // account id being renamed
  const [newName, setNewName] = React.useState("");
  const [pfpProg, setPfpProg] = React.useState(null); // {done,total,finished}

  // FEATURE 17 — apply one picture to every account (0.1/s → 10s apart, background).
  const applyPfpAll = async (file) => {
    if (!file) return;
    const n = (data || []).filter((a) => a.status === "active").length;
    const secs = Math.max(0, (n - 1) * 10);
    if (!(await confirmDialog(`⚠️ به دلیل محدودیت Green API، هر شماره ۱۰ ثانیه فاصله دارد. برای ${n} شماره حدود ${secs} ثانیه طول می‌کشد. ادامه؟`))) return;
    try {
      const r = await Api.applyProfilePictureAll(file);
      setPfpProg({ done: 0, total: r.total, finished: false });
      const t = setInterval(async () => {
        try {
          const p = await Api.pfpProgress();
          setPfpProg(p);
          if (p.finished) { clearInterval(t); reload(); setTimeout(() => setPfpProg(null), 4000); }
        } catch { /* ignore */ }
      }, 2000);
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  const startRename = (acc) => { setRenaming(acc.id); setNewName(acc.name); };
  const saveRename = async (id) => {
    const name = newName.trim();
    if (!name) return toast.error("نام حساب نمی‌تواند خالی باشد");
    setBusy(id);
    try {
      await Api.rename(id, name);
      setRenaming(null);
      await reload();
      toast.success("نام حساب تغییر کرد");
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setBusy(null);
    }
  };

  const act = async (fn, id) => {
    setBusy(id);
    try {
      await fn();
      await reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setBusy(null);
    }
  };

  const showQr = async (id) => {
    try {
      const r = await Api.qr(id);
      setQr(r || {});
    } catch (e) {
      toast.error("دریافت QR ناموفق بود");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">حساب‌ها</h2>
        <div className="flex gap-2">
          <label className="btn-secondary cursor-pointer whitespace-nowrap">
            🖼 اعمال عکس روی همه شماره‌ها
            <input type="file" accept="image/*" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; applyPfpAll(f); }} />
          </label>
          <button className="btn-primary" onClick={() => setShowAdd(true)}>+ افزودن حساب</button>
        </div>
      </div>

      {pfpProg && (
        <div className="card border-amber-500/40 bg-amber-500/10 text-amber-200 text-sm">
          {pfpProg.finished ? "✅ عکس روی همه شماره‌ها اعمال شد" : `در حال اعمال عکس پروفایل: ${pfpProg.done} از ${pfpProg.total} شماره…`}
        </div>
      )}

      <div className="card text-sm text-slate-300 bg-sky-500/10 border-sky-500/30">
        هر حساب یک شماره واتساپ مستقل است. می‌توانید چندین حساب همزمان فعال داشته باشید. کمپین‌ها به‌صورت چرخشی (round-robin) بین حساب‌های فعال ارسال می‌شوند.
      </div>

      {loading && <Spinner />}
      {error && <div className="card text-red-400">{error}</div>}
      {data && data.length === 0 && <Empty label="هیچ حسابی ثبت نشده است." />}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {data?.map((a) => (
          <div key={a.id} className="card space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {a.profile_picture_url
                  ? <img src={a.profile_picture_url} alt="" className="w-8 h-8 rounded-full object-cover" />
                  : <div className="w-8 h-8 rounded-full bg-slate-700" />}
                <span className="font-bold">{a.name}</span>
                {a.is_default && (
                  <span className="badge bg-emerald-500/20 text-emerald-300 border-emerald-500/40">پیش‌فرض ⭐</span>
                )}
              </div>
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
              <button className="btn-secondary" onClick={() => startRename(a)}>✏️ ویرایش نام</button>
              <label className="btn-secondary cursor-pointer whitespace-nowrap">
                🖼 عکس پروفایل
                <input type="file" accept="image/*" className="hidden" onChange={async (e) => {
                  const file = e.target.files?.[0]; e.target.value = "";
                  if (!file) return;
                  try { await Api.setProfilePicture(a.id, file); toast.success("عکس پروفایل تنظیم شد"); reload(); }
                  catch (err) { toast.error(err?.response?.data?.detail || err.message); }
                }} />
              </label>
              {!a.is_default && (
                <button className="btn-secondary" disabled={busy === a.id} onClick={() => act(() => Api.setDefault(a.id), a.id)}>تنظیم به‌عنوان پیش‌فرض</button>
              )}
              <button className="btn-danger" disabled={busy === a.id} onClick={async () => {
                if (await confirmDialog("حذف این حساب؟")) act(() => Api.remove(a.id), a.id);
              }}>حذف</button>
            </div>
            {renaming === a.id && (
              <div className="flex gap-2">
                <input
                  className="input flex-1 text-sm"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && saveRename(a.id)}
                  placeholder="نام جدید حساب"
                  autoFocus
                />
                <button className="btn-primary text-xs" disabled={busy === a.id} onClick={() => saveRename(a.id)}>ذخیره</button>
                <button className="btn-secondary text-xs" onClick={() => setRenaming(null)}>لغو</button>
              </div>
            )}
            <HealthSection accountId={a.id} />
            <ProxySection accountId={a.id} />
            <LimitsSection accountId={a.id} />
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
      toast.info(enabled ? (r.applied ? "پروکسی فعال شد" : "ذخیره شد (اعمال روی واتساپ ناموفق)") : "پروکسی غیرفعال شد");
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setBusy(false);
    }
  };

  const syncBlocked = async () => {
    setBusy(true);
    try {
      const r = await ProxyApi.getBlocked(accountId);
      toast.success(`${r.count} مخاطب بلاک‌شده همگام‌سازی شد`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "دریافت لیست بلاک ناموفق بود");
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

function LimitsSection({ accountId }) {
  const [open, setOpen] = React.useState(false);
  const [loaded, setLoaded] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [detail, setDetail] = React.useState(null);
  const [f, setF] = React.useState({ max_daily_absolute: 100, incoming_ratio_multiplier: 0.5 });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const load = async () => {
    try {
      const r = await Api.dailyLimitDetail(accountId);
      setDetail(r);
      setF((prev) => ({
        ...prev,
        max_daily_absolute: r?.breakdown?.absolute_cap ?? prev.max_daily_absolute,
      }));
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
    setLoaded(true);
  };

  const toggle = () => {
    const n = !open;
    setOpen(n);
    if (n && !loaded) load();
  };

  const saveLimits = async () => {
    setBusy(true);
    try {
      const r = await Api.updateLimits(accountId, {
        max_daily_absolute: Number(f.max_daily_absolute),
        incoming_ratio_multiplier: Number(f.incoming_ratio_multiplier),
        max_sends_per_minute: 2.0,
      });
      await load();
      toast.success(`ذخیره شد — سقف مؤثر: ${r.effective_limit}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border-t border-slate-700 pt-3">
      <button className="text-xs text-slate-400 hover:text-slate-200" onClick={toggle}>
        📊 محدودیت‌های ارسال {open ? "▲" : "▼"}
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          {!loaded && <Spinner />}
          {detail && (
            <div className="bg-slate-900 rounded-lg p-3 text-xs space-y-1">
              <p className="font-bold text-emerald-400">
                سقف امروز: {detail.effective_limit} پیام ({detail.sent_today} ارسال، {detail.remaining_today} باقی)
              </p>
              <p className="text-slate-300">{detail.explanation}</p>
              <p className={detail?.breakdown?.week1_cap_active ? "text-amber-400" : "text-emerald-400"}>
                {detail?.meta_compliance?.status}
              </p>
            </div>
          )}
          <div>
            <label className="label">حداکثر ارسال روزانه (مطلق)</label>
            <input
              className="input"
              type="number"
              min="1"
              max="500"
              value={f.max_daily_absolute}
              onChange={set("max_daily_absolute")}
            />
          </div>
          <div>
            <label className="label">ضریب پیام‌های دریافتی (۰.۱ تا ۲.۰)</label>
            <input
              className="input"
              type="number"
              step="0.1"
              value={f.incoming_ratio_multiplier}
              onChange={set("incoming_ratio_multiplier")}
            />
            <p className="text-xs text-slate-500">بیشتر = پیام دریافتی بیشتر سقف را بالا می‌برد</p>
          </div>
          <button className="btn-primary text-sm" disabled={busy} onClick={saveLimits}>ذخیره محدودیت‌ها</button>
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
    if (!form.name || !form.instance_id || !form.api_token) return toast.error("همه فیلدها لازم است");
    setSaving(true);
    try {
      await Api.create(form.name, form.instance_id, form.api_token);
      await onDone();
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title="افزودن حساب جدید" onClose={onClose}>
      <div className="space-y-3">
        <div className="text-xs text-slate-400 space-y-1">
          <p>گام ۱: در green-api.com وارد شوید</p>
          <p>گام ۲: یک Instance جدید بسازید</p>
          <p>گام ۳: Instance ID و API Token را کپی کنید</p>
          <p>گام ۴: اینجا وارد کنید و سپس QR را اسکن کنید</p>
        </div>
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
