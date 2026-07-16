import React from "react";
import { QR_ANTIBAN_TITLE, QR_ANTIBAN_HEADER, QR_ANTIBAN_RULES } from "../data/qrAntibanRules.js";

// V22 — Prominent amber anti-ban rules box shown on the QR-scan screen BEFORE scanning.
// RTL Persian. Rule ۱ (the 24-hour wait) is emphasized as the most important.
export default function QrAntibanRules() {
  return (
    <div
      dir="rtl"
      className="rounded-lg border border-amber-500/40 bg-amber-500/10 text-amber-100 p-3 space-y-2 text-sm"
    >
      <h4 className="font-bold text-amber-300 text-base">{QR_ANTIBAN_TITLE}</h4>
      <p className="text-xs text-amber-200/90">{QR_ANTIBAN_HEADER}</p>
      <ol className="space-y-2">
        {QR_ANTIBAN_RULES.map((r) => (
          <li
            key={r.n}
            className={
              r.emphasized
                ? "rounded-md border border-amber-400/60 bg-amber-500/20 px-2 py-1.5 text-amber-50"
                : "px-1"
            }
          >
            <span className={r.emphasized ? "font-extrabold text-amber-200" : "font-bold text-amber-200"}>
              {r.title}
            </span>{" "}
            <span className={r.emphasized ? "font-semibold" : "text-amber-100/90"}>{r.body}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
