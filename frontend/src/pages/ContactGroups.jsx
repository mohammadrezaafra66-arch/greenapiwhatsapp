import React from "react";
import { ContactGroupsApi as Api, Contacts as ContactsApi } from "../api.js";
import { Spinner, Empty, Modal, useAsync } from "../ui.jsx";
import { toast, confirmDialog } from "../ui/toast.jsx";

export default function ContactGroups() {
  const { data, loading, error, reload } = useAsync(() => Api.list(), []);
  const [edit, setEdit] = React.useState(null); // null | {} (new) | group (edit)
  const [members, setMembers] = React.useState(null); // null | group

  const remove = async (id) => {
    if (!(await confirmDialog("حذف گروه؟"))) return;
    try {
      await Api.delete(id);
      await reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">گروه‌های مخاطبین</h2>
        <button className="btn-primary" onClick={() => setEdit({})}>+ گروه جدید</button>
      </div>

      <div className="card text-sm text-slate-300 bg-sky-500/10 border-sky-500/30">
        مخاطبین خود را در گروه‌های دلخواه دسته‌بندی کنید تا ارسال پیام آسان‌تر شود.
      </div>

      {loading && <Spinner />}
      {error && <div className="card text-red-400">{error}</div>}
      {data && data.length === 0 && <Empty label="هیچ گروهی وجود ندارد." />}

      {data && data.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((g) => (
            <div key={g.id} className="card space-y-3">
              <div className="flex items-center gap-2">
                <span
                  className="w-5 h-5 rounded-full border border-slate-600 flex-shrink-0"
                  style={{ background: g.color || "#25D366" }}
                />
                <span className="font-bold truncate">{g.name}</span>
                <span className="badge bg-slate-500/20 text-slate-300 border-slate-500/40 mr-auto">
                  {g.member_count ?? 0} عضو
                </span>
              </div>
              {g.description && (
                <p className="text-sm text-slate-400">{g.description}</p>
              )}
              <div className="flex gap-2 text-sm">
                <button className="text-emerald-400 hover:underline" onClick={() => setMembers(g)}>مشاهده اعضا</button>
                <button className="text-sky-400 hover:underline" onClick={() => setEdit(g)}>ویرایش</button>
                <button className="text-red-400 hover:underline" onClick={() => remove(g.id)}>حذف</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {edit && <GroupModal group={edit} onClose={() => setEdit(null)} onDone={reload} />}
      {members && <MembersModal group={members} onClose={() => setMembers(null)} onDone={reload} />}
    </div>
  );
}

function GroupModal({ group, onClose, onDone }) {
  const isEdit = !!group.id;
  const [f, setF] = React.useState({
    name: group.name || "",
    description: group.description || "",
    color: group.color || "#25D366",
  });
  const [saving, setSaving] = React.useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = async () => {
    if (!f.name.trim()) return toast.error("نام گروه لازم است");
    setSaving(true);
    try {
      const body = { name: f.name, description: f.description, color: f.color };
      if (isEdit) await Api.update(group.id, body);
      else await Api.create(body);
      await onDone();
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title={isEdit ? "ویرایش گروه" : "گروه جدید"} onClose={onClose}>
      <div className="space-y-3">
        <div><label className="label">نام</label><input className="input" value={f.name} onChange={set("name")} /></div>
        <div><label className="label">توضیحات</label><textarea className="input h-24" value={f.description} onChange={set("description")} /></div>
        <div>
          <label className="label">رنگ</label>
          <div className="flex items-center gap-3">
            <input type="color" className="h-10 w-16 rounded bg-slate-800 border border-slate-700 cursor-pointer" value={f.color} onChange={set("color")} />
            <span className="text-sm text-slate-400">{f.color}</span>
          </div>
        </div>
        <button className="btn-primary w-full" disabled={saving} onClick={submit}>{saving ? "..." : "ذخیره"}</button>
      </div>
    </Modal>
  );
}

function MembersModal({ group, onClose, onDone }) {
  const { data: members, loading, error, reload } = useAsync(() => Api.contacts(group.id), [group.id]);
  const [search, setSearch] = React.useState("");
  const [results, setResults] = React.useState(null);
  const [searching, setSearching] = React.useState(false);

  const doSearch = async () => {
    setSearching(true);
    try {
      const list = await ContactsApi.list({ search });
      setResults(list);
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setSearching(false);
    }
  };

  const add = async (contactId) => {
    try {
      await Api.addMembers(group.id, [contactId]);
      await reload();
      await onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  const removeMember = async (contactId) => {
    try {
      await Api.removeMember(group.id, contactId);
      await reload();
      await onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  return (
    <Modal title={`اعضای گروه: ${group.name}`} onClose={onClose} wide>
      <div className="space-y-4">
        <div>
          <h4 className="font-bold mb-2 text-sm">اعضای فعلی</h4>
          {loading && <Spinner />}
          {error && <div className="text-red-400 text-sm">{error}</div>}
          {members && members.length === 0 && <Empty label="این گروه عضوی ندارد." />}
          {members && members.length > 0 && (
            <div className="space-y-1 max-h-52 overflow-y-auto">
              {members.map((m) => (
                <div key={m.id} className="flex items-center gap-2 text-sm border-b border-slate-800 py-1">
                  <span className="font-bold">{m.name || "بدون نام"}</span>
                  <span className="text-slate-400" dir="ltr">{m.phone}</span>
                  {m.has_whatsapp && <span className="badge bg-emerald-500/20 text-emerald-300 border-emerald-500/40">واتساپ</span>}
                  <button className="text-red-400 hover:underline mr-auto" onClick={() => removeMember(m.id)}>حذف</button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="border-t border-slate-700 pt-4">
          <h4 className="font-bold mb-2 text-sm">افزودن عضو</h4>
          <div className="flex gap-2">
            <input
              className="input"
              placeholder="جستجوی مخاطب (نام یا شماره)"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && doSearch()}
            />
            <button className="btn-secondary whitespace-nowrap" disabled={searching} onClick={doSearch}>
              {searching ? "..." : "جستجو"}
            </button>
          </div>
          {results && results.length === 0 && <p className="text-slate-500 text-sm mt-2">مخاطبی یافت نشد.</p>}
          {results && results.length > 0 && (
            <div className="space-y-1 max-h-52 overflow-y-auto mt-2">
              {results.map((c) => (
                <div key={c.id} className="flex items-center gap-2 text-sm border-b border-slate-800 py-1">
                  <span className="font-bold">{c.name || "بدون نام"}</span>
                  <span className="text-slate-400" dir="ltr">{c.phone}</span>
                  {c.province && <span className="text-slate-500">{c.province}</span>}
                  {c.has_whatsapp && <span className="badge bg-emerald-500/20 text-emerald-300 border-emerald-500/40">واتساپ</span>}
                  <button className="text-emerald-400 hover:underline mr-auto" onClick={() => add(c.id)}>افزودن</button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}
