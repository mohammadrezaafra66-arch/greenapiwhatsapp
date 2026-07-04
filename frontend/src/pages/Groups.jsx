import React from "react";
import { Groups as Api, Accounts as AccApi } from "../api.js";
import { Spinner, Empty, Modal } from "../ui.jsx";

const CHAT_TYPE_LABELS = {
  group: { label: "گروه معمولی", icon: "👥", cls: "text-emerald-400" },
  broadcast: { label: "لیست انتشار", icon: "📢", cls: "text-sky-400" },
};

const MEMBER_FILTERS = [
  { label: "همه", min: 0 },
  { label: "+۱۰ نفر", min: 10 },
  { label: "+۵۰ نفر", min: 50 },
  { label: "+۱۰۰ نفر", min: 100 },
  { label: "+۵۰۰ نفر", min: 500 },
];

const TYPE_TABS = [
  { key: "all", label: "همه" },
  { key: "group", label: "👥 گروه" },
  { key: "broadcast", label: "📢 انتشار" },
];

const fa = (n) => Number(n || 0).toLocaleString("fa-IR");

export default function Groups() {
  const [groups, setGroups] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);
  const [search, setSearch] = React.useState("");
  const [typeFilter, setTypeFilter] = React.useState("all");
  const [minMembers, setMinMembers] = React.useState(0);
  const [accounts, setAccounts] = React.useState([]);
  const [selectedAccount, setSelectedAccount] = React.useState("");
  const [syncing, setSyncing] = React.useState(false);
  const [showAdd, setShowAdd] = React.useState(false);
  const [send, setSend] = React.useState(null);
  const [busy, setBusy] = React.useState(null);

  const loadGroups = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {};
      if (typeFilter !== "all") params.chat_type = typeFilter;
      if (minMembers > 0) params.min_members = minMembers;
      setGroups(await Api.list(params));
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [typeFilter, minMembers]);

  React.useEffect(() => {
    AccApi.list()
      .then((a) => {
        setAccounts(a || []);
        const act = (a || []).find((x) => x.status === "active");
        if (act) setSelectedAccount(act.id);
      })
      .catch(() => {});
  }, []);

  React.useEffect(() => { loadGroups(); }, [loadGroups]);

  const activeAccounts = accounts.filter((a) => a.status === "active");
  const filtered = groups.filter((g) => g.name?.includes(search) || g.group_chat_id?.includes(search));

  const syncGroups = async () => {
    if (!selectedAccount) return alert("حساب فعالی انتخاب نشده است");
    setSyncing(true);
    try {
      const r = await Api.sync(selectedAccount);
      alert(`${r.synced_new} گروه جدید + ${r.updated} به‌روزرسانی شد`);
      await loadGroups();
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    } finally {
      setSyncing(false);
    }
  };

  const refreshMembers = async (gid) => {
    setBusy(gid);
    try {
      await Api.refreshMembers(gid);
      await loadGroups();
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    } finally {
      setBusy(null);
    }
  };

  const copyId = (id) => {
    navigator.clipboard?.writeText(id);
    alert("شناسه کپی شد");
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="text-2xl font-bold">گروه‌های واتساپ</h2>
        <div className="flex gap-2 flex-wrap">
          <select className="input w-auto" value={selectedAccount} onChange={(e) => setSelectedAccount(e.target.value)}>
            {activeAccounts.length === 0 && <option value="">— حساب فعالی نیست —</option>}
            {activeAccounts.map((a) => <option key={a.id} value={a.id}>{a.name}{a.phone ? ` (${a.phone})` : ""}</option>)}
          </select>
          <button className="btn-secondary" disabled={syncing} onClick={syncGroups}>
            {syncing ? "در حال همگام‌سازی..." : "🔄 همگام‌سازی با واتساپ"}
          </button>
          <button className="btn-primary" onClick={() => setShowAdd(true)}>+ ساخت گروه</button>
        </div>
      </div>

      <div className="card text-sm text-sky-300 bg-sky-500/10 border-sky-500/30">
        💡 برای نمایش گروه‌ها ابتدا «همگام‌سازی با واتساپ» را بزنید. گروه‌های معمولی و لیست‌های انتشاری که عضو آن‌ها هستید نمایش داده می‌شوند. کانال‌های واتساپ پشتیبانی نمی‌شوند.
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <input
          className="input flex-1 min-w-48"
          placeholder="جستجو بر اساس نام گروه یا شناسه..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="flex gap-1 bg-slate-800 rounded-lg p-1">
          {TYPE_TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTypeFilter(t.key)}
              className={`px-3 py-1 rounded text-sm ${typeFilter === t.key ? "bg-brand text-white" : "text-slate-400 hover:text-slate-200"}`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <select className="input w-auto" value={minMembers} onChange={(e) => setMinMembers(Number(e.target.value))}>
          {MEMBER_FILTERS.map((f) => <option key={f.min} value={f.min}>{f.label}</option>)}
        </select>
      </div>

      <div className="text-sm text-slate-400">
        {fa(filtered.length)} گروه نمایش داده می‌شود
        {groups.length !== filtered.length && ` (از ${fa(groups.length)} کل)`}
      </div>

      {loading && <Spinner />}
      {error && <div className="card text-red-400">{error}</div>}
      {!loading && filtered.length === 0 && (
        <Empty label={groups.length === 0 ? "گروهی پیدا نشد — ابتدا همگام‌سازی کنید." : "گروهی با این فیلترها پیدا نشد."} />
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map((g) => {
          const t = CHAT_TYPE_LABELS[g.chat_type] || CHAT_TYPE_LABELS.group;
          return (
            <div key={g.id} className="card space-y-2">
              <div className="flex justify-between items-start gap-2">
                <h3 className="font-bold text-sm leading-tight">{g.name}</h3>
                <span className={`text-xs whitespace-nowrap ${t.cls}`}>{t.icon} {t.label}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-2xl font-bold text-emerald-400">{g.member_count > 0 ? fa(g.member_count) : "—"}</span>
                <span className="text-slate-400 text-sm">عضو</span>
                <button
                  className="text-xs text-slate-500 hover:text-slate-300 mr-auto disabled:opacity-40"
                  disabled={busy === g.id}
                  title="به‌روزرسانی تعداد اعضا"
                  onClick={() => refreshMembers(g.id)}
                >
                  {busy === g.id ? "…" : "🔄"}
                </button>
              </div>
              {g.description && <p className="text-slate-400 text-xs line-clamp-2">{g.description}</p>}
              <p className="text-slate-500 text-xs font-mono truncate">{g.group_chat_id || "بدون شناسه"}</p>
              <div className="flex gap-2">
                <button className="btn-secondary flex-1 text-xs" onClick={() => setSend(g)}>ارسال پیام</button>
                <button className="btn-secondary text-xs px-2" title="کپی شناسه" onClick={() => copyId(g.group_chat_id)}>📋</button>
              </div>
            </div>
          );
        })}
      </div>

      {showAdd && <AddGroupModal onClose={() => setShowAdd(false)} onDone={loadGroups} />}
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
