# Plan — Delete 30-day auto-escalation, add manual admin step-override

**Decision record:** ADR-0027 (read it first — it holds the *why*)
**Implementer:** Kimi Code · **Tracker:** `admin-step-override`
**Grilled with jakkaritw 2026-08-01** (`/grill-with-docs`), 6 decisions locked below.
**Docs already updated by the grilling session — do NOT redo:** `docs/adr/0027-*.md` (new),
`docs/adr/0006-*.md` (escalation clause struck through + consequences amended), `CONTEXT.md`
(Turn / Turn reminder / Step override / Auto-escalation-RETIRED), `docs/reference/approval-workflow.md`
(rules list + email trigger table + anchor note).

## 1. Locked decisions

| # | Decision |
|---|---|
| D1 | **Delete** the 30-day auto-escalation outright — job, action constant, `is_step_stale`, workflow step, tests. Not flag-gated, not dormant. |
| D2 | **Add** a manual admin step-override: advances **exactly one step**, follows the same active-position walk as a real approve, and may **never** land `APPROVED`. |
| D3 | Available **immediately** (no stale-time gate) and **no reason required**. |
| D4 | **Position 1 only.** Positions 2/3 (Nipaporn/Waraporn = budget dept) can never be overridden by anyone. jakkaritw did not object to this hard lock — it is Claude's proposal, flag it in the close-out summary so he can still veto. |
| D5 | On override, send an event mail **immediately**: To = the ฝ่าย's submitter, **cc = the approver who was skipped**. No monthly digest. |
| D7 | **One button in the UI** (jakkaritw 2026-08-01): the admin reuses the normal อนุมัติ button; only the confirm dialog differs (it must name the person being skipped). The approve/override split is server-side only — two endpoints, two log actions. |
| D6 | Turn reminders repeat **every 7 days forever** until the approver acts — no end date, no cc escalation after N rounds, no cap. |

Live-data facts that make D1 safe (verified 2026-08-01): `budget.approval_log` = **0 rows**
(no `AUTO_ESCALATE` history to preserve), `budget.approval_status` = 0 rows.

## 2. Part A — remove the auto-escalation

Delete, in one commit:

- `backend/jobs/auto_escalate.py` (whole file)
- `backend/tests/test_jobs_auto_escalate.py` (whole file)
- `backend/app/approval.py`: `auto_escalate_step`, `is_step_stale`, `ACTION_AUTO_ESCALATE`,
  `AUTO_ESCALATE_ACTOR_EMAIL`, `AUTO_ESCALATE_THRESHOLD_DAYS`, and the docstring paragraphs in
  `_advance_one_step` / `_notify_after_transition` that explain the auto-escalate branch
- `.github/workflows/budget-automations.yml`: the whole "Auto-escalate stale approvals, 30-day
  SLA (A11)" step (leave auto-submit and reminders untouched); update the header comment block
- any auto-escalate assertions in `backend/tests/test_approval.py`,
  `backend/tests/test_integration_live_jobs.py`, `backend/tests/test_jobs_common.py`

**KEEP** `_current_step_started_at` and `current_turn_info` — the 7-day reminder cadence
anchors on them. `current_turn_info`'s docstring currently justifies itself by "so the reminder
cadence can never drift from the 30-day auto-escalate clock"; rewrite that sentence, don't
delete the function.

## 3. Part B — the override itself (`backend/app/approval.py`)

New action constant `ACTION_ADMIN_STEP_OVERRIDE = "ADMIN_STEP_OVERRIDE"` (naming is a proposal;
it must be visibly distinct from `APPROVE` and from the existing `ADMIN_SUBMIT` /
`ADMIN_OVERRIDE_ORPHAN` / `ADMIN_OVERRIDE_DEADLINE`, which are submit-side).

```
def admin_override_step(conn, department, fiscal_year, admin_email) -> ApprovalStatusState
```

Order of checks — each its own typed error, no silent no-ops:

1. row exists, else `ApprovalRecordNotFoundError`
2. `row["status"] == PENDING_APPROVER1` exactly. Any other PENDING_* → a NEW error
   (`StepNotOverridableError`) meaning "positions 2/3 are the budget-dept review, never
   overridable" (D4). DRAFT/APPROVED/REJECTED → the existing `InvalidApprovalStateError`.
3. compute `_active_positions` and the next status the SAME way `approve_department` does.
   If position 1 is the only active position, the next status would be `APPROVED` → **refuse**
   (`StepNotOverridableError`): an override may never finalise a budget (ADR-0027). This is
   reachable in real data — a ฝ่าย whose chain collapsed to `[manager]` only.
4. reuse `_advance_one_step` unchanged (same conditional UPDATE race guard, same
   `approverN_actioned_at` stamp, same log+commit), with
   `action=ACTION_ADMIN_STEP_OVERRIDE`, `by_empcode=resolve_submitter(admin_email)[0]`
   (**may be None** — jakkaritw has no `v_employee_budget_01` row; that is fine and expected),
   `by_email=admin_email` (the real human, never a `system:` literal),
   `comment="admin step override (ADR-0027)"`.

Authorization lives in the router, not here (mirrors how `submit_department` takes `scope`).

### Router — `backend/app/routers/approval.py`

`POST /approval/override-step`, body `{department, fiscal_year}`:

- resolve scope; **403 unless `scope.is_admin`** — this is the only gate (D3: no waiting
  period, no reason field)
- call `admin_override_step`
- map `StepNotOverridableError` → 409 with a Thai detail the UI can show directly
- notify (below) through the same `_notify_after_transition` try/except posture: **a mail
  failure must never fail the action**, it only sets `notification_warning`

## 4. Part C — notification #6 (`backend/app/notifications.py`)

```
def notify_step_overridden(conn, *, department, fiscal_year, submitter_email,
                           skipped_approver_empcode, admin_email, dry_run, settings=None)
```

- To = `submitter_email` (the value frozen on the row — same source `notify_approved` uses)
- cc = the **skipped** approver's email, resolved from `skipped_approver_empcode` via
  `lookup_email_by_empcode`, reusing `_resolve_approver1_cc`'s skip rules: no cc when the
  empcode is blank, the lookup finds nothing, or cc == To; a cc lookup failure is swallowed and
  the To send still goes out
- Thai subject in the house style, e.g.
  `ดำเนินการแทนผู้อนุมัติ งบประมาณของฝ่าย {department} ปีงบประมาณ {fiscal_year}`
- body: ฝ่าย, ปีงบประมาณ (label year via `_year_phrase`), ผู้ที่ถูกข้าม, ผู้ดำเนินการแทน
  (`admin_email`), วันเวลา, สถานะปัจจุบัน (who it is waiting on now) + deep link (ADR-0016)
- wire it into `_notify_after_transition` as its own `action == "override_step"` branch — the
  next approver ALSO still gets their normal `notify_turn` "ถึงตาคุณ" mail, so an override
  produces exactly two mails

## 5. Part D — frontend (`frontend/src/approval/ApprovalActionBar.tsx` + `api/approval.ts`)

**ONE button, not two** (jakkaritw 2026-08-01, revising Claude's first draft which added a
second button): the admin sees the same **อนุมัติ** button everyone else sees. Only the confirm
dialog changes, and the split lives server-side where the user never sees it.

- `overrideStep(department, fiscalYear)` in `api/approval.ts` hitting the new endpoint —
  a separate client function, but NOT a separate button
- the existing อนุมัติ button becomes visible when `status.can_act` **OR**
  (`scope.isAdmin && status === 'PENDING_APPROVER1'`)
- on click, branch on `status.can_act`:
  - `can_act === true` → existing confirm text, call `approveDepartment` (unchanged path)
  - `can_act === false` → **override confirm**, call `overrideStep`. Text must NAME the person
    being skipped and state both consequences, e.g.
    `⚠️ คุณกำลังอนุมัติแทน {ชื่อผู้อนุมัติขั้นที่ 1} — ระบบจะบันทึกว่าคุณกดแทน และส่งอีเมลแจ้งผู้กรอกงบ พร้อมสำเนาถึง {ชื่อเดียวกัน} · ยืนยันหรือไม่?`
    The dialog is the ONLY guard against an accidental override (D3 removed the stale-gate and
    the reason field), so the skipped person's name is mandatory in it — never a generic
    "ยืนยันการอนุมัติ".
  - To render the name, the status payload needs the current approver's display name, not just
    `current_approver_empcode`. If it is not already exposed, add it to
    `ApprovalStatusState` (server-side lookup, same source as the mail's cc resolution) rather
    than doing a second client fetch.
- on 409, surface the server's Thai detail as-is
- after success, refetch status + the รออนุมัติ badge exactly like approve/reject do

**Why the backend still keeps two endpoints and two log actions** (invisible to the user, do
not "simplify" it away): a normal approve may finalise `APPROVED` and is authorized as the
frozen occupant; an override may never finalise, is admin-only, position-1-only, and must be
distinguishable in `approval_log` forever — one merged endpoint would make the audit trail
unable to answer "was this step actually reviewed by its owner?".

## 6. Part E — tests (mocked; no live DB, no real mail)

`tests/test_approval.py`
1. override on `PENDING_APPROVER1` with an active position 2 → status becomes
   `PENDING_APPROVER2`, `approver1_actioned_at` stamped, one `ADMIN_STEP_OVERRIDE` log row
   carrying the admin's email
2. override when position 1 is the ONLY active position → raises, status unchanged, **no log
   row**, never `APPROVED`
3. override on `PENDING_APPROVER2` / `PENDING_APPROVER3` → raises (D4)
4. override on DRAFT / APPROVED / REJECTED → `InvalidApprovalStateError`
5. concurrent-change guard: underlying status moved → `ConcurrentApprovalError`, no log row
6. admin with no employee row → log written with `by_empcode = None`, `by_email` = real email
7. **removal regressions**: `auto_escalate_step`, `is_step_stale`, `AUTO_ESCALATE` no longer
   importable from `app.approval` (assert `ImportError`/`AttributeError`)

`tests/test_approval_router.py`
8. non-admin caller → 403 (filler AND a step-2 approver who is not on the allowlist)
9. admin caller → 200 and `notify_step_overridden` called with the skipped approver's empcode
10. notification raises → action still succeeds, `notification_warning` set

`tests/test_notifications.py`
11. To = submitter, cc = skipped approver's email; cc dropped when unresolvable / equal to To;
    To still sent when the cc lookup throws
12. body carries ฝ่าย, label year, both names, and the deep link

`tests/test_jobs_send_reminders.py`
13. turn reminders still fire at 7/14/21/28+ days with NO upper bound and no extra cc (D6) —
    a "still due at day 120" case, so nobody reintroduces a stop condition later

## 7. Close-out

1. Full mocked suite green (baseline today: 756 passed; the 4 `tests_data_sync` failures are
   another lane's fixture rename, ignore them).
2. Gate 06+07+08 — 07 matters here: the endpoint changes who may move money-bearing state.
   Check the 403 path with a non-admin approver, and that no PII beyond work emails reaches
   the log or the mail body.
3. One commit: backend + frontend + workflow + tests + `.claude/plan.md` tick. The four docs in
   the header are already committed by the grilling session.
4. Report to jakkaritw: confirm D4's hard lock (his to veto), plus the two accepted risks from
   ADR-0027 — a stuck ฝ่าย now resolves only if a human notices, and overrides carry no
   recorded reason.
5. **Holds unchanged**: no `NOTIFICATIONS_DRY_RUN` flip, no prd deploy without approval. The
   nightly cron stays as it is (dry-run preview).
