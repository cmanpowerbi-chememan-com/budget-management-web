## 1. Deployment ground truth (verified via `az`, 2026-09-06)

| | staging | production |
|---|---|---|
| Container | `cman-budget-web-stg` | `cman-budget-web-prd` |
| Active revision | `cman-budget-web-stg--0000068` (created 2026-09-05T17:23Z; env-only bump 09-06) | `cman-budget-web-prd--0000033` (created 2026-09-05T18:35Z) |
| Image | `cmanbudgetacr.azurecr.io/budget-web:72affd9` | `cmanbudgetacr.azurecr.io/budget-web:72affd9` |
| Traffic | 100% | 100% |
| `FABRIC_SQL_SERVER` | `v5o4qez3u4cupase7cogkwvyke-bby6xlm3ncqexly4ozejod2vqe.database.fabric.microsoft.com` | **identical string** |
| `FABRIC_SQL_DATABASE` | `fabric_sql_database-a42ef9f3-f190-464a-8d5e-c0d41ef9ce42` | **identical string** |
| `APP_ENV` | `local` | `production` |
| `NOTIFICATIONS_DRY_RUN` | `false` (real mail) | `false` |
| `ADMIN_EMAILS` | `jakkaritw@,nipapornt@,warapornt@` | same (laddawank is **not** admin) |
| Cookie lifetime | **no `cookieExpiration` block at all** → Container Apps default ≈8h | `14:00:00` |
| `SIT_IMPERSONATE` | `jakkaritw@chememan.com:pornthipp,laddawank,nipapornt,warapornt,arthids` (5 targets) | not set |
| `DEV_AUTH_EMAIL` | `pornthipp@chememan.com` | not set |

**Both envs run the same image tag `72affd9`.** So *every* user-visible change since SIT is LIVE on BOTH. The memory note "other-travel GL move — PRD NOT deployed, prd still 55e0753" is **STALE** — prd went to `72affd9` (which contains `bab089b`) on 2026-09-05 18:35Z; ticket `T04-prd-deploy.md` is `[CLOSED 2026-09-06]`.

`git ls-remote origin main` = local `HEAD` = `62d42a7`. HEAD is 3 commits ahead of the deployed tag, all three docs/chore (`b16119c`, `6cd0a8c`, `62d42a7`) → **deployed code == committed code**. No `frontend/src`, `backend/app` or `frontend/e2e` file is dirty (the 53 dirty entries are deleted design mockups/spec artifacts).

**Hazard for `DEV_AUTH_EMAIL`**: `backend/app/auth.py:45` — `if settings.is_local and settings.dev_auth_email: return settings.dev_auth_email`. Staging has `APP_ENV=local` **and** `DEV_AUTH_EMAIL=pornthipp@chememan.com`. It only fires when the Easy Auth header is absent, and Easy Auth is currently ON (`unauthenticatedClientAction=RedirectToLoginPage`, anonymous → 401). If Easy Auth is switched off for a UAT convenience window, **every anonymous caller silently becomes Pornthip and writes to the shared prd DB**.

---

## 2. Commit inventory 2026-08-17 → 2026-09-06 on `main`

**37 commits total. 23 user-visible. 14 filtered out**, namely: 8 tracker-chore (`4bf1d82`, `1b537f9`, `cf4afcb`, `79ed6f0`, `6aa5189`, `c747bff`, `35ac2ee`, `7e7e9be`), 3 docs (`bc734eb`, `b16119c`, `6cd0a8c`), 1 test-only (`1fb5d05` contrast ratchet), 2 chore (`a67cedd` cryptography 48.0.1→50.0.1 + msal 1.38 + `.gitignore`; `62d42a7` drop tracked SIT snapshot).

### The SIT dividing line
Tracker `sit-round-closed-2026-08-19`; workbook execution + re-verification ran through **2026-08-20** (staging rev `0000057`, image `4bf1d82`). Staging rev **`0000058` (image `1b537f9`, theme commit `8013391`) landed 2026-08-21 13:22 — after all workbook execution**. Everything from `8013391` onward was never exercised by any SIT case.

### 2a. Shipped AFTER the SIT round — zero workbook coverage (12)

| Commit | Date | User-visible behaviour | UI surface | stg | prd |
|---|---|---|---|---|---|
| `8013391` | 08-21 | Full repaint onto real CHEMEMAN CI palette: shell green `#00805e`, dark `#09532d`, navy `#1b3564`, paper tint `#e5eefa`, original logo on a white plate. 18 files incl. `tokens.css`, `global.css`, `App.tsx` | Every screen | LIVE | LIVE |
| `f32dcc7` | 08-22 | Per-diem tier-3: country master 13→29 rows, new group label `ต่างประเทศ-อื่นๆ`; 16 new destinations now priceable | Trip Manager destination + per-diem calc | LIVE | LIVE |
| `91a9e21` | 08-23 | DESTINATION became a **searchable combobox** (was a plain select) across 29 countries | Trip Manager | LIVE | LIVE |
| `c615999` | 08-24 | Approver chips carry real EN HR titles: `นิภาพร ทองกิ่ง (Senior Associate)`, `วราพร ติรสิทธิ์ (Assistant Department Head)` — replaced an invented Thai gloss | Approval status chip | LIVE | LIVE |
| `965042f` | 08-29 | Toolbar legend note `หมายเหตุ: กรอกได้ตั้งแต่ 100 ขึ้นไป …` (`data-testid=pending-rounding-note`) | Grid toolbar | LIVE | LIVE |
| `a096e26` | 08-29 | Training & Seminar GLs (`5210100150`/`6210100150`) **withheld from the +add-transaction picker** unless the CC belongs to Talent & Culture; admins bypass; existing rows/grid/totals untouched | GL picker in `+ เพิ่ม Transaction` | LIVE | LIVE |
| `053fabc` | 08-29 | **Brand-new toast surface** (`platform/notice.ts` + `NoticeToasts.tsx`, App root, TTL 6 s, max 3, `role=status`) narrating every Pending-amount correction, 3 distinct Thai messages | Global toast stack | LIVE | LIVE |
| `55e0753` | 09-04 | Trip Manager `รายละเอียด` note became **real and editable** (was hardcoded `disabled`); persists to new column `budget.budget_trip.remark NVARCHAR(500) NULL`; placeholder `ระบุรายละเอียด เช่น ค่าวีซ่า / ประกัน` | Trip Manager card | LIVE | LIVE |
| `bab089b` | 09-04 | Other-travel GL pair `5210400999`/`6210400999` **dropped from the trip form**; section label `B — ค่าใช้จ่าย 4 ประเภท` → `3 ประเภท`; header copy `3 ประเภทค่าใช้จ่าย`; removed from `TRAVEL_GL_BY_TYPE_SIDE` | Trip Manager + main grid | LIVE | LIVE |
| `ad12d4a` | 09-05 | Approver buttons `ตีกลับทั้งฝ่าย`/`อนุมัติทั้งฝ่าย` → **`Reject`/`Approve`** | Approval action bar | LIVE | LIVE |
| `230ffa7` | 09-05 | Approval module fully English: status chips `Draft — not submitted` / `Approved` / `Rejected` / `Pending · Step N (…)`, position-1 label `Direct manager`, all 7 submit-blocked reasons, submit + override confirm dialogs | Approval bar, dept picker, confirm dialogs | LIVE | LIVE |
| `72affd9` | 09-05 | Last Thai in the approval flow → English, **including backend error strings** (`approval.py` 775/782/1151/1167/1177, `routers/approval.py` 140/149/355) and the **dept-picker badge `รออนุมัติ` → `Pending`**, plus `client.ts` lock message | Approval bar, **department picker badge**, API errors | LIVE | LIVE |

### 2b. Shipped DURING SIT (08-17…08-20) — partial/incidental coverage (11)

`f39f671` SIT impersonation decoupled from mail label + 2nd target · `da84db7` reminder cadence configurable in minutes · `3852f1b` blank Entertainment type blocked client-side (was raw 400) · `82ac689` **first logout control `ออกจากระบบ`** (SIT TC-004 re-pointed at it) · `4f54681` blank Lease dropdown = unchosen · `7ba8f49` decimals in special-GL/trip month amounts *(superseded 3 days later — see below)* · `4bae6e5` manager sees own สายงาน instead of `ไม่ระบุสายงาน` · `68592a4` scope chips capped at 3 names + `+N` tail · `52e60d8` **Pending amounts round to whole hundreds (half-up) and clamp at 100,000,000/cell**, backend rejects with `amount_over_cap` 400 · `30841c3` month/total column sizing · `36af1e0` every enterable special-GL field required before save.

Contradiction worth naming: `7ba8f49` (08-19) allowed decimals; `52e60d8` (08-19/20) then made `sanitizeMonthInput` strip everything non-digit for **every** money input in the app (`grid/model.ts:165-167`, used by `MonthCell` **and** the subform/Trip `MonthAmountInput`). Net live behaviour = **integer-only, hundreds-rounded, 100 M cap** in every Pending input.

---

## 3. Tracker ledger — open leftovers, known gaps, deliberate non-fixes

Ran `python tracker/task.py list`; 103 non-autolog entries updated in the window.

**Still `doing` / `willdo`:**

- `wayfinder-uat-prep` (doing, 09-06T03:41): *"…settle role assignment (pornthipp+laddawank each cover 2 depts: Data Analytic + Solution Delivery; open Q whether laddawank displaces suchanya on Solution Delivery)… KEY HAZARD found at chart time: stg+prd share ONE Fabric SQL DB and stg mail is unsandboxed+unlabelled, so every UAT click writes real prd data and mails real colleagues. Map lives at .scratch/uat-prep/MAP.md"* — **that MAP.md does not exist on disk** (`.scratch/` contains only `other-travel-gl-move`), and **`requirement_spec/5_uat/` is an empty directory**.
- `q-sit-email-coverage-audit` (doing, 08-24): *"Q: does SIT cover all 6 notification email types, and which TC ids… Running workflow audit"* — never concluded.
- `q-bulk-edit-multi-cc-gl-dept` (doing, 08-24): SharePoint-Excel → REPLACE `budget.pending_budget` for a chosen scope; 6 design-GATE questions still unanswered.
- `sit-tc040-041-055-fix` (doing, 08-20): *"the live workbook has diverged heavily… TC-048/TC-053 evidence images are GONE from '2. Test Cases' - ws._images count = 0… a NEW 4th sheet 'Note' was added… a NEW 'PIC' column was inserted into '2. Test Cases' at col4… TC-041/042 confirmed still fully untouched."*

**Deliberate non-fixes (do not re-litigate):**

- `fx-change-flow-explainer` (08-21): *"jakkaritw verdict 08-21: gap ACCEPTABLE, 'ไม่ต้องแก้' - declined (a) auto-triggering the job from the DW sync notebook, (b) stamping fx_rate/rate_per_day onto pending_budget_detail (so an approved amount is NOT auditable back to its rate; master is overwritten with no history). Do NOT re-propose either."*
- `pending-round-to-hundreds` (08-20): *"'100 ล้าน ตอนนี้ตัดเงียบ OK' … no warning dialog, no toast, no inline message… DO NOT 'improve' this later into a warning without asking him again."* — note `053fabc` (9 days later) **did** add a toast for exactly this, so the ledger's "no toast" line is now superseded by shipped code.
- `signoff-spec-b-stale-accepted` (09-06): *"do NOT revise the signed spec docs after the other-travel GL move. Spec B PDF (laddawan) + 01_special_gl_subform_spec.docx (jakkaritw) still list a 4-row trip expense table incl. 'ค่าใช้จ่ายเดินทางอื่น 5210400999/6210400999'; live Trip Manager has 3 rows. Accepted documentation drift."*
- `sit-leftover-audit-prd` (08-21): *"LEAVE BOTH LEFTOVERS IN PLACE - do NOT delete."*

**Env facts the ledger records that break SIT cases:**

- `stg-revert-session-and-sit-impersonate` (08-20): *"CONSEQUENCE FOR SIT: testers now get the ~8h session again (TC-005's 20-minute expiry check can no longer be exercised on staging without re-applying the setting)"* — confirmed live: staging has no `cookieExpiration`.
- `security-easyauth-logout-does-not-revoke` (08-18): logout clears the browser cookie only; *"its copy must never say 'ออกจากระบบเรียบร้อย' or imply the session died"*. Still open operationally: *"the two session cookies he pasted into chat earlier were never revoked."*
- `sit-folder-cleanup` (09-06): `requirement_spec/4_sit/Budget_SIT_Test_Cases_10.08.2026.xlsx` *"still carries an UNCOMMITTED modification dating from 2026-08-20 (pre-existing, jakkaritw not yet decided whether to commit it)"*.

---

## 4. The seven named in-flight items

**(a) Other-travel GL move — DONE end-to-end, LIVE both envs.**
Master flipped 2026-09-05 06:31:36; verified live now: `5210400999` and `6210400999` both read `Other manpower exp (Per diem,Health check,Uniform…etc)`, `edit_by='user'`; group counts `Travelling Expense`=6, target group=12, `Training & Seminar`=2, 19 distinct groups (no typo twin). Code `bab089b` in prd via `72affd9`. Old data wiped 09-04 (`detail_id 248` + parent row; siblings 245/246/247 = 4,500.00 preserved). **User-visible:** trip form shows 3 expense rows (per-diem auto + transport + accommodation manual); the 2 GLs are now ordinary typed monthly cells reachable from `+ เพิ่ม Transaction`; `backend/app/write_model.py:1013` now raises `"<gl> is not a recognised Travelling Expense detail account"` if a stale client posts them as trip lines. D8 was a **money-loss** fix: before it, deleting any trip in the same CC+FY silently recomputed the now-plain cell to `SUM(detail)=0` and orphan-deleted the row — *"No error, no log, no email."*

**(b) Seminar GL restriction — LIVE both envs (`a096e26`, 08-29).**
`frontend/src/grid/model.ts:766` `DEPT_RESTRICTED_GL_GROUPS = { 'Training & Seminar': 'Talent & Culture' }`. Scope is **picker-only** — existing rows, grid and totals unchanged, because non-T&C CCs already carry approved FY2026 seminar money. Fails **closed**: no CC picked, or a CC with no `departments` row, hides the GL. Admins bypass entirely. Two distinct messages: `DEPT_RESTRICTED_GL_REASON_TH` (stale selection) and `DEPT_DATA_UNAVAILABLE_REASON_TH` (`GET /scope/departments` failed → *"โหลดข้อมูลฝ่ายไม่สำเร็จ จึงยังไม่แสดง GL บางรายการ…"*, rendered at `AddTransactionForm.tsx:270`).

**(c) Trip `รายละเอียด` / remark — LIVE both envs (`55e0753`, 09-04).**
Root cause was a hardcoded `disabled` on the input. Column `budget.budget_trip.remark NVARCHAR(500) NULL` applied to the live DB; migration `setup/migrate_budget_trip_remark.py`. Migration MUST precede backend (`fetch_trips` SELECTs it unconditionally). Proven with real typing: trip_id 43 / `10IT013000` / FY2027 / remark `test111`.

**(d) English approval copy — LIVE both envs (`ad12d4a` + `230ffa7` + `72affd9`, 09-05).**
Exact live strings: buttons `Reject` / `Approve` / `Submit`; reject panel `Reject reason (required)`, `Cancel`, `Confirm Reject`; chips `Draft — not submitted` / `Approved` / `Rejected` / `Pending · Step 2 (นิภาพร ทองกิ่ง (Senior Associate))`; lock note `Submitted — locked for editing until it is rejected`; 409 → `Someone else changed this status. Reload the page and try again.`; **dept-picker badge `รออนุมัติ` → `Pending`**; backend 403 `Only an administrator can approve on behalf of an approver.` **`backend/app/notifications.py` was NOT touched — it still has 120 Thai lines**, so the UI is English while every notification email stays Thai.

**(e) Admin manual step-override — LIVE since 2026-08-02 (`09ce34d`, ADR-0027), pre-dates SIT; its COPY changed 09-05.**
No separate button: `ApprovalActionBar.tsx:133` — same `Approve` button, admin-only, position 1 only (2/3 server-409). Guard is the confirm dialog alone (D3 removed the stale-gate and the reason field). New English text: `⚠️ You are approving on behalf of <name> (approver step 1) for department "<dept>", FY <year> / The system will record that you approved on their behalf and will email the budget filler, with a copy to <name>. Continue?` Refusal messages (also new English) cover: already at the Budget Dept, no manager step, only one approval step left.

**(f) Toast/notification UI — NEW SURFACE, LIVE both envs (`053fabc`, 08-29).**
`platform/notice.ts` module-level pub/sub, `NoticeToasts` mounted once at App root above the fullscreen grid (z300) and subform modal (z500); `NOTICE_TTL_MS = 6000`, `MAX_VISIBLE = 3`, `role="status"` + `aria-live="polite"`. Exactly one publisher today — `pendingAmountNoticeTh` — with three messages: `กรอก 30 ซึ่งต่ำกว่า 100 · ระบบบันทึกเป็น 0 (กรอกได้ตั้งแต่ 100 ขึ้นไป)` / `กรอก 999,999,999 ซึ่งเกินเพดาน 100 ล้านต่อช่อง · ระบบบันทึกเป็น 100,000,000` / `กรอก 146 · ระบบปรับเป็น 100 (ปัดเศษเป็นหลักร้อย)`.

**(g) FX-change staleness — accepted as-is, NO code change, no test exists.**
Live behaviour: master FX edit → `dbo.master_currency_rate` → **subform recomputes on read instantly**, but `budget.pending_budget_detail` / `pending_budget` keep the old figure until a re-save or a manual `python -m jobs.repersist_perdiem_fx --fiscal-year N --run`. Worked example from the ledger: Vietnam group-2, 1 day × 80 USD × FX 33 = 2,640.00; after FX 33→35 the subform shows 2,800 while the grid still shows 2,640. Diagram at `docs/diagrams/fx-change-flow.png`.

---

## 5. `.scratch/other-travel-gl-move/` — items naming SIT/UAT as unresolved

`MAP.md` § **Not yet specified** (verbatim):
> - *"Whether the SIT test-case workbook on SharePoint has cases covering the 4-row trip form, and who re-runs them."* ← the only explicit SIT/UAT follow-up in the map, still open.
> - *"Whether a new ADR is warranted for the governance rule this exposed: a master-data edit can change an app entry mode, with no code review in the loop."*
> - *"Product consequence: 'other travel' amounts lose their trip linkage (no trip_id, no traveler, no travel-month coupling). Where the guidance for users lives — the trip รายละเอียด note, the row remark, or nowhere — is unresolved."*

`T03-staging-verify.md` header is `[PARTIALLY CLOSED 2026-09-04 · UI check needs a human]`, § **Still open — needs jakkaritw**:
> *"A human must open Trip Manager on staging and confirm it renders 3 expense rows, not 4."*
(`T04`'s resolution says jakkaritw reviewed staging and approved, but T03 was never flipped to CLOSED and no headless/visual evidence of the 3-row render exists.)

`T07-wipe-script-duplication.md` — `[OPEN · low priority]`: `setup/wipe_other_travel_gl_rows.py` re-implements the app's delete contract in raw SQL; *"nothing pins it to the app's logic, so a future change to the delete rules leaves it silently stale."*

`T06-signoff-docs.md` — `[CLOSED 2026-09-06 — deliberately not done]`; **UAT testers reading Spec B will expect a 4th trip row that no longer exists.**

`MAP.md` § Out of scope: the `TOTAL DAYS / YEAR` field — *"jakkaritw: 'forget it' (2026-09-04)"*.

No `.scratch/uat-prep/` folder exists.

---

## 6. Live DB facts that constrain the UAT plan (SELECT-only probe, shared prd DB)

- **`dbo.cc_filler_map`: `Data & Analytic` = 2 CC / 2 fillers (`laddawank@`, `pornthipp@`, 2 CCs each). `Solution Delivery` = 1 CC / 1 filler = `suchanyay@chememan.com`.** Neither Pornthip nor Laddawan is a filler on Solution Delivery today → **the "each carries 2 departments" plan is not executable without a `cc dept.xlsx` master edit + sync, or SIT-impersonating `suchanyay`** (who is not in the current 5-target `SIT_IMPERSONATE` list).
- `budget.approval_status`: `Data & Analytic` FY2027 = **REJECTED**, `reject_reason='test'`, `rejected_by_empcode=101622` (arthids), submitted by `laddawank@` 2026-09-05 17:15. `Budgeting and Management` FY2027 = APPROVED. **UAT will open on a rejected department showing the word "test" as the reason** unless it is reset.
- `budget.pending_budget` = 17 rows total; `Data & Analytic` FY2027 = 3 rows / 42,040.00. `pending_budget_detail` = 9. `budget_trip` = 3 (trip 43 China/`test111`, 48 Thailand/อบรม, 50 Thailand/ดูงาน). `approval_log` = 13.
- `dbo.submission_deadline` FY2027: `deadline_date 2026-10-07`, `reminder_date 2026-09-22`, `_load_dttm 2026-09-05 06:31:58`. FY2027 is **open** for the whole plausible UAT window — but the real deadline-reminder mail fires **2026-09-22** to real fillers.

---

## 7. Candidate NEW UAT test cases

Every row is behaviour that is LIVE on both envs and has **no** passing SIT case, or has a SIT case whose text is now factually wrong.

| # | Module | Proposed scenario (Thai) | Why SIT did not cover it |
|---|---|---|---|
| U-01 | Special GL Subform | สร้างทริป 1 ใบ แล้วตรวจว่าตาราง "B — ค่าใช้จ่าย 3 ประเภท" แสดง **3 แถว** (เบี้ยเลี้ยง / ค่าพาหนะ / ค่าที่พัก) และ **ไม่มี** แถว "ค่าใช้จ่ายเดินทางอื่น 6210400999" อีกต่อไป | `bab089b` shipped 09-04, 15 วันหลัง SIT ปิดรอบ. TC-061 ยังเขียนว่า "ตาราง B — ค่าใช้จ่าย 4 ประเภท" และคาด GL 6210400999 |
| U-02 | Budget Entry | กด "+ เพิ่ม Transaction" เลือก GL `6210400999` / `5210400999` แล้วกรอกยอดรายเดือนในตารางหลักโดยตรง ตรวจว่าแก้ไข/ลบได้เหมือน GL ปกติ และไม่มีปุ่มเปิดฟอร์มย่อย | GL คู่นี้เพิ่งกลายเป็นช่องกรอกธรรมดาเมื่อ master sync 09-05 06:31 + deploy prd 09-05 |
| U-03 | Data Integrity | กรอกยอดในช่อง `6210400999` ของ Cost Center หนึ่ง แล้วให้อีกคนลบทริปใน Cost Center + ปีเดียวกัน ตรวจว่ายอดในช่องนั้น **ไม่หายและไม่กลายเป็น 0** | D8: bug เงินหายเงียบ ๆ (ไม่มี error/log/email) ที่เพิ่งปิดโดยการแก้โครงสร้าง — ไม่เคยมีเคสใน workbook |
| U-04 | Special GL Subform | เปิด Trip Manager พิมพ์ข้อความในช่อง "รายละเอียด" กด "บันทึก & ลงบัญชี" ปิดหน้าต่าง เปิดกลับมาตรวจว่าข้อความยังอยู่ (ยาวได้ถึง 500 ตัวอักษร) | TC-061 คาดว่า *"ช่อง 'รายละเอียด' ใต้ตารางเป็นสีเทา พิมพ์ไม่ได้"* — `55e0753` ทำให้พิมพ์ได้จริงเมื่อ 09-04 |
| U-05 | Budget Entry | ล็อกอินเป็น Filler ที่ไม่ได้อยู่ฝ่าย Talent & Culture กด "+ เพิ่ม Transaction" ตรวจว่า **ไม่เห็น** GL `5210100150` / `6210100150` ในรายการเลือก และแถวเดิมที่มีอยู่แล้วยังแสดงและยังกรอกได้ตามปกติ | `a096e26` (08-29) หลังปิดรอบ SIT; TC-057 ยังใช้ GL 6210100150 กับฝ่าย Data & Analytic ซึ่งตอนนี้เลือกไม่ได้แล้ว |
| U-06 | Security / Admin | ล็อกอินเป็น admin (jakkaritw / nipapornt / warapornt) เปิด picker เดียวกัน ตรวจว่า **ยังเห็น** GL อบรมและสัมมนาอยู่ (admin bypass) | ข้อยกเว้น admin เป็นกติกาใหม่ ไม่มีเคสไหนแยกมุมมอง admin กับ filler ในหน้า picker |
| U-07 | UI / UX | พิมพ์ `146` ในช่องเดือนแล้วคลิกออก ตรวจว่าช่องกลายเป็น `100` **และ** มีกล่องข้อความเด้งมุมจอว่า "กรอก 146 · ระบบปรับเป็น 100 (ปัดเศษเป็นหลักร้อย)" ซึ่งหายไปเองใน 6 วินาที | toast เป็น UI surface ใหม่ทั้งหมด (`053fabc`, 08-29) — SIT ไม่เคยเห็น |
| U-08 | UI / UX | พิมพ์ `30` แล้วคลิกออก ตรวจข้อความ "กรอก 30 ซึ่งต่ำกว่า 100 · ระบบบันทึกเป็น 0 (กรอกได้ตั้งแต่ 100 ขึ้นไป)" และช่องกลายเป็น 0 | เคสเงินหายจากการปัดลงเป็น 0 ไม่เคยถูกทดสอบ; ledger บันทึกว่า jakkaritw ยืนยันกติกานี้แล้ว |
| U-09 | Budget Entry | พิมพ์ `999999999` คลิกออก ตรวจว่ากลายเป็น `100,000,000` พร้อมข้อความ "เกินเพดาน 100 ล้านต่อช่อง" (แทน TC-013 เดิม) | TC-013 หมายเหตุระบุตรง ๆ ว่า *"ขอให้ทดสอบข้อนี้ซ้ำอีกครั้งเพื่อยืนยัน"* และสถานะ Pass เดิมมาจากพฤติกรรม infinity ที่ถูกแก้ไปแล้ว |
| U-10 | Data Integrity | กรอก `33,333.33` ในช่องเดือน ตรวจว่าระบบตัดจุดทศนิยมทิ้งแล้วปัดเป็นหลักร้อย (`3,333,300`) และยอดรวมตรงกับกติกาใหม่ | TC-035 ยังทดสอบ "ความแม่นยำทศนิยม" ซึ่งขัดกับ `sanitizeMonthInput` ที่ตัดอักขระที่ไม่ใช่ตัวเลขทั้งหมด (`52e60d8`) |
| U-11 | UI / UX | ตรวจว่าใต้ toolbar มีหมายเหตุอธิบายกติกาว่า "กรอกได้ตั้งแต่ 100 ขึ้นไป" ก่อนเริ่มกรอก | `965042f` (08-29) หลังปิดรอบ |
| U-12 | Approval | ผู้อนุมัติเปิดฝ่ายที่รออนุมัติ ตรวจว่าปุ่มเป็น **Reject / Approve**, chip เป็น "Pending · Step 1 (Direct manager)" และป้ายในตัวเลือกฝ่ายเป็น **"Pending"** ไม่ใช่ "รออนุมัติ" | 15 เคส SIT (TC-002/015/017/018/019/020/021/022/023/024/037/040/043/044/046) ยังอ้างคำว่า "รออนุมัติ"; 11 เคสอ้าง "ตีกลับ"; 4 เคสอ้าง "อนุมัติแล้ว"; 3 เคสอ้าง "แบบร่าง" |
| U-13 | Approval | กด Reject ตรวจว่ากล่องเหตุผลชื่อ "Reject reason (required)" ปุ่ม Cancel / Confirm Reject และปุ่ม Confirm ถูกปิดจนกว่าจะพิมพ์เหตุผล | TC-021/TC-022 เขียนด้วยคำไทยเดิมทั้งหมด |
| U-14 | Email Alert | หลัง Approve/Reject ตรวจอีเมลที่ได้รับว่า **ยังเป็นภาษาไทย** ขณะที่หน้าจอเป็นภาษาอังกฤษ แล้วให้ผู้ใช้ยืนยันว่ารับสภาพนี้ได้หรือต้องแปลอีเมลด้วย | `backend/app/notifications.py` ไม่ถูกแตะ (ยังมีข้อความไทย 120 บรรทัด); ไม่มีเคสไหนเปรียบเทียบภาษาหน้าจอกับภาษาอีเมล |
| U-15 | Approval / Admin | admin กด Approve บนฝ่ายที่ค้างขั้นที่ 1 ตรวจข้อความยืนยันภาษาอังกฤษที่ระบุชื่อผู้อนุมัติที่ถูกข้าม แล้วยืนยัน และตรวจว่า admin กดแทนขั้น 2/3 ไม่ได้ | TC-039 ตรวจเฉพาะ **อีเมล** ของ step override; ตัวกล่องยืนยัน (ซึ่งเป็นด่านป้องกันเดียว) เพิ่งเปลี่ยนเป็นอังกฤษ 09-05 และไม่เคยมีเคสของตัวเอง |
| U-16 | Submission / RLS | Filler ที่ถือ 2 ฝ่าย ล็อกอินแล้วตรวจว่าตัวเลือกฝ่ายมี 2 ฝ่าย สลับไปมาแล้วตารางเปลี่ยนตาม และ Submit แยกกันได้ทีละฝ่าย โดยฝ่ายที่ Submit แล้วขึ้นป้าย "Pending" | SIT รันด้วยฝ่ายเดียว (Data Analytic) — การสลับฝ่ายและ scope ข้ามฝ่ายแทบไม่ถูกออกแรงเลย |
| U-17 | Approval | ผู้อนุมัติที่ดูแล 2 ฝ่าย ตรวจว่าตัวเลือกฝ่ายนับ "Pending" ถูกต้อง อนุมัติทีละฝ่ายได้ และฝ่ายที่ยังไม่ถึงคิวไม่ปรากฏปุ่ม Approve | เหมือน U-16 — TC-024 ("ไม่เห็นงบของแผนกอื่น") อ่อนมากเมื่อมีฝ่ายเดียวในระบบทดสอบ |
| U-18 | UI / UX | ผู้ใช้ที่มีหลาย Cost Center / หลายฝ่าย ตรวจว่าแถบด้านบนแสดงชื่อไม่เกิน 3 ตัว แล้วต่อท้ายด้วย "+N" และตัวเลขนับตรงกับจำนวนจริง | `68592a4` (08-19) เข้าหลังเคส Login ถูกรัน; ไม่มีเคสใดตรวจการตัดชื่อ และเป็นเรื่องที่จะเห็นผลจริงเฉพาะตอนถือ 2 ฝ่าย |
| U-19 | Login / UI | laddawank ล็อกอิน ตรวจว่าแถบด้านบนแสดง **สายงานจริง** ไม่ใช่ "ไม่ระบุสายงาน" | `4bae6e5` (08-19) แก้หลัง TC-002 ถูก mark Pass ไปแล้ว |
| U-20 | Approval | ตรวจว่า chip ของขั้น 2 / 3 แสดง "นิภาพร ทองกิ่ง (Senior Associate)" และ "วราพร ติรสิทธิ์ (Assistant Department Head)" | `c615999` (08-24) แทนคำไทยที่แต่งเอง ("ผู้จัดการฝ่ายงบประมาณ") ซึ่งระบุตำแหน่งวราพรสูงเกินจริง — เกิดหลัง SIT |
| U-21 | UI / UX | ตรวจสี/โลโก้ทุกหน้าจอตามชุดสี CI จริง (เขียว `#00805e`, กรมท่า `#1b3564`) ว่าอ่านออกชัดทั้งตาราง ปุ่ม ป้ายสถานะ และฟอร์มย่อย | `8013391` ขึ้น staging 08-21 13:22 **หลัง** การรันเคสทั้งหมดจบ; TC-028/TC-030 (UI/UX) รันบนธีม Sea Green `#2E8B57` เดิมที่เลิกใช้แล้ว |
| U-22 | Special GL Subform | เปิด Trip Manager พิมพ์ค้นหาปลายทาง (เช่น "Sing") เลือกจากรายการ ตรวจว่าเลือกประเทศกลุ่ม 3 "ต่างประเทศ-อื่นๆ" ได้ และเบี้ยเลี้ยงคำนวณตามกลุ่มนั้น | `f32dcc7` + `91a9e21` (08-22/23) — ทั้ง combobox ค้นหาได้และ 16 ประเทศใหม่เกิดหลังปิดรอบ |
| U-23 | Special GL Subform | บันทึกแถว special-GL โดยเว้นช่องบังคับไว้ 1 ช่อง ตรวจว่าระบบไม่ยอมบันทึกและระบุช่องที่ขาด (ทดสอบทั้ง Entertainment, Lease & Rental) | `36af1e0` + `3852f1b` + `4f54681` ปิดช่องโหว่ 400 ระหว่างรอบ; jakkaritw ตรวจสดบน staging แต่ **ไม่มีเคสใน workbook** |
| U-24 | Business Rules | เปลี่ยนอัตราแลกเปลี่ยนใน master แล้วตรวจว่าฟอร์มย่อยแสดงยอดใหม่ทันที แต่ตารางหลักยังเป็นยอดเดิมจนกว่าจะกดบันทึกซ้ำ — ให้ผู้ใช้ยืนยันว่ายอมรับพฤติกรรมนี้ | เป็น **ช่องว่างที่ตั้งใจไม่แก้** (jakkaritw 08-21 "ไม่ต้องแก้") — ควรให้ผู้ใช้เซ็นรับรู้ใน UAT แทนที่จะค้นพบเองตอนใช้จริง |
| U-25 | Login | ปรับ cookie บน staging เป็น 1 ชั่วโมง ล็อกอินใหม่ ทิ้งไว้จนหมดอายุ ตรวจกล่อง "หมดเวลาการเข้าใช้งาน" และค่าที่ยังไม่บันทึกต้องไม่ถูกบันทึก | TC-005 ล็อกไว้ที่ 20 นาที และ staging **ไม่มี `cookieExpiration`** อยู่ตอนนี้ (ค่า default ~8 ชม.) → เคสเดิมรันไม่ได้ตามที่เขียน |

### Two blockers to settle before the pack is written
1. **Solution Delivery has exactly one filler, `suchanyay@chememan.com`.** U-16/U-17 (the whole "2 departments each" premise) cannot run until either `cc dept.xlsx` adds Pornthip/Laddawan as fillers on that CC and the sync runs, or `suchanyay` is added to `SIT_IMPERSONATE`.
2. **Every UAT click writes the production database and sends real mail** — `FABRIC_SQL_SERVER`/`FABRIC_SQL_DATABASE` are byte-identical on both containers and `NOTIFICATIONS_DRY_RUN=false` on staging. The FY2027 deadline reminder to real fillers fires 2026-09-22.