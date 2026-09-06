## 0 · Verified baseline (checked, not assumed)

| Fact | Value | Source |
|---|---|---|
| stg image / revision | `cmanbudgetacr.azurecr.io/budget-web:72affd9` / `cman-budget-web-stg--0000068` | `az containerapp show` |
| prd image / revision | **same image `:72affd9`** / `cman-budget-web-prd--0000033` | `az containerapp show` (supersedes the memory note "PRD still 55e0753") |
| stg Easy Auth | `platform.enabled=true`, `RedirectToLoginPage`, clientId `7035aa47-0398-4b71-8411-7fc372e82123` | `az containerapp auth show` |
| stg env | `APP_ENV=local`, `DEV_AUTH_EMAIL=pornthipp@chememan.com`, `NOTIFICATIONS_DRY_RUN=false`, **no** `NOTIFICATIONS_ENVIRONMENT_LABEL`, **no** `NOTIFICATIONS_REDIRECT_ALL_TO`, `GL_EDIT_BY_ENABLED=true`, `SIT_IMPERSONATE=jakkaritw→{pornthipp,laddawank,nipapornt,warapornt,arthids}` | container env |
| prd env | `APP_ENV=production`, `GL_EDIT_BY_ENABLED=true`, `NOTIFICATIONS_DRY_RUN=false`, no SIT_IMPERSONATE | container env |
| Fabric SQL (stg) | `v5o4qez3u4cupase7cogkwvyke-bby6xlm3ncqexly4ozejod2vqe.database.fabric.microsoft.com` / `fabric_sql_database-a42ef9f3-f190-464a-8d5e-c0d41ef9ce42` | container env |
| `dbo.submission_deadline` | **exactly ONE row: fiscal_year 2027, deadline_date 2026-10-07**. Every other year = NOT_OPEN | SELECT |
| `dbo.cc_filler_map` UAT depts | `Data & Analytic` = CC `10IT011300` + `10IT013000`, fillers `pornthipp`,`laddawank` (both CCs). **`Solution Delivery` = 1 CC `10IT012000`, filler `suchanyay@chememan.com` only** | SELECT |
| Filler breadth | pornthipp 1 dept/2 CC · laddawank 1 dept/2 CC · **jakkaritw 0 rows (admin only)** · nipapornt 5 depts/7 CC · warapornt 5 depts/7 CC | SELECT |

⚠️ **Blocker for the stated UAT plan:** "Pornthip and Laddawan each carry 2 departments" is **impossible today** — neither is a Filler of `Solution Delivery` (only `suchanyay@chememan.com` is). `cc dept.xlsx` on SharePoint must be edited + synced before UAT, otherwise the multi-ฝ่าย picker still cannot be exercised.

---

## 1 · SIT coverage per module (61 cases, sheet `2. Test Cases` rows 4–64)

| Module (col C) | Cases | n | What it actually asserts |
|---|---|---|---|
| Login / Authentication | TC-001…005 | 5 | Filler login, Approver login (badge+read-only), wrong password (Microsoft layer), logout+Back, session expiry dialog (session forced to 20 min for the test; prod = 14 h) |
| Budget Entry (Filler) | TC-006…014 | 9 | Grid renders for 1 dept; type + autosave-on-blur + survives reload; total auto-sum (=35,500); number format 1,234,567.89; Add-Transaction required-field validation; letters rejected; negatives rejected; huge number (999999999999); edit draft again |
| Submission / Workflow | TC-015…018 | 4 | Submit → `Pending step 1`; filler locked after submit; approver notified; status parity both sides |
| Approval (Approver1) | TC-019…024 | 6 | View detail, Approve→step 2, Reject+reason, reason mandatory (UI + server), Filler edit+resubmit, cross-department isolation |
| Business Rules | TC-025, 026 | 2 | Submitted total == typed total; no duplicate submit |
| Reports / Export | TC-027 | 1 | **N/A — declared out of scope** (correct: no export exists anywhere in `frontend/src`) |
| UI / UX | TC-028…030 | 3 | Thai renders/ellipsis/tooltip; error copy has no stack trace; Chrome+Edge, 1366×768 horizontal scroll, frozen CC/GL columns |
| Security | TC-031…033 | 3 | Unauthenticated → Microsoft login; Filler cannot approve; XSS/injection in text fields |
| Data Integrity | TC-034, 035 | 2 | 2-tab concurrent edit → 409 Thai message; rounding precision |
| Email Alert / Notification | TC-036…042, 047…055 | 16 | turn mail, reject mail, approved mail, step-override mail, 7-day turn reminder, deadline reminder (×2, one N/A), From/To/CC, subject format, body fields, deep-link, Thai encoding, not-in-Junk, 2027-vs-Year-2026 mapping, step-2/3 sequencing |
| Approval (Approver 2/3) | TC-043…046 | 4 | Step 2 approve → step 3; step 3 approve → APPROVED; step 2/3 reject returns straight to Filler; out-of-turn approver has no buttons |
| **Special GL Subform** | TC-056…061 | 6 | Entertainment (2 lines, 2 GLs, dropdown sets), Training & Seminar (course+Method, integer-only month input), Professional & Legal Fee (edit + delete line, parent re-sum), Public Relation & Donation (3 lines under 1 GL), Lease & Rental (4 meta cols, "อื่นๆ" plate + validation, 2nd GL with fewer cols), Trip Manager (1 trip, Singapore, 5 days, per-diem auto row + 3 manual rows). Each carries backend verification SQL (Q1–Q5) |

All 61 = Pass except **TC-027 (N/A, out of scope)** and **TC-042 (N/A, "ทดสอบซ้ำ 41 / skipped")**.
Note: 14 of 61 are recorded `Actual = "Pass by AI"`, i.e. verified by the dev/AI, not by a business tester — TC-002, 017, 019–025, 029, 036, 037, 039, 043–046, 055.

---

## 2 · Actual shipped user-facing surface (`frontend/src`, `backend/app/routers`)

Single route: `frontend/src/app/page.tsx` → `App.tsx` (no router, no second page). Regions:

**Chrome / identity**
- Nav bar with logo plate (`App.tsx:52-58`)
- `UserBar` (`userbar/UserBar.tsx`) — avatar, email local-part, full email, role badge (`ผู้ดูแลระบบ / ผู้กรอกงบประมาณ / ดูอย่างเดียว / ไม่มีสิทธิ์เข้าถึง`), สายงาน text, ฝ่าย chips *first 3 + "+N"*, ฝ่าย count, Cost Centers pill, GL Codes pill (`useFillGlCount`), admin line "เห็นข้อมูลทั้งหมด · ทุก Cost Center", logout `<a>` to Easy Auth
- `SessionExpiredDialog` (`auth/SessionExpiredDialog.tsx`), `NoticeToasts` (`platform/NoticeToasts.tsx`, TTL 6 s, max 3)
- Deep link `?dept=&year=` (`filters/deepLink.ts`), validated against real scope

**Toolbar** (`grid/BudgetGrid.tsx:481-527`)
- `YearPicker` — `<select>`, options 2020…currentYear+1 as planning year, **labelled `Year (y-1)`**
- `DeptPicker` — trigger, search box, division groups + counts, per-dept CC count, `Pending` badge, Enter picks single match, Esc closes, empty state `ไม่พบฝ่ายในสิทธิ์ของคุณ`
- `AddTransactionForm` — CC combobox + GL combobox + `validateNewTransaction` (7 distinct refusal messages incl. year-not-open, locked dept, dept-restricted GL, GL-gone-from-master, duplicate row)
- **`แนบไฟล์` button** → `AttachmentsModal`
- **`AdminModeToggle`** (dual-role admins only; `admin/useAdminViewToggle.ts`, persisted)
- Legend (3 layers, each stamped with its year) + rounding note "กรอกได้ตั้งแต่ 100 ขึ้นไป…"
- **Admin zone strip** (`data-testid="admin-zone"`) with the FX / Approved-provenance tooltip

**Grid** (`grid/GridTable.tsx`, 1491 lines)
- Two side-tables: `ฝั่งผลิต / ต้นทุน (5xxx)` and `ฝั่งบริหาร / ขาย · SG&A (6xxx)`
- 3 stacked layer rows per (CC, GL): **SAP · ใช้จริง / Approved · งบ / Pending**
- 12 month cells + `รวมทั้งปี` + `Jan–Dec` header, per-GL-group subtotals + grand totals
- **5 per-column filter inputs** (`filter-cc`, `filter-gl`, `filter-glgroup`, `filter-remark`, `filter-status`)
- **Draggable column widths** persisted to `localStorage['budgetGridColWidths']` + **Reset-columns** button (×2, one per side)
- **Collapse/expand** GL Group / Remark / Status columns
- **Fullscreen toggle ⤢ / ⤡ + Esc**, body-scroll lock
- Frozen CC/GL columns via computed `--frz1..5`
- **Remark inline edit** (`aria-label="Remark <cc> <gl>"`)
- **Delete-row button** `ลบรายการนี้` for manually-added rows only + Thai confirm
- Special-GL open button, two variants: `แก้ไขผ่านฟอร์มย่อย` and locked `อ่านอย่างเดียว — แก้ไม่ได้ในสถานะนี้` (🔒)
- **ADR-0026 hidden SAP months** — en-dash `–` + tooltip `ข้อมูล SAP เดือนนี้ยังไม่ครบ จึงยังไม่แสดง`, plus `sapCoverageLabel()` caveat on the SAP year total
- MonthCell: digits-only sanitiser, **round-to-100**, **cap 100,000,000**, 3 distinct Thai toasts (`pendingAmountNoticeTh`)

**Modals**
- `DetailSubform` (5 special groups, dynamic meta columns, add/delete line + confirm, Monthly-total row, `Rows: n · Year total`, read-only variant)
- `TripManager` (1187 lines) — multi-trip cards, traveler combobox (search by name/email/position), destination combobox off the country master, Project, purpose, **days**, **month multi-select toggles**, side `<select>` locked to the clicked row's side + cross-side warning note, 4-type expense table with **server-computed per-diem** row, delete-trip confirm, `บันทึก & ลงบัญชี`, read-only variant, per-diem error text
- `AttachmentsModal` — list (name/size/uploader/date), upload (`.pdf,.xlsx,.xls,.png,.jpg,.jpeg`, **10 MB**, `attachments.py:33-34`), download (opens Graph URL in new tab), delete + confirm, `canUpload = adminViewEnabled || isFillerOfSelectedDept`

**Approval bar** (`approval/ApprovalActionBar.tsx`)
- Status chip, `Submit` (+ confirm text naming rows & CC count), `Approve`, `Reject` → reason panel (`Confirm Reject` disabled while empty), **admin step-override on the SAME Approve button with a different confirm dialog**, 7 `submit_blocked_reason` hint strings, persisted reject-reason display

**Empty state:** `no-scope-empty-state` (`role === 'none'`), naming `nipapornt@chememan.com` + `cc dept.xlsx`.

**Backend endpoints** (30): `/me`, `/scope`, `/scope/departments`, `/budget`, `/budget/sap-coverage`, `/budget/gl-accounts`, `/budget/detail`, `/budget/trip`, `/reference/travelers`, `/reference/countries`, `PUT|DELETE /rows|/detail|/trip`, `POST /trip`, `/approval/{submit,approve,reject,override-step,pending-for-me,locked-departments,status}`, `/attachments{,/upload,/download-url}` + `DELETE`, `/health`, `/sit/impersonate` (GET+POST).

---

## 3 · Features with **ZERO** SIT coverage

Verified by keyword sweep of all 61 rows (`แนบ`, `Admin`, `กรอง`, `เต็มจอ`, `board`, `FX`, `remark`, `ปิดรับ`, `ลบ`, …) plus reading every Scenario/Steps/Expected cell.

### A. Attachments — the entire feature (0 cases)
The only hit is TC-030's layout check "ปุ่มส่งอนุมัติ **แนบไฟล์** และแถบอนุมัติกดได้ครบ ไม่ถูกบัง" — button *visibility* only.
Uncovered: open modal · list existing files · upload each allowed type · **rejected extension** message · **>10 MB** rejection (`too_large_message`) · download-in-new-tab · **delete + Thai confirm** (irreversible for a filler) · `canUpload=false` hides the drop zone for a See-only user · missing-SharePoint-folder Thai error · Thai filename sanitisation · the `เอกสาร ฝ่าย/` path guard.
**UAT: IN SCOPE, high priority.** It writes to a live SharePoint library that also holds the 8 admin master workbooks; delete is irreversible for a business user.

### B. Admin mode toggle + admin overlay (0 cases)
TC-039 logs in as Admin only to press step-override for an *email* assertion. Never tested: the `โหมด Admin` toggle itself, its persistence, that flipping it **resets the ฝ่าย and re-resolves** (`handleAdminModeToggle`), admin-wide department list (all 114 ฝ่าย), admin bypass of the department lock / year-not-open / dept-restricted GL, the `admin-zone` strip and its tooltip, admin-Submit → straight `APPROVED` (ADR-0012), pure-admin vs dual-role-admin behaviour.
**UAT: SPLIT.** Nipaporn + Waraporn are real dual-role admins and are attending — the toggle, the admin-wide picker and admin-Submit ARE in scope. Pure-admin/no-scope admin behaviour is an ops concern; skip.

### C. Department picker with >1 ฝ่าย (0 cases — was untestable)
SIT had one department. Never tested: >1 ฝ่าย → **no auto-select, picker starts blank**; search box; division grouping + counts; CC counts; Enter-selects-single-match; Esc; `Pending` badge on a non-selected ฝ่าย; switching ฝ่าย reloads the grid, the approval bar, the attachments folder and the lock state; the UserBar "3 chips + N" overflow.
**UAT: IN SCOPE, top priority** — it is the single biggest behavioural delta from SIT. **Requires the `cc dept.xlsx` fix above first.**

### D. Approved / `board_budget` layer (0 cases)
Only TC-009 checks that the Approved row *formats* like the others. Never tested: that the Approved layer shows **FY = planning_year − 1**, that an Approved-only row (no SAP, no Pending) still appears (ADR-0010 FULL OUTER), that Approved is read-only everywhere, that the year label on the legend matches.
**UAT: IN SCOPE (read-only comparison).** Fillers plan against these numbers; a wrong-year column is a business error, not a bug class only devs can see.

### E. SAP actuals columns (0 cases)
Never tested: SAP values reconcile to SAP; SAP is read-only; **ADR-0026 hidden months** (`–` + tooltip) and the `รวมเฉพาะเดือนที่ข้อมูลครบ:` caveat on the year total; a SAP-leader row appearing with empty Pending; the net-zero row-hide rule.
**UAT: IN SCOPE for the masking UX** (the `–` is confusing without explanation and a filler WILL ask). SAP↔SAP reconciliation itself is a data-engineering check, not a UAT case.

### F. Per-diem calculation — the number (partially covered; the amount is not)
TC-061 destination = Singapore (`country_group=2` → **USD rate × FX**) but its Expected Result says only "ยอดเบี้ยเลี้ยงที่ระบบคำนวณ" — **no THB figure is asserted anywhere**. Never tested: a domestic trip (`country_group=1`, THB, no FX); position-driven rate differences; a **multi-month** trip (per-diem split across `travel_months` — TC-061 used one month); `days` change → recompute; `MissingPerDiemRateError` / `MissingFxRateError` Thai messages (`ไม่พบอัตราเบี้ยเลี้ยงหรืออัตราแลกเปลี่ยนสำหรับปีนี้`); **2+ trips on one CC**; **delete trip** (`ลบทริปนี้ทั้งหมด?`); editing a saved trip; opening a trip stored on the *other* accounting side.
**UAT: IN SCOPE, high priority** — a per-diem baht figure the business can hand-check (`days × rate × FX`), plus delete-trip and a multi-month trip. This is money the app computes on its own.

### G. FX / currency (0 cases)
`FX` appears zero times in the workbook. Never tested: the USD→THB `master_currency_rate` value actually used, its visibility in the admin-zone tooltip, or the known accepted gap (subform recomputes, grid stays stale until a repersist job).
**UAT: OUT OF SCOPE as a standalone case** — jakkaritw already accepted the FX-change gap (2026-08-21) and the rate is an admin master. Fold it into F by picking a foreign trip and reconciling one number.

### H. Year lock / `NOT_OPEN` / past deadline (0 cases)
"ปิดรับ" appears only inside deadline-reminder *email* cases. Never tested: switching the YearPicker to a year with **no `submission_deadline` row** → `+ เพิ่ม Transaction` refuses with `ปีงบประมาณนี้ไม่เปิดให้กรอกในเว็บ…`, Submit hidden, hint `This fiscal year is not open for submission yet.`; nor `past_deadline`; nor admin bypass of both.
**Live fact:** only FY2027 has a row (deadline **2026-10-07**), so **every other year in the picker is NOT_OPEN right now** — a UAT tester who touches the year dropdown WILL hit this.
**UAT: IN SCOPE (1 case).** Switch to `Year 2025` and confirm the refusal reads sensibly. Past-deadline is admin/ops — skip.

### I. Read-only lock on locked/approved rows — grid-side (partially covered)
TC-016 covers "filler cannot edit after submit". Never tested: the **locked special-GL button variant** (🔒 `อ่านอย่างเดียว — แก้ไม่ได้ในสถานะนี้`) opening the subform/Trip Manager in read-only mode with the fieldset disabled and Save/Add hidden; `+ เพิ่ม Transaction` refusing a locked CC with `lockedAddReasonTh`; `ALL_COST_CENTERS_LOCKED_REASON_TH`; the trailing delete button disappearing when locked.
**UAT: IN SCOPE (1–2 cases)** — this is exactly what a Filler sees the day after submitting.

### J. Hidden / masked / restricted GLs (0 cases)
Never tested: a GL present in SAP but absent from `dbo.gl_group` is invisible to everyone; the **`edit_by='admin'` lock** (13 GLs, `GL_EDIT_BY_ENABLED=true` on both stg and prd) hiding rows from a non-admin and 403-ing on write; **`Training & Seminar` restricted to `Talent & Culture`** — the GL simply does not appear in a Data & Analytic filler's GL picker; `DEPT_DATA_UNAVAILABLE_REASON_TH`.
**UAT: SPLIT.** The Training & Seminar restriction IS in scope — TC-057 had a Data & Analytic filler entering `6210100150` and it passed at SIT-time, so the restriction (added 2026-08-29, `a096e26`) has **never been retested and is now expected to hide that GL**. This is a live regression risk. The admin-GL hide is a security check, not UAT.

### K. Grid interaction / UI-parity block (0 cases)
Never tested: **5 column filters**, **column-width drag + localStorage persistence + Reset**, **collapse/expand columns**, **fullscreen + Esc**, frozen-column alignment while filtered, sub-100 / cap / rounding **toasts** (the *behaviour* is covered by TC-013's retest request; the toast copy shipped later, 2026-08-29), the `+ เพิ่ม Transaction` searchable comboboxes, duplicate-row refusal, GL-removed-from-master refusal.
**UAT: PARTLY IN SCOPE.** Filters + column width/reset + fullscreen are daily ergonomics for a 12-month × N-row grid — 1 combined case. The rest (localStorage persistence, frozen-column pixel alignment) is dev QA, skip.

### L. Delete a manually-added row from the grid (0 cases)
`ลบ` in the workbook always refers to deleting a *subform line* (TC-058) or a *trip*. The grid's own trailing `ลบรายการนี้` column, its Thai confirm and its 409 refetch are untested.
**UAT: IN SCOPE (1 case)** — irreversible, and fillers add rows by hand constantly.

### M. Remark column (0 cases)
`remark` appears zero times. The Pending remark input, its save path (same whole-row `PUT /budget/rows`), empty→null normalisation, and the remark column filter are untested.
**UAT: IN SCOPE (fold into the grid case).**

### N. No-scope empty state (0 cases)
`no-scope-empty-state` and its `nipapornt@chememan.com` / `cc dept.xlsx` copy are untested.
**UAT: OUT OF SCOPE.** All 5 attendees have scope (or are admins); manufacturing a no-scope account means editing the live master. Verify by screenshot/dev instead.

### O. Notify / reminder — there are **no buttons** to test
There is no notify or reminder control anywhere in the UI. Both reminders are the CLI job `backend/jobs/send_reminders.py`. SIT covered them as jobs (TC-040 turn reminder; TC-041 deadline reminder, TC-042 skipped) but **only ever with N=1 department** (TC-040 remark: "ทดสอบได้ 1 ฝ่ายเพราะทั้งบริษัทมีฝ่ายเดียวที่ผู้อนุมัติขั้น 1 เป็นลัดดาวัลย์"). The "one mail listing N departments" aggregation is therefore **unproven for N>1**.
**UAT: IN SCOPE only as an observation** — with 2 departments, if Laddawan is approver-1 of both, one reminder run proves the N=2 aggregation. Do not build a tester-driven case; a dev runs the job.

### P. UserBar / scope read-out (0 cases)
สายงาน › ฝ่าย(count) › CC pill › GL-count pill, the "+N" overflow, the role badge, **logout link**. TC-004 covers logout behaviourally but not from this control.
**UAT: IN SCOPE, trivial (fold into login case)** — it is the first thing every tester reads and the counts must match their real scope.

### Q. Deep-link parameter handling (0 direct cases)
TC-051 clicks an email link, which exercises it end-to-end. Never tested: a deep link to a ฝ่าย **outside** the caller's scope (must be ignored, not honoured) — a security-relevant case.
**UAT: OUT OF SCOPE** — negative-security case, dev/security verifies.

### R. `GET /budget/sap-coverage` — dead in the UI
`sapFreshnessLine()` (`grid/model.ts:946`) and `/budget/sap-coverage` exist but **no frontend client calls them** (`frontend/src/api/*` has no such function). Untested and unreachable.
**UAT: OUT OF SCOPE** — dead code, report to the dev team.

### S. `/sit/impersonate` (0 cases)
The HTML picker page + cookie, CSRF check, target allow-list.
**UAT: OUT OF SCOPE for testers — but a live hazard.** It is enabled on staging (`APP_ENV=local` ≠ production + `SIT_IMPERSONATE` set) and **writes real data signed as the impersonated person**. If it is used to drive UAT, `approval_log` will name the impersonated person, not the operator.

---

## 4 · Cases that are covered but whose expectations are now **STALE** (must be re-worded for UAT)

The approval UI was translated to English after SIT (commits `230ffa7`, `72affd9` — both now live on stg **and** prd).

| SIT expects (Thai) | App now renders (English) |
|---|---|
| `รออนุมัติ · ขั้น 1 (ผู้บังคับบัญชาสายตรง)` | `Pending · Step 1 (Direct manager)` |
| `รออนุมัติ · ขั้น 2 (นิภาพร ทองกิ่ง (ฝ่ายงบประมาณ))` | `Pending · Step 2 (นิภาพร ทองกิ่ง (Senior Associate))` |
| `รออนุมัติ · ขั้น 3 (วราพร ติรสิทธิ์ (ผู้จัดการฝ่ายงบประมาณ))` | `Pending · Step 3 (วราพร ติรสิทธิ์ (Assistant Department Head))` |
| `แบบร่าง (ยังไม่ส่งอนุมัติ)` | `Draft — not submitted` |
| `อนุมัติแล้ว` | `Approved` |
| ปุ่ม `อนุมัติ` / `ตีกลับ` | `Approve` / `Reject`, `Reject reason (required)`, `Confirm Reject` |
| — | `Submitted — locked for editing until it is rejected` |

Affects **TC-002, 007, 014, 015, 018, 020, 021, 023, 043, 044, 046** (11 cases). Also the Training & Seminar GL restriction (§J) may invalidate **TC-057**.

---

## 5 · Unresolved questions / complaints left by testers (verbatim Thai)

**Sheet `Note`** — items numbered 2, 3, 4 (there is no item 1; 6 screenshots are embedded, anchored at rows 5, 19, 33, 45 and two in col 19):

> **2.** `บางรายการที่เพิ่ม transaction เอง แต่ไม่ได้ใส่ข้อมูลครบเช่นด้านล่างใส่แค่สถานที่ใช้งาน สามารถกดบันทึกได้`
> **3.** `ข้อ TC060 : สามารถเว้นการกรอกรายละเอยดกิจกรรมได้??`
> **4.** `ยอดยาวๆจะทับกันไหม??`

**Open items inside `Actual Result` / `Remarks` (cols K/P), all on rows marked Pass:**

> **TC-011** `ระบบไม่รับค่า / **** แต่ไม่ได้แจ้งเตือน`
> **TC-013** `ใส่ค่าตัวเลขขนาดใหญ่ได้ / **** แต่แสดงผลเป็น infinity & สัญลักษณ์ infinity ไม่แน่ใจว่าตอนส่งขออนุมติแสดงผลยังไง` — remark: `…แก้แล้วใน commit 52e60d8 … ขึ้น staging แล้ว (revision 0000054, 2026-08-20) · **ขอให้ทดสอบข้อนี้ซ้ำอีกครั้งเพื่อยืนยัน**` → **the retest was never recorded**
> **TC-030** `…ยังต้องให้คนตรวจบน Edge` → **Edge never human-verified**
> **TC-052** `…ยังต้องให้คนเปิดดูบนมือถือ` → **mobile mail rendering never human-verified**
> **TC-061** `**** มีแค่คำบน tool tiips ที่ไม่เหมือน expected result` → tooltip wording mismatch, unresolved
> **TC-040** `ทดสอบได้ 1 ฝ่ายเพราะทั้งบริษัทมีฝ่ายเดียวที่ผู้อนุมัติขั้น 1 เป็นลัดดาวัลย์` → N>1 aggregation unproven
> **TC-056** `1. ถ้ากดเพิ่มข้อมูลแล้ว แก้ไขที่หน้าตารางข้างนอกไม่ได้ ต้องแก้ไขผ่านฟอร์มย่อย / 2. ถ้าเพิ่ม transaction ไปแล้ว เพิ่มซ้ำอีกไม่ได้` (observation, by design)
> **TC-004 / TC-005** Remarks both read only `edit program` (cryptic — meaning unrecoverable from the workbook)
> **TC-042** `ทดสอบซ้ำ 41 / skipped`
> **TC-029** `…jakkaritw ตัดสินว่าผ่าน (2026-08-20): เปิดหน้าจอ 2 แท็บแล้วตัวเลขอัปเดตให้ทันที โอกาสเกิดข้อผิดพลาดจึงน้อยมาก ไม่ต้องไล่ครบทั้ง 4 กรณี` (3 of 4 sub-cases waived)

---

## 6 · Exact workbook shape (for generating the UAT workbook)

**Sheet `2. Test Cases`** — `A1:P64`, `A1:P1` merged title `Budget Web App — SIT Test Cases` (fill `FF1F3864`).

| Col | Header (row 2) | Width | Notes |
|---|---|---|---|
| A | `No.` | 8.29 | integer 1…61 |
| B | `Test Case ID` | 12.0 | `TC-001`… |
| C | `Module` | 21.57 | drives the Summary COUNTIFs |
| D | `PIC` | default | tester name |
| E | `Test Scenario` | 37.71 | |
| F | `Priority` | 20.57 | DV list `High,Medium,Low` on `F3:F64` |
| G | `Preconditions / เงื่อนไขก่อนทดสอบ` | 34.71 | |
| H | `Test Steps` | 47.29 | newline-separated `1. … 2. …` |
| I | `Test Data` | 45.57 | |
| J | `Expected Result` | 53.71 | |
| **K** | `Actual Result` | 18.57 | **YELLOW `FFFFF2CC`** |
| **L** | `Status` | 11.0 | **YELLOW**; DV list `Not Run,Pass,Fail,Blocked,N/A` on `L3:L64` |
| **M** | `Severity` | default | **YELLOW**; DV list `Critical,High,Medium,Low,-` on `M3:M64` |
| **N** | `Tester` | 12.0 | **YELLOW** |
| **O** | `Test Date` | default | **YELLOW**; real `datetime` values, not strings |
| **P** | `Remarks / หมายเหตุ` | 25.43 | **YELLOW** |

- Header row **2**, fill `FF2E5496`. Row **3** = example row `EX` / `TC-EX` (excluded from all counts). Data rows **4–64**.
- `auto_filter.ref = A2:P64`; `freeze_panes = I36`.
- No conditional formatting rules; no images on this sheet except 2 screenshots anchored near rows 51 and 56.

**Sheet `3. Summary`** — `B2:E27`, all formulas over the fixed range `$4:$64`:

```
C6  =COUNTA('2. Test Cases'!$B$4:$B$64)                       → 61
C7  =COUNTIF('2. Test Cases'!$L$4:$L$64,"Pass")
C8  =COUNTIF(...,"Fail")   C9 =...,"Blocked"   C10 =...,"Not Run"   C11 =...,"N/A"
C12 =IFERROR(Pass/(Pass+Fail+Blocked),"-")                    ← N/A excluded from the denominator
B16:B26  module names (11 rows)
C16 =COUNTIF('2. Test Cases'!$C$4:$C$64,<module>)
D16 =COUNTIFS($C$4:$C$64,<module>,$L$4:$L$64,"Pass")
E16 =COUNTIFS($C$4:$C$64,<module>,$L$4:$L$64,"Fail")
```

**Three defects to fix when regenerating:**
1. **The module breakdown is missing `Special GL Subform`.** `B16:B26` lists 11 modules covering only 55 of the 61 cases — TC-056…061 are counted in `C6` but appear in no module row.
2. **The instructions promise a column that does not exist.** `1. Info & Instructions!A20` says testers fill *"Actual Result, Status, Severity, **Defect ID**, Tester, Test Date, Remarks"* — there is **no Defect ID column**. Either add one (between M and N) or drop it from the text.
3. **Hard-coded `$4:$64` and `freeze_panes = I36`.** Any UAT row past 64 is silently uncounted (same trap as the SIT-workbook append incident), and `I36` freezes 35 rows — almost certainly accidental; use `I3` (or `A3`) and size the ranges to the real last row.