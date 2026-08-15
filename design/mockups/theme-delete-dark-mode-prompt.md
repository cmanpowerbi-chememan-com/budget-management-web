# Handoff prompt — delete dark mode

jakkaritw, 2026-08-15: the app ships one theme (Sea Green `#2E8B57`, light).
Dark mode goes away entirely — tokens, toggle, storage key, docs.

Two repos are affected. Part A is the budget app, Part B is the design system.
They can be done by different sessions, in either order.

Side effect worth knowing: this closes the open dark-accent conflict (the design
system carried `#3fa06e`/`#5cbf8c` while the app file showed `#2f7f55`/`#227d66`)
— with dark mode deleted there is nothing left to reconcile.

---

```
Delete dark mode. jakkaritw decided 2026-08-15: one theme only, the light Sea
Green #2E8B57 theme. Remove it completely — no dead tokens, no orphan toggle, no
docs that still promise a dark theme.

=== PART A — the budget app (c:\04.budget_management_web) ===
Touchpoints (grep first, another session has been editing these files, so line
numbers will have moved):
- frontend/src/styles/tokens.css — delete the whole `[data-theme='dark']` block
  (~30 lines: ink/paper/surface/line/special/status/accent + the on-shell
  aliases). Delete the comments that explain it too.
- frontend/src/app/layout.tsx — delete the pre-paint <script> that reads
  localStorage 'budget-theme' and sets document.documentElement.dataset.theme.
  Then decide what `<html data-theme="light">` is still worth: with no second
  theme and no selector reading the attribute, it is dead markup — remove it
  unless a grep proves something still keys off it.
- frontend/src/App.tsx — delete the nav-bar theme toggle (the moon/sun button),
  THEME_STORAGE_KEY = 'budget-theme', encodeTheme, the Theme type, the
  usePersistedState call for theme and the effect that writes dataset.theme.
- frontend/src/platform/usePersistedToggle.ts — grep for OTHER consumers before
  touching it. If the theme toggle was the only one, delete the file; if
  anything else uses it, leave it alone.
- frontend/src/styles/global.css — remove any dark-only rules.
- Tests: grep the whole frontend for 'budget-theme', 'data-theme', 'ThemeToggle',
  'dark' across src/**/*.test.tsx and e2e/*.spec.ts. Delete the assertions that
  exercised the toggle; do not leave a spec that flips a control which no longer
  renders.
VERIFY (evidence required):
  cd frontend && npx next build     # MANDATORY — vitest does NOT type-check
  cd frontend && npx vitest run     # 633 tests were green before this change
  grep -rn "data-theme\|budget-theme\|prefers-color-scheme" frontend/src frontend/e2e
    -> zero hits (or only hits you can justify out loud)

=== PART B — the design system (c:\10.cman-design-system) ===
Repo HEAD is 554802b on main, already pushed. Dark values live in:
  tokens/tokens.css          — the dark block + its explanatory comments
  tokens/tokens.json         — a "dark" value on ~23 token entries
  tokens/tailwind.preset.js  — 2 references
  tokens/tokens.pptx.json    — 1 reference
  tools/check-tokens.py      — it was made dark-theme aware in the rebuild;
                               make it light-only again and keep it exiting 0
  README.md (6) / CLAUDE.md (8) / adapters/web/WEB.md (5) — prose promising a
                               dark theme
Strip all of it, then:
  python tools/check-tokens.py            -> exit 0
  python -X utf8 tools/shot-app-shell.py  -> re-render examples/app-shell.png
  grep -rni "dark" . --exclude-dir=.git   -> only legitimate hits (e.g. "darken",
      or a one-line note that dark mode was removed on 2026-08-15)
Do NOT read the regenerated PNG into context — jakkaritw reviews it.

=== RULES ===
- Log the work in tracker/pending.json via `python tracker/task.py add|done`
  (budget-app repo) before starting and when finished.
- Commit in each repo separately, Conventional Commits. DO NOT PUSH — jakkaritw
  approves pushes.
- Any new file goes inside the repo tree, in the folder that already owns that
  purpose — never a scratchpad.
- Report: files changed per repo, the verify outputs above, commit hashes, and
  anything you deliberately left alone (e.g. usePersistedToggle.ts if it has
  other consumers).
```
