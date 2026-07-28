# Phase 2 production verification results — 2026-07-28

Target: `https://cman-budget-web-prd.kindstone-f34836dd.southeastasia.azurecontainerapps.io` (Easy Auth ON).
Persona: jakkaritw@chememan.com (admin, fills no CC) via AppServiceAuthSession cookie.
Sentinel: every app write used `fiscal_year = 2099`; cleanup verified 0 rows in the 5 budget
tables after each run (`frontend/e2e/live_db.py cleanup`). Harnesses: `setup/phase2_harness_abc.py`,
`setup/phase2_harness_dkl.py` (re-runnable). Section F skipped per jakkaritw (real approver personas).

## A. Write path & validation / B. Concurrency / C. Subforms

| item | result | evidence |
|---|---|---|
| P2-A1 | PASS | PUT -> 200, SQL m01=123.45, GET /budget m01=123.45 |
| P2-A2 | PASS | 2x100.005 -> m01=100.00 m02=100.00, total_year=200.00 == SUM exact in SQL |
| P2-A3 | PASS | negative -> 400; 12x9.9e15 -> 400 data_overflow (SQL 22003, no silent truncation) |
| P2-A4 | PASS | unknown GL / unknown CC / excluded CC(CMKK01) -> all 400 |
| P2-A5 | PASS | special-GL direct edit -> 400; per-diem direct edit -> 400 |
| P2-A6 | PASS | DELETE /rows -> 200, row + detail lines gone in SQL |
| P2-A7 | PASS | dims persisted (dept/gl_group/Thai gl_name); re-create same key -> 409 |
| P2-A8 | PASS | Thai remark round-trips identically in SQL + API, no '?' mojibake |
| P2-B1 | PASS | same-token concurrent PUTs -> [200, 409] |
| P2-B2 | PASS | different-row concurrent PUTs -> [200, 200] |
| P2-B3 | FAIL | concurrent submits -> [200, 502] — PRODUCT BUG: _admin_direct_approve INSERT (approval.py:655) does not map IntegrityError -> ConcurrentApprovalError (unlike _insert_new_approval_row:498); loser sees 502 "Database unavailable". DB end-state correct (1 status + 1 log row). |
| P2-B4 | PASS | retry submit -> 409, still exactly 1 approval_status + 1 approval_log |
| P2-B5 | PASS | repeat POST same client_token -> same trip_id, 1 trip in SQL |
| P2-B6 | DEFER | admin bypasses department lock by design (ADR-0012) — needs non-admin filler persona (section F) |
| P2-C1 | PASS | all 6 special groups add/edit/delete, parent total == SUM(detail) in SQL every step |
| P2-C2 | PASS | bad ประเภทการรับรอง / bad สถานที่ใช้งาน / empty ทะเบียนรถ -> all 400 invalid_meta |
| CLEANUP | PASS | 0 rows at fiscal_year=2099 in all 5 tables (pre + post run) |

## D. Attachments

| item | result | evidence |
|---|---|---|
| P2-D1 | PASS | upload pdf -> 200, xlsx -> 200, list -> 200 ['-..-x.pdf', 'TEST-PROBE-file.pdf', 'TEST-PROBE-file.xlsx'], download-url fetch (no auth) -> 200, content matches=True |
| P2-D2 | PASS | .exe -> 400, 11MB -> 413 ({"detail":"request body is 11534727 bytes -- exceeds the 104), CON.pdf -> 400 ({"detail":"filename 'CON.pdf' uses a reserved device name (C), ../../x.pdf -> 200 stored-as='-..-x.pdf', nothing outside folder=True |
| P2-D3 | PASS | year 2098 (no folder) -> 502 {"detail":"the folder 'เอกสาร ฝ่าย/Accounting Division/2098' does not exist yet — ask the admin to create it f |
| P2-D4 | PASS | re-upload same name -> 200, list entries with that name=1, content now v2=True / CONFIRMED: overwrite semantics, no delete endpoint in routers/attachments.py |
| P2-D5 | PASS | fetch WITHOUT any auth -> 200: CONFIRMED pre-authenticated Graph @microsoft.graph.downloadUrl (host=chememan.sharepoint.com, ~minutes-lived by Graph design — expiry wait not done; PDPA note for the user guide: never forward the link) |
| P2-D6 | DEFER | see-only/out-of-scope upload+list 403 — needs a second persona (section F batch) |

## E. RLS / roles / admin

| item | result | evidence |
|---|---|---|
| P2-E1 | DEFER | no-scope persona — needs a real no-scope user (section F batch) |
| P2-E2 | DEFER | see-only persona — needs a real see-only user (section F batch) |
| P2-E3 | DEFER | fill-scope cross-CC 403 — needs a real filler persona (section F batch) |
| P2-E4 | PASS | /scope: is_admin=True fill=[] see=[] / grid admin_view=true -> 200 1005 rows, toggle-off -> 0 rows / edit of non-filled CC 10AC010000 -> 200 (A-C harness wrote this CC all day with an empty Fill scope) |
| P2-E5 | PASS | template=ADMIN setup -> 200; admin submit while PENDING_APPROVER1 -> 409 body={"detail":"Accounting Division/2099 is PENDING_APPROVER1 — mid-approval; admin cannot admin-submit until it is rejected or the sub / status after=PENDING_APPROVER1 (unchanged), approval_log rows=0 — MidChainAdminOverwrite guard holds, no silent overwrite |
| P2-E6 | DEFER | GL_EDIT_BY flip is a planned soft-launch moment — harness must not flip prod config |
| P2-E7 | DEFER | dept-picker rule is frontend behavior (1 ฝ่าย auto-select / >1 blank / deep-link wins) — browser check; API-side note: jakkaritw's scope has 0 fillable depts so picker never renders for admin |

## G. Notifications & email quality

| item | result | evidence |
|---|---|---|
| P2-G1 | PASS | jakkaritw verified 2026-07-28: all 4 types render correctly in Outlook desktop + web + mobile — Thai subjects clean, table/borders/colors/signature intact |
| P2-G2 | DEFER | Safe Links/ATP rewrite — click the deep link FROM THE REAL MAILBOX (one of the 4 probe emails) and confirm it lands on TEST-PROBE/2099 still authenticated |
| P2-G3 | DEFER | Inbox-not-Junk + sender display name — check the 4 probe emails' placement in jakkaritw@chememan.com (and one strict-filter approver at go-live) |
| P2-G4 | COVERED | notification failure never fails the action — unit: test_approval_router.py::test_submit_notification_failure_never_fails_the_request and ::test_approve_final_step_notification_failure_never_fails_the_request (response carries notification_warning, action commits) |
| P2-G5 | PASS | 4 bodies built via the real notify_* path: subjects=['รอการอนุมัติ งบประมาณของฝ่าย TEST-PROBE (ทดสอบระบบ) ปีงบประมาณ 2099', 'ถูกตีกลับ งบประมาณของฝ่าย TEST-PROBE (ทดสอบระบบ) ปีงบประมาณ 2099', 'ได้รับการอนุมัติ งบประมาณของฝ่าย TEST-PROBE (ทดสอบระบบ) ปีงบประมาณ 2099', 'แจ้งเตือน: ยังไม่ได้ส่งงบประมาณ ปีงบประมาณ 2099'] / leaks=none — bodies contain dept name/year/submitter/deep-link only (cross-checked against 114 real department names + amount regex) |

## H. Scheduled jobs (dry-run only)

| item | result | evidence |
|---|---|---|
| P2-H1 | PASS | jobs.send_reminders dry-run rc=0 (no-op expected: reminder_date=2026-10-15 not reached) :: 2026-07-28 23:33:17,047 INFO jobs.send_reminders: starting send_reminders fiscal_year=2027 dry_run=True notifications_dry_run=True // 2026-07-28 23:33:19,210 INFO jobs.send_reminders: fiscal_year=2027: reminder_date not yet reached (or no submission_deadline row configured) � nothing to do |
| P2-H2 | PASS | jobs.auto_submit dry-run rc=0 (no-op expected: 2027 deadline=2026-10-31 not reached) :: 2026-07-28 23:33:19,864 INFO jobs.auto_submit: starting auto_submit fiscal_year=2027 dry_run=True notifications_dry_run=True // 2026-07-28 23:33:22,026 INFO jobs.auto_submit: fiscal_year=2027 is not yet past its submission deadline (or no deadline row configured) � nothing to do |
| P2-H3 | PASS | jobs.auto_escalate dry-run rc=0 (no-op expected: no PENDING steps at 2027) :: 2026-07-28 23:33:22,788 INFO jobs.auto_escalate: starting auto_escalate fiscal_year=2027 dry_run=True notifications_dry_run=True // 2026-07-28 23:33:25,099 INFO jobs.auto_escalate: fiscal_year=2027: 0 stale (>=30d) PENDING_* row(s) found � nothing to escalate |
| P2-H4 | PASS | repersist_perdiem_fx dry-run rc=0 :: 2026-07-28 23:33:25,820 INFO jobs.repersist_perdiem_fx: starting repersist_perdiem_fx fiscal_year=2027 dry_run=True // 2026-07-28 23:33:28,196 INFO jobs.repersist_perdiem_fx: fiscal_year=2027 fx=33.0000: 0 trip(s) found, dry_run=True // 2026-07-28 23:33:28,197 INFO jobs.repersist_perdiem_fx: fiscal_ / --run on a controlled year: DEFERRED pending jakkaritw's year choice |
| P2-H5 | COVERED | mid-run failure mode (from code): every job commits per-department/per-trip (auto_submit/auto_escalate: submit_department & co. commit internally per dept; a crash leaves earlier units each fully consistent — status row + log row written in the same commit — never a half-written unit); send_reminders is send-only (no DB writes); repersist_perdiem_fx batches commits per chunk and is re-runnable (idempotent re-derive). Unit: test_jobs_auto_submit.py::test_notify_failure_does_not_block_other_departments |
| P2-H6 | PASS | cron still commented out in budget-automations.yml (True) — workflow_dispatch only; enable only after H1-H5 pass on a controlled year + jakkaritw approval |

## I. Deadline, lock & timezone

| item | result | evidence |
|---|---|---|
| P2-I1 | PASS | deadline=today(BKK 2026-07-28): edit -> 200 (inclusive day OK), submit -> 403 (in-cycle branch) / deadline=yesterday: admin edit -> 200, admin submit -> 200 action=ADMIN_OVERRIDE_DEADLINE (post-deadline override door — proves bangkok_today() flip) |
| P2-I3 | PASS | admin edit past deadline -> 200 (ADR-0012) / non-admin past-deadline edit -> 403 past_deadline: NEEDS filler persona (unit-covered in test_write_model past_deadline tests) — partial DEFER |
| P2-I1-cleanup | PASS | temporary submission_deadline 2099 row removed: True |
| P2-I2 | PASS | 2099 had NO submission_deadline row during the whole A-C harness and every write succeeded (missing row = OPEN, never silently locked); reminders for it never fire (send_reminders gates on reminder_date, missing row -> no-op, jobs/send_reminders.py) |
| P2-I4 | DEFER | budget_closing_date master-editor cross-check — manual, one-truth review with jakkaritw |

## J. Data integrity & control numbers

| item | result | evidence |
|---|---|---|
| P2-J1 | PASS | real-year control numbers identical before/after: {"budget.pending_budget": {}, "budget.pending_budget_detail": {}, "budget.budget_trip": {}, "budget.approval_status": {}, "budget.approval_log": {}} / NOTE: budget.* is GENUINELY EMPTY for all real years (pre-UAT) — '0 = 0' caveat from the plan applies; this snapshot doubles as the P0-35 baseline |
| P2-J2 | DEFER | post-repersist control-number reconcile — tied to the deferred P2-H4 --run |
| P2-J3 | PASS | Quicklime Production (KK) planning-2027 grid: 41 rows x 12 SAP months = 492 cells compared (gold fetch_sap_actuals FY2026 — same source query as the API, transport/merge fidelity check; the 2026-07-22 independent 91,858-cell method covered query correctness) + pending layer: mismatches=0 [] |
| P2-J4 | PASS | 10OS011400 has 3 mapping rows (fillers: ['jintanapo@chememan.com', 'khattariyas@chememan.com', 'taweesaks@chememan.com'], one dept 'Environment (RY)'); no double counting possible: grid sums come from budget.pending_budget keyed (cc,gl,year) and NEVER join cc_filler_map; cc_filler_map is only read with SELECT DISTINCT for scope/approval (pending rows for this CC today: 0) |
| P2-J5 | PASS | intentionally hidden on the 2027 grid (SAP FY2026): 0 net-zero (cc,gl) keys (reversal pairs, no board/pending row — contribute 0 to every subtotal, plan/hide-netzero-gl-rows.md) + 874 keys whose GL is absent from the gl master (hidden for EVERY caller incl. admin, read_model.py GL-master rule). These are NOT missing money — do not re-open as a bug. |

## K. Performance & resilience

| item | result | evidence |
|---|---|---|
| P2-K1 | PASS | staging (min-replicas 0): first request after idle -> 401 in 0.3s (likely warm), immediate second -> 401 in 0.1s; an earlier same-day run caught a genuine cold spin-up: 25.2s first request vs 0.1s warm / cookie is prd-app-reg so stg auth 401s — TTFB measured at the Easy Auth boundary; app-level msodbcsql HYT00 watch NOT verifiable here (needs a stg-app cookie) |
| P2-K2 | PASS | Quicklime Production (KK) (largest dept, 42 CC mapping rows): 41 grid rows, 5 runs p50=1.19s p95(max)=1.39s vs 3s Appendix-E threshold — times=['1.39', '1.05', '1.29', '1.19', '0.90'] |
| P2-K3 | COVERED | multi-replica optimistic lock — lock is DB-grain (AND _updated_at=? in SQL, zero per-process state), proven against prod by P2-B1/P2-B2 in the A-C harness |
| P2-K4 | PASS (revised threshold) | First run (min-replicas 1): 10 concurrent GETs, codes=[200], min=7.01s max=9.81s — exceeded the original 3s (~7x degradation). After scaling prd to **min-replicas 2**: 3 rounds × 10 concurrent, all 200, means 5.1–5.9s, max 7.5s. jakkaritw decided the two-tier threshold (2026-07-28): single-user ≤3s (K2 passes at p95 1.39s) + **10-concurrent ≤8s → PASS**. Post-UAT backlog: SAP-actuals caching + DB connection pooling (the remaining cost is downstream of the replicas). |
| P2-K5 | PASS | PUT with bogus cookie -> 401 content-type='' body[:120]='' / non-HTML response — check apiFetch maps this to the re-login path |
| P2-K6 | DEFER | browser/viewport matrix (Edge/Chrome desktop + phone-sized approver viewport) — manual |
| P2-K7 | COVERED | network-flaky mid-save — Thai  เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ + retry-no-duplicate: unit (api/client.test.ts) + e2e edge-states + P2-B4/B5 idempotency evidence |
| P2-K8 | DEFER | 1-hour long-session token-refresh soak — manual |

## L. Cleanup & evidence

| item | result | evidence |
|---|---|---|
| P2-L1 | PASS | live_db cleanup rc=0 {"fiscal_year": 2099, "remaining": {"budget.pending_budget_detail": 0, "budget.budget_trip": 0, "budget.pending_budget": 0, "budget.approval_log": 0, "budget.approval_status": 0}} / real-year control numbers still match the pre-run baseline: True |
| P2-L2 | PASS | SharePoint files left in เอกสาร ฝ่าย/Accounting Division/2099 (scratch folder, created by this harness): [('-..-x.pdf', 538), ('TEST-PROBE-file.pdf', 548), ('TEST-PROBE-file.xlsx', 535)] — they STAY per the scratch-folder decision (no delete endpoint exists); jakkaritw may delete them in the UI/SharePoint. The 2098/CON.exe/11MB rejects never landed. |
| P2-L3 | PASS | NO real-year rows written or left by this harness: all app writes used fiscal_year=2099 (verified by P2-J1/P2-L1 control numbers); the only real-scope touch was the temporary dbo.submission_deadline 2099 row (deleted, P2-I1-cleanup) and read-only dry-run jobs on 2027. |
| P2-L4 | PASS | full results table written to docs/test/phase2-results-2026-07-28.md (A-L incl. F=DEFER) — tracker verdict update remains a jakkaritw action |

## F. Approval loop — SKIPPED

| item | result | evidence |
|---|---|---|
| P2-F1..F12 | DEFER (whole section) | SKIPPED per jakkaritw — full approval loop with real approver personas on a real pilot ฝ่าย/year; scheduled separately with real users |

## Product bugs found (recorded, NOT patched)

1. **P2-B3 — concurrent submit loser gets 502 instead of 409.** `_admin_direct_approve`'s INSERT
   (`backend/app/approval.py:655`) does not catch `pyodbc.IntegrityError`; unlike
   `_insert_new_approval_row` (:498) it never maps the PK violation to `ConcurrentApprovalError`,
   so the router's generic `pyodbc.Error` handler returns 502 "Database unavailable". Reproduced
   deterministically twice on prod (barrier-synced concurrent submits). DB end-state stays correct.

## Open items for the human/persona batch (with section F)

- P2-B6, P2-D6, P2-E1/E2/E3, P2-I3 non-admin half — need filler / see-only / no-scope personas.
- P2-E6 — GL_EDIT_BY soft-launch flip (planned moment, not from a harness).
- P2-E7, P2-K6, P2-K8 — browser/viewport/long-session manual checks.
- P2-G1/G2/G3 — jakkaritw's mailbox: 4 probe emails (rendering, Safe Links click-through, Junk placement).
- P2-H4 --run + P2-J2 — pending jakkaritw's controlled-year choice.
- P2-H6 — enable cron only after H1–H5 pass + approval.
- P2-I4 — budget_closing_date master-editor cross-check (manual).
