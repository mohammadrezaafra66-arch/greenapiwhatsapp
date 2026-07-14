import React from "react";
import { MessagesApi } from "../api.js";
import { useAsync, Spinner, Empty } from "../ui.jsx";
import { toast, confirmDialog } from "../ui/toast.jsx";

// FEATURE 12/13 — «کارت تماس و موقعیت»: manage reusable contact cards + locations.
export default function Content() {
  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">کارت تماس و موقعیت</h2>
      <SavedContacts />
      <SavedLocations />
    </div>
  );
}

function SavedContacts() {
  const { data, loading, reload } = useAsync(() => MessagesApi.savedContacts(), []);
  const [f, setF] = React.useState({ label: "", phone_contact: "", first_name: "", last_name: "", company: "افراکالا" });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  async function add() {
    if (!f.label.trim() || !f.phone_contact.trim()) return toast.error("عنوان و شماره لازم است");
    try {
      await MessagesApi.createSavedContact(f);
      toast.success("کارت ذخیره شد");
      setF({ label: "", phone_contact: "", first_name: "", last_name: "", company: "افراکالا" });
      reload();
    } catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }
  async function del(id) {
    if (!(await confirmDialog("این کارت حذف شود؟"))) return;
    await MessagesApi.deleteSavedContact(id); reload();
  }

  return (
    <div className="card space-y-3">
      <h3 className="font-bold">کارت‌های تماس ذخیره‌شده</h3>
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
        <input className="input" placeholder="عنوان (مثلاً: پشتیبانی)" value={f.label} onChange={set("label")} />
        <input className="input" placeholder="شماره (989...)" value={f.phone_contact} onChange={set("phone_contact")} />
        <input className="input" placeholder="نام" value={f.first_name} onChange={set("first_name")} />
        <input className="input" placeholder="نام خانوادگی" value={f.last_name} onChange={set("last_name")} />
        <input className="input" placeholder="شرکت" value={f.company} onChange={set("company")} />
      </div>
      <button className="btn-primary" onClick={add}>افزودن کارت</button>
      {loading ? <Spinner /> : (!data || data.length === 0) ? <Empty label="کارتی ذخیره نشده." /> : (
        <table className="w-full text-sm">
          <tbody>
            {data.map((c) => (
              <tr key={c.id} className="border-t border-slate-800">
                <td className="p-2">{c.label}</td>
                <td className="p-2 font-mono text-xs">{c.phone_contact}</td>
                <td className="p-2">{[c.first_name, c.last_name].filter(Boolean).join(" ")}</td>
                <td className="p-2">{c.company}</td>
                <td className="p-2 text-left"><button className="btn-danger text-xs" onClick={() => del(c.id)}>حذف</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function SavedLocations() {
  const { data, loading, reload } = useAsync(() => MessagesApi.savedLocations(), []);
  const [f, setF] = React.useState({ name: "", address: "", latitude: "", longitude: "" });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  async function add() {
    if (!f.name.trim() || !f.latitude || !f.longitude) return toast.error("نام و مختصات لازم است");
    try {
      await MessagesApi.createSavedLocation({
        name: f.name, address: f.address,
        latitude: Number(f.latitude), longitude: Number(f.longitude),
      });
      toast.success("موقعیت ذخیره شد");
      setF({ name: "", address: "", latitude: "", longitude: "" });
      reload();
    } catch (e) { toast.error(e?.response?.data?.detail || e.message); }
  }
  async function del(id) {
    if (!(await confirmDialog("این موقعیت حذف شود؟"))) return;
    await MessagesApi.deleteSavedLocation(id); reload();
  }

  return (
    <div className="card space-y-3">
      <h3 className="font-bold">موقعیت‌های ذخیره‌شده</h3>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <input className="input" placeholder="نام (مثلاً: فروشگاه)" value={f.name} onChange={set("name")} />
        <input className="input" placeholder="آدرس" value={f.address} onChange={set("address")} />
        <input className="input" placeholder="عرض (latitude)" value={f.latitude} onChange={set("latitude")} />
        <input className="input" placeholder="طول (longitude)" value={f.longitude} onChange={set("longitude")} />
      </div>
      <button className="btn-primary" onClick={add}>افزودن موقعیت</button>
      {loading ? <Spinner /> : (!data || data.length === 0) ? <Empty label="موقعیتی ذخیره نشده." /> : (
        <table className="w-full text-sm">
          <tbody>
            {data.map((l) => (
              <tr key={l.id} className="border-t border-slate-800">
                <td className="p-2">{l.name}</td>
                <td className="p-2">{l.address}</td>
                <td className="p-2 font-mono text-xs">{l.latitude}, {l.longitude}</td>
                <td className="p-2 text-left"><button className="btn-danger text-xs" onClick={() => del(l.id)}>حذف</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
