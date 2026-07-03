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
  const [waGroups, setWaGroups] = React.useState(null);
  const [syncing, setSyncing] = React.useState(false);
  const [manual, setManual] = React.useState({ group_chat_id: "", group_name: "" });

  React.useEffect(() => {
    Accounts.list()
      .then((list) => {
        setAccounts(list);
        if (list.length > 0) setAccountId(String(list[0].id));
      })
      .catch(() => {});
  }, []);

  const sync = async () => {
    if (!accountId) return alert("ابتدا یک حساب انتخاب کنید");
    setSyncing(true);
    try {
      await GroupsApi.sync(accountId);
      const list = await GroupsApi.list();
      setWaGroups(list);
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
    } finally {
      setSyncing(false);
    }
  };

  const addGroup = async (group_chat_id, group_name) => {
    if (!group_chat_id) return alert("شناسه گروه لازم است");
    try {
      await Api.addGroup(collection.id, { group_chat_id, group_name });
      await reload();
      await onDone();
    } catch (e) {
      alert(e?.response?.data?.detail || e.message);
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
    await addGroup(manual.group_chat_id.trim(), manual.group_name.trim());
    setManual({ group_chat_id: "", group_name: "" });
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
          <div className="flex gap-2">
            <select className="input" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
              {accounts.length === 0 && <option value="">حسابی موجود نیست</option>}
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </select>
            <button className="btn-secondary whitespace-nowrap" disabled={syncing} onClick={sync}>
              {syncing ? "..." : "همگام‌سازی گروه‌های واتساپ"}
            </button>
          </div>
          {waGroups && waGroups.length === 0 && <p className="text-slate-500 text-sm">گروهی یافت نشد.</p>}
          {waGroups && waGroups.length > 0 && (
            <div className="space-y-1 max-h-52 overflow-y-auto">
              {waGroups.map((g) => (
                <div key={g.id} className="flex items-center gap-2 text-sm border-b border-slate-800 py-1">
                  <span className="font-bold">{g.name || "بدون نام"}</span>
                  <span className="text-slate-500 text-xs" dir="ltr">{g.green_group_id}</span>
                  {g.member_count != null && <span className="text-slate-500">{g.member_count} عضو</span>}
                  <button className="text-emerald-400 hover:underline mr-auto" onClick={() => addGroup(g.green_group_id, g.name)}>افزودن</button>
                </div>
              ))}
            </div>
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
