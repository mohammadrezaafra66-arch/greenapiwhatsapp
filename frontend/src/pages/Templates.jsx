import React from "react";
import { Templates as Api } from "../api.js";
import { Spinner, Empty, Modal, useAsync } from "../ui.jsx";

export default function Templates() {
  const { data, loading, error, reload } = useAsync(() => Api.list(), []);
  const [showAdd, setShowAdd] = React.useState(false);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">قالب‌های پیام</h2>
        <button className="btn-primary" onClick={() => setShowAdd(true)}>+ قالب جدید</button>
      </div>

      {loading && <Spinner />}
      {error && <div className="card text-red-400">{error}</div>}
      {data && data.length === 0 && <Empty label="قالبی وجود ندارد." />}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {data?.map((t) => (
          <div key={t.id} className="card space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-bold">{t.name}</span>
              <span className="badge bg-slate-700 text-slate-300 border-slate-600">{t.category || "عمومی"}</span>
            </div>
            <p className="text-sm text-slate-300 whitespace-pre-wrap">{t.content}</p>
            <div className="flex items-center justify-between text-xs text-slate-500">
              <span>استفاده: {t.use_count} بار</span>
              <div className="flex gap-2">
                <button className="text-sky-400 hover:underline" onClick={async () => { const r = await Api.use(t.id); navigator.clipboard?.writeText(r.content); alert("کپی شد"); reload(); }}>کپی</button>
                <button className="text-red-400 hover:underline" onClick={async () => { if (confirm("حذف؟")) { await Api.remove(t.id); reload(); } }}>حذف</button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {showAdd && <AddTemplateModal onClose={() => setShowAdd(false)} onDone={reload} />}
    </div>
  );
}

function AddTemplateModal({ onClose, onDone }) {
  const [f, setF] = React.useState({ name: "", category: "", content: "", campaign_type: "text" });
  const [saving, setSaving] = React.useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = async () => {
    if (!f.name || !f.content) return alert("نام و متن لازم است");
    setSaving(true);
    try {
      await Api.create(f);
      await onDone();
      onClose();
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title="قالب جدید" onClose={onClose}>
      <div className="space-y-3">
        <div><label className="label">نام</label><input className="input" value={f.name} onChange={set("name")} /></div>
        <div><label className="label">دسته (اختیاری)</label><input className="input" value={f.category} onChange={set("category")} placeholder="مثلا: مناسبتی / محصول / عمومی" /></div>
        <div><label className="label">متن</label><textarea className="input h-28" value={f.content} onChange={set("content")} /></div>
        <button className="btn-primary w-full" disabled={saving} onClick={submit}>{saving ? "در حال ذخیره..." : "ذخیره"}</button>
      </div>
    </Modal>
  );
}
