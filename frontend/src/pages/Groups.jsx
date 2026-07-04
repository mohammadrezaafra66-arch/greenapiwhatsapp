import React from "react";
import { Groups as Api, Accounts as AccApi } from "../api.js";
import { Spinner, Empty, Modal, useAsync } from "../ui.jsx";

export default function Groups() {
  const { data, loading, error, reload } = useAsync(Api.list, []);
  const [showAdd, setShowAdd] = React.useState(false);
  const [send, setSend] = React.useState(null);
  const [syncing, setSyncing] = React.useState(false);
  const [search, setSearch] = React.useState("");

  const filtered = (data || []).filter(
    (g) =>
      g.name?.toLowerCase().includes(search.toLowerCase()) ||
      g.green_group_id?.includes(search)
  );

  const syncWhatsapp = async () => {
    setSyncing(true);
    try {
      const accounts = await AccApi.list();
      if (!accounts || accounts.length === 0) return alert("حسابی موجود نیست");
      const account = accounts.find((a) => a.status === "active") || accounts[0];
      const r = await Api.sync(account.id);
      alert(`${r.synced} گروه همگام‌سازی شد`);
      await reload();
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">گروه‌ها</h2>
        <div className="flex gap-2">
          <button className="btn-secondary" disabled={syncing} onClick={syncWhatsapp}>
            {syncing ? "در حال همگام‌سازی..." : "همگام‌سازی با واتساپ"}
          </button>
          <button className="btn-primary" onClick={() => setShowAdd(true)}>+ ساخت گروه</button>
        </div>
      </div>

      <div className="card text-sm text-slate-300 bg-sky-500/10 border-sky-500/30">
        برای نمایش گروه‌های واتساپ، ابتدا روی «همگام‌سازی با واتساپ» کلیک کنید.
      </div>

      <input
        className="input"
        placeholder="جستجو بر اساس نام گروه یا شناسه..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      {loading && <Spinner />}
      {error && <div className="card text-red-400">{error}</div>}
      {data && data.length === 0 && <Empty label="گروهی وجود ندارد." />}
      {data && data.length > 0 && (
        <p className="text-xs text-slate-500">{filtered.length} گروه پیدا شد</p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map((g) => (
          <div key={g.id} className="card space-y-2">
            <div className="font-bold">{g.name}</div>
            <p className="text-sm text-slate-400">{g.description || "—"}</p>
            <p className="text-xs text-slate-500">اعضا: {g.member_count}</p>
            <p className="text-xs text-slate-500 font-mono">{g.green_group_id || "بدون شناسه گروه"}</p>
            <button className="btn-secondary w-full" onClick={() => setSend(g)}>ارسال پیام</button>
          </div>
        ))}
      </div>

      {showAdd && <AddGroupModal onClose={() => setShowAdd(false)} onDone={reload} />}
      {send && <SendModal group={send} onClose={() => setSend(null)} />}
    </div>
  );
}

function AddGroupModal({ onClose, onDone }) {
  const [accounts, setAccounts] = React.useState([]);
  const [f, setF] = React.useState({ account_id: "", name: "", description: "", phones: "" });
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => { AccApi.list().then((a) => { setAccounts(a); if (a[0]) setF((p) => ({ ...p, account_id: a[0].id })); }); }, []);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = async () => {
    if (!f.account_id || !f.name) return alert("حساب و نام لازم است");
    setSaving(true);
    try {
      await Api.create({
        account_id: f.account_id,
        name: f.name,
        description: f.description || null,
        phones: f.phones ? f.phones.split("\n").map((s) => s.trim()).filter(Boolean) : [],
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
    <Modal title="ساخت گروه جدید" onClose={onClose}>
      <div className="space-y-3">
        <div>
          <label className="label">حساب سازنده</label>
          <select className="input" value={f.account_id} onChange={set("account_id")}>
            {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </div>
        <div><label className="label">نام گروه</label><input className="input" value={f.name} onChange={set("name")} /></div>
        <div><label className="label">توضیحات</label><input className="input" value={f.description} onChange={set("description")} /></div>
        <div><label className="label">شماره اعضا (هر خط یک شماره)</label><textarea className="input h-24" value={f.phones} onChange={set("phones")} /></div>
        <button className="btn-primary w-full" disabled={saving} onClick={submit}>{saving ? "..." : "ساخت گروه"}</button>
      </div>
    </Modal>
  );
}

function SendModal({ group, onClose }) {
  const [text, setText] = React.useState("");
  const [sending, setSending] = React.useState(false);
  const send = async () => {
    if (!text) return;
    setSending(true);
    try {
      const r = await Api.send(group.id, text);
      alert(r.sent ? "ارسال شد" : "ارسال ناموفق");
      onClose();
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    } finally {
      setSending(false);
    }
  };
  return (
    <Modal title={`ارسال به گروه: ${group.name}`} onClose={onClose}>
      <div className="space-y-3">
        <textarea className="input h-28" value={text} onChange={(e) => setText(e.target.value)} placeholder="متن پیام..." />
        <button className="btn-primary w-full" disabled={sending} onClick={send}>{sending ? "..." : "ارسال"}</button>
      </div>
    </Modal>
  );
}
