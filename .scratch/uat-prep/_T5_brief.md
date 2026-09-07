# BRIEF — build the UAT test-script pack (ticket T5, partial)

> **REVISION 2, 2026-09-07 — the case list is now 54 cases, not 68.** jakkaritw reviewed the
> first list and approved a de-duplication pass: 13 cases that shared a screen and a click-path
> with a neighbour were merged into that neighbour, and 1 case was cut outright. Nothing about
> the coverage changed — every assertion from the 68 still appears, it just lives in fewer rows.
> If you already generated a 68-case file, regenerate it from this list.

Repo: `C:\04.budget_management_web`. You are implementing, inline, the UAT test-case
workbook + a readable Thai companion doc + a generator + a validator.

## Deliverables (exactly these, nothing else)

```
requirement_spec/5_uat/
├── Budget_UAT_Test_Cases_07.09.2026.xlsx      <- generated, committed snapshot
├── UAT_Test_Script.md                          <- Thai readable companion
└── _build/
    ├── build_uat_test_cases.py                 <- generator (idempotent, re-runnable)
    └── validate_uat_pack.py                    <- validator
```

DO NOT build: entry/exit criteria file, the .docx guides, the sign-off sheet, any
SharePoint upload, any `assets/` screenshots. Those are blocked on ticket D7 or out of
this dispatch. No `--upload` flag anywhere.

## Sources you MUST read before writing anything

1. `requirement_spec/4_sit/Budget_SIT_Test_Cases_10.08.2026.xlsx` — the shape to copy and
   the Thai Preconditions/Steps/Expected text to inherit for every case marked `SIT:` below.
   Read it with openpyxl. Sheet `2. Test Cases`, header row 2, data rows 4-64.
2. `.scratch/uat-prep/research/post-sit-changes.md` section 7 — the Thai scenario lines for
   every case marked `NEW(U-xx)` below.
3. `.scratch/uat-prep/research/sit-coverage-gaps.md` sections 2, 3, 6 — the live UI surface
   (exact button labels, testids, Thai strings, limits) for every case marked `NEW(§X)`, and
   section 6 for the exact workbook shape (columns, widths, fills, DV lists, formulas).
4. `.scratch/uat-prep/MAP.md` "Ground truth verified at chart time" table — environment,
   people, fiscal year.

Compose each case's Preconditions / Test Steps / Expected Result in **Thai**, in the same
voice as the SIT workbook. Inherit and re-word; do not invent behaviour. Where a source says
the app renders an English string (`Approve`, `Reject`, `Pending · Step 1 (Direct manager)`,
`Draft — not submitted`, `Approved`, `Reject reason (required)`, `Confirm Reject`), quote that
English string verbatim inside the Thai sentence.

**A merged case keeps every assertion of the rows it absorbed.** Where the list below says a
case merges several old ones, write it with numbered sub-steps or a multi-row `Test Data`
block so no assertion is silently lost. A merged case is one row on the sheet, not one check.

## Fixed header facts for sheet `1. Info & Instructions`

| Field | Value |
|---|---|
| Application | Budget Web Application |
| Environment | `https://cman-budget-web-prd.kindstone-f34836dd.southeastasia.azurecontainerapps.io/` (production — already resolved, use this literal string). The staging URL must NOT appear anywhere in the workbook. |
| Test Phase | User Acceptance Test (UAT) |
| Departments under test | Data & Analytic ; Solution Delivery |
| Fiscal year under test | FY2027 (screen shows `Year 2026`) — the only open year |
| Role — Filler (both departments) | Pornthip (pornthipp@chememan.com) |
| Role — Approver 1 (both departments) | Laddawan (laddawank@chememan.com) |
| Role — Approver 2 | Nipaporn (nipapornt@chememan.com) |
| Role — Approver 3 | Waraporn (warapornt@chememan.com) |
| Role — Observer / read-only on Solution Delivery | Suchanya (suchanyay@chememan.com) |
| Test Lead | Data and Analytics team |
| Test Cycle / Round | UAT Round 1 |
| Start / End Date | leave BLANK (decided by ticket D7) |

Add a **`ข้อควรระวังก่อนเริ่มทดสอบ`** block to sheet 1, in Thai, carrying these four warnings
verbatim in meaning:

1. UAT รันบน **ระบบจริง (production)** ใช้ฐานข้อมูลจริงและส่งอีเมลจริงถึงเพื่อนร่วมงานจริง — ไม่มีระบบทดลองแยก
2. สถานะ **`Approved` ย้อนกลับไม่ได้ในระบบ** ต้องแก้ที่ฐานข้อมูลเท่านั้น อย่ากด Approve ขั้นที่ 3 จนกว่าจะถึงเคสที่ระบุ
3. อายุ session ระหว่าง UAT = **1 ชั่วโมง** (ค่าจริงคือ 14 ชั่วโมง จะคืนค่าหลังจบรอบ)
4. **KNOWN ISSUE ที่ไม่ต้องแจ้งเป็น defect:** กล่อง "หมดเวลาการเข้าใช้งาน" ยังเขียนว่า 14 ชั่วโมง ทั้งที่ตั้งไว้ 1 ชั่วโมง — ตัดสินแล้วว่ายอมรับ (jakkaritw 2026-09-06)

## Workbook shape

Copy the SIT shape exactly (see coverage-gaps section 6), with these five changes:

1. **New column `Department`** after `Module` — DV list `Data & Analytic,Solution Delivery,ทั้งสองฝ่าย,-`.
2. **New column `Wave`** as the FIRST column (before `No.`) — values `W1`..`W8`, so a tester can
   sort and work one wave at a time. Freeze panes so Wave/No./ID/Module stay visible.
3. **New column `Defect ID`** between `Severity` and `Tester` (yellow, tester-filled) — the SIT
   instructions promised it and it never existed.
4. **New sheet `4. Defects`** — columns: `Defect ID` (D-001…), `UAT Case ID`, `Department`,
   `Title`, `Severity` (DV `Blocker,Major,Minor`), `Reported by`, `Reported date`, `Owner`,
   `Status` (DV `Open,In Progress,Fixed,Retested,Closed,Wont Fix`), `Fixed in`, `Retest date`,
   `Retest result` (DV `Pass,Fail`), `Notes`. Pre-fill 40 blank numbered rows.
5. **Sheet `3. Summary` fixed**: every range computed from the REAL last data row, never
   hard-coded `$4:$64`; module breakdown lists all 8 modules below with none missing;
   add a **breakdown by Wave** and a **breakdown by Department** beside it.

Keep: header row 2, header fill `FF2E5496`, title fill `FF1F3864`, yellow `FFFFF2CC` on every
tester-filled column, DV `Not Run,Pass,Fail,Blocked,N/A` on Status, DV `Critical,High,Medium,Low,-`
on Severity, DV `High,Medium,Low` on Priority, `auto_filter` over the real used range.
Drop the SIT example row `TC-EX` — instead put one worked example inside sheet 1's instructions.
Mark AI-written cells purple font `7030A0` per the project's SIT workbook editing protocol.

## The 8 modules (Summary breakdown must list exactly these)

Login / Authentication · Budget Entry (Filler) · Special GL Subform · Attachments ·
Submission / Workflow · Approval · Email Alert / Notification · Business Rules & UI

## THE CASE LIST — 54 cases, in this exact order, numbered UAT-01 … UAT-54

Legend for the Source column: `SIT: TC-xxx` = inherit and re-word that SIT case ·
`NEW(U-xx)` = post-sit-changes.md section 7 row · `NEW(§X)` = sit-coverage-gaps.md section 3 gap X.
`Dept`: `A`=Data & Analytic, `S`=Solution Delivery, `both`=ทั้งสองฝ่าย, `-`=n/a.

### W1 — เข้าระบบและสิทธิ์ที่มองเห็น · Module `Login / Authentication` · 5 cases

| ID | Pri | Dept | Source | Scenario (Thai, expand into full steps) |
|---|---|---|---|---|
| UAT-01 | High | both | SIT: TC-001 + NEW(§P) + NEW(U-18) | Pornthip ล็อกอิน · แถบบนแสดง สายงาน / ชื่อฝ่าย / จำนวน Cost Center / จำนวน GL ตรงกับสิทธิ์จริง · role badge = `ผู้กรอกงบประมาณ` · **และ** ชื่อฝ่ายแสดงไม่เกิน 3 ชื่อ แล้วต่อท้าย `+N` โดย N ตรงกับจำนวนจริง |
| UAT-02 | High | both | NEW(U-16) | Filler ที่ถือ 2 ฝ่าย: ตัวเลือกฝ่าย **ไม่เลือกให้อัตโนมัติ เริ่มต้นว่าง** · มีทั้ง 2 ฝ่าย + ช่องค้นหา + จำนวน CC ต่อฝ่าย · สลับฝ่ายแล้วตารางเปลี่ยนตาม |
| UAT-03 | High | both | SIT: TC-002 (re-word) | Laddawan ล็อกอิน · ป้ายในตัวเลือกฝ่ายเป็น **`Pending`** (อังกฤษ ไม่ใช่ `รออนุมัติ`) · ตัวเลขทั้งหมดอ่านอย่างเดียว |
| UAT-04 | Low | - | SIT: TC-004 | ออกจากระบบ แล้วกด Back ของเบราว์เซอร์ ต้องไม่เห็นข้อมูลเดิม |
| UAT-05 | Medium | - | SIT: TC-005 (rewrite) + NEW(U-25) | Session 1 ชั่วโมงหมดอายุ → กล่อง `หมดเวลาการเข้าใช้งาน` · ค่าที่พิมพ์ค้างยังแสดงบนจอแต่ **ต้องไม่ถูกบันทึก** · กด `เข้าสู่ระบบใหม่` แล้วกลับมาที่ฝ่าย+ปีเดิม · **ข้อความ 14 ชั่วโมงในกล่องคือ known issue ห้ามแจ้งเป็น defect** |

### W2 — กรอกงบในตารางหลัก · Module `Budget Entry (Filler)` · 14 cases

| ID | Pri | Dept | Source | Scenario |
|---|---|---|---|---|
| UAT-06 | High | A | SIT: TC-006 | ตารางแสดง 2 ฝั่ง (`ฝั่งผลิต/ต้นทุน 5xxx`, `ฝั่งบริหาร/ขาย SG&A 6xxx`) · 3 ชั้นต่อแถว (SAP · Approved · Pending) · 12 เดือน + `รวมทั้งปี` |
| UAT-07 | High | A | NEW(§D) | ชั้น `Approved` และ `SAP` แสดงข้อมูลของ **ปีที่วางแผน − 1** และป้ายปีบน legend ตรงกัน · ทั้งสองชั้นแก้ไม่ได้ · แถวที่มีแต่ Approved (ไม่มี SAP ไม่มี Pending) ต้องยังปรากฏ |
| UAT-08 | Low | A | NEW(§E) | เดือนที่ข้อมูล SAP ยังไม่ครบแสดง `–` พร้อม tooltip `ข้อมูล SAP เดือนนี้ยังไม่ครบ จึงยังไม่แสดง` · ยอดรวมปีมีข้อความกำกับ `รวมเฉพาะเดือนที่ข้อมูลครบ:` |
| UAT-09 | High | A | SIT: TC-007 | กรอกยอด คลิกออกจากช่อง = บันทึกอัตโนมัติ · refresh หน้าแล้วค่ายังอยู่ |
| UAT-10 | High | A | SIT: TC-008 | ยอด `รวมทั้งปี` + ยอดรวมย่อยต่อกลุ่ม GL + ยอดรวมใหญ่ คำนวณถูกต้อง |
| UAT-11 | Medium | A | NEW(U-11) | เห็นหมายเหตุใต้ toolbar `หมายเหตุ: กรอกได้ตั้งแต่ 100 ขึ้นไป …` ก่อนเริ่มกรอก |
| **UAT-12** | **High** | A | **MERGED** — SIT: TC-011 + TC-012 + TC-013(rewrite) + TC-035(rewrite) + NEW(U-07,U-08,U-09,U-10) | **กติกาช่องกรอกเงิน — เคสเดียว ตาราง `Test Data` 6 บรรทัด ทุกบรรทัดต้องยืนยันผลแยกกัน:** (1) `146` → `100` + กล่องข้อความเด้งมุมจอเรื่องปัดหลักร้อย หายเองใน 6 วินาที · (2) `30` → `0` + ข้อความว่าต่ำกว่า 100 จึงบันทึกเป็น 0 · (3) `999999999` → `100,000,000` + ข้อความเกินเพดาน (**คือการ retest ที่ SIT ขอไว้แล้วไม่เคยทำ — ของเดิมแสดงเป็น infinity**) · (4) `33333.33` → ทศนิยมถูกตัด แล้วปัดหลักร้อย · (5) ตัวอักษร → ไม่รับ · (6) ค่าติดลบ → ไม่รับ · **บันทึกให้ชัดทุกบรรทัดว่ามีข้อความแจ้งเตือนหรือไม่** (SIT ติงว่าบางกรณีไม่แจ้ง) · ยอดรวมต้องขยับตามกติกาใหม่ทุกครั้ง |
| UAT-13 | High | A | SIT: TC-010 | `+ เพิ่ม Transaction`: เว้นช่องบังคับ → ปฏิเสธพร้อมเหตุผลอ่านรู้เรื่อง · เพิ่มแถวซ้ำกับที่มีอยู่ → ปฏิเสธ |
| UAT-14 | High | A | NEW(U-05) | Filler ที่ไม่ได้อยู่ฝ่าย Talent & Culture กด `+ เพิ่ม Transaction` → **ไม่เห็น** GL `5210100150` / `6210100150` ในรายการ · แถวที่มีอยู่แล้วยังแสดงและกรอกได้ตามปกติ |
| UAT-15 | Medium | A | NEW(U-06) | Admin เปิด picker เดียวกัน → **ยังเห็น** GL อบรมและสัมมนา (admin bypass) |
| UAT-16 | High | A | NEW(U-02) | GL `5210400999` / `6210400999` เป็นแถวกรอกยอดตรงในตารางหลัก ไม่มีปุ่มเปิดฟอร์มย่อย · แก้และลบได้เหมือน GL ปกติ |
| UAT-17 | Medium | A | NEW(§L) | ลบแถวที่เพิ่มเอง: ปุ่ม `ลบรายการนี้` + กล่องยืนยันภาษาไทย · แถวที่ระบบสร้างเองต้องไม่มีปุ่มลบ |
| UAT-18 | Low | A | NEW(§K + §M) | ตัวกรอง 5 คอลัมน์ · ลากปรับความกว้างคอลัมน์ + ปุ่ม Reset · ปุ่มเต็มจอ `⤢` และกด Esc ออก · กรอกช่อง Remark แล้วค่าคงอยู่หลัง refresh |
| UAT-19 | Medium | A | NEW(§H) | เลือกปีที่ไม่เปิดรับ (เช่น `Year 2025`) → `+ เพิ่ม Transaction` ปฏิเสธด้วยข้อความอ่านรู้เรื่อง · ปุ่ม Submit ไม่ปรากฏ |

### W3 — ฟอร์มย่อยและทริปเดินทาง · Module `Special GL Subform` · 7 cases

| ID | Pri | Dept | Source | Scenario |
|---|---|---|---|---|
| **UAT-20** | High | A | **MERGED** — SIT: TC-056 + TC-059 | Entertainment 2 รายการ → ตัวเลขขึ้นตารางหลักแบบแก้ไม่ได้ ต้องแก้ผ่านฟอร์มย่อย · เปิดกลับมาเห็นค่าทุกช่องเหมือนเดิม · **และยืนยันว่าหลายรายการภายใต้ GL เดียวถูกเก็บแยกแถว ไม่รวมเป็นก้อนเดียว** (ข้อนี้เดิมเป็นเคส Public Relation & Donation แยกต่างหาก) |
| UAT-21 | High | A | SIT: TC-058 | Professional & Legal Fee: แยก Project กับรายละเอียดเป็นคนละช่อง · แก้ยอดเดือนของรายการเดิม → ยอดตารางหลักขยับตาม · ลบบรรทัดได้ |
| UAT-22 | High | A | SIT: TC-060 + SIT Note ข้อ 3 | Lease & Rental ครบ 4 ช่อง รวมกรณีทะเบียนรถ `อื่นๆ` แล้วพิมพ์เอง · **ตอบคำถามค้างจาก SIT: เว้นช่องรายละเอียดกิจกรรมได้หรือไม่** |
| UAT-23 | High | A | NEW(U-23) + SIT Note ข้อ 2 | เว้นช่องบังคับไว้ 1 ช่องแล้วกดบันทึก → ระบบต้องไม่ยอมบันทึกและระบุช่องที่ขาด · ทดสอบทั้ง Entertainment และ Lease & Rental · **นี่คือข้อร้องเรียนข้อ 2 จาก SIT ที่ยังไม่ปิด** |
| **UAT-24** | High | A | **MERGED** — SIT: TC-061(rewrite) + NEW(U-01, U-22, U-04) | **สร้างทริป 1 ใบ แล้วตรวจ 4 อย่างในรอบเดียว:** (1) พิมพ์ค้นหาปลายทาง (เช่น `Sing`) เลือกจากรายการได้ และเลือกประเทศกลุ่ม 3 `ต่างประเทศ-อื่นๆ` ได้ · (2) ตาราง `B — ค่าใช้จ่าย 3 ประเภท` แสดง **3 แถว** (เบี้ยเลี้ยง / ค่าพาหนะ / ค่าที่พัก) และ **ไม่มี** แถว `ค่าใช้จ่ายเดินทางอื่น 6210400999` · (3) ช่อง `รายละเอียด` พิมพ์ได้จริง กด `บันทึก & ลงบัญชี` ปิดแล้วเปิดกลับมา ข้อความยังอยู่ ยาวได้ถึง 500 ตัวอักษร · (4) ยอดกระจายไปที่ GL คนละแถวในตารางหลัก |
| UAT-25 | High | A | NEW(§F) | **ตรวจยอดเบี้ยเลี้ยงด้วยมือ**: ทริปต่างประเทศ 1 ใบ + ในประเทศ 1 ใบ · คำนวณ `จำนวนวัน × อัตราตามตำแหน่ง × อัตราแลกเปลี่ยน` ด้วยเครื่องคิดเลขแล้วเทียบกับยอดที่ระบบคำนวณ · จดตัวเลขทั้งสองฝั่งลงช่อง Actual Result |
| UAT-26 | Medium | A | NEW(§F) | ทริปข้ามหลายเดือน: เบี้ยเลี้ยงกระจายตามเดือนที่เลือก · แก้จำนวนวัน → คำนวณใหม่ · ลบทริป + กล่องยืนยัน `ลบทริปนี้ทั้งหมด?` |

### W4 — แนบเอกสาร · Module `Attachments` · 5 cases

> ทั้ง wave นี้ **ไม่เคยถูกทดสอบใน SIT เลยแม้แต่เคสเดียว** และไฟล์ไปอยู่บน SharePoint library จริง

| ID | Pri | Dept | Source | Scenario |
|---|---|---|---|---|
| UAT-27 | High | A | NEW(§A) | เปิดปุ่ม `แนบไฟล์` → เห็นรายการไฟล์เดิม · อัปโหลด `.pdf` และ `.xlsx` สำเร็จ · รายการแสดงชื่อ / ขนาด / ผู้อัปโหลด / วันที่ ถูกต้อง |
| UAT-28 | High | A | NEW(§A) | อัปโหลดนามสกุลที่ไม่อนุญาต (เช่น `.docx` หรือ `.zip`) → ปฏิเสธพร้อมข้อความบอกนามสกุลที่รับได้ · อัปโหลดไฟล์ใหญ่กว่า **10 MB** → ปฏิเสธพร้อมข้อความ |
| UAT-29 | Medium | A | NEW(§A) | กดดาวน์โหลด → เปิดแท็บใหม่และได้ไฟล์ที่ถูกต้อง |
| UAT-30 | High | A | NEW(§A) | ลบไฟล์ → มีกล่องยืนยันภาษาไทย · ยืนยันแล้วหายจากรายการ · **การลบย้อนกลับไม่ได้ ให้ลบเฉพาะไฟล์ที่ตัวเองอัปโหลดในรอบนี้เท่านั้น** |
| UAT-31 | Medium | S | NEW(§A) | ผู้ที่เห็นฝ่ายนั้นแต่ไม่ได้เป็นผู้กรอก (เช่น Suchanya บนฝ่ายที่ Pornthip ถืออยู่) → ต้องไม่มีปุ่มอัปโหลดและปุ่มลบ |

### W5 — ส่งขออนุมัติ · Module `Submission / Workflow` · 5 cases

| ID | Pri | Dept | Source | Scenario |
|---|---|---|---|---|
| UAT-32 | High | A | SIT: TC-015 | กด Submit → กล่องยืนยันบอกจำนวนแถวและจำนวน Cost Center · สถานะเปลี่ยนเป็น `Pending · Step 1 (Direct manager)` |
| UAT-33 | High | A | SIT: TC-025 | **ยอดรวมที่ส่งเข้าอนุมัติ = ยอดรวมที่กรอก** · จดตัวเลขก่อนส่งและหลังส่งลงช่อง Actual Result ทั้งสองค่า |
| UAT-34 | High | A | SIT: TC-016 + NEW(§I) | หลัง Submit: ตารางแก้ไม่ได้ · ปุ่มฟอร์มย่อยกลายเป็น 🔒 `อ่านอย่างเดียว — แก้ไม่ได้ในสถานะนี้` และเปิดขึ้นมาแบบกรอกไม่ได้ · `+ เพิ่ม Transaction` ปฏิเสธ · ปุ่มลบแถวหายไป |
| UAT-35 | Medium | A | SIT: TC-026 | กด Submit ซ้ำสำหรับฝ่าย+ปีเดิมไม่ได้ |
| UAT-36 | High | both | NEW(U-16) | Submit แยกทีละฝ่าย: ฝ่ายที่ส่งแล้วขึ้นป้าย `Pending` · **อีกฝ่ายยังเป็น `Draft — not submitted` และยังกรอกได้ตามปกติ** |

### W6 — อนุมัติ 3 ขั้น · Module `Approval` · 9 cases

| ID | Pri | Dept | Source | Scenario |
|---|---|---|---|---|
| **UAT-37** | High | A | **MERGED** — SIT: TC-019 + NEW(U-12, U-20) | **ผู้อนุมัติเปิดฝ่ายที่รออนุมัติ แล้วตรวจหน้าจอทั้งหน้าในครั้งเดียว:** (1) เห็นรายละเอียดงบที่ส่งมาแบบอ่านอย่างเดียว · (2) ปุ่มเป็น **`Reject` / `Approve`** · (3) chip สถานะ = `Pending · Step 1 (Direct manager)` · (4) ป้ายในตัวเลือกฝ่าย = `Pending` ไม่ใช่ `รออนุมัติ` · (5) chip ขั้น 2 และ 3 แสดง `นิภาพร ทองกิ่ง (Senior Associate)` และ `วราพร ติรสิทธิ์ (Assistant Department Head)` |
| UAT-38 | High | A | SIT: TC-021 + TC-022 + NEW(U-13) | กด `Reject` → กล่อง `Reject reason (required)` · ปุ่ม `Confirm Reject` กดไม่ได้จนกว่าจะพิมพ์เหตุผล · มีปุ่ม `Cancel` |
| UAT-39 | High | A | SIT: TC-023 | Filler เห็นเหตุผลที่ถูกตีกลับ · แก้ไขแล้วส่งใหม่ได้ |
| UAT-40 | High | A | SIT: TC-020 + TC-043 + TC-044 | อนุมัติครบ 3 ขั้นตามลำดับ → สถานะเป็น `Approved` · **คำเตือน: สถานะนี้ย้อนกลับไม่ได้ในระบบ ทำเคสนี้เป็นลำดับสุดท้ายของฝ่ายนั้น** |
| UAT-41 | Medium | A | SIT: TC-045 | ผู้อนุมัติขั้น 2 หรือ 3 ตีกลับ → กลับไปหาผู้กรอกโดยตรง ไม่ย้อนทีละขั้น |
| UAT-42 | High | A | SIT: TC-046 | ผู้อนุมัติที่ยังไม่ถึงคิว กดอนุมัติก่อนไม่ได้ (ไม่มีปุ่มให้กด) |
| UAT-43 | High | both | SIT: TC-024 + NEW(U-17) | ผู้อนุมัติเห็นเฉพาะฝ่ายในสิทธิ์ของตน · ถือ 2 ฝ่าย → ตัวเลขนับ `Pending` ถูกต้อง และอนุมัติทีละฝ่ายได้ · ฝ่ายที่ยังไม่ถึงคิวไม่มีปุ่ม Approve |
| **UAT-44** | Medium | A | **MERGED** — NEW(U-15) + SIT: TC-039 | **Admin ทำแทนผู้อนุมัติขั้นที่ 1 ที่ค้าง แล้วตรวจทั้งหน้าจอและอีเมล:** (1) กล่องยืนยันภาษาอังกฤษระบุชื่อผู้อนุมัติที่ถูกข้าม · (2) Admin ทำแทนขั้น 2/3 ไม่ได้ · (3) **อีเมลแจ้ง step override ถูกส่งออกและเนื้อหาถูกต้อง** (ข้อนี้เดิมเป็นเคสอีเมลแยกต่างหาก) |
| UAT-45 | Medium | both | NEW(§B) | โหมด Admin: เปิด/ปิด toggle → รีเซ็ตฝ่ายที่เลือกและเห็นฝ่ายทั้งบริษัท · แถบ `admin-zone` และ tooltip แสดงถูกต้อง (ทดสอบโดย Nipaporn หรือ Waraporn) |

### W7 — อีเมลแจ้งเตือน · Module `Email Alert / Notification` · 5 cases

| ID | Pri | Dept | Source | Scenario |
|---|---|---|---|---|
| UAT-46 | High | A | SIT: TC-036 | Submit → อีเมลถึงผู้อนุมัติขั้นที่ 1 ภายในเวลาที่ยอมรับได้ |
| **UAT-47** | High | A | **MERGED** — SIT: TC-055 + TC-038 | **อีเมลตลอดสาย 3 ขั้น จากการกดอนุมัติชุดเดียวกัน:** (1) อนุมัติขั้น 1 → อีเมล `รอการอนุมัติ` ถึงขั้นที่ 2 · (2) อนุมัติขั้น 2 → อีเมลถึงขั้นที่ 3 · (3) อนุมัติขั้น 3 → **อีเมลแจ้งผู้ส่งว่าอนุมัติครบทุกขั้นแล้ว** (ข้อนี้เดิมเป็นเคสแยกต่างหาก) |
| UAT-48 | High | A | SIT: TC-037 | Reject → อีเมลถึงผู้ส่ง พร้อมเหตุผลที่พิมพ์ไว้ |
| UAT-49 | High | A | SIT: TC-047…TC-054 **MERGED** | ตรวจเนื้อหาอีเมลฉบับใดฉบับหนึ่งเป็น checklist 8 ข้อในเคสเดียว: (1) ผู้ส่งเป็น `CMAN_PowerBI` (2) To / CC ถูกคน (3) หัวข้อถูกรูปแบบ (4) เนื้อหามี ฝ่าย / ปีงบ / สถานะ ครบ (5) ลิงก์ `คลิกที่นี่เพื่อดูรายละเอียด` เปิดหน้าถูก (6) ภาษาไทยไม่เพี้ยน (7) เข้า Inbox ไม่ตก Junk (8) ปีงบในอีเมลคือ 2027 ตรงกับจอที่แสดง `Year 2026` · **ให้เปิดบนมือถือด้วย 1 ครั้ง** (SIT ค้างข้อนี้ไว้) |
| UAT-50 | Medium | A | NEW(U-14) | อีเมล **ยังเป็นภาษาไทย** ขณะที่หน้าจออนุมัติเป็นภาษาอังกฤษ → **ผู้ใช้ตัดสินและบันทึกคำตอบในช่อง Remarks ว่ารับสภาพนี้ได้ หรือต้องแปลอีเมลด้วย** |

### W8 — หน้าตาและกติกาที่ต้องยอมรับ · Module `Business Rules & UI` · 4 cases

| ID | Pri | Dept | Source | Scenario |
|---|---|---|---|---|
| **UAT-51** | Medium | - | **MERGED** — NEW(U-21) + SIT: TC-028 + SIT Note ข้อ 4 | **กวาดตาดูทุกหน้าจอรอบเดียว ทั้ง Chrome และ Edge** (SIT ยังไม่มีคนตรวจ Edge): (1) ชุดสี CI จริง (เขียว `#00805e`, กรมท่า `#1b3564`) อ่านชัดทั้งตาราง ปุ่ม ป้ายสถานะ ฟอร์มย่อย · (2) ข้อความไทยแสดงครบ ไม่ถูกตัดหาย · (3) **ยอดตัวเลขยาว ๆ ไม่ทับกัน** (ข้อค้างจาก SIT Note ข้อ 4) |
| UAT-52 | Medium | - | SIT: TC-029 | ข้อความ error บอกสาเหตุและวิธีแก้ ไม่แสดง stack trace หรือศัพท์เทคนิคให้ผู้ใช้ |
| UAT-53 | High | A | NEW(U-03) | **เงินต้องไม่หายเงียบ**: กรอกยอดในช่อง `6210400999` ของ Cost Center หนึ่ง แล้วลบทริปใน Cost Center + ปีเดียวกัน → ยอดในช่องนั้นต้องไม่หายและไม่กลายเป็น 0 |
| UAT-54 | Medium | A | NEW(U-24) | เปลี่ยนอัตราแลกเปลี่ยนใน master → ฟอร์มย่อยแสดงยอดใหม่ทันที แต่ตารางหลักยังเป็นยอดเดิมจนกดบันทึกซ้ำ · **ผู้ใช้ต้องเซ็นรับทราบว่ายอมรับพฤติกรรมนี้** (ตัดสินไปแล้ว 2026-08-21 ว่าไม่แก้ ไม่ต้องแจ้งเป็น defect) |

### Cut outright — do NOT include

`SIT: TC-034` แก้พร้อมกัน 2 หน้าต่าง (concurrent edit). jakkaritw ตัดสินเมื่อ 2026-08-20 ว่าผ่าน
และยกเว้น 3 ใน 4 กรณีย่อย เพราะตัวเลขอัปเดตให้ทันทีอยู่แล้ว โอกาสพลาดน้อยมาก. Record it in the
companion doc's out-of-scope section with that reason; do not create a case row for it.

## `UAT_Test_Script.md` — the Thai companion

Written for a business reader who was not in any of these sessions. Required sections:

1. **UAT คืออะไรและรอบนี้ทดสอบอะไร** — 5 บรรทัด
2. **ข้อควรระวัง 4 ข้อ** — the same four warnings as sheet 1, spelled out
3. **ใครทำอะไร** — the role table above, with each person's departments
4. **8 ระลอก (waves) และลำดับการทดสอบ** — one line per wave saying what it proves and roughly
   how long it takes; state plainly that waves run in order because W5 locks what W2–W4 created
   and W6 ends in an irreversible `Approved`
5. **วิธีกรอกผลลงไฟล์ Excel** — which columns the tester fills, what each Status means, when to
   open a row on `4. Defects`. Say explicitly that a **merged case is one row but several checks**,
   so a tester must read the whole Expected Result before marking Pass.
6. **สิ่งที่ตัดออกจากรอบนี้โดยตั้งใจ (Out of scope / NOT applied)** — list, with the reason:
   Security module (TC-031/032/033), การส่งออก Excel/PDF (TC-027 — ยังไม่มีในระบบเวอร์ชันนี้),
   แก้พร้อมกัน 2 หน้าต่าง (TC-034 — ตัดสินแล้ว 2026-08-20 ว่าผ่าน), เคสที่ตัดสินผลได้เฉพาะจากการ
   อ่าน SQL หรือ log, หน้าจอตอนไม่มีสิทธิ์เลย (no-scope) เพราะต้องแก้ master จริง, deep link
   ข้ามฝ่าย, `/sit/impersonate`, `GET /budget/sap-coverage` (dead code), การกระทบยอด SAP กับ SAP,
   การล็อก GL ที่ `edit_by='admin'`
7. **สิ่งที่ยังไม่ได้ตัดสิน (ยังไม่ทำ ไม่ใช่ตั้งใจไม่ทำ)** — วันเริ่ม/วันจบรอบ, เกณฑ์ผ่าน/ไม่ผ่าน
   (entry/exit criteria), ใบเซ็นรับรองผล, คู่มือ 1 หน้า 2 ฉบับ — ติดอยู่ที่การตัดสิน D7 บนแผนที่
   `.scratch/uat-prep/MAP.md`
8. **ที่มาของแต่ละเคส** — a table `UAT-xx → SIT TC-xxx / ใหม่` so a returning SIT tester can see
   what carried over, with merged cases listing every SIT id they absorbed. Generate it from the
   same data the workbook uses; do not hand-type it.

## `validate_uat_pack.py` — must assert and print PASS/FAIL per check

1. 4 sheets present with the expected names
2. header row is row 2 on `2. Test Cases`; data starts row 3 (no `TC-EX` row)
3. exactly **54** data rows, ids `UAT-01`…`UAT-54` contiguous, no duplicates
4. every Summary range ends at the real last data row (parse the formula strings; fail on any
   literal `$64`)
5. the 8 module names in the Summary breakdown exactly equal the distinct modules used in
   `2. Test Cases`, and the per-module totals sum to **54**
6. every DV list present on the columns that need one, covering the real used range
7. the production URL appears in sheet 1 and the staging hostname `cman-budget-web-stg`
   appears **nowhere** in the workbook
8. `UAT_Test_Script.md` exists and its `UAT-xx → SIT` table has **54** rows
9. **coverage check** — every one of these SIT ids appears somewhere in the Source/traceability
   data: TC-001, 002, 004, 005, 006, 007, 008, 010, 011, 012, 013, 015, 016, 019, 020, 021, 022,
   023, 024, 025, 026, 028, 029, 035, 036, 037, 038, 039, 043, 044, 045, 046, 047, 048, 049, 050,
   051, 052, 053, 054, 055, 056, 058, 059, 060, 061. And every one of U-01…U-25 appears except
   none — all 25 must appear. Fail loudly if any is missing; the de-duplication pass must not
   have dropped coverage.

Write the validator's output to a file and print only the compact PASS/FAIL summary
(Windows console is cp1252 — run everything with `python -X utf8`, and every `open()` passes
`encoding="utf-8"`).

## Constraints

- **Never install anything.** `openpyxl` is already available.
- Every `open()` gets `encoding="utf-8"`. Run scripts as `python -X utf8 <file>.py`.
- Do not pipe multi-line Python through the shell; write `.py` files and run them.
- Do not upload anything to SharePoint. Do not run `az` commands that mutate.
- Do not commit. Report what you changed and let the main session handle git.
- Report back: files written, the validator's PASS/FAIL lines, and anything in the brief you
  could not do.
