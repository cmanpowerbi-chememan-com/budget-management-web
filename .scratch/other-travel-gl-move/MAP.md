# Map — Other-Travel GL leaves the trip form

Label: `wayfinder:map` · charted 2026-09-04 · tracker id `other-travel-gl-degroup`

## Destination

GL `5210400999` (COST) and `6210400999` (SG&A) — "ค่าใช้จ่ายเดินทางอื่น (รวมในประเทศ และ
ต่างประเทศ)" — are LIVE IN PRODUCTION as ordinary monthly main-grid cells under gl_group
`Other manpower exp (Per diem,Health check,Uniform…etc)`, no longer reachable from Trip
Manager. Travelling Expense holds 6 GLs (3 types x 2 sides); the trip form shows 3 rows.
Pre-existing values for the pair are deleted, not migrated.

## Notes

- **Execution is IN the map** (jakkaritw, Q5 = ข). This map does not stop at a spec; it ends
  when the change is verified in production. Wayfinder's plan-don't-do default is overridden.
- Domain: CMAN budget web. "Special GL group" = a gl_group whose GLs are entered through a
  subform instead of a grid cell; the list of 6 such groups is hardcoded in
  `backend/app/special_gl.py`, NOT in the master. The master (SharePoint Excel) only says
  which group a GL belongs to.
- `budget.pending_budget.gl_group` is a SNAPSHOT copied at save time
  (`write_model._derive_dim_snapshot`), never a live join — a master change does not
  retro-update saved rows.
- Skills each session should consult: `00-team-workflow` routing, `11-code-standards`,
  `10-deploy-checklist` before any deploy.
- Never-cut: deploy approved by jakkaritw; verify-deploy-landed; verify-target + explicit
  confirm before the destructive delete.

## Decisions so far

- [D1 — Both accounting sides move](tickets/D1-both-sides.md): 2 GLs, `5210400999` and
  `6210400999`, not just the SG&A one.
- [D2 — Target group](tickets/D2-target-group.md): `Other manpower exp (Per
  diem,Health check,Uniform…etc)` — exact live string, U+2026 ellipsis, no space after
  commas. Chosen over a brand-new group because group names must match SAP (they join to
  Accruals) and over a per-GL code exception because special-ness is group-grained.
- [D3 — Old values are wiped](tickets/D3-wipe-not-migrate.md): live footprint is 1
  `pending_budget` row (FY2027 / 10AC020000 / 6210400999 / total_year 0.00 / dept Budgeting
  & Cost Accounting / approval_status NULL) + 1 `pending_budget_detail` line on 1 trip.
  Zero rows for `5210400999`. Nothing is locked, so the wipe is safe.
- [D4 — Ordering: code ships BEFORE the master sync lands](tickets/D4-ordering.md): the
  Excel is already edited; the daily ~06:31 sync will flip `dbo.gl_group`. From that moment
  `_save_one_detail_line` (`backend/app/write_model.py:991`) raises `NotSpecialGlError`
  while `TripManager.tsx:624` still saves that row → user-visible failure. Hard deadline.
- [D5 — Travelling Expense stays a special group](tickets/D5-group-stays-special.md): only
  its membership shrinks 8 → 6. `SPECIAL_GL_GROUPS` is untouched.
- [D6 — Wipe BEFORE the deploy](tickets/D6-wipe-first.md): the clean, invariant-preserving
  delete only exists while old code and old master are still coherent. FY2027 is confirmed
  open (`dbo.submission_deadline` deadline 2026-10-07), so the app path is available.
- [D7 — Deadline is 2026-09-05 ~06:31](tickets/D7-deadline.md): `dbo.submission_deadline
  ._load_dttm` = 2026-09-04 06:31:55 proves today's sync ran BEFORE the Excel edit, so the
  flip lands on the next run.
- [D8 — The dict edit is a money-loss fix, not cleanup](tickets/D8-silent-zeroing.md): with
  `other` still in `TRAVEL_GL_BY_TYPE_SIDE`, deleting ANY trip in the same cost_center +
  fiscal_year recomputes the now-plain cell to SUM(detail)=0 and then orphan-deletes the row.
  No error, no log, no email. Regression-tested.

## Not yet specified

- Whether the SIT test-case workbook on SharePoint has cases covering the 4-row trip form,
  and who re-runs them.
- Whether a new ADR is warranted for the governance rule this exposed: *a master-data edit
  can change an app entry mode*, with no code review in the loop.
- Product consequence: "other travel" amounts lose their trip linkage (no trip_id, no
  traveler, no travel-month coupling). Where the guidance for users lives — the trip
  รายละเอียด note, the row remark, or nowhere — is unresolved.

### Graduated out of the fog 2026-09-04 (resolved, no ticket needed)

- **Read path / stale snapshot** — the grid never routes on the saved snapshot;
  `GridTable.tsx:569` resolves `glMetaFor(...)` from the LIVE `GET /budget/gl-accounts`.
  And `_recompute_parent_cell` rewrites `gl_group` on any touch, so snapshots self-heal.
- **Gold / board_budget** — the approved-budget file carries no gl_group at all; dims are
  re-derived from the master on every Replace-by-Year load. Nothing to update.
- **Notifications / approval** — `grep gl_group backend/app/` returns one docstring hit in
  `approval.py` and zero in `notifications.py` / `jobs/`. Approval is (department, year)
  grained. Positive clearance.
- **Deploy skew** — `backend/Dockerfile` bakes `frontend/out` into the same image FastAPI
  serves, so frontend and backend ship together by construction. HTML is `no-cache`, so a
  browser refresh suffices; there is no CDN purge step.
- **gl_group caching** — there is none. `fetch_gl_accounts` / `fetch_master_gl_codes` /
  `_lookup_gl_group` all hit the table per request, so the flip is live on the next request
  and nothing needs invalidating.

## Out of scope

- The **TOTAL DAYS / YEAR** field circled in the original screenshot — jakkaritw: "forget
  it" (2026-09-04). Not fog; consciously ruled out of this effort.
- Migrating the old values into the new normal row — rejected in D3 in favour of wiping.
- Editing the DW sync notebook or the SharePoint master (master edit already done by
  jakkaritw; the notebook lives in workspace `cman-dw-ws`, another repo).
- **Revising the signed Spec B / subform spec documents** — jakkaritw, 2026-09-06: chosen not to
  do it. The documents still describe a 4-row trip expense table; the app has 3. Documentation
  drift is accepted, no system impact. See [T06](tickets/T06-signoff-docs.md).
