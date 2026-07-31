# MENU/SIDEBAR RESEARCH PROMPT (research + touchable prototype only — DO NOT implement in the real app yet)

> MODE: AUTONOMOUS RESEARCH + PROTOTYPE ONLY. Do not modify the real application's menu,
> sidebar, routes, or navigation in this pass. Do not ask questions — investigate, design,
> and produce a standalone, clickable HTML prototype the user can open in a browser and
> click through, entirely separate from the real running app. The real implementation
> will be a SEPARATE prompt after the user reviews this prototype and gives direction.
>
> OUTPUT LANGUAGE: report to the user in English only, per this project's CLAUDE.md rule.
> The prototype's own UI text should stay Persian/RTL, matching the real app's convention.

---

## 0. CONTEXT

Project: C:\Users\AFRA\Desktop\bots\claudegreenapi. Over many rounds of feature work
(V16 through V45), this project's sidebar has grown substantially — dashboard, messaging,
campaigns, contacts, content, conversations, inbox, message history, auto-reply, group
monitoring, calls, numbers (with sub-items: new-number setup, WhatsApp accounts, Telegram
accounts, account scheduling), protection & health, smart warm-up, team collaboration,
partner management, reports (with sub-items: daily report, product tracking, best send
hours, campaign ROI, top-repeated-products, active WhatsApp contacts), settings (with
sub-items: AI keys, AI settings, Green API capabilities, group/channel links, emergency
numbers), and likely more added since. The user wants this audited and potentially
reorganized for usability, before deciding whether/how to actually change the real app.

---

## STEP 1 — Inventory the ACTUAL current structure (do not guess)

- Read the real current sidebar/navigation component(s) in frontend/src (e.g.
  Layout.jsx or wherever the nav tree is defined) and list EVERY current top-level item
  and every sub-item, exactly as it exists today — do not rely on memory or assumption;
  read the actual file(s).
- For each item, note: how many clicks deep it is, whether it has a badge/counter, and
  (if determinable from the code/comments) roughly how core vs. niche/rarely-used it
  seems to be.

---

## STEP 2 — Propose a reorganized information architecture

- Group related items logically (e.g., everything about a single WhatsApp/Telegram
  number's lifecycle together; everything about anti-ban/health together; everything
  about reporting/analytics together; everything about team-collaboration/mesh warm-up
  together, etc.) — use your judgment on natural groupings given what each feature
  actually does, based on what you read in STEP 1 and, where helpful, a quick look at
  what each page actually shows.
- Consider standard UX patterns for large admin sidebars: collapsible sections, a
  pinned/favorites area for the most-used items, clearer top-level naming, reducing
  visual clutter, and whether some items are better as tabs within a parent page rather
  than separate sidebar entries.
- Produce a clear, written proposal: the NEW proposed grouping/hierarchy, with a short
  reason for each grouping decision, and explicitly note anything you'd consider merging,
  renaming, demoting to a sub-item, or promoting to be more prominent.

---

## STEP 3 — Build a standalone, clickable HTML prototype (not the real app)

- Create ONE self-contained HTML file (inline CSS/JS, no build step, no dependency on
  this project's actual codebase or backend) that visually represents the CURRENT
  sidebar structure on one side/tab and your PROPOSED new structure on the other/another
  tab, side by side or toggle-able, so the user can literally click through both and
  compare.
- The prototype should be genuinely clickable — expanding/collapsing sections, showing
  which page each item would represent (a simple placeholder label is fine, this does
  not need to connect to any real page) — so the user gets a real feel for the
  proposed navigation depth and grouping, not just a static picture.
- Match the real app's dark theme/RTL/Persian-label look reasonably closely (colors,
  RTL layout, font direction) so it feels representative, without needing pixel-perfect
  fidelity.
- Save this prototype file somewhere clearly separate from the real app's source (e.g.
  a top-level `ui-research/menu-prototype.html` file, NOT inside frontend/src), so there
  is zero risk of it being accidentally wired into the real build.

---

## FINAL REPORT
- The full current-structure inventory from STEP 1.
- The full reorganization proposal from STEP 2, with reasoning per grouping decision.
- The exact path to the clickable prototype file, and simple instructions for opening it
  (e.g., "open ui-research/menu-prototype.html directly in a browser — no server needed").
- Explicitly state: nothing in the real application was changed. This is a
  research/prototype deliverable only; the real implementation is a separate, later step
  once the user reviews this and gives direction.

Then STOP and await review.