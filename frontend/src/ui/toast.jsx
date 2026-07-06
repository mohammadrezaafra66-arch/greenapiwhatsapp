import React from "react";

// ── Toast notifications (C1.1) ─────────────────────────────
// Dependency-free, module-level emitter so toasts can be fired from anywhere
// (components or plain modules) via toast.success/error/info.
let _id = 0;
let _toasts = [];
const listeners = new Set();
const emit = () => listeners.forEach((l) => l([..._toasts]));

function push(type, message, ttl) {
  const id = ++_id;
  _toasts.push({ id, type, message: String(message ?? "") });
  emit();
  setTimeout(() => {
    _toasts = _toasts.filter((t) => t.id !== id);
    emit();
  }, ttl);
}

export const toast = {
  success: (m) => push("success", m, 4000),
  error: (m) => push("error", m, 6000),
  info: (m) => push("info", m, 4000),
};

const STYLES = {
  success: "bg-emerald-600/95 border-emerald-400",
  error: "bg-red-600/95 border-red-400",
  info: "bg-sky-600/95 border-sky-400",
};
const ICONS = { success: "✅", error: "⛔", info: "ℹ️" };

export function Toaster() {
  const [items, setItems] = React.useState([]);
  React.useEffect(() => {
    listeners.add(setItems);
    return () => listeners.delete(setItems);
  }, []);
  return (
    <div className="fixed top-4 left-1/2 -translate-x-1/2 z-[100] w-full max-w-sm px-2 space-y-2" dir="rtl">
      {items.map((t) => (
        <div
          key={t.id}
          className={`flex items-start gap-2 text-white text-sm rounded-lg border px-4 py-2 shadow-lg ${STYLES[t.type] || STYLES.info}`}
        >
          <span>{ICONS[t.type] || ICONS.info}</span>
          <span className="flex-1 whitespace-pre-line break-words">{t.message}</span>
        </div>
      ))}
    </div>
  );
}

// ── Promise-based confirm dialog (C1.2 — replaces window.confirm) ──
let _confirmResolver = null;
let _confirmState = null;
const confirmListeners = new Set();

export function confirmDialog(message, { confirmText = "تأیید", cancelText = "انصراف", danger = true } = {}) {
  return new Promise((resolve) => {
    _confirmResolver = resolve;
    _confirmState = { message, confirmText, cancelText, danger };
    confirmListeners.forEach((l) => l(_confirmState));
  });
}

function _close(result) {
  if (_confirmResolver) _confirmResolver(result);
  _confirmResolver = null;
  _confirmState = null;
  confirmListeners.forEach((l) => l(null));
}

export function ConfirmHost() {
  const [state, setState] = React.useState(null);
  React.useEffect(() => {
    confirmListeners.add(setState);
    return () => confirmListeners.delete(setState);
  }, []);
  if (!state) return null;
  return (
    <div className="fixed inset-0 z-[110] bg-black/60 flex items-center justify-center p-4" dir="rtl">
      <div className="card w-full max-w-sm">
        <p className="text-sm text-slate-200 mb-4 whitespace-pre-line">{state.message}</p>
        <div className="flex gap-2 justify-end">
          <button className="btn-secondary" onClick={() => _close(false)}>{state.cancelText}</button>
          <button className={state.danger ? "btn-danger" : "btn-primary"} onClick={() => _close(true)}>
            {state.confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
