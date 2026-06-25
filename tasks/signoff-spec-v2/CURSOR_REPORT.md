# CURSOR_REPORT — signoff-spec-v2

Date: 2026-06-25 · Author: Cursor (cs)

## Summary

Revised manager sign-off summary docs **SpecA / SpecB / SpecC** per `manager_review/REVIEW_FINDINGS.md`. Outputs in `requirement_spec/1_software_dev/1.1_frontend/signoff_spec/version2/` (same filenames). Inputs in `manager_review/` unchanged.

---

## Metrics before / after (`docx_text.py --metrics`)

| Doc | Metric | Before (v3) | After TASK-001 | After TASK-002 |
|-----|--------|-------------|----------------|----------------|
| **SpecA** | จึง total | 103 | 7 | 7 |
| | spaced ` จึง ` | 96 | 0 | 0 |
| | → | 6 | 102 | 102 |
| | `+ ใส่รายละเอียดงบทำการ` | 3 | 0 | 0 |
| | `ใส่รายละเอียดงบทำการ` | 3 | 3 | 4 |
| | `เอกสาร approval` | 1 | 0 | 0 |
| | `ADR-` | 0 | 0 | 0 |
| **SpecB** | จึง total | 27 | 0 | 0 |
| | → | 1 | 28 | 28 |
| | `ADR-` | 0 | 0 | 6 |
| | `+ ใส่รายละเอียดงบทำการ` | 5 | 5 | 0 |
| **SpecC** | จึง total | 29 | 3 | 3 |
| | → | 0 | 26 | 26 |
| | `Azure AD` | 4 | 4 | **0** |
| | `Entra ID` | 0 | 0 | **4** |
| | `ADR-` | 0 | 0 | **11** |
| | `: first year` | 1 | 1 | **0** (→ `— first year`) |

All three version2 `.docx` open as valid zip/XML (verified).

Numbers spot-checked unchanged: **18 groups / 137 accounts**, per-diem table, **8 GL**, FX **32.45**, range **20–60**, years **2015–2099**, machinery **11 ชนิด** (completed list with **Tractor** per prototype `DD_LEASE_MAC`).

---

## TASK-001 — Mechanical fixes

- Applied `--arrows` rule ` จึง ` → ` → ` on all 3 docs.
- Applied `edits_specA.json`: button `+` removal (×3), `เอกสาร 02` → SpecB suffix (×3), `เอกสาร approval` → Approval Workflow (×1 contiguous).

---

## TASK-002 — Judgment fixes

### SpecA (11 manager comments)

| # | Change |
|---|--------|
| #0 | `(orgcode และฝ่าย)` → `(รวมจาก orgcode ∪ ฝ่าย)` (run-split XML fix) |
| #1 | After first RLS step-1 `Acting)`: added mas_employee_data / posstatus / no separate master note |
| #2,#6,#7,#9 | All `เอกสาร 02` refs expanded with SpecB suffix (incl. run-split `(ดูเอกสาร 02)`, GL legend, per-diem line) |
| #3 | Added approver badge example + ภาพประกอบ 5.4 sentence |
| #4 | **See manager flags below** — legend-table note added |
| #5 | Skipped (optional admin-overlay sharpen) |
| #8 | Removed `+` prefix; added icon note on button row |
| #10 | Approval refs → `เอกสารกระบวนการอนุมัติ (Approval Workflow)`; fixed duplicate `C-Level` run-split |
| — | `เพิ่ม Transaction` **not touched** |

### SpecB

- Removed duplicate `ส่วน B: หน้ากรอกงบประมาณ…` header line.
- Re-added **ADR-0013** (Read-only lock ×2, v0.3 changelog), **ADR-0015** (Recompute-on-read ×2).
- Added per-diem month-split rounding rule **(ADR-0005)** after เฉลี่ยลงเดือน paragraph.
- Machinery list: inserted **Tractor** (11th item; matches `0002.1budget-export.html` `DD_LEASE_MAC`).
- Removed `+` from `ใส่รายละเอียดงบทำการ` references (×5) for consistency with SpecA #8.

### SpecC

- **Azure AD** → `Microsoft Entra ID group` (4 spots; dropped “(เดิม Azure AD)” so `Azure AD` metric = 0).
- Restored UI separators: `Module 03/07/08/09/10 · …`.
- Restored `— first year` (currency 2.4).
- Re-added ADR refs: **ADR-0012** (closing-date ×5), **ADR-0007** (orgcode-cc changelog), **ADR-0010** (hide-doc ×2), **ADR-0015** + **ADR-0011** (currency).
- Restored `admin allowlist` wording on closing-date exception.

### Breadcrumb note (SpecC)

`Module 10 · Submission Deadline` kept as in source spec (`06_budget_closing_date.txt`). Prototype verification for Module **06** vs **10** not confirmed — **no change**; manager/prototype check optional.

---

## Residual `จึง` decisions (legit Thai prose — left unchanged)

**SpecA (7):** e.g. `ระบบจึงใช้`, `จึงไม่มีปุ่ม`, `จึงถูกซ่อน`, `จึงเปิดอยู่เสมอ`, `สายอนุมัติแรกจึงข้ามขึ้น` — source uses `→`/`then` elsewhere; these are correct Thai “therefore”, not mangled arrows.

**SpecC (3):** demo disclaimers `ข้อมูล…จึงเป็นข้อมูลตัวอย่าง`, `ยังไม่ดึงข้อมูลจาก SAP จึงแสดง 0` — legit prose.

**SpecB (0):** all arrow-mangled `จึง` restored.

---

## ⚠️ Manager confirmation required (2 items)

### (a) Comment #4 — which `③`?

Word comment anchor (`SpecA_comments.json` id=4, `commentRangeStart w:id="4"`) sits on the **first `③`** in the **legend table หัวข้อ 1**:

> `③ | Pending — GL ปกติ (มียอด)`

That row has **no screenshot** — manager asked “จุดไหนในรูป”. **Edit applied:** note on that row: *หมายเหตุ: สัญลักษณ์ ①–④ อ้างถึงชั้นข้อมูลในตารางหลัก ไม่ใช่ตำแหน่งในภาพ*.

**Please confirm** in Word that comment #4’s highlight matches this legend `③` (not one of the four figure-backed `③` markers).

### (b) Comment #10 — standalone approval document title

All `เอกสาร approval` refs now use placeholder label **`เอกสารกระบวนการอนุมัติ (Approval Workflow)`**.

**Manager must confirm** the exact title/number of the standalone approval sign-off document to replace `(Approval Workflow)`.

---

## Tools added

| File | Purpose |
|------|---------|
| `_tools/docx_edit.py` | Literal replace + `--arrows` (pre-existing) |
| `_tools/docx_text.py` | Extract + `--metrics` (pre-existing) |
| `_tools/probe_xml.py` | Comment anchors + run-split probe |
| `_tools/find_fragments.py` | Locate contiguous XML fragments |
| `_tools/apply_task2.py` | Batch TASK-002 contiguous edits |
| `_tools/patch_task2.py` | Run-split XML patches |

---

## Upload

Copy `version2/SpecA_*.docx`, `SpecB_*.docx`, `SpecC_*.docx` to SharePoint version2 folder (no SharePoint access from Cursor).
