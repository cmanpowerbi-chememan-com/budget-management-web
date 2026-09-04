# T02 — Delete the pre-existing values  [OPEN · blocked by T01]

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
