# Reference — Data Sources (Actuals)

What this is: reference facts about the SAP **Actuals** data feed — where it comes from, how it
loads, the Accruals row schema, and the query-time filter rules. Source of truth for the Actuals
side of the dashboard. Decisions (the *why*) live in `docs/adr/`; this file is descriptive only.

> **Canonical table:** Actuals land in the Fabric **Lakehouse** as `dbo.gold_sap_gl_trans`
> (SQL Analytics Endpoint, read-only). The Lakehouse schema is `dbo`; the `gold_`/`silver_`
> prefix is part of the table *name*, not the schema. Older notes say `silver_src.sap_gl_trans` —
> that is the Bronze→Silver promotion step (see `docs/reference/data-platform-map.md`); the
> dashboard reads the `gold_` table.

---

## Data Sources Overview

| Data | Source | How | Frequency |
|------|--------|-----|-----------|
| Actuals | SAP T-Code FAGLL03H | Excel export → upload to Lakehouse | Monthly — ไม่มีวันปิด สามารถ re-upload ได้เสมอ |
| Budget (board approved) | Excel upload | Budget dept uploads via web | Yearly |
| Budget (user input) | Web form (this app) | Cell by cell per GL Account | Per budget cycle — **มีวันปิดรับข้อมูล** |

---

## SAP Export Settings

- Company Code: `1000`
- Layout: `/FORTEMPLATE`
- SAP exports **ALL rows** — ไม่มีการ filter ตอน export (filtering happens at query time, see below)

---

## Accruals Table (SAP G/L Line Items)

**คืออะไร:** ข้อมูล G/L Line Items จาก SAP (T-Code FAGLL03H) ระดับ transaction — ใช้เป็น Actuals
เปรียบเทียบกับ Budget บน Dashboard โหลดลง Fabric Lakehouse รายเดือน

### Facts จากข้อมูลตัวอย่างจริง (verified จาก requirement_detail.xlsx)
- ข้อมูลตัวอย่าง: 2,437 rows, Fiscal Year 2026, สกุลเงิน THB, Company Code 1000
- Unique G/L Accounts ที่มีรายการ: 89 accounts (จาก 137 ทั้งหมดในระบบ — บาง GL อาจไม่มีรายการทุกเดือน)
- Unique Cost Centers: 141 cost centers

### ข้อควรระวัง
1. **Debit/Credit ind** — มีทั้ง `S` (Debit/รายจ่าย) และ `H` (Credit/reversal) ปนกัน — sum logic ต้อง flip sign ของ `H`
2. **Amount ติดลบได้** — reversal entries มียอดลบ ต้องระวังการรวมยอด
3. **Cost Center ≠ Division** — มี 141 cost centers แต่ user แบ่งตาม division ต้องทำ mapping (ดูด้านล่าง)
4. **group_exp ต้องใช้ชื่อจาก SAP เสมอ** — "Oversea Trip" และ "Fuel" คือ sub-template (ฟอร์ม input เท่านั้น)
   ไม่ใช่ GL group จริง (ดู `docs/reference/gl-master.md`)

### Schema — 26 columns

| # | Column Name | Data Type | ตัวอย่าง |
|---|-------------|-----------|---------|
| 1 | Company Code | VARCHAR | `1000` |
| 2 | G/L Account | VARCHAR | `5120300020` |
| 3 | G/L Account: Long Text | VARCHAR | `Oil Expenses` |
| 4 | Posting Date | DATE | `2026-03-19` |
| 5 | Ledger | VARCHAR | `0L` |
| 6 | Company Code Currency Key | VARCHAR | `THB` |
| 7 | Company Code Currency Value | DECIMAL | `4480.10` |
| 8 | Cost Center | VARCHAR | `TKTRUCK` |
| 9 | Cost Center: Long Text | VARCHAR | `TK-Truck` |
| 10 | Profit Center | VARCHAR | `1000` |
| 11 | Assignment | VARCHAR | `TKTRUCK` |
| 12 | Document Number | VARCHAR | `5300016837` |
| 13 | Document type | VARCHAR | `WA` |
| 14 | Transaction Code | VARCHAR | `MB1A` |
| 15 | Entry Date | DATE | `2026-03-22` |
| 16 | Order: Short Text | VARCHAR | `99-5424/T12` |
| 17 | Text | VARCHAR | `Mileage : 304760 KM` |
| 18 | Order | VARCHAR | `OXXTK008` |
| 19 | Quantity | DECIMAL | `140` |
| 20 | Unit of Measure | VARCHAR | `L` |
| 21 | Purchasing Document | VARCHAR | *(blank)* |
| 22 | Invoice Reference | VARCHAR | `5300016837` |
| 23 | G/L Account (dup) | VARCHAR | `5120300020` |
| 24 | Fiscal Year | INT | `2026` |
| 25 | Object Class | VARCHAR | `Overhead` |
| 26 | Debit/Credit ind | CHAR(1) | `S` |

---

## Actuals Filter Rule (apply ตอน query — ใน Lakehouse/Warehouse ไม่ใช่ตอน load)

- Exclude rows where **Document type** = `CO`
- Exclude rows where **Cost Center** = `10SC012000`, `CMRY01`, `CMKK01`, `CMPB01`, `MNLB00-04`, หรือ *(Blanks)*
- Exclude rows where **Assignment** = `TFRS16`

---

## Actuals Data Load Strategy — Replace by Month

- ไม่มีวันปิดรับข้อมูล — สามารถ re-upload ข้อมูลเดือนที่ผ่านไปแล้วได้เสมอ
- วิธี: **Replace by Month** — ก่อน insert ให้ DELETE rows ที่ YEAR(posting_date) + MONTH(posting_date)
  ตรงกันก่อน แล้ว append ใหม่
- ทำใน Fabric Notebook รับ parameter: `fiscal_year`, `month`
- UI (Admin page): Budget dept เลือกปี+เดือน → แสดง warning → confirm → trigger Notebook
- ⚠️ ห้าม append ทับโดยไม่ลบก่อน — ข้อมูลจะซ้ำและยอดรวมผิด

---

## Cost Center → Division Mapping

- ตาราง Accruals มี Cost Center แต่ไม่มี Division ตรงๆ
- ต้องทำ mapping Cost Center → Division เพื่อแสดงผลบน Dashboard ระดับสายงาน
- mapping table อาจเก็บใน Fabric SQL DB (`cfg_master`) หรือเป็น reference table ใน Lakehouse
- See `docs/adr/0001-rls-via-orgcode-costcenter-map.md` for the orgcode↔CostCenter resolution path.
