export const PLATFORM_TABS = [
  ["all", "همه"],
  ["whatsapp", "واتساپ"],
  ["telegram", "تلگرام ✈️"],
];

export function filterByPlatform(items, platform) {
  if (!platform || platform === "all") return items || [];
  return (items || []).filter(
    (it) => (it.platform || "whatsapp") === platform
  );
}
