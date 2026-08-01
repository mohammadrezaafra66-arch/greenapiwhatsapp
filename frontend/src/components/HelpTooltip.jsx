import React from "react";

// V54 — a small «؟» that reveals a plain-Persian explanation.
//
// Why this exists next to the older HelpTip: HelpTip reveals its text purely with CSS
// `group-hover`, which never fires reliably on touch devices — on a phone the text is simply
// unreachable. This one TOGGLES on click (tap) as well as opening on hover and keyboard focus,
// so it works on mobile and desktop alike. HelpTip is deliberately left untouched so the three
// pages already using it keep their exact current behaviour.
//
// The trigger is a <button>, so it must never be rendered INSIDE another <button> (invalid HTML) —
// place it as a sibling of the control it documents. Clicks are stopped from propagating so the
// icon can sit inside clickable containers (e.g. a sortable table header) without triggering them.
export default function HelpTooltip({ text, className = "" }) {
  const [pinned, setPinned] = React.useState(false);   // click/tap — stays open
  const [peek, setPeek] = React.useState(false);       // hover/focus — transient
  const ref = React.useRef(null);

  React.useEffect(() => {
    if (!pinned) return undefined;
    function onDocPointerDown(e) {
      if (ref.current && !ref.current.contains(e.target)) setPinned(false);
    }
    function onKeyDown(e) {
      if (e.key === "Escape") setPinned(false);
    }
    document.addEventListener("mousedown", onDocPointerDown);
    document.addEventListener("touchstart", onDocPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onDocPointerDown);
      document.removeEventListener("touchstart", onDocPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [pinned]);

  const open = pinned || peek;

  return (
    <span ref={ref} className={`relative inline-flex align-middle mr-1 ${className}`}>
      <button
        type="button"
        aria-label={`راهنما: ${text}`}
        aria-expanded={open}
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); setPinned((p) => !p); }}
        onMouseEnter={() => setPeek(true)}
        onMouseLeave={() => setPeek(false)}
        onFocus={() => setPeek(true)}
        onBlur={() => setPeek(false)}
        className="w-4 h-4 shrink-0 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-600
                   text-[10px] leading-4 text-center cursor-pointer font-normal"
      >
        ؟
      </button>
      {open && (
        <span
          dir="rtl"
          role="tooltip"
          className="absolute z-[80] bottom-full right-0 mb-1 w-[250px] max-w-[78vw]
                     rounded-lg bg-surface border border-line text-ink text-xs p-2
                     leading-relaxed shadow-card text-right font-normal whitespace-normal"
        >
          {text}
        </span>
      )}
    </span>
  );
}
