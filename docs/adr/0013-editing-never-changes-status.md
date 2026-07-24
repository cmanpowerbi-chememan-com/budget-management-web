# 13. Editing a number never changes status; APPROVED is freely editable

Date: 2026-06-13
Status: Accepted
Supersedes the **edit-lock table** of ADR-0006 — specifically the `APPROVED` row
("editing resets the whole CC+year to re-approval") and the "edit-APPROVED guarded by an
explicit confirm" rule. The rest of ADR-0006 (chain, snapshot, escalation, status enum) stands.

## Context

ADR-0006 made editing an APPROVED budget bounce the whole ฝ่าย back into the chain (DRAFT →
re-snapshot → re-approve), behind a confirm dialog — to stop an approved budget changing silently.

Grilling 2026-06-13: the user wants the mental model dead simple — **"แก้ตัวเลข = save; สถานะคงเดิม;
ไม่มีข้อยกเว้น"** — and explicitly wants approved numbers to remain editable without any re-approval
ceremony.

## Decision

- **Editing a Pending number NEVER changes the `(ฝ่าย, fiscal_year)` status by itself.** Status moves
  ONLY via explicit button actions — Submit / Approve / Reject. There is **no exception** (no
  edit-APPROVED confirm, no bounce-to-DRAFT, no re-snapshot — all removed from ADR-0006).
- **Edit rights by role × status:**

  | status | submitter (own ฝ่าย) | admin (any CC) |
  |--------|----------------------|----------------|
  | `DRAFT` | ✅ edit (stays DRAFT) | ✅ edit |
  | `REJECTED` | ✅ edit (stays REJECTED; = draft-like) | ✅ edit |
  | `PENDING_APPROVER1/2/3` | 🔒 locked (in an approver's queue) | ✅ edit (override) |
  | `APPROVED` | 🔒 locked (corrections go through admin) | ✅ **edit — stays APPROVED, no review** |

- **Admin editing an APPROVED ฝ่าย** = the number changes in `pending_budget`, status **stays
  `APPROVED`** — no confirm, no re-approval ("พิมพ์ทับได้เลย"). This is the deliberately-accepted
  "approved budget changes silently" trade-off (scoped to admin only).
- **The in-flight PENDING lock is retained** so an approver never approves numbers that shift under
  them mid-review (a submitter cannot edit/recall while it is PENDING; only admin override may).
- **Audit:** every edit is recorded via `updated_by` / `updated_at` (activity tracking, CLAUDE.md), so a
  post-approval admin change is traceable even though it does not re-enter approval.

## Consequences

- One simple rule: **"edit = save the number; buttons move the status."** No special APPROVED path, no
  confirm modal, no re-snapshot on edit. Less code, less for users to understand.
- **Trade-off (accepted):** an APPROVED budget's numbers CAN change afterward without re-review. So
  `APPROVED` now means *"this ฝ่าย was approved at least once,"* NOT *"the current numbers are frozen."*
  Acceptable for an internal tool — changes are logged (`updated_by`/`updated_at`), and budget-dept /
  admin oversight covers misuse. If a stronger guarantee is ever needed, lock APPROVED instead (the
  rejected option A from this grilling).
- The in-flight PENDING lock is retained so an approver never approves numbers that shift under them
  mid-review.
- Mockup `0002.1budget-export.html` has no edit-APPROVED confirm (good), but does NOT yet enforce the
  per-status edit lock (submitter PENDING/APPROVED → read-only): all Pending inputs are currently plain
  editable regardless of status/role. Wiring the status×role edit-lock is deferred (same task as the
  "lock Pending read-only when an approver views").

## Addendum (2026-07-24) — FX-reconciliation job is an explicit exception to the edit-lock

The new job `backend/jobs/repersist_perdiem_fx.py` (financial reconciliation, GATE decision
2026-07-24) is a deliberate, narrow exception to the edit-rights-by-status table above. It
re-persists the **DERIVED, system-managed per-diem line** (the `per_diem_gl` detail row +
its parent cell) for **every trip of a fiscal_year, regardless of `(department,
fiscal_year)` approval status** — including `PENDING_APPROVER1/2/3` and `APPROVED` — and
deliberately does **not** call `_ensure_department_not_locked` / look up
`budget.approval_status` at all.

This does not contradict "editing never changes status" above: the job is not a user
edit. It never touches human-typed amounts (transport/accommodation/other travel lines, or
any non-Travelling GL) and never moves status (no re-approval, no bounce-to-DRAFT) — it
only re-derives the one per-diem figure that ADR-0015 already defines as a value tracking
the shared Master FX, not a frozen number. Treat it like "admin edits an APPROVED ฝ่าย"
above: a deliberate, logged (`_user="system:fx_repersist"`), authority-gated correction —
run manually, dry-run by default — not a loophole. See ADR-0015's addendum (2026-07-24)
for why the per-diem figure is allowed to move after approval in the first place.
