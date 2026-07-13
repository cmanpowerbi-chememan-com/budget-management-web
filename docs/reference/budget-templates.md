# Reference — Budget Input Templates

Operational reference for the budget-input template structures: which templates exist, who
fills them, their column layouts, and the sub-template linkages. This is a **structure
lookup sheet** — the *why* of any behavior lives in the ADRs and is linked, not restated.

- **Term definitions** (Cost Center, GL group, ฝ่าย, etc.): see `CONTEXT.md`.
- **Special-GL detail editors** (the six groups that open "+ ใส่รายละเอียดงบทำการ"): full
  dropdown/column spec in `docs/13Template Special/_dropdown_summary.md`.
- **Source of truth for column shapes:** `01requirement_detail.xlsx` and the master files
  under `02docs/` and `docs/13Template Special/`. Canonical mockup:
  `design/mockups/0002claude design/0002.2budget-export.html` (main page + special-GL
  subforms — sole surviving mockup; 0002.1 and the standalone `0012-main-table-demo.html`
  were removed, superseded by this file).

---

## Templates overview

| Template | Type | Who fills | Notes |
|----------|------|-----------|-------|
| 1.1 Main | Budget per GL Account per month | Each dept user | Budget & Actuals by สายงาน (business line) |
| 1.2 Oversea Trip | Detail breakdown | Dept user | Sub-template |
| 1.2 Lease & Rental | Detail breakdown | Dept user | Sub-template |
| 1.2 Fuel (ค่าน้ำมัน) | Detail breakdown | Dept user | Sub-template |
| 1.2 Professional & Legal Fee | Detail breakdown | Dept user | Sub-template |
| 2. Budget dept template | Batch upload | Budget dept only | "งบประมาณกำหนดเอง" — no approval chain (see approval-workflow.md) |

> **Consolidation rule:** data from Template 1.1 + Template 2 are merged into one combined
> data file ("ไฟล์รวม Data") for reporting and dashboards.

---

## Template 1.1 Main — column structure (33 cols)

**Template name:** งบทำการ - ค่าใช้จ่ายอื่น · **Header fields:** สายงาน (Business Line), หน่วยงาน (Department)

| Group | Column | Description | Editable |
|-------|--------|-------------|:---:|
| Key | รหัสบัญชี | GL Account Code | No |
| Key | ชื่อบัญชี (ภาษาไทย) | GL Account Name (Thai) | No |
| Reference | Approved (งบอนุมัติ, prior year) | Prior year approved budget | No |
| Reference | Actuals Jan-Aug 25 (บาท) | YTD actuals — auto from SAP | No |
| Actuals | ม.ค.–ธ.ค. (12 cols) | Monthly actuals — auto from SAP | No |
| Budget Input | Template 2026 (บาท) | Next-year total (auto-sum) | No |
| **Budget Input** | **ม.ค.–ธ.ค. (12 cols)** | **Monthly budget** | **Yes — USER FILLS** |

User edits **only** the 12 monthly budget cells; the yearly total is auto-summed; all
reference/actuals columns are read-only.

### GL groups in Template 1.1 and their sub-template link

| GL Group | Sub-template link |
|----------|------------------|
| Communication Expense | — |
| Electricity & Water | — |
| Entertainment | — special-GL detail editor (see `_dropdown_summary.md`) |
| Lease & Rental | → ชีท "Lease & Rental" |
| Office Expenses | — |
| Other Admin. Expenses | Fuel items → ชีท "ค่าน้ำมันเชื้อเพลิง" |
| Other Manpower Expenses | — |
| Personal Expenses | — |
| Professional & Legal Fee | → ชีท "Professional & Legal Fee" |
| Repair & Maintenance | — |
| Travelling Expense | Oversea items → ชีท "Oversea Trip" |

> "Oversea Trip" and "Fuel" are **sub-templates** (detail input sheets), NOT GL groups —
> their GL accounts belong to Travelling Expense and Other Admin. Expenses respectively.

---

## ไฟล์รวม Data — combined data file (27 cols, sheet: ไฟล์รวม Data)

| # | Column | ตัวอย่าง | หมายเหตุ |
|---|--------|---------|---------|
| 1 | ค่าใช้จ่าย | ค่าพาหนะเดินทางต่างประเทศ | GL Account name |
| 2 | รหัสบัญชี | 6210400020 | GL Account code |
| 3–14 | ม.ค.–ธ.ค. | ยอดรายเดือน (12 cols) | — |
| 15 | Y2026 | ยอดรวมทั้งปี | auto-sum |
| **16** | **Template** | **`Opex` / `งบประมาณกำหนดเอง`** | **key แยกที่มา** |
| 17 | C-Level | Chief Technology Officer | — |
| 18 | Division | Maintenance Services Division | สายงาน |
| 19 | Department | Vehicle & Mobile Equipment | หน่วยงาน |
| 20 | ประเภทค่าใช้จ่าย | SGA / Indirect OH cost | — |
| 21 | Grouping | Travelling Expense | GL Group name |
| 22 | ประเภทค่าใช้จ่าย (SGA) | Admin expenses | — |
| 23 | Plant | KK | fixed |
| 24 | Cost center | 10MN010000 | — |
| 25 | Remark (Explanation) | เบี้ยประกันภัย กท 52-3381 | Template 2 มี; Template 1.1 = NULL |

> **Template 2 monthly input:** user กรอก ม.ค.–ธ.ค. รายเดือนได้; Y2026 = auto-sum — ไม่ใช่ยอดรวมปีเท่านั้น.

---

## Template 1.2a Oversea Trip — sheet structure (rows 2–131)

**Header:** Template name + สายงาน + Exchange rate (USDTHB). Sheet = **1 ตารางหลัก + 4 ตารางย่อย**.

### ตารางหลัก — Trip Planning (rows 6–27)

| Column | รายละเอียด |
|--------|------------|
| หน่วยงาน | Department |
| ปลายทาง | Destination |
| รายชื่อผู้เดินทาง | Traveler name |
| วัตถุประสงค์การเดินทาง | Travel purpose |
| ค่าเบี้ยเลี้ยง/วัน (USD) | Daily allowance rate (USD) |
| จำนวนวัน ต่อทริป | Days per trip |
| จำนวนทริป | Number of trips |
| ม.ค.–ธ.ค. | Monthly trip count (12 cols) |

### 4 ตารางย่อย (คำนวณยอดเป็นบาท — GL Account + รวม + รายเดือน)

| ตาราง | Row | GL Account | คอลัมพิเศษ |
|-------|-----|-----------|------------|
| ค่าเบี้ยเลี้ยง | 30–54 | 6210400010 | — |
| ค่าตั๋วเครื่องบิน | 55–79 | — | Flight Details, ค่าตั๋ว/ทริป |
| ค่าที่พัก | 80–104 | 6210400030 | — |
| ค่าใช้จ่ายเดินทางอื่น | 105–131 | — | รายละเอียด (แทน รายชื่อผู้เดินทาง) |

> **DB note:** each sub-table has its own GL Account — store rows split by expense_type
> (เบี้ยเลี้ยง / ตั๋วเครื่องบิน / ที่พัก / อื่น). ค่าตั๋วเครื่องบิน has an extra "Flight Details" field.

**Per-diem / FX behavior is a decision — see `.claude/project-context.md` ("Travelling
Expense") and ADR-0015:** per-diem = `days × rate(position, country-group) × FX(year)`,
**recompute-on-read** (not snapshot), with the year's rate from the Currency Master (Module
09). The OPEX page shows FX read-only. The entry model is **GL-split: 1 GL = 1 expense-type ×
1 accounting side = 8 GL** — do not restate the rationale here.

---

## Template Opex in React — main Submit Budget page (structure)

UI = table grouped by GL Group, each GL Account with its reference data + monthly input cells.

- Read-only columns: รหัสบัญชี, ชื่อบัญชี, prior-year Approved, Actuals.
- Editable: ม.ค.–ธ.ค. (12 cols) only.
- Yearly total (Template 2026) = auto-sum in frontend before render.
- A GL linked to a sub-template renders read-only + a button to navigate to the sub-template
  route; special-GL groups open a detail subform instead of typing monthly amounts directly.

**Save / Submit / Deadline are decisions — see the ADRs / project-context (don't restate):**
- Auto-save draft (no manual Save button), shared draft keyed `(cost_center, gl_account,
  fiscal_year)`, optimistic lock, lean warn-don't-block validation —
  `.claude/project-context.md` ("Budget submission form").
- Submit enters the approval chain (status → `PENDING_APPROVER1`); approval surface is the
  main page — **ADR-0006 / ADR-0008 / ADR-0016**; see `docs/reference/approval-workflow.md`.
- Deadline lock per `fiscal_year`, admin override, auto-submit DRAFT at cutoff —
  `.claude/project-context.md` ("Deadline lock") + **ADR-0009 / ADR-0012**.

> **Persistence note:** the transactional store is **Microsoft Fabric SQL Database**, not
> Azure SQL Database (retired) — **ADR-0017**.
