# Combined task for Claude Code — Team Collaboration status report + new log filter

Do two things in order.

---

## PART A — Build: add a new filter option to the Team Collaboration log dropdown

**Context:** On `/team-collaboration`, the «لاگ رویدادها» tab has a dropdown (currently:
همهٔ رویدادها / درخواست / یادآوری / تشکر / پاسخ اکانت سرد / پیام دریافتی / هشدار ایمنی).

**Add ONE new option**, e.g. **«درخواست‌های بی‌پاسخ»** (unresponded requests), that shows
exactly the contacts who: received an ask (and possibly a reminder), but have NOT yet
completed the task (task status is `asked`, `reminded`, or the terminal `no_response` —
i.e., everything EXCEPT `done`). For each row shown, make clear: contact name, sender,
cold account, ask date/time, whether/when a reminder was sent, and current status
(asked / reminded / no_response). Reuse the existing log table/filtering pattern — do not
build a separate page.

Guardrails: no polling, don't touch ngrok/webhook, don't touch mesh/V27/V26/Telegram code,
Persian RTL, Shamsi dates. Test, commit, push, report.

---

## PART B — DIAGNOSTIC ONLY (change nothing): full Team Collaboration status report

Answer these with REAL data, not assumptions:

1. **«محافظت و سلامت» page:** Is this page live/real-time, or does it show cached/stale
   data? For each banner/warning currently shown there, confirm it reflects the actual
   current state (query the same tables it should be reading from and compare). Is it
   correctly connected to live Green API state checks?

2. **Today's thank-you count:** How many thank-you events fired today via
   `warmup_helper_log`? If zero (or fewer than expected), why — trace the actual reason
   (e.g., no completions detected today, a gate blocking the thank-you send, an error in
   the thank-you task, or genuinely no contact completed a task today). Show the last time
   ANY thank-you fired and why none has fired today if that's the case.

3. **Is Team Collaboration progressing correctly overall?** Give current counts of tasks by
   status (pending/asked/reminded/done/no_response). Is the pending queue actually
   draining over time (compare to counts from recent diagnostics if available in logs), or
   stuck anywhere? Are ALL active contacts eventually getting asked, or are some stuck
   indefinitely? Check for any silent errors in `process-helper-warmup` /
   `process-team-schedule` in the last 24h.

4. **Per-sender health/capacity view:** Where can the user see, per sender account, its
   current warmth level (کم/متوسط/بالا) and how many messages/day it's allowed to send?
   Confirm this is actually visible somewhere in the current UI (which page/component), and
   report the CURRENT warmth score + effective daily send capacity for every active sender
   right now.

5. **Cold-account auto-reply (V29 PART 5):** When a contact completes an ask (messages the
   assigned cold account), does the cold account currently send a reply back? Show the last
   3 real examples (or confirm there are none yet) with timestamps and whether the reply was
   sent within the expected delay (not instant). Also give your own recommendation: is this
   cold-account auto-reply actually necessary/valuable, or could it be skipped — factor in
   any ban-risk tradeoff of the cold account itself sending vs. only receiving.

Report each of these 5 as its own clearly labeled section. Change nothing.