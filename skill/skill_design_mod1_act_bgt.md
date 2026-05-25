# Design Prompt — Module 1: Actual / Budget Table (This Year)

## Context
Internal OPEX budget management web app for a Thai company (CMAN).  
This table is the core read-only view showing either **Actuals** or **Budget** figures per GL Account per month for the current fiscal year (January–December).

---

## What to Design

A **data table component** embedded inside a dashboard page.  
The table shows OPEX expenses grouped by GL Account Group → GL Account, with monthly columns across the top.

---

## Table Structure

### Y-Axis (Rows) — 2-layer hierarchy

**Layer 1 — GL Group header row** (visually bigger/bolder, acts as a section separator):
- Spans full width or is indented as a group label
- Examples: `Communication Expense`, `Electricity & Water`, `Entertainment`, `Lease & Rental`, `Office expenses`, `Other admin. Expenses`, `Other manpower expenses`, `Personal expenses`, `Professional & Legal Fee`, `Repair & Maintenance`, `Travelling Expense`
- Should show a **subtotal** for the group (sum of all GL accounts under it, for each month)
- Total row at the very bottom summing all groups

**Layer 2 — GL Account rows** (indented under each group):
- 2 fixed columns: `รหัสบัญชี` (GL Code, e.g. `6210600010`) + `ชื่อบัญชี` (GL Name in Thai, e.g. `ค่าโทรศัพท์ / ค่าโทรศัพท์มือถือ`)
- GL Code is monospace, shorter; GL Name is the main label

**Real data example (from actual template):**

```
▼ Communication Expense                [subtotal row]
    6210600010  ค่าโทรศัพท์ / ค่าโทรศัพท์มือถือ
    5210600020  ค่าเช่า/บริการ วงจรสื่อสาร
    5210900060  ค่าไปรษณีย์

▼ Electricity & Water                  [subtotal row]
    5210500020  ค่าน้ำประปา

▼ Entertainment                        [subtotal row]
    6211900030  ค่าเลี้ยงรับรอง (ภายนอก)
    6211900031  ค่าเลี้ยงรับรอง (ภายใน)

▼ Lease & Rental                       [subtotal row]
    5211200030  ค่าเช่า - เครื่องจักร,อุปกรณ์โรงงาน
    5211200040  ค่าเช่า - อุปกรณ์สำนักงาน
    5211200060  ค่าเช่า - ยานพาหนะ

▼ Office expenses                      [subtotal row]
    6211400999  ค่าธรรมเนียมอื่น (วีซ่าเดินทาง)
    5210900010  ค่าจัดส่งเอกสาร
    5210900999  ค่าบริการอื่นๆ
    5211800010  เครื่องเขียนแบบพิมพ์
    5211800020  วัสดุสิ้นเปลืองเกี่ยวกับการทำความสะอาด
    5211800030  อุปกรณ์และเครื่องใช้สำนักงาน (มูลค่า < 5,000 บาท)
    5211800040  วัสดุสิ้นเปลืองสำนักงาน-โรงงาน
    5211800050  วัสดุสิ้นเปลืองเกี่ยวกับการรักษาความปลอดภัย
    5211800060  วัสดุสิ้นเปลืองเกี่ยวกับห้องทดลอง
    5211800070  วัสดุสิ้นเปลืองเกี่ยวกับการดูแลสวน,ต้นไม้

▼ Other admin. Expenses                [subtotal row]
    5120300020  ค่าน้ำมันเชื้อเพลิง
    5120300030  ค่าวัสดุและบรรจุภัณฑ์ (Packaging Used)
    5210500030  ค่าน้ำบาดาล
    5210900020  ค่ารักษาความปลอดภัย
    5210900030  ค่าบริการกำจัดของเสีย
    5210900040  ค่าบริการบรรจุปูน
    5211400010  ค่าวารสารและสมาชิก
    5211400020  ค่าปรับอื่นๆ
    5211400999  ค่าธรรมเนียมอื่น
    5211900040  ค่าใช้จ่ายในการจัดประชุม
    5211900060  ค่าใช้จ่ายเกี่ยวกับรถยนต์นั่ง

▼ Other manpower expenses              [subtotal row]
    5210100090  ค่ายูนิฟอร์ม
    5210100110  ค่าตรวจสุขภาพประจำปี
    5210400010  เบี้ยเลี้ยง
    6210400010  เบี้ยเลี้ยงต่างประเทศ

▼ Personal expenses                    [subtotal row]
    6210100140  ค่าใช้จ่ายในกิจกรรมของบริษัท (งานกีฬา, ปีใหม่)

▼ Professional & Legal Fee             [subtotal row]
    5210700010  ค่าจ้างที่ปรึกษา - วิจัยและพัฒนาผลิตภัณฑ์
    5210700020  ค่าจ้างที่ปรึกษา - ด้านเทคนิค
    5210700999  ค่าจ้างที่ปรึกษา - อื่นๆ
    5211900020  ค่าใช้จ่ายเกี่ยวกับ ISO

▼ Repair & Maintenance                 [subtotal row]
    5211100060  ค่าซ่อมบำรุง - เฟอร์นิเจอร์
    5211100070  ค่าซ่อมบำรุง - เครื่องใช้สำนักงาน
    5211100080  ค่าซ่อมบำรุง - คอมพิวเตอร์

▼ Travelling Expense                   [subtotal row]
    5210400020  ค่าพาหนะเดินทางต่างประเทศ
    5210400030  ค่าที่พักต่างประเทศ
    5210400999  ค่าใช้จ่ายเดินทางอื่นต่างประเทศ
    6210400020  ค่าพาหนะเดินทาง
    6210400030  ค่าที่พัก
    6210400999  ค่าใช้จ่ายเดินทางอื่น

══════════════════════════════════════
  GRAND TOTAL                         [total row]
```

---

### X-Axis (Columns) — 12 months + YTD total

| Column | Thai Label | Note |
|--------|-----------|------|
| ม.ค. | January | |
| ก.พ. | February | |
| มี.ค. | March | |
| เม.ย. | April | |
| พ.ค. | May | |
| มิ.ย. | June | |
| ก.ค. | July | |
| ส.ค. | August | |
| ก.ย. | September | |
| ต.ค. | October | |
| พ.ย. | November | |
| ธ.ค. | December | |
| รวม (YTD) | Year Total | auto-sum Jan–Dec, pinned last col |

**Value format:** Thai Baht, no decimals, thousands separator  
Example: `1,234,500` (no ฿ symbol in cell — show in header only)

---

## Filters (above the table)

```
[ สายงาน ▼ ]   [ หน่วยงาน ▼ ]   [ Actual | Budget ] toggle
```

- **สายงาน** (Division) — dropdown, single select, required
- **หน่วยงาน** (Department) — dropdown, cascades from สายงาน, single select
- **Actual / Budget** — pill toggle or segmented button (2 options only)
- Filters apply instantly on change (no submit button)

---

## Visual Design Requirements

### Must feel: **clean, easy on the eyes, professional — not spreadsheet-heavy**

1. **GL Group rows** — visually distinct from GL account rows:
   - Slightly darker background (e.g. soft blue-gray or warm gray)
   - Bold text, slightly larger font
   - Left-aligned group name spanning label columns
   - Collapse/expand chevron (▼/▶) — groups start expanded
   - Monthly subtotals shown in group row

2. **GL Account rows** — clean, alternating row background (white / very light gray)
   - GL Code: monospace font, muted color (e.g. `#6B7280`), narrower column
   - GL Name: regular weight, Thai font friendly
   - Monthly values: right-aligned, tabular numbers

3. **Grand Total row** — pinned at bottom, bold, stronger background (matches header)

4. **Month columns** — equal width, right-aligned values, header row shows Thai month abbreviation
   - Current month column: subtle highlight (e.g. soft yellow or blue tint) to show "we are here"
   - YTD total column: slightly separated by a light divider line

5. **Zero / no-spend values** — show as `—` (em dash) instead of `0` to reduce visual noise

6. **Scrolling** — horizontal scroll for months if screen is narrow; first 2 columns (GL Code + GL Name) should be **sticky/frozen** on the left

7. **Toggle Actual/Budget** — when switching, animate the value change (fade or slide); add a subtle badge/label on the table header showing which mode is active

8. **Typography** — use a clean sans-serif that renders Thai script well (e.g. Noto Sans Thai, Sarabun, or IBM Plex Sans Thai)

9. **Color palette** — suggest a calm blue-white palette (corporate but not cold). Avoid heavy borders — use whitespace and subtle backgrounds to separate rows instead.

---

## Responsive Behavior

- Desktop (primary): full table with all 12 months visible
- Tablet: horizontal scroll kicks in, first 2 columns frozen
- Do NOT design for mobile — this is an internal desktop-first tool

---

## Additional Notes

- This is a **read-only view** — no editing in this table
- Data volume: ~52 GL accounts across 11 groups (one division's data)
- Thai text in GL Name can be long (40–50 chars) — allow wrapping or truncate with tooltip
- Table header: show currently selected สายงาน + หน่วยงาน + fiscal year as context  
  Example: `สายงาน: Maintenance Services Division | หน่วยงาน: Vehicle & Mobile Equipment | ปี 2026`

---

## Mock Data (use this to populate the design — Actual mode, ปี 2026)

**Filter context:** สายงาน = Maintenance Services Division | หน่วยงาน = Vehicle & Mobile Equipment

Values in Thai Baht (฿), no decimals. Current month = May (พ.ค.).  
Months Jun–Dec are future → show `—` (not yet incurred).

```
GL Group / GL Account                        ม.ค.      ก.พ.      มี.ค.     เม.ย.     พ.ค.      มิ.ย.  ก.ค.  ส.ค.  ก.ย.  ต.ค.  พ.ย.  ธ.ค.   รวม YTD
─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
▼ Communication Expense (subtotal)           12,400    11,800    13,200    10,500    12,900     —      —     —     —     —     —     —      60,800
  6210600010  ค่าโทรศัพท์ / ค่าโทรศัพท์มือถือ  8,500     8,200     9,100     7,300     8,600     —      —     —     —     —     —     —      41,700
  5210600020  ค่าเช่า/บริการ วงจรสื่อสาร        3,500     3,500     3,500     3,200     3,500     —      —     —     —     —     —     —      17,200
  5210900060  ค่าไปรษณีย์                         400       100       600        —         800     —      —     —     —     —     —     —       1,900

▼ Electricity & Water (subtotal)             45,200    38,700    52,100    41,800    47,300     —      —     —     —     —     —     —     225,100
  5210500020  ค่าน้ำประปา                       45,200    38,700    52,100    41,800    47,300     —      —     —     —     —     —     —     225,100

▼ Entertainment (subtotal)                      —       5,800        —      12,400       —       —      —     —     —     —     —     —      18,200
  6211900030  ค่าเลี้ยงรับรอง (ภายนอก)             —       5,800        —      12,400       —       —      —     —     —     —     —     —      18,200
  6211900031  ค่าเลี้ยงรับรอง (ภายใน)               —         —          —          —         —       —      —     —     —     —     —     —         —

▼ Lease & Rental (subtotal)                 128,000   128,000   128,000   128,000   128,000     —      —     —     —     —     —     —     640,000
  5211200030  ค่าเช่า - เครื่องจักร,อุปกรณ์       80,000    80,000    80,000    80,000    80,000     —      —     —     —     —     —     —     400,000
  5211200040  ค่าเช่า - อุปกรณ์สำนักงาน           18,000    18,000    18,000    18,000    18,000     —      —     —     —     —     —     —      90,000
  5211200060  ค่าเช่า - ยานพาหนะ                  30,000    30,000    30,000    30,000    30,000     —      —     —     —     —     —     —     150,000

▼ Office expenses (subtotal)                 23,400    19,850    31,200    18,700    25,600     —      —     —     —     —     —     —     118,750
  6211400999  ค่าธรรมเนียมอื่น (วีซ่าเดินทาง)       —         —       4,500        —         —       —      —     —     —     —     —     —       4,500
  5210900010  ค่าจัดส่งเอกสาร                     1,200       800     1,400       950     1,100     —      —     —     —     —     —     —       5,450
  5210900999  ค่าบริการอื่นๆ                      5,200     4,500     6,300     4,200     5,800     —      —     —     —     —     —     —      26,000
  5211800010  เครื่องเขียนแบบพิมพ์                3,400     2,800     4,100     2,600     3,200     —      —     —     —     —     —     —      16,100
  5211800020  วัสดุสิ้นเปลืองทำความสะอาด           4,800     4,200     5,100     4,000     4,900     —      —     —     —     —     —     —      23,000
  5211800030  อุปกรณ์และเครื่องใช้สำนักงาน         6,200     5,350     7,200     4,850     7,400     —      —     —     —     —     —     —      31,000
  5211800040  วัสดุสิ้นเปลืองสำนักงาน-โรงงาน       2,100     1,700     2,600     1,600     2,400     —      —     —     —     —     —     —      10,400
  5211800050  วัสดุสิ้นเปลืองรักษาความปลอดภัย        500       500       —         500       800     —      —     —     —     —     —     —       2,300
  5211800060  วัสดุสิ้นเปลืองห้องทดลอง               —         —         —          —         —       —      —     —     —     —     —     —         —
  5211800070  วัสดุสิ้นเปลืองดูแลสวน                 —         —         —          —         —       —      —     —     —     —     —     —         —

▼ Other admin. Expenses (subtotal)          156,300   148,200   189,400   143,100   161,500     —      —     —     —     —     —     —     798,500
  5120300020  ค่าน้ำมันเชื้อเพลิง                 98,000    94,500   124,000    89,000   105,000     —      —     —     —     —     —     —     510,500
  5120300030  ค่าวัสดุและบรรจุภัณฑ์               18,500    16,200    22,400    15,800    19,200     —      —     —     —     —     —     —      92,100
  5210500030  ค่าน้ำบาดาล                          8,200     7,900     9,800     7,400     8,600     —      —     —     —     —     —     —      41,900
  5210900020  ค่ารักษาความปลอดภัย                 22,000    22,000    22,000    22,000    22,000     —      —     —     —     —     —     —     110,000
  5210900030  ค่าบริการกำจัดของเสีย                5,400     5,400     5,400     5,400     5,400     —      —     —     —     —     —     —      27,000
  5210900040  ค่าบริการบรรจุปูน                    4,200     2,200     5,800     3,500     1,300     —      —     —     —     —     —     —      17,000
  5211400010  ค่าวารสารและสมาชิก                   —         —         —          —         —       —      —     —     —     —     —     —         —
  5211400020  ค่าปรับอื่นๆ                          —         —         —          —         —       —      —     —     —     —     —     —         —
  5211400999  ค่าธรรมเนียมอื่น                      —         —         —         500        —       —      —     —     —     —     —     —         500
  5211900040  ค่าใช้จ่ายในการจัดประชุม               —         —         —          —         —       —      —     —     —     —     —     —         —
  5211900060  ค่าใช้จ่ายเกี่ยวกับรถยนต์นั่ง          —         —         —          —         —       —      —     —     —     —     —     —         —

▼ Other manpower expenses (subtotal)         14,200    11,800    16,500    13,400    15,200     —      —     —     —     —     —     —      71,100
  5210100090  ค่ายูนิฟอร์ม                          —         —       8,500        —         —       —      —     —     —     —     —     —       8,500
  5210100110  ค่าตรวจสุขภาพประจำปี                   —         —         —          —       4,200     —      —     —     —     —     —     —       4,200
  5210400010  เบี้ยเลี้ยง                           9,800     8,400    11,200     9,800    11,000     —      —     —     —     —     —     —      50,200
  6210400010  เบี้ยเลี้ยงต่างประเทศ                 4,400     3,400     4,800     3,600       —       —      —     —     —     —     —     —      16,200 ★

▼ Personal expenses (subtotal)                  —         —          —          —      18,500     —      —     —     —     —     —     —      18,500
  6210100140  ค่าใช้จ่ายกิจกรรมบริษัท (ปีใหม่)       —         —          —          —      18,500     —      —     —     —     —     —     —      18,500

▼ Professional & Legal Fee (subtotal)        35,000    35,000    35,000    35,000    35,000     —      —     —     —     —     —     —     175,000
  5210700010  ค่าจ้างที่ปรึกษา - R&D                  —         —          —          —         —       —      —     —     —     —     —     —         —
  5210700020  ค่าจ้างที่ปรึกษา - ด้านเทคนิค          35,000    35,000    35,000    35,000    35,000     —      —     —     —     —     —     —     175,000
  5210700999  ค่าจ้างที่ปรึกษา - อื่นๆ                —         —          —          —         —       —      —     —     —     —     —     —         —
  5211900020  ค่าใช้จ่ายเกี่ยวกับ ISO                  —         —          —          —         —       —      —     —     —     —     —     —         —

▼ Repair & Maintenance (subtotal)            28,400    19,800    34,500    22,100    31,200     —      —     —     —     —     —     —     136,000
  5211100060  ค่าซ่อมบำรุง - เฟอร์นิเจอร์             —       4,500        —       3,200       —       —      —     —     —     —     —     —       7,700
  5211100070  ค่าซ่อมบำรุง - เครื่องใช้สำนักงาน      8,200     6,800     9,500     7,400     8,900     —      —     —     —     —     —     —      40,800
  5211100080  ค่าซ่อมบำรุง - คอมพิวเตอร์            20,200     8,500    25,000    11,500    22,300     —      —     —     —     —     —     —      87,500

▼ Travelling Expense (subtotal)              42,500    18,200    68,400    31,800    24,600     —      —     —     —     —     —     —     185,500
  5210400020  ค่าพาหนะเดินทางต่างประเทศ             12,000       —       28,000       —         —       —      —     —     —     —     —     —      40,000 ★
  5210400030  ค่าที่พักต่างประเทศ                   18,000       —       32,000       —         —       —      —     —     —     —     —     —      50,000 ★
  5210400999  ค่าใช้จ่ายเดินทางอื่นต่างประเทศ         4,500       —        8,400       —         —       —      —     —     —     —     —     —      12,900 ★
  6210400020  ค่าพาหนะเดินทาง                        3,200     8,200     —         12,400     9,800     —      —     —     —     —     —     —      33,600
  6210400030  ค่าที่พัก                              4,800    10,000       —        19,400    14,800     —      —     —     —     —     —     —      49,000
  6210400999  ค่าใช้จ่ายเดินทางอื่น                   —          —          —          —          —       —      —     —     —     —     —     —         —

══════════════════════════════════════════════════════════════════════════════════════════════════════
  GRAND TOTAL                               485,400   377,350   568,300   417,800   499,800     —      —     —     —     —     —     —   2,348,650
```

**Notes on mock data:**
- ★ = Oversea Trip items — linked from sub-template (show a small link icon or tooltip note)
- `—` in future months (มิ.ย.–ธ.ค.) = no data yet, future period
- `—` in past months = GL account had no transactions that month (not zero budget — just no spend)
- พ.ค. (May) = current month, highlight the column header and cells with a very subtle tint
