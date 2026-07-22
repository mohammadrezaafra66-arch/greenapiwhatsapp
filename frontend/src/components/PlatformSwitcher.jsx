import React from "react";
export { PLATFORM_TABS, filterByPlatform } from "./platformSwitcherUtils.js";
import { PLATFORM_TABS } from "./platformSwitcherUtils.js";

// TG PART 7 — reusable platform tab switcher (Persian, RTL). Used on Accounts, Campaigns,
// Group Monitoring, Inbox, Warm-up, Reports so those pages scope to one platform at a time.
// value: "all" | "whatsapp" | "telegram".
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
