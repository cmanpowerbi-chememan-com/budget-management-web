# Plan — Hide net-zero GL rows on the budget grid

**Date:** 2026-07-24 · **Decision:** jakkaritw approved hiding ("ซ่อน")
**Trigger finding:** GL rows whose SAP postings cancel out (original + reversal,
e.g. 10GE000000/6210500010: +1,648.13 / −1,648.13 in m01 FY2026) render as
all-"—" rows that look like bugs. Measured: **56 net-zero (cc,gl) keys in SAP
FY2026, 51 of them with no board + no pending row** — these become hidden.

## The rule (precise — the pending safeguard is the point)

A grid row `(cost_center, gl_account, fiscal_year)` is **HIDDEN** when ALL are true:
1. SAP layer: net total of the 12 months == 0 (or no SAP row at all), AND
2. Approved layer: no `dbo.board_budget` row for the key, AND
3. Pending layer: **no `budget.pending_budget` row for the key — in ANY state
   (blank, all-zero, or filled).**

**Always SHOW when any of:** a pending row exists (user's work-in-progress —
a "+ เพิ่ม Transaction" blank row or a deliberately zeroed row must never
vanish), OR any SAP month ≠ 0, OR a board row exists.

Why the safeguard matters: without rule 3, a user who creates a blank row (or
zeros a mistake) would see their row disappear before they can fill/fix it.
The ONLY rows this hides are reversal-style net-zero SAP keys with nothing
else attached — exactly the noise case.

## Properties (verified by construction)

- **Totals unchanged** — hidden rows contribute 0 to every subtotal (net-zero).
- **"+ เพิ่ม Transaction" unaffected** — the GL combobox lists the GL master,
  not grid rows; creating a hidden GL's row inserts a pending row → it
  immediately re-appears (consistent).
- **Per-FY natural scoping** — the key includes fiscal_year; a GL hidden in one
  year's view may show in another.
- **Reversible** — a reversal-of-the-reversal (new non-zero posting) makes the
  row reappear on the next fetch.

## Implementation (small, TDD)

Backend only — one place, all clients consistent:
- `backend/app/read_model.py` `merge_budget_rows`: after building merged keys,
  drop keys matching the rule above (SAP months all zero AND key not in board
  result AND key not in pending result). ~5 lines + comment referencing this
  plan + the 2026-07-24 decision.
- Tests (`backend/tests/test_read_model*.py` or nearest merge tests):
  1. net-zero SAP key, no board, no pending → EXCLUDED
  2. net-zero SAP key WITH a pending row (even all-zero) → INCLUDED (safeguard)
  3. net-zero SAP key WITH a board row → INCLUDED
  4. SAP key with any non-zero month, no board/pending → INCLUDED (existing behavior)
  5. subtotal/total parity: totals identical with and without hidden rows
- No frontend change expected (the API simply stops returning those rows) —
  verify no frontend code assumes those rows exist (quick grep for special
  handling of empty months; expected none).

## Verification

- New unit tests green + full mocked backend suite green.
- Live check as nipapornt: dept General, GL 6210500010 (the original case)
  no longer renders; then "+ เพิ่ม Transaction" the SAME GL → blank row
  appears and stays (safeguard); cleanup the row → it disappears again.
- Regression: spot-check one dept's grid totals vs DB before/after — must be
  identical.

## Out of scope

- No change to the GL master, "+ เพิ่ม Transaction" picker, or any totals.
- No per-user "show hidden rows" toggle (offer later only if users ask).
