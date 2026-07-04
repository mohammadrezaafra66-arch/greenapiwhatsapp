import React from "react";
import { WaCollectionsApi as Api, Groups as GroupsApi, Accounts } from "../api.js";
import { Spinner, Empty, Modal, useAsync } from "../ui.jsx";

export default function WaCollections() {
  const { data, loading, error, reload } = useAsync(() => Api.list(), []);
  const [edit, setEdit] = React.useState(null); // null | {} (new) | collection (edit)
  const [groups, setGroups] = React.useState(null); // null | collection

  const remove = async (id) => {
    if (!confirm("حذف مجموعه؟")) return;
    try {
      await Api.delete(id);
      await reload();
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">مجموعه گروه‌های واتساپ</h2>
        <button className="btn-primary" onClick={() => setEdit({})}>+ مجموعه جدید</button>
      </div>

      <div className="card text-sm text-slate-300 bg-sky-500/10 border-sky-500/30">
        گروه‌های واتساپ خود را در مجموعه‌های دلخواه دسته‌بندی کنید تا ارسال پیام گروهی ساده‌تر شود.
      </div>

      {loading && <Spinner />}
      {error && <div className="card text-red-400">{error}</div>}
      {data && data.length === 0 && <Empty label="هیچ مجموعه‌ای وجود ندارد." />}

      {data && data.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((c) => (
            <div key={c.id} className="card space-y-3">
              <div className="flex items-center gap-2">
                <span className="font-bold truncate">{c.name}</span>
                <span className="badge bg-slate-500/20 text-slate-300 border-slate-500/40 mr-auto">
                  {c.group_count ?? 0} گروه
                </span>
              </div>
              {c.description && (
                <p className="text-sm text-slate-400">{c.description}</p>
              )}
              <div className="flex gap-2 text-sm">
                <button className="text-emerald-400 hover:underline" onClick={() => setGroups(c)}>مشاهده گروه‌ها</button>
                <button className="text-sky-400 hover:underline" onClick={() => setEdit(c)}>ویرایش</button>
                <button className="text-red-400 hover:underline" onClick={() => remove(c.id)}>حذف</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {edit && <CollectionModal collection={edit} onClose={() => setEdit(null)} onDone={reload} />}
      {groups && <GroupsModal collection={groups} onClose={() => setGroups(null)} onDone={reload} />}
    </div>
  );
}

function CollectionModal({ collection, onClose, onDone }) {
  const isEdit = !!collection.id;
  const [f, setF] = React.useState({
    name: collection.name || "",
    description: collection.description || "",
  });
  const [saving, setSaving] = React.useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = async () => {
    if (!f.name.trim()) return alert("نام مجموعه لازم است");
    setSaving(true);
    try {
      const body = { name: f.name, description: f.description };
      if (isEdit) await Api.update(collection.id, body);
      else await Api.create(body);
      await onDone();
      onClose();
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title={isEdit ? "ویرایش مجموعه" : "مجموعه جدید"} onClose={onClose}>
      <div className="space-y-3">
        <div><label className="label">نام</label><input className="input" value={f.name} onChange={set("name")} /></div>
        <div><label className="label">توضیحات</label><textarea className="input h-24" value={f.description} onChange={set("description")} /></div>
        <button className="btn-primary w-full" disabled={saving} onClick={submit}>{saving ? "..." : "ذخیره"}</button>
      </div>
    </Modal>
  );
}

function GroupsModal({ collection, onClose, onDone }) {
  const { data: current, loading, error, reload } = useAsync(() => Api.groups(collection.id), [collection.id]);
  const [accounts, setAccounts] = React.useState([]);
  const [accountId, setAccountId] = React.useState("");
  const [syncedGroups, setSyncedGroups] = React.useState(null);
  const [selected, setSelected] = React.useState([]);
  const [syncing, setSyncing] = React.useState(false);
  const [adding, setAdding] = React.useState(false);
  const [manual, setManual] = React.useState({ group_chat_id: "", group_name: "" });

  React.useEffect(() => {
    Accounts.list()
      .then((list) => {
        setAccounts(list);
        if (list.length > 0) setAccountId(String(list[0].id));
      })
      .catch(() => {});
  }, []);

  // Step 1: sync WhatsApp groups then load available groups
  const sync = async () => {
    if (!accountId) return alert("ابتدا یک حساب انتخاب کنید");
    setSyncing(true);
    try {
      await GroupsApi.sync(accountId);
      const gs = await Api.availableGroups(accountId);
      setSyncedGroups(gs);
      setSelected([]);
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    } finally {
      setSyncing(false);
    }
  };

  const toggle = (chatId) => {
    setSelected((prev) =>
      prev.includes(chatId) ? prev.filter((c) => c !== chatId) : [...prev, chatId]
    );
  };

  // Step 2: add all selected groups to the collection
  const addSelected = async () => {
    if (selected.length === 0) return alert("ابتدا گروهی را انتخاب کنید");
    setAdding(true);
    try {
      const chosen = (syncedGroups || []).filter((g) => selected.includes(g.group_chat_id));
      for (const g of chosen) {
        await Api.addGroup(collection.id, { group_chat_id: g.group_chat_id, group_name: g.name });
      }
      await reload();
      await onDone();
      setSelected([]);
      alert(`${chosen.length} گروه افزوده شد`);
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    } finally {
      setAdding(false);
    }
  };

  const removeGroup = async (chatId) => {
    try {
      await Api.removeGroup(collection.id, chatId);
      await reload();
      await onDone();
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    }
  };

  const addManual = async () => {
    const group_chat_id = manual.group_chat_id.trim();
    if (!group_chat_id) return alert("شناسه گروه لازم است");
    try {
      await Api.addGroup(collection.id, { group_chat_id, group_name: manual.group_name.trim() });
      await reload();
      await onDone();
      setManual({ group_chat_id: "", group_name: "" });
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    }
  };

  return (
    <Modal title={`گروه‌های مجموعه: ${collection.name}`} onClose={onClose} wide>
      <div className="space-y-4">
        <div>
          <h4 className="font-bold mb-2 text-sm">گروه‌های فعلی</h4>
          {loading && <Spinner />}
          {error && <div className="text-red-400 text-sm">{error}</div>}
          {current && current.length === 0 && <Empty label="این مجموعه گروهی ندارد." />}
          {current && current.length > 0 && (
            <div className="space-y-1 max-h-52 overflow-y-auto">
              {current.map((g) => (
                <div key={g.id} className="flex items-center gap-2 text-sm border-b border-slate-800 py-1">
                  <span className="font-bold">{g.group_name || "بدون نام"}</span>
                  <span className="text-slate-500 text-xs" dir="ltr">{g.group_chat_id}</span>
                  <button className="text-red-400 hover:underline mr-auto" onClick={() => removeGroup(g.group_chat_id)}>حذف</button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="border-t border-slate-700 pt-4 space-y-2">
          <h4 className="font-bold text-sm">افزودن از واتساپ</h4>

          {/* Step 1: pick account + sync */}
          <div className="flex gap-2">
            <select className="input" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
              {accounts.length === 0 && <option value="">حسابی موجود نیست</option>}
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </select>
            <button className="btn-secondary whitespace-nowrap" disabled={syncing} onClick={sync}>
              {syncing ? "در حال همگام‌سازی..." : "همگام‌سازی گروه‌ها"}
            </button>
          </div>

          {/* Step 2: checkbox list of synced groups */}
          {syncedGroups && syncedGroups.length === 0 && <p className="text-slate-500 text-sm">گروهی یافت نشد.</p>}
          {syncedGroups && syncedGroups.length > 0 && (
            <>
              <div className="space-y-1 max-h-52 overflow-y-auto border border-slate-700 rounded-lg p-2">
                {syncedGroups.map((g) => (
                  <label key={g.group_chat_id} className="flex items-center gap-2 cursor-pointer border-b border-slate-800 py-1 last:border-0">
                    <input
                      type="checkbox"
                      checked={selected.includes(g.group_chat_id)}
                      onChange={() => toggle(g.group_chat_id)}
                    />
                    <span>{g.name}</span>
                    <span className="text-xs text-slate-400">{g.member_count} عضو</span>
                    <span className="text-[10px] text-slate-500 font-mono mr-auto" dir="ltr">{g.group_chat_id}</span>
                  </label>
                ))}
              </div>
              <button className="btn-primary w-full" disabled={adding} onClick={addSelected}>
                {adding ? "در حال افزودن..." : `افزودن گروه‌های انتخابی (${selected.length})`}
              </button>
            </>
          )}
        </div>

        <div className="border-t border-slate-700 pt-4 space-y-2">
          <h4 className="font-bold text-sm">افزودن دستی</h4>
          <div className="grid grid-cols-2 gap-2">
            <input
              className="input"
              placeholder="شناسه گروه"
              value={manual.group_chat_id}
              onChange={(e) => setManual({ ...manual, group_chat_id: e.target.value })}
            />
            <input
              className="input"
              placeholder="نام گروه"
              value={manual.group_name}
              onChange={(e) => setManual({ ...manual, group_name: e.target.value })}
            />
          </div>
          <button className="btn-secondary w-full" onClick={addManual}>افزودن دستی</button>
        </div>
      </div>
    </Modal>
  );
}
