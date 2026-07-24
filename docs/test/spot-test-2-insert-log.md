# SPOT TEST #2 — APPROVER JOURNEY — insert log

Date: 2026-07-23 · Lane: cost center 10IT012000 (ฝ่าย Solution Delivery) FY2027 + /approval/* only
DB: real Fabric SQL (APP_ENV=local). All writes via the app's own API except DB-verified cleanup DELETEs.

## PRE-FLIGHT findings

### State machine (backend/app/approval.py)
- Unit of approval = `(department, fiscal_year)` — NOT cost center (ADR-0008). Dept here = `Solution Delivery`.
- States: `DRAFT` → `PENDING_APPROVER1` → `PENDING_APPROVER2` → `PENDING_APPROVER3` → `APPROVED`; `REJECTED` from any PENDING_*; resubmit from REJECTED restarts the chain (`RESUBMIT`).
- Chain (ADR-0006): 3 FIXED positions — pos1 = submitter's manager (frozen as `approver1_empcode` at submit, resolved from `dbo.v_employee_budget_01.manager_employee_code`; fallback = Nipaporn), pos2 = Nipaporn (`NIPAPORN_EMPCODE='101032'`, compile-time), pos3 = Waraporn (`WARAPORN_EMPCODE='100427'`). Self-skip + dedup, never renumbered.
- Tables: `budget.approval_status` (1 row per dept/FY; INSERT on first submit, conditional UPDATEs after), `budget.approval_log` (append-only; SUBMIT/RESUBMIT/APPROVE/REJECT + AUTO_* job actions).
- Error map (routers/approval.py + approval.py): not_filler 403 · invalid_approval_state 409 · record_not_found 404 · not_current_approver 403 · missing_reject_reason **400** (blank string; a MISSING `reason` key is Pydantic 422) · not_authorized_to_view 403 · concurrent 409.
- Write lock (write_model.py `_ensure_department_not_locked`): status in PENDING_*|APPROVED → non-admin PUT/DELETE rows 403 `department_locked`. Admin bypasses. DRAFT/REJECTED/no-row = editable.
- Auth: header `x-ms-client-principal-name` wins over DEV_AUTH_EMAIL fallback (auth.py) → persona impersonation via header works locally.

### EMAIL SAFETY (hard gate) — SAFE, evidence:
1. `backend/.env` has NO `NOTIFICATIONS_DRY_RUN` key (full key list checked) → `Settings.notifications_dry_run` = default **True** (config.py:64 "fail-safe default TRUE").
2. `notifications.send_mail(dry_run=True)` → builds payload + logs, "ZERO HTTP calls (no token fetch, no sendMail POST)" (notifications.py:129-131).
3. Router passes the setting straight through (routers/approval.py:79,84,90) and wraps notify in try/except — a notify failure can never fail the request (sets `notification_warning` only).
4. Conclusion: submit/approve/reject from this local run CANNOT send real email. Proceed.

### Cleanup precedent (docs/test/ui-test-results-2026-07-22.md §"ข้อมูลทดสอบ & การเก็บกวาด")
Delete every row created for CC 10IT012000/FY2027 in `budget.pending_budget`, `budget.pending_budget_detail`, `budget.budget_trip`, and for (Solution Delivery, 2027) in `budget.approval_status` + `budget.approval_log`. End state = 0 rows in all of those.

### Known limitation from 2026-07-22 cycle (affects UI step)
Approvers pos2/pos3 (Nipaporn/Waraporn) do NOT have 10IT012000 in See scope → dept never shows in their ฝ่าย-picker; approval actions had to be done via API. `GET /approval/status` also 403s for non-admin callers with no See scope on the dept (B1 gate).

## DB DISCOVERY (pre-write)

- Dept `Solution Delivery` has exactly ONE cost center: `10IT012000` (cc_filler_map) → dept-scoped approval stays inside this lane. Filler on the map: suchanyay@chememan.com.
- Employee view (`dbo.v_employee_budget_01`): suchanyay=`101159`, manager=`101622`=**arthids@chememan.com**. Constants: pos2 Nipaporn=`101032`=nipapornt@, pos3 Waraporn=`100427`=warapornt@. No self-skip/dedup (submitter 101159 ≠ any occupant) → **predicted chain: 1=arthids → 2=nipapornt → 3=warapornt** (all 3 positions active).
- Pre-state: approval_status=0, approval_log=0 rows for (Solution Delivery, 2027); approval_log whole table=0. pending_budget_detail=0, budget_trip=0 for CC/FY.
- **ANOMALY-A (pre-existing row):** `budget.pending_budget` already had **1 row** for 10IT012000/2027 BEFORE this round: gl `6210900060`, all months 0, total 0, template USER, remark NULL, _user `suchanyay@chememan.com` (the DEV_AUTH_EMAIL fallback identity), _updated_at 2026-07-23 10:15:56 (~40 min before this session; brief said state was verified 0 rows). Zero-amount, so it cannot distort amounts; left untouched during the journey, deleted at cleanup to reach the mandated 0-row end state, and flagged in the report.
- `dbo.submission_deadline` FY2027: deadline_date=2026-10-31 > today 2026-07-23 → cycle OPEN, normal submit path available.

## JOURNEY LOG

### Step 1 — setup rows (as suchanyay, PUT /budget/rows)
- INSERT budget.pending_budget: (10IT012000, 5211400040, 2027) m01=311 m02=311 total=622 remark='spot-test 2' — HTTP 200, updated_at 2026-07-23T11:03:07Z
- INSERT budget.pending_budget: (10IT012000, 5210600010, 2027) m03=322 m04=322 total=644 remark='spot-test 2' — HTTP 200, updated_at 2026-07-23T11:03:28Z
- DB verify: 3 rows total for CC/FY (my 2 + ANOMALY-A zero row 6210900060), amounts/remark/_user correct.

### Step 2 — submit (POST /approval/submit as suchanyay)
- HTTP 200 → status=`PENDING_APPROVER1`, current_position=1, current_approver_empcode=`101622` (arthids), can_act=false (for submitter), notification_warning=null.
- INSERT budget.approval_status: (Solution Delivery, 2027, PENDING_APPROVER1, submitter 101159/suchanyay, submitted_at 2026-07-23 11:04:07 UTC, approver1_empcode=101622).
- INSERT budget.approval_log: SUBMIT by 101159/suchanyay, previous=NULL → new=PENDING_APPROVER1, comment NULL, action_at = submitted_at.
- LOCK PROBE: PUT a 3rd row (5210600020) as suchanyay → **HTTP 403** `Solution Delivery/2027 is PENDING_APPROVER1 — mid-approval or approved, editing is locked`. Lock applies immediately; probe row NOT inserted.

### Step 3 — chain-order visibility (GET /approval/pending-for-me?fiscal_year=2027, at PENDING_APPROVER1)
- arthids (current L1): `["Solution Delivery"]` ✅
- nipapornt (L2): `[]` ✅ · warapornt (L3): `[]` ✅ · suchanyay (filler): `[]` ✅

### Step 4 — wrong-actor approve guards (no writes, no log rows created)
- warapornt (non-current approver) approve → **403** `warapornt@chememan.com is not the current approver for Solution Delivery/2027`
- suchanyay (filler) approve → **403** same shape
- adirekn@chememan.com (unrelated, in employee view) approve → **403** same shape

### Step 5 — reject path
- Missing `reason` key → **422** Pydantic `Field required` (loc body.reason).
- Blank/whitespace `reason:"   "` → **400** `reject_reason is required` (MissingReasonError). NOTE: brief expected 422 for blank — actual blank-STRING is a 400 business error; 422 only for a MISSING field. No state change, no log row from either failure.
- Real reject by arthids → **200**, status=REJECTED, rejected_by=101622, reason stored. INSERT approval_log: REJECT (PENDING_APPROVER1→REJECTED, comment=reason).
- Editability restored: suchanyay PUT 5211400040 (update) → **200**.

### Step 6 — resubmit + full chain (INSERT approval_log per transition)
- suchanyay resubmit → **200** PENDING_APPROVER1 (all actioned_at + reject fields cleared). Log: RESUBMIT (REJECTED→PENDING_APPROVER1).
- arthids approve → **200** PENDING_APPROVER2 (approver1_actioned_at stamped). pending-for-me flips: arthids `[]`, nipapornt `["Solution Delivery"]`, warapornt `[]`.
- nipapornt approve → **200** PENDING_APPROVER3. pending-for-me: nipapornt `[]`, warapornt `["Solution Delivery"]`.
- warapornt approve (final) → **200** APPROVED (approver3_actioned_at stamped). pending-for-me: empty for ALL.
- **Exact chain: L1 arthids (101622, direct manager) → L2 nipapornt (101032, fixed) → L3 warapornt (100427, fixed).** Matches prediction from discovery.

### Step 9 — UI check (sequenced mid-chain at PENDING_APPROVER1, before any approve; Playwright, deep-link /?dept=Solution%20Delivery&year=2026, header injected only for 127.0.0.1)
- arthids (CURRENT): status chip `รออนุมัติ · ขั้น 1 (ผู้บังคับบัญชาสายตรง)`; approve-btn=1, reject-btn=1, submit-btn=0, locked-hint=0 ✅
- suchanyay (NON-current filler): same chip; approve-btn=0, reject-btn=0, submit-btn=0, locked-hint `ส่งแล้ว — แก้ไขไม่ได้จนกว่าจะถูกตีกลับ`=1 ✅

### Step 7 — post-approval state (after final approve)
- `budget.pending_budget`: my 2 rows STILL THERE, byte-identical (amounts, remark, _updated_at unchanged) — approving never mutates/moves/flags money rows (ADR-0013). detail/trip tables: 0 rows.
- GET /budget?year=2027&cost_center=10IT012000 (as suchanyay): 10 rows, 3 layers per row — `sap` (actuals), `board`, `pending` (my 311/322 values intact). **Observation: `editable:true` on rows even while APPROVED** — read_model.py:364 sets `editable = admin_wide or cc in fill_ccs` (scope-only, deliberately lock-agnostic); the approval lock is enforced ONLY on the write path.
- Filler write-lock under APPROVED: PUT new row → **403** `Solution Delivery/2027 is APPROVED — mid-approval or approved, editing is locked` (frontend maps this detail to Thai `ฝ่ายนี้อยู่ระหว่างรออนุมัติ/อนุมัติแล้ว — แก้ไขไม่ได้`).

### Step 8 — audit trail (budget.approval_log, 6 rows, ordered)
1. SUBMIT suchanyay(101159) 11:04:07 None→PENDING_APPROVER1
2. REJECT arthids(101622) 11:06:56 PENDING_APPROVER1→REJECTED comment='spot-test 2: figures need review before approval'
3. RESUBMIT suchanyay(101159) 11:08:24 REJECTED→PENDING_APPROVER1
4. APPROVE arthids(101622) 11:13:24 PENDING_APPROVER1→PENDING_APPROVER2 comment='spot-test 2 L1 ok'
5. APPROVE nipapornt(101032) 11:13:45 PENDING_APPROVER2→PENDING_APPROVER3 comment='spot-test 2 L2 ok'
6. APPROVE warapornt(100427) 11:14:03 PENDING_APPROVER3→APPROVED comment='spot-test 2 L3 final'
- Failed guards (wrong-actor, blank-reject) wrote ZERO log rows. Final approval_status: APPROVED, all 3 actioned_at stamped.

## CLEANUP

Executed 2026-07-23 ~11:20 UTC via DB DELETE (the sanctioned cleanup path; every DELETE logged here):

| Table | Filter | Deleted |
|---|---|---|
| budget.pending_budget | CC 10IT012000, FY2027, gl IN (5211400040, 5210600010) — the 2 setup rows | 2 |
| budget.pending_budget | CC 10IT012000, FY2027, gl 6210900060, total=0, remark NULL — ANOMALY-A zero row | 1 |
| budget.approval_status | dept Solution Delivery, FY2027 | 1 |
| budget.approval_log | dept Solution Delivery, FY2027 | 6 |

Post-cleanup SELECT verification — **all 0**:
- budget.pending_budget (CC/FY): 0 · budget.pending_budget_detail (CC/FY): 0 · budget.budget_trip (CC/FY): 0
- budget.approval_status (dept/FY): 0 · budget.approval_log (dept/FY): 0 · budget.approval_log (WHOLE TABLE): 0 (back to its pre-test state)

Temp scripts removed: backend/spot2_discover.py, backend/spot2_cleanup.py, frontend/spot2_ui.mjs. The only artifact kept is this log.
