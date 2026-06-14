# 14. Admin powers are an opt-in mode (toggle), not always-on, for dual-role admins

Date: 2026-06-13
Status: Accepted
Builds on: ADR-0004 (admin = `ADMIN_EMAILS` overlay on one Entra identity, not a separate account),
ADR-0012 (admin submit = direct APPROVED).

## Context

Three of the four admins (วราพร, นิภาพร, ปิยะดา) are ALSO normal actors — they submit their own
ฝ่าย and/or approve others through the chain. Their admin overlay (sees-all, edit any CC, orphan /
post-deadline direct-approve, board_budget CSV import) STACKS on top of that base role. The user's
concern (2026-06-13): if the admin overlay is always-on, these people see their approver/submitter
actions mixed with dangerous admin powers in one view — confusing, and easy to act with the wrong
"hat" (e.g. silently edit someone else's APPROVED budget while meaning to approve their own queue).

Separating identities (a second admin email/account) was rejected — it contradicts ADR-0004 (one
Entra identity, allowlist = role flag) and adds login-switching + duplicate RLS for no real gain.

## Decision

- **Admin powers are gated behind an explicit "โหมด Admin" toggle**, default **OFF**:
  - **OFF** → the person acts as their **base role** (approver / submitter): picker shows their own
    ฝ่าย + approval queue (with รออนุมัติ badges), Approve/Reject available, NO sees-all, NO CSV
    import zone, NO orphan/override submit.
  - **ON** → the **admin hat**: sees ALL ฝ่าย (no approval badges), edit any CC, Submit orphan
    (in-cycle) / any ฝ่าย (post-deadline) → APPROVED directly (ADR-0012), board_budget CSV zone
    visible. Approve/Reject is hidden in admin mode (administering ≠ approving).
- **Pure admins** (role `admin`, no base actor role — incl. **jakkaritw**, who has no
  `mas_employee_data` row) have nothing to switch to, so they are **always in admin mode** and get
  **no toggle**.
- Switching the toggle resets the locked ฝ่าย (scope differs between hats) and, turning OFF, clears
  the post-deadline test flag.
- Still one identity / one login (ADR-0004) — the toggle changes the active *hat*, not the account.

## Consequences

- Dual-role admins default to their everyday (approver/submitter) view; the dangerous cross-department
  powers require a deliberate switch — fewer "wrong hat" mistakes, clearer mental model.
- A clean conceptual split: **approve** (move someone's budget through the chain) vs **administer**
  (edit/override/import as the budget authority). They never appear at once.
- jakkaritw stays simple (always admin). In the mockup jakkaritw is also `superTest` (Submit any ฝ่าย)
  for fast UI testing — orthogonal to this toggle.
- Wired in mockup `0002.1budget-export.html`: `adminMode` state, `isAdminUser()` / `adminActive()`
  helpers, `🛡️ โหมด Admin` toggle (shown only for overlay admins), `onAdminModeToggle()`. นิภาพร is
  the demo dual-role persona (approver2 + admin).
