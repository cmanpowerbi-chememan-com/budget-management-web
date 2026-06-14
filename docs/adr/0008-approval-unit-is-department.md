# 8. Approval unit = department (ฝ่าย), not Cost Center

Date: 2026-06-09
Status: Accepted
Supersedes the approval-unit decision in ADR-0003, ADR-0006, ADR-0007 (which used
`(cost_center, fiscal_year)`).

## Context

ADR-0003/0006/0007 set the approval unit to `(cost_center, fiscal_year)` with per-CC
first-wins, PENDING-lock, and batch-skip — chosen because a submitter-level ("whole
report") unit broke on shared CCs (one CC appearing in many submitters' reports, routing
to different managers).

Grilling 2026-06-09 surfaced a cleaner unit. The user wants **reject to bounce the whole
department** (a submitter fills and submits their ฝ่าย as one package, so a rejection
should return the whole ฝ่าย, not one CC). Checking the data: **`Cost Center → ฝ่าย` is a
function — 210/210 CCs map to exactly one ฝ่าย (0 violations)**. So ฝ่าย partitions CCs
cleanly (one-to-many: a ฝ่าย has 1.8 CCs avg, max 21). This is exactly what the
submitter-report unit lacked: a report spanned many ฝ่าย and CCs overlapped across
reports, but a **ฝ่าย never overlaps another ฝ่าย's CCs**.

## Decision

- **Approval unit = `(ฝ่าย/department, fiscal_year)`.** One approval record per
  department per year covers ALL Cost Centers of that ฝ่าย (~114 ฝ่าย vs ~205 CCs).
- **Submit** = the whole ฝ่าย's working_budget enters approval as one package.
- **Approve** = approve the whole ฝ่าย at once (the inbox can still bulk-select many ฝ่าย).
- **Reject** = bounce the **whole ฝ่าย** (all its CCs) with one reason → status back to
  DRAFT for the ฝ่าย; submitter fixes and resubmits the package.
- **Notify the last submitter** — when a ฝ่าย is collaboratively filled by several people,
  the rejection (and chain notifications) go to whoever **clicked Submit last** (the
  submitter of record for that ฝ่าย submission).
- **approver1 = the last submitter's `managerempcode`** (then Nipaporn → Waraporn, per
  ADR-0006). Special-case skips unchanged.
- **`approval_status` PK changes from `(cost_center, fiscal_year)` to
  `(ฝ่าย, fiscal_year)`** (+ last_submitter_empcode, snapshot approver1/2/3). The
  per-CC first-wins / PENDING-lock / batch-skip machinery from ADR-0006 is **no longer
  needed** — superseded by the ฝ่าย unit.
- **`budget.working_budget` data is UNCHANGED** — still keyed `(cost_center, gl_account,
  fiscal_year)`. Only the approval layer regroups to ฝ่าย. A ฝ่าย's CCs are found via the
  `Cost Center → ฝ่าย` map (file02; lives in cost-center master).

## Consequences

- Simpler than per-CC: ~114 approval records, no first-wins/skip logic, submit/reject as a
  natural department package — matches how a department actually works on its budget.
- No shared-CC conflict (CC→ฝ่าย is 1:1, proven) — the reason per-CC was chosen no longer
  applies, so ฝ่าย-unit is strictly cleaner here.
- Collaboration within a ฝ่าย still works (shared draft); the **last submitter owns** the
  approval and receives reject/notifications.
- Edge: a ฝ่าย's members may have different managers (e.g. Warehouse PB: 2 people, 2
  managers). approver1 = the **last submitter's** manager — accepted (one coherent path
  per submission).
- Inbox lists one row per `(ฝ่าย, year)` (not per CC); drill-down shows the ฝ่าย's CCs and
  their GLs. See `design/mockups/0013-approver-inbox-demo.html`.
  (superseded — approver inbox dropped; see ADR-0016, approve on main page)
