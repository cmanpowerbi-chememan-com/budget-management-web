# D4 — Code ships before the master sync lands  [CLOSED 2026-09-04]

## Question
Which comes first: flipping the master, or deploying the code?

## Resolution
Code first — and the project is already in the wrong order, which is what makes this urgent.
The Excel is edited; the daily ~06:31 sync will push it into `dbo.gl_group`.

Failure mode if code lags the sync, traced in the code rather than assumed:
`_save_one_detail_line` resolves the LIVE gl_group via `_derive_dim_snapshot`, calls
`classify_special_gl`, gets `None` for the new group, and raises `NotSpecialGlError`
(`backend/app/write_model.py:989-992`, error code `not_special_gl`). The frontend keeps
rendering and saving that row (`MANUAL_TRAVEL_TYPES` loop, `TripManager.tsx:624-635`), so a
user typing in ค่าใช้จ่ายเดินทางอื่นๆ gets a save error with no way around it.

The reverse order (code first, master later) is safe: the code stops writing those GLs through
the detail endpoint, and until the master flips they simply stay locked grid cells.
