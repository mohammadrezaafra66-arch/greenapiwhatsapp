import React from "react";

// TG PART 7 — reusable platform tab switcher (Persian, RTL). Used on Accounts, Campaigns,
// Group Monitoring, Inbox, Warm-up, Reports so those pages scope to one platform at a time.
// value: "all" | "whatsapp" | "telegram".
export const PLATFORM_TABS = [
  ["all", "همه"],
  ["whatsapp", "واتساپ"],
  ["telegram", "تلگرام ✈️"],
];

export default function PlatformSwitcher({ value, onChange, includeAll = true }) {
  const tabs = includeAll ? PLATFORM_TABS : PLATFORM_TABS.filter(([k]) => k !== "all");
  return (
    <div className="flex gap-1" role="tablist" aria-label="پلتفرم">
      {tabs.map(([k, label]) => (
        <button
          key={k}
          role="tab"
          aria-selected={value === k}
          className={value === k ? "btn-primary" : "btn-ghost"}
          onClick={() => onChange(k)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

// Pure filter helper (shared + unit-testable): keep items whose `platform` matches.
export function filterByPlatform(items, platform) {
  if (!platform || platform === "all") return items || [];
  return (items || []).filter(
    (it) => (it.platform || "whatsapp") === platform
  );
}
