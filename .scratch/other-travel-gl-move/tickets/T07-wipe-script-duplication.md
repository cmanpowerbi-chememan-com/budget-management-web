# T07 — Fold the wipe script back onto the app's own delete path  [OPEN · low priority]

Type: `wayfinder:task` (AFK) · raised by the 06+07+08 gate, 2026-09-04 · NOT blocking tonight

## Question
`setup/wipe_other_travel_gl_rows.py` re-implements the app's delete contract in raw SQL
(mirroring `_delete_one_detail_line` + `_delete_parent_if_orphaned`) rather than calling it.
Its guards are sound today — dry-run by default, refuses a parent with a non-zero total or a
remark, parameterised `WHERE` bound to the 2 GL codes, `.env` resolved from the file's own
location so it cannot silently hit the wrong DB — but nothing pins it to the app's logic, so
a future change to the delete rules leaves it silently stale.

Options: call `write_model.delete_detail_line` directly, or give the script a test that
asserts its SQL still matches the app's. Decide after tonight's deploy.
