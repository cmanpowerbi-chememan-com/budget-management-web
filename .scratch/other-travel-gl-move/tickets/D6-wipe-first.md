# D6 — Wipe before the deploy  [CLOSED 2026-09-04]

## Question
Delete the leftover row before shipping the code, or after?

## Resolution
Before. While old code + old master are still coherent, the app's own delete path recomputes
the parent and orphan-deletes it correctly, leaving the trip and its sibling lines intact.
After the code ships, `_delete_one_trip`'s loop no longer covers those GLs, so a surviving
detail line becomes unreachable from Trip Manager.

Blocker checked and cleared: `_ensure_year_open_for_write` (`write_model.py:358`) raises
before the admin bypass when `dbo.submission_deadline` has no row for the year. FY2027 HAS a
row — deadline 2026-10-07, reminder 2026-09-22 — so the UI path works for everyone.

Verified target (dry run, `setup/wipe_other_travel_gl_rows.py`): detail_id 248 on trip 50
(นิภาพร ทองกิ่ง, Thailand, FY2027, CC 10AC020000), amount 0.00, plus its 0.00 parent row with
no remark. Sibling lines that MUST survive: 245 per-diem 500.00, 246 transport 1,000.00,
247 accommodation 3,000.00.
