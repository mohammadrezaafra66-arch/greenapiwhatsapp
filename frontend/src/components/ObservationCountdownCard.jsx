import React from "react";
import { http } from "../api.js";
import { SESSION_2_META, buildObservationCardModel } from "../observation/session2Meta.js";

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

function LiveRow({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-2 text-xs sm:text-sm py-0.5">
      <span className="text-muted">{label}</span>
      <span className="font-medium tabular-nums" dir="ltr">{value}</span>
    </div>
  );
}

/**
 * Read-only Observation Window reminder. No buttons. No mutations. No new APIs.
 */
export default function ObservationCountdownCard() {
  const [now, setNow] = React.useState(() => Date.now());
  const [cohortCount, setCohortCount] = React.useState(null);
  const [anyCutover, setAnyCutover] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      setNow(Date.now());
      try {
        const rows = await http.get("/fleet/accounts", { params: { limit: 500 } }).then((r) => r.data);
        if (cancelled) return;
        if (Array.isArray(rows)) {
          setCohortCount(rows.length);
          setAnyCutover(rows.some((a) => a && a.cutover === true));
        } else {
          setCohortCount(null);
        }
      } catch {
        if (!cancelled) setCohortCount(null);
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
    cohortCount,
    snapshotCount: null, // no unauthenticated snapshot endpoint; never invent API
    cutover: anyCutover,
    canary: false,
    humanContacts: false,
    scheduler: null,
    runtime: null,
    shadow: null,
  });

  const color = model.statusColor;
  const shell = COLOR_CLASS[color] || COLOR_CLASS.gray;

  return (
    <section
      dir="rtl"
      aria-label="Observation Window"
      data-testid="observation-countdown-card"
      data-has-actions="false"
      className={`rounded-xl border p-4 sm:p-5 shadow-sm ${shell}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base sm:text-lg font-bold tracking-tight">{model.title}</h2>
          <p className="text-sm opacity-80 mt-0.5">{model.subtitle}</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap justify-end">
          <span
            className="inline-flex items-center gap-1.5 rounded-full border border-current/20 px-2.5 py-1 text-xs font-semibold"
            dir="ltr"
          >
            <span className={`w-2 h-2 rounded-full ${DOT[color] || DOT.gray}`} />
            {model.status}
          </span>
          {model.simulationOnly && (
            <span
              className="inline-flex rounded-full bg-white/70 dark:bg-black/30 border border-current/15 px-2.5 py-1 text-xs font-semibold"
              dir="ltr"
            >
              Simulation Only
            </span>
          )}
        </div>
      </div>

      <p className="mt-3 text-2xl sm:text-3xl font-bold tabular-nums" dir="ltr">
        {model.dayLabel}
      </p>

      <p className="mt-2 text-sm font-medium leading-relaxed">{model.warning}</p>

      <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
        <div className="rounded-lg bg-white/50 dark:bg-black/20 border border-current/10 p-3 space-y-1">
          <LiveRow label="Current Session" value={model.currentSession} />
          <LiveRow label="Current Day" value={model.currentDay} />
          <LiveRow label="Started At UTC" value={model.startedAtUtc} />
          <LiveRow label="Started At Tehran" value={model.startedAtTehran} />
          <LiveRow label="Run ID" value={model.runId} />
          <LiveRow label="Current Cohort Count" value={model.cohortCount} />
          <LiveRow label="Current Snapshot Count" value={model.snapshotCount} />
        </div>
        <div className="rounded-lg bg-white/50 dark:bg-black/20 border border-current/10 p-3 space-y-1">
          <p className="text-xs font-semibold mb-1 opacity-70">Live Status (read-only)</p>
          <LiveRow label="Scheduler" value={model.live.scheduler} />
          <LiveRow label="Runtime" value={model.live.runtime} />
          <LiveRow label="Shadow" value={model.live.shadow} />
          <LiveRow label="Cutover" value={model.live.cutover} />
          <LiveRow label="Canary" value={model.live.canary} />
          <LiveRow label="Human Contacts" value={model.live.humanContacts} />
        </div>
      </div>
    </section>
  );
}
