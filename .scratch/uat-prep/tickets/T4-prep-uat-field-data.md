# T4 — Prepare the field: clean the leftovers, seed enough to click

Type: `wayfinder:task` (AFK, destructive steps need verify-target + explicit confirm) · Status: OPEN
Blocked by: **D2, T3**

## Question

Both UAT departments start in a state that would derail day 1. What gets cleared, and what gets
seeded so testers have something to exercise?

## The starting state

| | `Data & Analytic` | `Solution Delivery` |
|---|---|---|
| FY2027 approval_status | **REJECTED**, reason literally `test`, rejected by Arthid 2026-09-05 | no row at all |
| FY2027 pending_budget | 3 rows / 42,040.00 THB, part written by jakkaritw | **0 rows** |
| Trips | trip 43, China, project `test`, remark `test111` | none |

Two problems follow:
1. Testers open the round looking at a rejection whose reason is the word `test`.
2. **Solution Delivery is empty, so a submit is refused outright** with `department_empty`
   (`approval.py:688`) — the second department cannot even start the flow.

There is also a data-thinness problem SIT already hit and jakkaritw already owned: Data &
Analytic's real history is thin, with only 1 of 6 special-GL groups populated (travel, 300.00
THB), so testers have nothing to click in most subforms.

## Work

1. Clear the leftover test state per D2, using the app's own delete paths wherever they exist so
   cascades and recomputes stay correct, and the restore script's statements otherwise.
2. Seed enough FY2027 starting data in both departments that every in-scope case has something to
   act on — in particular at least one row in each special-GL group that D4's pack tests, and at
   least one existing trip.
3. Verify the SharePoint attachment folders exist for both departments, since the attachments
   cases are in scope and a missing folder surfaces as a Thai error.
4. Record the post-seed control number per (department, year) so the exit reconcile has something
   to compare against.

## Constraints

- **Verify the target and get explicit confirmation before every destructive statement** —
  never-cut rule. Quote the `SELECT` that proves what is about to be deleted.
- Every `DELETE` carries an explicit `fiscal_year` predicate.
- Delete order for trips: `pending_budget_detail` → `budget_trip` → `pending_budget`, or use the
  app's own trip-delete button and let it cascade.
- Seeded amounts must obey the live input rules: integers, rounded half-up to hundreds, capped at
  100,000,000 per cell.

## Definition of done

Both departments in a known, documented starting state · the control numbers recorded · every
destructive statement preceded by its verifying `SELECT` and by written approval.
