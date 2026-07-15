# 12. Admin submit = direct APPROVED (orphan in-cycle, everything post-deadline)

Date: 2026-06-13
Status: Accepted
Supersedes the **admin-submit / override-submit** decision of ADR-0009 (the two-mode
admin submit, the orphan-via-admin-loop, and the 4-row admin-loop routing table).
ADR-0009's deadline-lock, orphan-ฝ่าย identification, and `ADMIN_OVERRIDE` logging still stand.
Builds on ADR-0008 (approval unit = ฝ่าย).

## Context

ADR-0009 gave Admin a nuanced submit power: in the open cycle submit own-orgcode CCs + orphan
ฝ่าย; after the deadline override-submit any ฝ่าย — and **all of it routed on a 4-row
"admin-loop" table** (วราพร→APPROVED, ปิยะดา→APPROVED, นิภาพร→วราพร, jakkaritw→นิภาพร→วราพร).

Grilling 2026-06-13 simplified this. The user's model: **Admin is an oversight editor, not a
budget-pusher.** An admin can fix any Pending number, but should not push a normal department's
budget through the approval chain during the open cycle — that is the submitter's job. The only
budgets an admin legitimately *owns* are (a) **orphan ฝ่าย** (no submitter exists) and (b)
**everything after the deadline** (the cycle is closed; the admin is the only operator). And for
both, since the admin IS the budget authority, the budget is **APPROVED directly — no approval
chain** (the admin-loop routing is unnecessary ceremony).

## Decision

- **Admin can EDIT any CC's Pending, always** (oversight / emergency fix) — unchanged.
- **Admin Submit — when allowed, goes straight to `APPROVED`, NOT into any chain** (no managerempcode,
  no Nipaporn/Waraporn, no admin-loop table). Logged `ADMIN_OVERRIDE` (who/when/ฝ่าย/old→new).
- **Open cycle:** Admin may Submit **ONLY orphan ฝ่าย** (a ฝ่าย with CCs in file02 but NO submitter in
  `user_fill_dept` — verified 8 ฝ่าย / 10 CC: CFO, COO, Company Secretary, General, KK/PBB
  Factory-node, Security KK/TK). Admin fills + submits these as the fallback owner → APPROVED.
  Admin **cannot** Submit any normal (owned) ฝ่าย while the cycle is open — only edit it.
- **After the deadline:** the cycle is locked for all normal users; **Admin handles everything** —
  edit + Submit **any** ฝ่าย → APPROVED directly. This also resolves the post-deadline deadlock
  ADR-0009 worried about (a ฝ่าย rejected/left-DRAFT after cutoff): the admin simply completes it.
  No "extend the deadline" step is required (still available as an alternative to re-open a ฝ่าย to
  its original submitter, but not the primary path).
- **Submit/Approve still act on the whole `(ฝ่าย, fiscal_year)` block** (reaffirms ADR-0008) — an
  admin one-CC fix submits the entire ฝ่าย.
- **`board_budget` (Approved) import/export CSV is the admin's other lane** and is unchanged —
  separate lifecycle, unaffected by the deadline lock.
- **AMENDED 2026-07-16 (A6 gate, confirmed by jakkaritw — "กันไว้ก่อน" / fail-closed):** while the
  cycle is OPEN, an admin Submit (both the orphan branch and the Template-2 `ADMIN_SUBMIT` branch)
  must NOT overwrite a `(ฝ่าย, fiscal_year)` record that is mid-chain (`PENDING_APPROVER1/2/3`) or
  already `APPROVED` — the API returns 409; the admin must wait for a reject or for the deadline to
  pass. Rationale: a dept can hold both Template-1.1 CCs (in the real chain) and Template-2 CCs; an
  in-cycle admin submit would silently skip the pending approvers for the whole block (ADR-0008
  whole-ฝ่าย semantics). The **post-deadline branch keeps its override-everything behavior**
  unchanged. Backend guard: `_ensure_admin_overwrite_allowed` in `backend/app/approval.py`.
  `ADMIN_OVERRIDE` logging is now split into `ADMIN_OVERRIDE_ORPHAN` / `ADMIN_OVERRIDE_DEADLINE`
  so the audit trail distinguishes the two branches.

## Consequences

- Much simpler than ADR-0009: no admin-loop table, no own-orgcode submit rule, no chain routing for
  admin actions. Admin submit is a single concept: *"the budget authority records it as approved."*
- **Trust caveat — DECIDED 2026-06-13 (option A):** the rule treats ALL `ADMIN_EMAILS` equally; a
  direct-APPROVE bypasses budget review. For budget authorities (วราพร / ปิยะดา / นิภาพร) that is
  correct. **jakkaritw** (external/Data-Analytics admin, no `mas_employee_data` row) is **a FULL
  production admin and MAY direct-approve** — accepted because this is an internal tool and jakkaritw
  is trusted. No separate "system admin" vs "budget admin" tier. (Rejected alternative B: strip
  jakkaritw's Submit→APPROVED power and keep it test-login-only.)
- Normal submitters are unaffected: they still Submit their own ฝ่าย into the real chain
  (managerempcode → Nipaporn → Waraporn). นิภาพร/วราพร dual-role unchanged (Submit own ฝ่าย via chain;
  approve others) — per CLAUDE.md special cases + ADR-0006/0008.
- Wired in mockup `design/mockups/0002claude design/0002.1budget-export.html`: `fillDeptsOf()`
  (admin → orphan in-cycle / `__ALL__` post-deadline), `updateActionBar()`, `submitToDB()` (admin
  branch → "APPROVED ตรงๆ"), a test `🔒 หลัง deadline` toggle, and an orphan ฝ่าย "General".
