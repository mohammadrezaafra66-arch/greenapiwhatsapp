import React from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

const NAV = [
  { label: "داشبورد", to: "/", icon: "📊", end: true },
  {
    label: "ارسال پیام", icon: "📨", children: [
      { to: "/campaigns", label: "گروه‌های پیام" },
      { to: "/contact-groups", label: "گروه مخاطبین" },
      { to: "/wa-collections", label: "مجموعه گروه‌های واتساپ" },
    ],
  },
  {
    label: "مخاطبین", icon: "👥", children: [
      { to: "/contacts", label: "مخاطبین" },
      { to: "/blacklist", label: "لیست سیاه" },
    ],
  },
  {
    label: "حساب‌ها", icon: "📱", children: [
      { to: "/accounts", label: "حساب‌های واتساپ" },
      { to: "/account-schedules", label: "زمان‌بندی حساب‌ها" },
    ],
  },
  {
    label: "ابزارها", icon: "🔧", children: [
      { to: "/inbox", label: "صندوق ورودی" },
      { to: "/groups", label: "گروه‌های واتساپ" },
      { to: "/keyword-rules", label: "پاسخ خودکار" },
      { to: "/templates", label: "قالب‌های پیام" },
      { to: "/statuses", label: "استوری‌ها" },
      { to: "/files", label: "فایل‌ها" },
      { to: "/journals", label: "تاریخچه پیام‌ها" },
      { to: "/ai-settings", label: "هوش مصنوعی" },
    ],
  },
  {
    label: "گزارش‌ها", icon: "📋", children: [
      { to: "/reporting", label: "گزارش روزانه" },
      { to: "/products", label: "رصد محصولات" },
    ],
  },
];

const linkClass = ({ isActive }) =>
  `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
    isActive ? "bg-brand/20 text-brand" : "text-slate-300 hover:bg-slate-800"
  }`;

function NavGroup({ item }) {
  const location = useLocation();
  const childActive = item.children.some((c) => location.pathname === c.to || location.pathname.startsWith(c.to + "/"));
  const [open, setOpen] = React.useState(childActive);

  React.useEffect(() => {
    if (childActive) setOpen(true);
  }, [childActive]);

  return (
    <div>
      <button
        onClick={() => setOpen((o) => !o)}
        className={`w-full flex items-center justify-between gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
          childActive ? "text-brand" : "text-slate-300 hover:bg-slate-800"
        }`}
      >
        <span className="flex items-center gap-3">
          <span>{item.icon}</span>
          <span>{item.label}</span>
        </span>
        <span className={`text-xs transition-transform ${open ? "rotate-90" : ""}`}>‹</span>
      </button>
      {open && (
        <div className="mr-4 mt-1 space-y-1 border-r border-slate-800 pr-2">
          {item.children.map((c) => (
            <NavLink key={c.to} to={c.to} className={linkClass}>
              <span className="text-xs">•</span>
              <span>{c.label}</span>
            </NavLink>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Layout() {
  return (
    <div className="flex h-full">
      {/* Sidebar (RTL → right side) */}
      <aside className="w-60 shrink-0 bg-slate-950 border-l border-slate-800 flex flex-col">
        <div className="p-5 border-b border-slate-800">
          <h1 className="text-lg font-bold text-brand">افراکالا</h1>
          <p className="text-xs text-slate-500 mt-0.5">پیام‌رسان افراکالا</p>
        </div>
        <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
          {NAV.map((n) =>
            n.children ? (
              <NavGroup key={n.label} item={n} />
            ) : (
              <NavLink key={n.to} to={n.to} end={n.end} className={linkClass}>
                <span>{n.icon}</span>
                <span>{n.label}</span>
              </NavLink>
            )
          )}
        </nav>
        <div className="p-3 text-xs text-slate-600 border-t border-slate-800">
          متصل به سرور
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-6xl mx-auto p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
