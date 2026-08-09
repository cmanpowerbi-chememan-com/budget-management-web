# 29. Approver see-overlay: a pending department is always visible to its current approver

Date: 2026-08-08

Status: Accepted and implemented 2026-08-08. Backend only, TDD, not yet committed/deployed
(per task instructions).

## Context

See-scope (`backend/app/rls.py::resolve_scope`) was, until this ADR, `Fill ∪
_MANAGER_SEE_ADD_SQL` — the caller's own Fill cost centers, unioned with the Fill cost
centers of anyone whose Primary-row manager is the caller (ADR-0019/ADR-0007). That
covers a position-1 approver (almost always the submitter's own manager) but not the
two FIXED step-2/3 approvers, นิภาพร (empcode 101032) and วราพร (empcode 100427,
ADR-0006) — neither is in any submitting Filler's manager chain by construction.

Measured live twice (2026-07-22 and 2026-08-08): both approvers' personal See-scope is
7 Cost Centers, byte-identical, containing neither the SIT (Solution Delivery) nor the
UAT pilot department (`10IT011300`, `10IT0130000`). A department `PENDING_APPROVER2` or
`PENDING_APPROVER3` on them therefore never appears in their own `GET
/scope/departments` list — it is invisible in the DeptPicker, so they cannot reach the
Approve button through the UI at all (the admin-hat-on view deliberately hides the
approve buttons; this is a normal, non-admin approval). The 2026-07-22 test round hit
exactly this and worked around it with direct API calls instead of the real UI flow —
masking a defect that would otherwise block the 17–21 Aug UAT approval chain end to end.

## Decision

`resolve_scope` gains a third addend to `see_cost_centers` only: the **approver
see-overlay** (`rls._pending_approval_overlay`) — the live `dbo.cc_filler_map` Cost
Centers of every department currently in a `PENDING_*` status whose CURRENT approver
(any position, any fiscal_year) is the calling user.

- **See-only, never Fill.** The overlay is unioned into `see_cost_centers` alone. An
  approver reviews a department; they never gain write access to it — ADR-0013's
  read-only lock already renders those rows `editable=false` with the "🔒 ดูรายละเอียด"
  affordance, which is exactly the case-3 persona in the sign-off spec. No new lock logic
  was needed: the read path already keys off `see_cost_centers` minus `fill_cost_centers`
  for that affordance.
- **Any fiscal_year.** `resolve_scope` itself takes no fiscal_year argument and is
  year-agnostic; a department pending in FY2027 but not FY2026 must not create a
  fiscal-year-dependent scope (a Cost Center that silently disappears from an approver's
  own DeptPicker depending on which year's grid they're viewing would be a new, more
  confusing bug than the one being fixed). `app.approval.departments_pending_for_empcode`
  therefore takes `fiscal_year: int | None = None`, and the overlay calls it with `None`.
- **One shared definition of "current approver".** "Currently pending on me" was already
  answered once, for the A10 รออนุมัติ badge (`GET /approval/pending-for-me`,
  ADR-0016). Rather than re-derive who the frozen current-position occupant is a second
  time in `rls.py` (a second definition that could silently drift from the first — e.g. if
  `_to_state`'s position/escalation logic ever changes), `list_departments_pending_my_
  approval` was refactored to share a new `app.approval.departments_pending_for_empcode`
  helper with the overlay; both build on the pre-existing `fetch_pending_rows` (query
  shape) and `_to_state(...).can_act` (the "is this empcode the frozen current-position
  occupant" check). A second new helper, `cost_centers_for_departments`, is the plural
  sibling of the pre-existing `_department_cost_centers` — one live `dbo.cc_filler_map`
  lookup for a batch of departments.
- **Empcode resolution reuses the existing path.** `resolve_scope` receives an email;
  the overlay resolves it to an empcode via `app.approval.resolve_submitter` (the same
  function A6's submit/approve/reject flow already uses) — no new email→empcode mapping.
  A caller with no `dbo.v_employee_budget_01` row (e.g. a pure admin such as jakkaritw)
  can never be a frozen approver, so `resolve_submitter` returning `(None, None)`
  short-circuits the overlay to an empty set with zero `budget.approval_status` query.
- **Role derivation unaffected by construction, not by a special case.** The `role`
  computation only tests `if see_cost_centers: role = "see_only"` — the overlay is
  unioned into `see_cost_centers` *before* that check runs, so a caller whose ONLY scope
  is one pending department (zero Fill, zero personal See-add) correctly comes out
  `see_only`, never `none`. This matters concretely: the frontend's `hasNoScope = scope
  .role === 'none'` gate (`BudgetGrid.tsx`) blocks the entire page behind a "no access"
  empty state — a `none` role here would have re-introduced the exact same UI dead end
  this ADR exists to remove.
- **Minimal lifetime.** The overlay is recomputed fresh on every `resolve_scope` call
  from `budget.approval_status`'s CURRENT state — nothing cached, nothing remembered.
  The moment a department leaves a `PENDING_*` status (this caller approves it, someone
  else rejects it, an admin overrides the step), it drops out of the overlay on the very
  next call. It never grants standing access.
- **Position-1 no-op.** A position-1 approver (almost always the submitter's own
  manager) already sees the department via `_MANAGER_SEE_ADD_SQL`. The overlay's result
  is unioned into a Python `set`, so a Cost Center already present from that rule is
  simply not duplicated — the overlay is a pure no-op for the common case, and only
  changes behavior for the two approvers who were never reachable by the manager-chain
  rule in the first place.

## Rejected alternative

**Hand-widen นิภาพร's and วราพร's personal scope in `cc dept.xlsx`** — add every
department they might ever need to approve as an extra row naming them as a "Filler" (or
a similar manual entry) in the admin-maintained Cost Center↔Filler map (ADR-0019).
Rejected: this rots on every approver change (a new step-2/3 assignment, or any future
extra fixed approver, needs the SAME manual widening repeated by hand, on a spreadsheet
nobody remembers to touch for this reason) and it would grant *standing* access to
departments not currently pending on them, rather than access that tracks the workflow
state. The overlay derives visibility from `budget.approval_status` itself — the source
of truth for "whose turn is it" already exists and already changes automatically as
departments move through the chain; deriving from it costs nothing to maintain.

## Consequences

- **Performance**: `resolve_scope` runs on every scoped request. The overlay adds two
  unconditional queries — `resolve_submitter` (a single indexed point lookup by email
  against `dbo.v_employee_budget_01`) and `fetch_pending_rows(conn, None)` (a full scan
  of `budget.approval_status` filtered to `status IN (PENDING_APPROVER1/2/3)`, a small
  table — ~114 departments × a few fiscal years) — plus one conditional query,
  `cost_centers_for_departments`, that only fires when the caller actually has ≥1
  department pending on them (the common case, a regular Filler who is nobody's current
  approver, never reaches it: `departments_pending_for_empcode` returns `[]` and the
  overlay short-circuits before that query). This is 2–3 small queries, not the
  originally-hoped single query — accepted because the alternative (folding "who is the
  current approver" into one SQL statement) would duplicate `_to_state`'s
  position/escalation logic in SQL, a second definition that could drift from the
  Python one guarding A6 itself; sharing the existing helper was judged more valuable
  than shaving one query off an already-small table.
- **Docstrings corrected**: `rls.py`'s module docstring and `resolve_scope`'s own
  docstring, which previously stated See = Fill ∪ manager-add only, now name the overlay
  as a third addend.
- **No frontend changes.** `GET /scope/departments` already derives its Cost Center list
  from `scope.see_cost_centers` (`routers/reference.py`) — the overlay flows through with
  zero route changes. `GET /budget`'s existing ADR-0013 lock logic already renders a
  See-but-not-Fill row `editable=false` — zero new lock code. `BudgetGrid.tsx`'s
  `hasNoScope` check already treats `see_only` as a fully-functional page. Verified by
  running the full frontend suite unchanged (612/612) and `next build` clean.
- **No change to who may act.** The overlay only ever widens *visibility* (`see_cost_
  centers`); `submit_department`/`approve_department`/`reject_department` in
  `app.approval` are completely untouched by this ADR and still gate on their own
  independent current-approver checks.
