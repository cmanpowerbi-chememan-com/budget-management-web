# Handoff prompt — repoint the app theme to Sea Green #2E8B57

Paste the block below into the session that is revising the web style.
Everything it needs is inline; the reference renders live next to this file.

Companion artifacts in `design/mockups/`:

| File | What it shows |
|------|---------------|
| `theme-shell-green-sea-2E8B57.png` | the picked shade, every existing ink token left untouched (the render jakkaritw approved the COLOR from) |
| `theme-shell-green-sea-2E8B57-white-ink.png` | **the target** — same shade, on-shell text white, gold accent retired (jakkaritw's choice, 2026-08-15) |
| `theme-shell-green-sea-deep-1A4E31.png` | rejected: deeper sea-green that would have kept the gold |
| `theme-shell-green-emerald-50C878.png` | the rejected alternative |
| `theme-shell-green-contrast.py` | the WCAG math behind every number quoted below |
| `theme-shell-green-shot.spec.ts` | regenerates all of the above (copy into `frontend/e2e/`, run, delete the copy) |

---

```
Repoint this app's theme green from the current #1a472a to Sea Green #2E8B57.
jakkaritw picked the shade on 2026-08-15 from design/mockups/theme-shell-green-sea-2E8B57.png.

WHERE THE GREEN LIVES
- frontend/src/styles/tokens.css — the only place green hexes are defined.
  Light theme (:root) carries it in SIX tokens that all currently hold the same
  two values: --paper, --accent, --c-forest = #1a472a (base) and --accent-2,
  --c-mint, --c-blue = #2d6a4f (the lighter hover step).
  --paper is the PAGE SHELL; --accent is also the fill of primary buttons.
- frontend/src/styles/global.css — call sites only, no green hexes. Grep it for
  --paper / --ink-on-shell / --accent-on-shell / --line-on-shell before editing:
  each of those has a comment explaining why that specific token is there.
- Do NOT touch --surface / --paper-2 (the light card family). Most of the app
  renders on cards; they are unaffected by a shell color change and were
  deliberately left light so cards float on the green field.
- Do NOT touch the [data-theme='dark'] block. Its accents (#3fa06e / #5cbf8c)
  are separately calibrated for a dark ground; light-theme greens fail there.
- Do NOT touch design/mockups/0002claude design/0002.3budget-export.html — the
  canonical sign-off mockup is intentionally still terracotta/serif.

THE HARD CONSTRAINT (measured, not guessed — WCAG 2.x, AA small text = 4.5)
#2E8B57 is much lighter than #1a472a, so the current "cream text + gold accent
painted directly on the shell" scheme breaks. Ratios against #2E8B57:
  --ink-on-shell   cream  #f2eee5 : 3.67  (was 9.17)  large text only
  --ink-on-shell-2 muted  #c6c0b2 : 2.34  (was 5.85)  FAIL
  --accent-on-shell gold  #d4ac52 : 1.99  (was 4.96)  FAIL at any size
  white button label      #ffffff : 4.25  (was 10.61) large text only
  near-black              #0a0a0a : 4.66                       AA
No light ink can reach AA on this shell — pure white tops out at 4.25. Only a
near-black ink clears it. Therefore the gold on-shell accent CANNOT survive on
#2E8B57 and must be replaced, not merely tweaked.

THE EXECUTION — DECIDED BY jakkaritw 2026-08-15, DO NOT RE-OPEN
Keep #2E8B57 exactly as picked and make the shell text white. Concretely, in
tokens.css's :root:
  --paper, --accent, --c-forest          -> #2E8B57
  --accent-2, --c-mint, --c-blue         -> #3fa06e   (lighter hover step)
  --ink-on-shell                         -> #ffffff
  --ink-on-shell-2                       -> #ffffff   (the muted tier cannot
     survive on this shell — #c6c0b2 is 2.34; collapse it to white rather than
     inventing a new grey that still fails)
  --accent-on-shell                      -> #ffffff   (gold #d4ac52 RETIRED)
  --line-on-shell                        -> rgba(255, 255, 255, 0.55)
Everything else in :root stays as-is, including --accent-text #b24222 (that one
is for accent text on LIGHT CARDS, a different role — leave it alone).
Accepted trade-offs jakkaritw signed off on: 4.25 is the best contrast reachable
here, i.e. below AA 4.5 for small text; and the gold highlight disappears from
the page title, the pending-amount line, and the admin-zone title, which all go
white. Reference render: theme-shell-green-sea-2E8B57-white-ink.png.
REJECTED alternative (for context only, do not build it): #1a4e31, a deeper
sea-green where every existing token including gold still passes — jakkaritw
chose the lighter picked shade over keeping the gold.
Update the tokens.css header comment, which still describes the #1a472a shell
and the gold on-shell accent, or it becomes a lie about live values.

VERIFY BEFORE CLAIMING DONE
- cd frontend && npx next build   <- MANDATORY. vitest does NOT type-check;
  green tests with a red CI has burned this repo before.
- cd frontend && npx vitest run   <- 633 tests were green before this change.
- Contrast: re-run the audit approach the previous theme session used (walk
  every rendered element, resolve its real background, compare). Read the
  result correctly — the OLD bar was ZERO violations against rgb(26,71,42), and
  this change CANNOT hold that bar: on rgb(46,139,87) the best a light ink can
  do is 4.25, so shell-direct text will report as an AA miss BY DESIGN. That is
  the signed-off trade-off, not a bug, and it is NOT a reason to darken the
  green back. What the audit must actually prove: (1) nothing painted on the
  shell is below 4.25 — i.e. no cream/muted/gold/#4a5e80 leftovers hiding in a
  spot the token sweep missed, (2) card-internal contrast is unchanged from
  HEAD. Chromium serializes color-mix(in oklab,...) as oklab(), which canvas
  fillStyle will not round-trip; convert explicitly or the audit reports false
  positives.
- Screenshots: save to design/mockups/ and let jakkaritw open them. Never read
  a PNG into context.

RULES FOR THIS REPO
- Log the task in tracker/pending.json via `python tracker/task.py add|done`
  BEFORE starting and when finished. It is the only cross-session hand-over.
- Any new file you create for this work goes inside the project tree (jakkaritw
  2026-08-15), not in a scratchpad, in the folder that already owns that
  purpose.
- Nothing deploys without jakkaritw's approval. The theme change is currently
  local-only and uncommitted.
```
