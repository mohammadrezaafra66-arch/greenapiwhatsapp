# CLAUDE.md

## Output language rule (communication only)

Write ALL conversational output to the user — reports, diagnostics, summaries, commit
messages, phase reports, risk notes, questions, and any other prose — ONLY in
English / Latin characters.

This is a COMMUNICATION-ONLY rule. It does NOT change the product:

- Every master prompt (V17 through V39) requires all in-app UI strings, button labels,
  and user-facing text to stay fully Persian/RTL. That guardrail is UNCHANGED. Never
  translate, remove, or alter any user-facing Persian string in the codebase because
  of this rule.
- Code, variable names, and code comments stay English (already established).

What this rule governs is ONLY how Claude talks to the user in the terminal:

- Write all prose, explanations, summaries, and questions in English.
- No Persian/Farsi sentences in Claude's own reports.
- No Persian digits or Persian punctuation in Claude's own prose.
- When quoting an exact Persian string from the app (a UI label, an error message, a
  log line, a DB value), put it in a code span/block exactly as-is, with a short
  English explanation next to it. Example: `ثبت شد` = "registered" status label.
- Structure longer reports with English headings, using only the sections that apply:
  Summary, Commits, Migrations/DDL, Tests, Risks, Manual QA, Next Steps.
- Commit messages stay English (existing V17–V39 convention).
