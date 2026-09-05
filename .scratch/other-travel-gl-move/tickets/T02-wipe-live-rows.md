# T02 — Delete the pre-existing values  [CLOSED 2026-09-04]

Type: `wayfinder:task` (AFK, destructive — needs verify-target + explicit confirm)

## Question
Delete the 1 `pending_budget_detail` line and its parent row for `6210400999`, leaving the
trip and its other lines intact. Confirm zero rows remain for BOTH GLs afterwards.

## Known facts
Target: FY2027 / cost_center `10AC020000` / gl `6210400999` / total_year 0.00 / dept
"Budgeting & Cost Accounting" / approval_status NULL / `_updated_at` 2026-08-30 13:29:15.831536.
`5210400999` has zero rows. `_delete_one_detail_line` (`write_model.py:1687`) does NOT call
`classify_special_gl`, so it works before or after the master flip, and
`_delete_parent_if_orphaned` removes the zeroed parent automatically — prefer the app's own
delete path over raw SQL so the parent==SUM(detail) invariant is preserved.

Re-run the census immediately before deleting: jakkaritw's screenshot showed 3,700 THB where
the DB shows 0.00, so an unsaved draft may have been saved since.

## Resolution
Executed 2026-09-04 with jakkaritw's explicit approval, after a re-run dry survey confirmed the
target was unchanged. `setup/wipe_other_travel_gl_rows.py --apply` deleted 1 detail line
(detail_id 248) and 1 parent row; the script's own post-check reported 0 remaining.

Reconciled independently afterwards:
- trip 50 still present (นิภาพร ทองกิ่ง / Thailand / FY2027 / 10AC020000);
- surviving sibling lines 245 per-diem 500.00, 246 transport 1,000.00, 247 accommodation
  3,000.00 — **sibling total 4,500.00, exactly the pre-delete figure**;
- 0 rows for BOTH GLs in `pending_budget` and `pending_budget_detail`;
- parent == SUM(detail) holds for every trip-driven cell in that CC/FY.

One row initially looked like a violation — `6210900010` parent 14,800.00 vs SUM(detail) 0.
It is not: that GL is in `Office expenses`, an ordinary typed cell that has no detail lines by
design. The invariant only binds cells that carry detail lines.
