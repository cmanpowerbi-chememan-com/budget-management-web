# 24. Admin-GL rows (`edit_by='admin'`) are self-approved on save — never enter `approval_status`

Date: 2026-07-17
Status: Accepted
Narrows: ADR-0011 (the "only `APPROVED` flows to Gold" rule applies to lane-2.1 / user-GL rows only)
Disambiguates from: ADR-0012 (Template-2 `template='ADMIN'` overlay door — a SEPARATE concept, see below)
Builds on: ADR-0008 (approval unit = department), ADR-0013 (editing never changes approval status)

## Context

`dbo.gl_group.edit_by` marks 13 live GL accounts (Insurance Premium, Employee benefits severance,
Depreciation) as `'admin'` — secret figures only the Budget dept (admin) may see or fill; regular
users, fillers, and approvers must never see or act on them (design v2, 2026-07-17, flag-gated by
`Settings.gl_edit_by_enabled`, still OFF). jakkaritw's rule: **"admin กรอก = อนุมัติเลย"** — an
admin-GL row is final/approved the instant the admin saves it, independent of the department's
normal chain.

A first implementation pass added `AdminGlInNormalSubmitError`: whenever an admin who ALSO Fills a
department tried a **normal** submit while that department held a pending admin-GL row, the guard
forced the submit into `_admin_direct_approve` instead. That was a bug: `_admin_direct_approve`
stamps the **whole** `(department, fiscal_year)` record `APPROVED` directly, with no chain — so an
admin's normal submit of their own department (which almost always also contains ordinary user-GL
rows a real approver must review) would silently bypass the real approver1/2/3 chain for those
user-GL rows too, just because the department happened to also hold one admin-GL line. The guard
conflated "this department has a secret row in it" with "this department's submit must skip
review" — wrong on both readings (an admin filler AND a non-admin filler need the identical normal
chain for their user-GL rows).

## Decision

- **Lane 2.2 (admin-GL) is identified by `dbo.gl_group.edit_by = 'admin'` only — never by
  `template`.** `template='ADMIN'` is the pre-existing, unrelated Template-2 overlay door (ADR-0012,
  `_department_has_admin_template_rows` / `_admin_direct_approve`'s `ACTION_ADMIN_SUBMIT` branch) —
  a department entered directly by the admin as a whole. `edit_by='admin'` is a property of the GL
  **account**, not of who typed the row or which template it used. The two must never be conflated:
  a lane-2.2 row can be saved under `template='USER'` by an admin who is also that department's
  filler, and a Template-2 department can be 100% ordinary user-GL rows.
- **Admin-GL pending rows never enter `budget.approval_status` at all.** They are not submitted,
  not chained, not approved/rejected through the state machine — they simply exist in
  `budget.pending_budget` (lane 2.2) the moment an admin saves them, and that existence + row
  ownership (`edit_by='admin'` on the GL) IS the approval. `submit_department`/`approve_department`/
  `reject_department` never reference them; `AdminGlInNormalSubmitError` and its supporting
  `gl_access.department_has_pending_admin_gl_rows` lookup are **removed** (the bug above) —
  `submit_department` now governs ONLY a department's lane-2.1 (user-GL) rows for BOTH an admin
  filler and a plain non-admin filler, exactly the same normal chain either way.
- **No new column, no `approval_log` row for the save-time "approval."** Audit trail = the existing
  `budget.pending_budget._user` (who saved it) + `_updated_at` (when) — sufficient at this scale
  (internal tool, 13 GLs, admin-only), no schema change.
- **`APPROVED` status on `budget.approval_status` describes lane-2.1 (user-GL) rows only.** A
  department's status can be `APPROVED` while its admin-GL rows were saved (and are therefore
  final) independently, on a different timeline, by a different actor path — the two lanes never
  share a status field.
- **auto_submit job exclusion (flag-gated):** `jobs/auto_submit.py`'s "last editor" discovery (used
  to resolve a true-DRAFT department's `approver1_empcode` from its manager) now excludes admin-GL
  rows from BOTH the candidate row and the correlated MAX(`_updated_at`) subquery, when
  `Settings.gl_edit_by_enabled` is True — so approver1 for an auto-submitted department is never
  resolved from someone who only ever touched a secret admin-GL line. Flag OFF: byte-identical query
  (no exclusion clause at all).

## Consequences

- **Phase-2 Gold promotion (not built — informational, narrows ADR-0011):** ADR-0011's "only
  `status = APPROVED` flows to `gold_budget`" rule applies to **lane-2.1 (user-GL) rows only**.
  Admin-GL pending rows flow to Gold **unconditionally** — every row in `budget.pending_budget`
  whose GL is admin-only is promoted regardless of its department's `approval_status`, since
  admin-GL rows have no chain to wait on in the first place. The eventual Gold view is a UNION of:
  (a) lane-2.1 rows where the department is `APPROVED`, (b) ALL lane-2.2 (admin-GL) pending rows
  unconditionally, (c) `board_budget` (prior approved-import reference, ADR-0003/0021).
- Removing `AdminGlInNormalSubmitError` fixes the bypass: an admin's normal submit of their own
  department now always runs the identical chain a non-admin filler would get — self-skip/dedup,
  manager resolution, PENDING_APPROVER1→2→3 — regardless of whether that department also holds
  admin-GL rows. The Template-2 (`template='ADMIN'`) direct-approve door (ADR-0012) is untouched and
  remains the only submit-time direct-APPROVED path.
- `gl_access.py` keeps only the 3 remaining call sites that read `edit_by` for visibility/write
  gating (`reference_data.fetch_gl_accounts`, `read_model.merge_budget_rows`, `write_model.py`'s
  write-time 403) — `approval.py` has no call site here anymore.
- Still flag-gated end to end (`Settings.gl_edit_by_enabled`, default False) — no behavior change
  until jakkaritw flips it on for the 13 real admin GLs.
