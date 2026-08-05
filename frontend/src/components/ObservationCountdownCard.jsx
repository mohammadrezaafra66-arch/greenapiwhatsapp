import React from "react";
import { http } from "../api.js";
import {
  SESSION_2_META,
  buildObservationCardModel,
  parseFleetAccountsHint,
} from "../observation/session2Meta.js";

const COLOR_CLASS = {
  gray: "border-slate-300 bg-slate-50 text-slate-700 dark:border-slate-600 dark:bg-slate-800/60 dark:text-slate-200",
  blue: "border-sky-300 bg-sky-50 text-sky-900 dark:border-sky-700 dark:bg-sky-950/40 dark:text-sky-100",
  green: "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-100",
  red: "border-red-300 bg-red-50 text-red-900 dark:border-red-700 dark:bg-red-950/40 dark:text-red-100",
  orange: "border-orange-300 bg-orange-50 text-orange-900 dark:border-orange-700 dark:bg-orange-950/40 dark:text-orange-100",
};

const DOT = {
  gray: "bg-slate-400",
  blue: "bg-sky-500",
  green: "bg-emerald-500",
  red: "bg-red-500",
  orange: "bg-orange-500",
};

function InfoRow({ label, value, ltr = false }) {
  return (
    <div className="flex items-center justify-between gap-2 text-xs sm:text-sm py-0.5">
      <span className="text-muted shrink-0">{label}</span>
      <span className={`font-medium text-left ${ltr ? "tabular-nums" : ""}`} dir={ltr ? "ltr" : "rtl"}>
        {value}
      </span>
    </div>
  );
}

function GuideList({ items }) {
  return (
    <ul className="mt-2 space-y-1.5 text-xs sm:text-sm leading-relaxed list-none p-0 m-0">
      {items.map((item) => (
        <li key={item} className="flex gap-2 items-start">
          <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-current opacity-50 shrink-0" aria-hidden />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

/**
 * Read-only Persian observation reminder. No buttons. No mutations. No new APIs.
 */
export default function ObservationCountdownCard() {
  const [now, setNow] = React.useState(() => Date.now());
  const [fleetAccountCount, setFleetAccountCount] = React.useState(null);
  const [anyCutover, setAnyCutover] = React.useState(null);

  React.useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      setNow(Date.now());
      try {
        const data = await http.get("/fleet/accounts", { params: { limit: 500 } }).then((r) => r.data);
        if (cancelled) return;
        const hint = parseFleetAccountsHint(data);
        setFleetAccountCount(hint.fleetAccountCount);
        setAnyCutover(hint.anyCutover);
      } catch {
        if (!cancelled) {
          setFleetAccountCount(null);
          setAnyCutover(null);
        }
      }
    };
    tick();
    const id = setInterval(tick, 60_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const model = buildObservationCardModel({
    now,
    startedAtUtc: SESSION_2_META.startedAtUtc,
    runId: SESSION_2_META.runId,
    fleetAccountCount,
    snapshotCount: null,
    cutover: anyCutover,
    canary: false,
    humanContacts: false,
    scheduler: null,
    runtime: null,
    shadow: null,
  });

  const color = model.statusColor;
  const shell = COLOR_CLASS[color] || COLOR_CLASS.gray;
  const L = model.labels;

  return (
    <section
      dir="rtl"
      aria-label="دوره مشاهده ۱۴ روزه"
      data-testid="observation-countdown-card"
      data-has-actions="false"
      className={`rounded-xl border p-4 sm:p-5 shadow-sm ${shell}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base sm:text-lg font-bold tracking-tight">{model.title}</h2>
          <p className="text-sm opacity-80 mt-0.5">{model.subtitle}</p>
          <p className="text-xs opacity-60 mt-1">{model.sessionBadge}</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap justify-end">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-current/20 px-2.5 py-1 text-xs font-semibold">
            <span className={`w-2 h-2 rounded-full ${DOT[color] || DOT.gray}`} />
            {model.statusLabel}
          </span>
          {model.simulationOnly && (
            <span className="inline-flex rounded-full bg-white/70 dark:bg-black/30 border border-current/15 px-2.5 py-1 text-xs font-semibold">
              {model.simulationBadge}
            </span>
          )}
        </div>
      </div>

      <p className="mt-3 text-2xl sm:text-3xl font-bold tabular-nums" data-testid="observation-day-label">
        {model.dayLabel}
      </p>
      <p className="mt-1 text-sm font-medium opacity-90">{model.progressHeadline}</p>
      <p className="mt-0.5 text-sm opacity-80">{model.remainingLabel}</p>

      <p className="mt-3 text-sm font-medium leading-relaxed">{model.warning}</p>
      <p className="mt-1 text-xs opacity-70 leading-relaxed" data-testid="observation-calendar-disclaimer">
        {model.disclaimer}
      </p>

      <div
        className="mt-4 rounded-lg border border-current/10 bg-white/55 dark:bg-black/25 p-3"
        data-testid="observation-purpose"
      >
        <p className="text-sm font-semibold">{model.purposeTitle}</p>
        <p className="mt-1 text-xs sm:text-sm leading-relaxed opacity-90">{model.purposeBody}</p>
      </div>

      <div
        className="mt-3 rounded-lg border border-sky-300/40 dark:border-sky-700/40 bg-sky-50/70 dark:bg-sky-950/30 p-3"
        data-testid="observation-daily-action"
      >
        <p className="text-sm font-semibold">{model.dailyActionTitle}</p>
        <p className="mt-1 text-xs sm:text-sm leading-relaxed font-medium">{model.dailyActionNormal}</p>
        <GuideList items={model.dailyChecklist} />
        <p className="mt-3 text-xs sm:text-sm leading-relaxed" data-testid="observation-owner-duty">
          {model.ownerDailyDuty}
        </p>
        <p className="mt-1 text-xs sm:text-sm leading-relaxed font-medium" data-testid="observation-owner-no-change">
          {model.ownerNoChange}
        </p>
        <p className="mt-1 text-xs opacity-80 leading-relaxed">{model.ownerEscalateHint}</p>
      </div>

      <div
        className="mt-3 rounded-lg border border-amber-300/50 dark:border-amber-700/40 bg-amber-50/70 dark:bg-amber-950/25 p-3"
        data-testid="observation-escalate"
      >
        <p className="text-sm font-semibold">{model.escalateTitle}</p>
        <GuideList items={model.escalateItems} />
        <p className="mt-2 text-xs sm:text-sm font-medium leading-relaxed">{model.escalateFooter}</p>
      </div>

      <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
        <div className="rounded-lg bg-white/50 dark:bg-black/20 border border-current/10 p-3 space-y-1">
          <InfoRow label={L.currentSession} value={model.currentSession} />
          <InfoRow label={L.currentDay} value={model.currentDay} />
          <InfoRow label={L.startedAtUtc} value={model.startedAtUtc} ltr />
          <InfoRow label={L.startedAtTehran} value={model.startedAtTehran} ltr />
          <InfoRow label={L.runId} value={model.runId} ltr />
          <InfoRow label={model.fleetAccountCountLabel} value={model.fleetAccountCount} />
          <InfoRow label={model.snapshotCountLabel} value={model.snapshotCount} />
          <p className="pt-1 text-[11px] opacity-65 leading-relaxed">{model.snapshotHint}</p>
        </div>
        <div className="rounded-lg bg-white/50 dark:bg-black/20 border border-current/10 p-3 space-y-1">
          <p className="text-xs font-semibold mb-1 opacity-70">{L.liveTitle}</p>
          <InfoRow label={L.scheduler} value={model.live.scheduler} />
          <InfoRow label={L.runtime} value={model.live.runtime} />
          <InfoRow label={L.shadow} value={model.live.shadow} />
          <InfoRow label={L.cutover} value={model.live.cutover} />
          <InfoRow label={L.canary} value={model.live.canary} />
          <InfoRow label={L.humanContacts} value={model.live.humanContacts} />
        </div>
      </div>
    </section>
  );
}
