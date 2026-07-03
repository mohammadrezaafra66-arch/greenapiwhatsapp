import React from "react";
import { Contacts as Api, Campaigns as CampApi, ContactExtrasApi } from "../api.js";
import { Spinner, Empty, Modal } from "../ui.jsx";

const DISAPPEARING_OPTS = [
  { label: "خاموش", value: 0 },
  { label: "۲۴ ساعت", value: 86400 },
  { label: "۷ روز", value: 604800 },
  { label: "۹۰ روز", value: 7776000 },
];

export default function Contacts() {
  const [search, setSearch] = React.useState("");
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [selected, setSelected] = React.useState(new Set());
  const [importing, setImporting] = React.useState(false);
  const [addToCampaign, setAddToCampaign] = React.useState(false);
  const [addManual, setAddManual] = React.useState(false);
  const [showGuide, setShowGuide] = React.useState(false);
  const [showCheckInfo, setShowCheckInfo] = React.useState(false);
  const [disappearing, setDisappearing] = React.useState(null); // contact | null

  const addToPhonebook = async (id) => {
    try {
      const r = await ContactExtrasApi.addToPhonebook(id);
      alert(r.added ? "به مخاطبین واتساپ اضافه شد" : "افزودن ناموفق بود");
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    }
  };

  const applyDisappearing = async (id, ephemeral) => {
    try {
      const r = await ContactExtrasApi.setDisappearing(id, ephemeral);
      alert(r.set ? `تنظیم شد: ${r.label}` : "تنظیم ناموفق بود");
      setDisappearing(null);
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    }
  };
  const fileRef = React.useRef();

  const load = React.useCallback(() => {
    setLoading(true);
    Api.list({ search: search || undefined })
      .then(setData)
      .finally(() => setLoading(false));
  }, [search]);

  React.useEffect(() => {
    const t = setTimeout(load, 300);
    return () => clearTimeout(t);
  }, [load]);

  const toggle = (id) => {
    const n = new Set(selected);
    n.has(id) ? n.delete(id) : n.add(id);
    setSelected(n);
  };

  const onImport = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const r = await Api.import(file);
      alert(`اضافه شد: ${r.added} · تکراری: ${r.skipped} · کل: ${r.total_in_file}`);
      load();
    } catch (err) {
      alert(err?.response?.data?.detail || err.message);
    } finally {
      setImporting(false);
      e.target.value = "";
    }
  };

  const checkSelected = async () => {
    if (selected.size === 0) return alert("هیچ مخاطبی انتخاب نشده");
    try {
      const r = await Api.checkBulk([...selected]);
      alert(`بررسی شد: ${r.checked} مخاطب`);
      load();
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="text-2xl font-bold">مخاطبین</h2>
        <div className="flex flex-wrap gap-2">
          <input ref={fileRef} type="file" accept=".xlsx,.xls" className="hidden" onChange={onImport} />
          <button className="btn-secondary" disabled={importing} onClick={() => fileRef.current?.click()}>
            {importing ? "در حال ورود..." : "ورود از اکسل"}
          </button>
          <button className="btn-secondary" onClick={() => setAddManual(true)}>افزودن دستی</button>
          <button className="btn-secondary" onClick={checkSelected}>بررسی واتس‌اپ ({selected.size})</button>
          <button className="btn-secondary" title="راهنما" onClick={() => setShowCheckInfo((v) => !v)}>؟</button>
          <button className="btn-primary" onClick={() => selected.size ? setAddToCampaign(true) : alert("مخاطبی انتخاب نشده")}>
            افزودن به گروه پیام ({selected.size})
          </button>
        </div>
      </div>

      {showCheckInfo && (
        <div className="card text-xs text-slate-400">
          این دکمه شماره‌های انتخاب‌شده را بررسی می‌کند که آیا واتساپ دارند یا خیر. شماره‌هایی که واتساپ ندارند از ارسال کمپین خودکار حذف می‌شوند.
        </div>
      )}

      <div className="card p-0 overflow-hidden">
        <button
          className="w-full flex items-center justify-between p-3 text-sm text-slate-300 hover:bg-slate-800/50"
          onClick={() => setShowGuide((v) => !v)}
        >
          <span className="flex items-center gap-2">
            <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-brand/20 text-brand text-xs font-bold">؟</span>
            راهنمای آپلود اکسل
          </span>
          <span className="text-slate-500">{showGuide ? "▲" : "▼"}</span>
        </button>
        {showGuide && (
          <div className="border-t border-slate-700 p-4 space-y-3 text-sm text-slate-300">
            <ul className="space-y-1.5 list-disc pr-5">
              <li><b>فرمت فایل:</b> xlsx یا xls</li>
              <li><b>ستون اجباری:</b> phone یا شماره یا موبایل</li>
              <li><b>ستون‌های اختیاری:</b> first_name/نام، last_name/فامیلی، province/استان، city/شهر</li>
              <li><b>فرمت شماره:</b> 09xxxxxxxxx یا 989xxxxxxxxx یا +98xxxxxxxxx (هر فرمتی قبول می‌شه)</li>
              <li>شماره‌های تکراری خودکار حذف می‌شن</li>
            </ul>
            <div>
              <p className="text-xs text-slate-500 mb-1">نمونه:</p>
              <div className="overflow-x-auto">
                <table className="text-xs border border-slate-700 rounded">
                  <thead className="text-slate-400 bg-slate-800/60">
                    <tr>
                      <th className="p-2 border border-slate-700 text-right">phone</th>
                      <th className="p-2 border border-slate-700 text-right">first_name</th>
                      <th className="p-2 border border-slate-700 text-right">last_name</th>
                      <th className="p-2 border border-slate-700 text-right">province</th>
                      <th className="p-2 border border-slate-700 text-right">city</th>
                    </tr>
                  </thead>
                  <tbody className="text-slate-300">
                    <tr>
                      <td className="p-2 border border-slate-700 font-mono">09121234567</td>
                      <td className="p-2 border border-slate-700">علی</td>
                      <td className="p-2 border border-slate-700">رضایی</td>
                      <td className="p-2 border border-slate-700">تهران</td>
                      <td className="p-2 border border-slate-700">تهران</td>
                    </tr>
                    <tr>
                      <td className="p-2 border border-slate-700 font-mono">989351234567</td>
                      <td className="p-2 border border-slate-700">مریم</td>
                      <td className="p-2 border border-slate-700">احمدی</td>
                      <td className="p-2 border border-slate-700">اصفهان</td>
                      <td className="p-2 border border-slate-700">کاشان</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </div>

      <input className="input" placeholder="جستجو بر اساس نام یا شماره..." value={search} onChange={(e) => setSearch(e.target.value)} />

      {loading && <Spinner />}
      {data && data.length === 0 && <Empty label="مخاطبی یافت نشد." />}

      {data && data.length > 0 && (
        <div className="card overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="text-slate-400 border-b border-slate-700">
              <tr>
                <th className="p-3 text-right">
                  <input type="checkbox" onChange={(e) => setSelected(e.target.checked ? new Set(data.map((c) => c.id)) : new Set())} checked={data.length > 0 && selected.size === data.length} />
                </th>
                <th className="p-3 text-right">نام</th>
                <th className="p-3 text-right">شماره</th>
                <th className="p-3 text-right">استان</th>
                <th className="p-3 text-right">واتس‌اپ</th>
                <th className="p-3 text-right"></th>
              </tr>
            </thead>
            <tbody>
              {data.map((c) => (
                <tr key={c.id} className="border-b border-slate-800 hover:bg-slate-800/50">
                  <td className="p-3"><input type="checkbox" checked={selected.has(c.id)} onChange={() => toggle(c.id)} /></td>
                  <td className="p-3">{c.name}</td>
                  <td className="p-3 font-mono text-xs">{c.phone}</td>
                  <td className="p-3">{c.province || "—"}</td>
                  <td className="p-3">
                    {c.has_whatsapp === true ? <span className="text-emerald-400">✓</span> : c.has_whatsapp === false ? <span className="text-red-400">✗</span> : <span className="text-slate-500">?</span>}
                  </td>
                  <td className="p-3">
                    <div className="flex gap-2 flex-wrap">
                      <button className="text-sky-400 hover:underline text-xs" title="پیام ناپدیدشونده" onClick={() => setDisappearing(c)}>⏱️</button>
                      <button className="text-emerald-400 hover:underline text-xs" title="افزودن به مخاطبین واتساپ" onClick={() => addToPhonebook(c.id)}>📱</button>
                      <button className="text-red-400 hover:underline text-xs" onClick={async () => { if (confirm("این مخاطب مسدود شود؟")) { await Api.blacklist(c.id); load(); } }}>لیست سیاه</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {addToCampaign && (
        <AddToCampaignModal contactIds={[...selected]} onClose={() => setAddToCampaign(false)} onDone={() => setSelected(new Set())} />
      )}

      {addManual && (
        <AddContactModal onClose={() => setAddManual(false)} onDone={load} />
      )}

      {disappearing && (
        <Modal title={`مدت نگهداری پیام — ${disappearing.name || disappearing.phone}`} onClose={() => setDisappearing(null)}>
          <div className="grid grid-cols-2 gap-3">
            {DISAPPEARING_OPTS.map((opt) => (
              <button key={opt.value} className="btn-secondary p-3 text-center" onClick={() => applyDisappearing(disappearing.id, opt.value)}>
                {opt.label}
              </button>
            ))}
          </div>
          <p className="text-xs text-slate-400 mt-3">پیام‌های این چت پس از مدت انتخابی به‌طور خودکار حذف می‌شوند.</p>
        </Modal>
      )}
    </div>
  );
}

function AddContactModal({ onClose, onDone }) {
  const [f, setF] = React.useState({ phone: "", first_name: "", last_name: "", province: "", city: "" });
  const [saving, setSaving] = React.useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = async () => {
    if (!f.phone.trim()) return alert("شماره موبایل الزامی است");
    setSaving(true);
    try {
      await Api.create({
        phone: f.phone.trim(),
        first_name: f.first_name.trim() || null,
        last_name: f.last_name.trim() || null,
        province: f.province.trim() || null,
        city: f.city.trim() || null,
      });
      await onDone();
      onClose();
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title="افزودن مخاطب دستی" onClose={onClose}>
      <div className="space-y-3">
        <div>
          <label className="label">شماره موبایل *</label>
          <input className="input" value={f.phone} onChange={set("phone")} placeholder="09123456789" />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div><label className="label">نام</label><input className="input" value={f.first_name} onChange={set("first_name")} /></div>
          <div><label className="label">نام خانوادگی</label><input className="input" value={f.last_name} onChange={set("last_name")} /></div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div><label className="label">استان</label><input className="input" value={f.province} onChange={set("province")} /></div>
          <div><label className="label">شهر</label><input className="input" value={f.city} onChange={set("city")} /></div>
        </div>
        <button className="btn-primary w-full" disabled={saving} onClick={submit}>{saving ? "در حال ذخیره..." : "ذخیره مخاطب"}</button>
      </div>
    </Modal>
  );
}

function AddToCampaignModal({ contactIds, onClose, onDone }) {
  const [campaigns, setCampaigns] = React.useState(null);
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => { CampApi.list().then(setCampaigns); }, []);

  const add = async (id) => {
    setBusy(true);
    try {
      const r = await CampApi.addContacts(id, contactIds);
      alert(`${r.added} مخاطب اضافه شد`);
      onDone();
      onClose();
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title={`افزودن ${contactIds.length} مخاطب به گروه پیام`} onClose={onClose}>
      {!campaigns && <Spinner />}
      {campaigns && campaigns.length === 0 && <Empty label="ابتدا یک گروه پیام بسازید." />}
      <div className="space-y-2">
        {campaigns?.map((c) => (
          <button key={c.id} disabled={busy} className="btn-secondary w-full text-right" onClick={() => add(c.id)}>
            {c.name}
          </button>
        ))}
      </div>
    </Modal>
  );
}
