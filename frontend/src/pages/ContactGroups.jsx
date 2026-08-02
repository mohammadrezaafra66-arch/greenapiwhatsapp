import React from "react";
import { ContactGroupsApi as Api, Contacts as ContactsApi } from "../api.js";
import { Spinner, Empty, Modal, useAsync } from "../ui.jsx";
import { toast, confirmDialog } from "../ui/toast.jsx";
import { excludeExisting, toggleSelected, resultsSummary } from "./contactGroupMembers.js";

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

      <div className="card text-sm bg-sky-50 text-sky-700 border-sky-200">
        مخاطبین خود را در گروه‌های دلخواه دسته‌بندی کنید تا ارسال پیام آسان‌تر شود.
      </div>

      {loading && <Spinner />}
      {error && <div className="card bg-red-50 text-red-700 border-red-200">{error}</div>}
      {data && data.length === 0 && <Empty label="هیچ گروهی وجود ندارد." />}

      {data && data.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((g) => (
            <div key={g.id} className="card space-y-3">
              <div className="flex items-center gap-2">
                <span
                  className="w-5 h-5 rounded-full border border-line flex-shrink-0"
                  style={{ background: g.color || "#25D366" }}
                />
                <span className="font-bold truncate">{g.name}</span>
                <span className="badge bg-slate-100 text-slate-600 border-slate-300 mr-auto">
                  {g.member_count ?? 0} عضو
                </span>
              </div>
              {g.description && (
                <p className="text-sm text-muted">{g.description}</p>
              )}
              <div className="flex gap-2">
                <button className="btn-secondary btn-sm" onClick={() => setMembers(g)}>مشاهده اعضا</button>
                <button className="btn-ghost btn-sm" onClick={() => setEdit(g)}>ویرایش</button>
                <button className="btn-danger btn-sm" onClick={() => remove(g.id)}>حذف</button>
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
            <input type="color" className="h-10 w-16 rounded bg-canvas border border-line cursor-pointer" value={f.color} onChange={set("color")} />
            <span className="text-sm text-muted">{f.color}</span>
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
  const [selected, setSelected] = React.useState(new Set());
  const [adding, setAdding] = React.useState(false);

  const doSearch = async () => {
    setSearching(true);
    try {
      // GET /contacts/ returns {total, skip, limit, contacts:[…]} — NOT a bare array.
      // Storing the object made `results.length` undefined, so neither the results nor the
      // "not found" line ever rendered and searching looked like it did nothing.
      setResults(await ContactsApi.list({ search }));
      setSelected(new Set());
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setSearching(false);
    }
  };

  // Contacts matching the search that are NOT already in this group.
  const candidates = React.useMemo(
    () => excludeExisting(results, members), [results, members]);

  const add = async (contactIds) => {
    const ids = contactIds.filter(Boolean);
    if (!ids.length) return;
    setAdding(true);
    try {
      const r = await Api.addMembers(group.id, ids);
      toast.success(`${r.added ?? ids.length} مخاطب به گروه اضافه شد`);
      setSelected(new Set());
      await reload();
      await onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setAdding(false);
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
          {error && <div className="text-red-700 text-sm">{error}</div>}
          {members && members.length === 0 && <Empty label="این گروه عضوی ندارد." />}
          {members && members.length > 0 && (
            <div className="space-y-1 max-h-52 overflow-y-auto">
              {members.map((m) => (
                <div key={m.id} className="flex items-center gap-2 text-sm border-b border-line py-1">
                  <span className="font-bold">{m.name || "بدون نام"}</span>
                  <span className="text-muted" dir="ltr">{m.phone}</span>
                  {m.has_whatsapp && <span className="badge bg-brand-light text-brand border-brand/30">واتساپ</span>}
                  <button className="btn-danger btn-sm mr-auto" onClick={() => removeMember(m.id)}>حذف</button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="border-t border-line pt-4">
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
          {results && (
            <p className="text-muted text-xs mt-2">{resultsSummary(results, members)}</p>
          )}
          {candidates.length > 0 && (
            <>
              {/* Bulk add — the backend has always accepted an array; only the UI was
                  one-at-a-time, which made a 30-contact group impractical to build. */}
              <div className="flex items-center gap-2 mt-2 flex-wrap">
                <label className="flex items-center gap-1 text-xs">
                  <input
                    type="checkbox"
                    checked={selected.size === candidates.length && candidates.length > 0}
                    onChange={(e) =>
                      setSelected(e.target.checked ? new Set(candidates.map((c) => c.id)) : new Set())
                    }
                  />
                  انتخاب همه ({candidates.length})
                </label>
                <button
                  className="btn-primary btn-sm mr-auto"
                  disabled={adding || selected.size === 0}
                  onClick={() => add([...selected])}>
                  {adding ? "در حال افزودن..." : `افزودن انتخاب‌شده‌ها (${selected.size})`}
                </button>
              </div>
              <div className="space-y-1 max-h-52 overflow-y-auto mt-2">
                {candidates.map((c) => (
                  <div key={c.id} className="flex items-center gap-2 text-sm border-b border-line py-1">
                    <input
                      type="checkbox"
                      checked={selected.has(c.id)}
                      onChange={() => setSelected((s) => toggleSelected(s, c.id))}
                    />
                    <span className="font-bold">{c.name || "بدون نام"}</span>
                    <span className="text-muted" dir="ltr">{c.phone}</span>
                    {c.province && <span className="text-muted">{c.province}</span>}
                    {c.has_whatsapp && <span className="badge bg-brand-light text-brand border-brand/30">واتساپ</span>}
                    <button className="btn-secondary btn-sm mr-auto" disabled={adding}
                      onClick={() => add([c.id])}>افزودن</button>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </Modal>
  );
}
