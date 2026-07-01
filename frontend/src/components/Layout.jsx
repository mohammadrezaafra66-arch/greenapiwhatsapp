import React from "react";
import { NavLink, Outlet } from "react-router-dom";

const NAV = [
  { to: "/", label: "داشبورد", icon: "📊", end: true },
  { to: "/accounts", label: "حساب‌ها", icon: "📱" },
  { to: "/campaigns", label: "کمپین‌ها", icon: "📨" },
  { to: "/contacts", label: "مخاطبین", icon: "👥" },
  { to: "/inbox", label: "صندوق ورودی", icon: "💬" },
  { to: "/groups", label: "گروه‌ها", icon: "👨‍👩‍👧" },
  { to: "/statuses", label: "استوری‌ها", icon: "🟢" },
  { to: "/templates", label: "قالب‌ها", icon: "📝" },
  { to: "/blacklist", label: "لیست سیاه", icon: "🚫" },
  { to: "/keyword-rules", label: "پاسخ خودکار", icon: "🔑" },
  { to: "/account-schedules", label: "زمان‌بندی حساب", icon: "⏱️" },
  { to: "/journals", label: "ژورنال پیام‌ها", icon: "📋" },
  { to: "/files", label: "فایل‌ها", icon: "📁" },
];

export default function Layout() {
  return (
    <div className="flex h-full">
      {/* Sidebar (RTL → right side) */}
      <aside className="w-60 shrink-0 bg-slate-950 border-l border-slate-800 flex flex-col">
        <div className="p-5 border-b border-slate-800">
          <h1 className="text-lg font-bold text-brand">افراکالا</h1>
          <p className="text-xs text-slate-500 mt-0.5">واتس‌اپ سندر v2</p>
        </div>
        <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? "bg-brand/20 text-brand"
                    : "text-slate-300 hover:bg-slate-800"
                }`
              }
            >
              <span>{n.icon}</span>
              <span>{n.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="p-3 text-xs text-slate-600 border-t border-slate-800">
          متصل به API محلی
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
