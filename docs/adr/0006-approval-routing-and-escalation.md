# 6. Approval routing, snapshot chain, and escalation

Date: 2026-06-07
Status: Accepted — **escalation clause superseded by ADR-0027 (2026-08-01)**; routing,
snapshot, fallback, self-skip/dedup, reject and state-machine rules all still current
Builds on: `requirement_spec/3_approval_workflow/approval_workflow_spec.md` (the chain + special cases)

## Context

The approval engine routes a submitted budget (one unit = `(ฝ่าย/department, fiscal_year)`
per **ADR-0008** — was `(cost_center, fiscal_year)`; the per-CC first-wins / PENDING-lock /
batch-skip parts of this ADR are superseded, but the routing/escalation/state-machine rules
below still apply, now at the ฝ่าย level) through up to three approvers: `approver1 = the submitter's managerempcode`,
`approver2 = Nipaporn (101032)`, `approver3 = Waraporn (100427)`. The spec already nails
the chain, the special-case skips (Nipaporn/Waraporn self-submit, C-level approve
themselves, intentional self-review), and reject→resubmit. Two things the spec left open
and one control question surfaced in grilling (2026-06-07): when the chain is resolved,
what happens when an approver is invalid, and what happens when one just sits on it.

## Decision

- **Resolve the chain at SUBMIT and snapshot it** into `approval_status` (store the
  resolved approver1/2/3 empcodes). The chain is frozen for that submission — a later HR
  reorg / managerempcode change does NOT shift an in-flight approval. (approver1 still
  comes from `mas_employee_data.managerempcode`, posstatus='Primary', at submit time.)
- **Invalid approver1 at submit** (null managerempcode, or it points to someone inactive /
  excluded — L5 / Gritsman / left) → **fall back directly to Nipaporn (approver2)**; do not
  block the submit, do not leave it ownerless.
- **Auto-submit DRAFT ฝ่าย at the deadline** (decided 2026-06-10): when the cutoff passes, a
  scheduled job submits every ฝ่าย still in DRAFT (with any working_budget rows) into the chain
  so nothing is silently lost (the reminder email is deferred). There is no human clicker, so
  `approver1 = managerempcode of the LAST EDITOR` of that ฝ่าย (the `_user` on the
  most-recently-updated working_budget row); invalid / absent → fall back to Nipaporn. Logged
  `AUTO_SUBMIT` (distinct from a normal submit). The normal chain then runs and any approver may
  reject incomplete numbers. A ฝ่าย with no rows at all has nothing to submit; orphan ฝ่าย are
  covered by the admin-fill fallback (ADR-0009), not auto-submit.
- **Detection of a stuck approval** (no remedy needs the user to notice first):
  1. submitter sees their own submission's status lingering;
  2. a cross-check against the daily employee sync flags PENDING approvals whose current
     approver empcode is no longer active in `mas_employee_data`;
  3. age — PENDING beyond a threshold is flagged.
  Surfaced in an **admin "overdue / stuck approvals" view**.
- **Approver departed mid-flight** (snapshot approver becomes inactive after submit) →
  admin reassign/override from that view, logged as `ADMIN_OVERRIDE` in `approval_log`.
- ~~**Approver valid but silent > 30 days** → **auto-escalate the stuck STEP only**: mark
  that one step approved, advance to the NEXT approver, and log `AUTO_ESCALATE`.~~
  **SUPERSEDED 2026-08-01 by ADR-0027**: the automatic 30-day escalation is deleted. A stuck
  step is now advanced only by a human — an admin clicking a manual step-override, position 1
  only, logged under its own action with the admin's real email. The invariant this clause
  protected is unchanged and restated in ADR-0027: the override advances ONE step and can
  never land final `APPROVED`; the remaining approvers (incl. budget dept Nipaporn/Waraporn)
  still review. What changed is only the trigger — clock → human — plus a 7-day reminder that
  now repeats indefinitely instead of ending in an automatic skip.
- **Status enum = neutral** `DRAFT / PENDING_APPROVER1 / PENDING_APPROVER2 /
  PENDING_APPROVER3 / APPROVED / REJECTED` (the spec's `PENDING_L1/2/3` are the same
  states — use the neutral names consistently; ADR-0003). Who each approver is + skip
  logic live in backend routing, not the schema.
- **Self-review / duplicate-in-chain rule = SELF-SKIP + DEDUP** (resolved 2026-07-14, grilled
  against real data): resolve the raw chain `[approver1 = submitter's Primary-row managerempcode,
  Nipaporn (101032), Waraporn (100427)]`, then (1) DROP any step whose approver = the submitter
  (nobody approves their own budget) and (2) DEDUP a repeated approver (keep the earliest step).
  The survivors are the actual chain. Real cases (Nipaporn & Waraporn jointly Fill 5 ฝ่าย, and
  Nipaporn's Primary-row manager IS Waraporn):
  - **Nipaporn submits her own ฝ่าย** → raw `[Waraporn, Nipaporn(self), Waraporn(dup)]` →
    **`[Waraporn]`** (she is both Nipaporn's manager and the Budget Manager, so one review covers both).
  - **Waraporn submits her own ฝ่าย** → raw `[Piyada (101218, her manager), Nipaporn, Waraporn(self)]`
    → **`[Piyada, Nipaporn]`** (Nipaporn's step is a budget-dept review, not a hierarchy sign-off —
    a subordinate reviewing the boss's budget is acceptable; Piyada is the hierarchy approver).
  - A normal submitter (not Nipaporn/Waraporn) → no collision → full `[manager, Nipaporn, Waraporn]`.
  Also covers a C-level whose own managerempcode is themselves (self-skip drops that step). If
  self-skip + dedup empties the chain entirely, fall back to Nipaporn (never auto-APPROVE with no review).
- **Reject** (at ANY step — approver1/2/3) → status = `REJECTED` (editable like `DRAFT`,
  bounced all the way back to the filler; NEVER a partial resume at the rejecting step). The
  submitter edits and **resubmits**, which then sets status → `PENDING_APPROVER1` and re-runs
  the WHOLE chain from the top (re-snapshotting approver1 = the submitter's current Primary-row
  manager). *(Reconciled 2026-07-12: the earlier "resets to PENDING_APPROVER1" wording conflated
  the reject-target with the resubmit-target and contradicted the state table below —
  `PENDING_APPROVER1` is LOCKED/uneditable, so reject cannot land there. Reject lands on the
  editable `REJECTED` state; only resubmit re-enters `PENDING_APPROVER1`. Confirmed by user: a
  reject at any layer always restarts the full chain, no resume.)*

### State machine & edit-lock (grilling 2026-06-07)

| Status | Submitter can edit? |
|--------|--------------------|
| `DRAFT` | Yes — auto-save. |
| `PENDING_APPROVER1/2/3` | **Locked** — no edit AND **no recall**. Once submitted, it waits for approve/reject; the only way back is an approver rejecting it. (Editing while an approver is reviewing = an implicit recall, so it's disallowed.) |
| `APPROVED` | Yes, but editing **resets the whole CC+year to re-approval** (status → back into the chain from `PENDING_APPROVER1`, re-snapshot). |
| `REJECTED` | Treated as back to `DRAFT` — editable, then resubmit. |

- **No recall** of a PENDING submission (decided). Mistakes after submit are handled by the
  approver rejecting.
- **Editing an APPROVED budget is guarded by an explicit confirm** ("editing will send the
  whole CC budget back into approval — continue?"). This prevents auto-save from silently
  un-approving an entire CC on a single keystroke. After confirm → DRAFT → edit (auto-save)
  → resubmit. Logged.

## Consequences

- In-flight approvals are stable against HR churn; the trade-off is a snapshot can go
  stale (the departed-approver case), which the sync cross-check + admin override cover.
- ~~The 30-day step auto-escalation keeps budgets moving without ever bypassing budget-dept
  sign-off — slowness is bounded, control is preserved.~~ **Superseded by ADR-0027**: slowness
  is no longer bounded by anything automatic. A stuck step waits until an admin overrides it,
  and the only automatic signal is the 7-day reminder to the (already silent) approver.
- `approval_status` must store the snapshot approver empcodes (not only the current state),
  so the data model gains approver1/2/3 columns on that table.
- Open: the "overdue / stuck approvals" admin view is still unbuilt. It mattered less while
  the 30-day escalation existed; under ADR-0027 it is the natural home for the manual
  step-override and the main mitigation for "nobody notices a stuck ฝ่าย".
