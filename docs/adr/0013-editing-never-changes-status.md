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
