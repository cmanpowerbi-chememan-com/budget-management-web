# CLAUDE.md — Budget Management Web Project Context

This file is auto-read by Claude at the start of every conversation in this folder.
Do NOT delete this file.

---

## Who I Am

- Developer: tanasedw (tanasedbsn@gmail.com)
- Background: Familiar with Microsoft Fabric / OneLake / Lakehouse — new to Azure SQL Database
- Working on: Internal budget management web app for the budget department

---

## Project Philosophy (Non-negotiable)

> **Lean, easy to use, not too complex — for users, developers, and approvers — while keeping performance at standard.**

- Prefer simple **and** clever solutions — elegant, not just minimal
- **Decrease manual tasks** — auto-fill, pre-populate, auto-calculate wherever possible (e.g., pull prior year budget, auto-sum totals, pre-fill division/department from login)
- Minimize clicks and screens for every role
- No feature that adds complexity without clear business value
- When in doubt: do less, do it well
- Approver/reviewer experience matters as much as user experience
- Developer should be able to maintain and extend without deep ramp-up

---

## Project Summary

Internal OPEX budget system replacing manual SAP exports and Excel consolidation.
Users fill budget by division → approval workflow → dashboard vs actuals.

**GitHub:** https://github.com/cmanpowerbi-chememan-com/budget-management-web
**Working folder:** `c:\04.budget_management_web\`

---

## Tech Stack (Final Decisions)

| Layer | Tool | Notes |
|-------|------|-------|
| Frontend | React + Vite (JavaScript) | SPA — replaces Streamlit |
| Backend API | FastAPI (Python) | REST API — replaces Streamlit server |
| Transactional DB | Azure SQL Database | Budget input, approvals, user roles |
| Analytical DB | Fabric Lakehouse (OneLake) | SAP actuals, medallion architecture (Bronze→Silver→Gold) |
| Authentication | Azure Entra ID | Login + RLS by division |
| Email Notifications | Fabric Notebook + Microsoft Graph API | No Power Automate |
| Deployment | Azure Container Apps | Via Azure Cloud Shell (no local Docker/CLI) |
| Version Control | GitHub | https://github.com/tanasedw/budget_management_web.git |

### Database Decision — Why NOT CosmosDB or Lakehouse-only
- **CosmosDB** ❌ — NoSQL, no SQL joins, expensive, overkill for structured budget rows
- **Lakehouse only** ❌ — Bulk analytical reads only, terrible for one-row-at-a-time CRUD form updates
- **Azure SQL** ✅ — Transactional CRUD: budget input forms, approval workflow, user roles
- **Fabric Lakehouse** ✅ — Medallion architecture: SAP actuals Bronze→Silver→Gold, dashboard Gold layer

```
User fills form → FastAPI → Azure SQL (budget_submissions, approval_status)
                                ↓
                    Fabric Notebook pulls from Azure SQL
                                ↓
                    Bronze → Silver → Gold (Lakehouse)
                                ↓
                    Dashboard reads Gold layer
```

---

## Key Architecture Decisions (Why)

1. **Azure SQL + Lakehouse (not Lakehouse only)**
   - Azure SQL for transactional writes (budget input, approval updates) — simple CRUD
   - Lakehouse for bulk analytical reads (SAP actuals, dashboards)
   - Lakehouse alone is bad for frequent small row updates

2. **No Power Automate**
   - Email notifications via Fabric Notebook + Microsoft Graph API instead
   - Triggered by Fabric REST API call from FastAPI backend when approval status changes

3. **No local Docker/Azure CLI**
   - Machine does not have admin rights to install
   - Use Azure Cloud Shell (portal.azure.com) for all deployment commands
   - Docker and az CLI are pre-installed in Cloud Shell

4. **ODBC Driver 17 (not 18)**
   - Driver 17 already installed on developer machine
   - Use `ODBC Driver 17 for SQL Server` in all connection strings

---

## Developer Machine — What Is Installed

| Tool | Version | Status |
|------|---------|--------|
| Python | 3.14.0 | Installed |
| Git | 2.52.0 | Installed |
| VS Code | latest | Installed |
| ODBC Driver 17 for SQL Server | - | Installed |
| Azure CLI | - | NOT installed (use Cloud Shell) |
| Docker Desktop | - | NOT installed (use Cloud Shell) |

### Python Packages Installed
```
streamlit==1.54.0
pyodbc==5.3.0
sqlalchemy==2.0.49
pandas==2.3.3
msal==1.36.0
openpyxl==3.1.5
python-dotenv
requests==2.32.4
plotly==6.7.0
Pillow==12.1.1
numpy==2.4.2
pytest==9.0.2
faker
```

---

## Azure SQL Database

- Connection uses `ODBC Driver 17 for SQL Server`
- Credentials stored in `.env` file (never committed to GitHub)
- Developer was new to Azure SQL — familiar with Fabric Lakehouse

### Connection Details
| Field | Value |
|-------|-------|
| Server | `cman-budget-mngt-web-sql.database.windows.net` |
| Database | `budget-mngt-web-db` |
| Admin login | `budgetmngtwebadmin` |
| Resource Group | `CMAN-BUDGET-MNGT-WEB-RG` |
| Location | Southeast Asia |

## Azure Container Registry (ACR)

| Field | Value |
|-------|-------|
| Registry name | `cmanbudgetacr` |
| Login server | `cmanbudgetacr.azurecr.io` |
| Resource Group | `CMAN-BUDGET-MNGT-WEB-RG` |
| Location | Southeast Asia |
| Pricing plan | Basic |
| Admin username | `cmanbudgetacr` |

## Microsoft Fabric

| Field | Value |
|-------|-------|
| Workspace | `budget_management_web` |
| Workspace ID | `8fbc17b7-c67d-4c55-94cd-7364e33d1de9` |
| Lakehouse | `lakehouse` |
| Lakehouse ID | `5cf438dc-6268-4ec1-b088-c6b5c311339d` |
| Notebook: nb_upload_actuals ID | `e8b33e92-1d36-48ed-8eb1-627536b3c450` |
| Notebook: nb_send_email ID | `8ab79259-b004-45c2-a011-d70d7e7b0c98` |

## Azure Container Apps

| Field | Value |
|-------|-------|
| Container app name | `cman-budget-mngt-web` |
| Environment | `managedEnvironment-CMANBUDGETMNGTW-b33f` |
| Log Analytics workspace | `workspacecmanbudgetmngtwebrgb513` |
| Resource Group | `CMAN-BUDGET-MNGT-WEB-RG` |
| Location | Southeast Asia |

### Tables
| Table | Purpose |
|-------|---------|
| `user_division_map` | User email → division → role → approver mapping |
| `budget_submissions` | Monthly budget input per GL Account per cost center |
| `approval_status` | Current approval state per submission |
| `approval_log` | Full history of every approval action |

### Approval Status Flow
```
DRAFT → PENDING_VP → PENDING_BUDGET_STAFF → PENDING_MANAGER → APPROVED
                ↘ REJECTED_BY_VP
                                       ↘ REJECTED_BY_STAFF
                                                            ↘ REJECTED_BY_MANAGER
```

---

## Approval Workflow

4-level chain (no skipping):
```
User → VP/AVP (of user's division) → Nipapornt (Budget Staff) → Warapornt (Budget Manager)
```

| Person | Role | Email variable |
|--------|------|----------------|
| Nipapornt | Budget Staff (3rd level) | `NIPAPORNT_EMAIL` in .env |
| Warapornt | Budget Manager (final) | `WARAPORNT_EMAIL` in .env |

### Workflow applies to which templates

| Template | Approval Workflow | เหตุผล |
|----------|------------------|--------|
| **1.1 + 1.2 (รวมกัน)** | **ใช่ — full 4-level workflow** | 1.2 เป็น detail ของ 1.1 → submit พร้อมกันเป็น 1 package |
| **Template 2** | **ไม่ — Warapornt confirm เอง** | Budget dept กรอกเอง, Nipapornt ไม่ควร approve ของตัวเอง |

### Approval Unit (granularity)

**1 Submission = 1 approval unit** ต่อ **Division + Fiscal Year** — ไม่ใช่ per row หรือ per GL Account

- User กรอก 1.1 ทุก GL + 1.2 ทุก sub-template → **Submit 1 ครั้ง**
- VP เห็น "งบของ Division X ปี 2026" → approve/reject ทั้งก้อน
- ตาราง `approval_status` track ระดับ submission (division + fiscal_year) ไม่ใช่ระดับ row

---

## Email Notification Triggers

| Event | Notify |
|-------|--------|
| User submits | VP/AVP of division |
| VP approves | Nipapornt |
| VP rejects | User |
| Nipapornt approves | Warapornt |
| Nipapornt rejects | User + VP/AVP |
| Warapornt approves | User (final confirmation) |
| Warapornt rejects | User + VP/AVP + Nipapornt |
| Deadline reminder | All users who have not submitted |

---

## Data Sources

| Data | Source | How | Frequency |
|------|--------|-----|-----------|
| Actuals | SAP T-Code FAGLL03H | Excel export → upload to Lakehouse | Monthly — ไม่มีวันปิด สามารถ re-upload ได้เสมอ |
| Budget (board approved) | Excel upload | Budget dept uploads via web | Yearly |
| Budget (user input) | Web form (this app) | Cell by cell per GL Account | Per budget cycle — **มีวันปิดรับข้อมูล** |

### Budget Submission Deadline
- วันปิดรับข้อมูล Budget กำหนดตาม **แผนการทำงบประมาณแต่ละปี** — ไม่ fixed เปลี่ยนได้ทุกปี
- Admin (Budget dept) ต้องสามารถตั้งค่าวันปิดรับได้ในระบบ
- เมื่อถึงวันปิด → ระบบปิด form ไม่ให้ user กรอกหรือแก้ไขเพิ่มได้
- ต้องมี deadline reminder email แจ้ง user ที่ยังไม่ได้ submit ก่อนถึงวันปิด

### SAP Export Settings
- Company Code: 1000
- Layout: /FORTEMPLATE
- SAP exports **ALL rows** — ไม่มีการ filter ตอน export

### Actuals Filter Rule (apply ตอน query — ใน Lakehouse/Warehouse ไม่ใช่ตอน load)
- Exclude rows where **Document type** = `CO`
- Exclude rows where **Cost Center** = `10SC012000`, `CMRY01`, `CMKK01`, `CMPB01`, `MNLB00-04`, หรือ *(Blanks)*
- Exclude rows where **Assignment** = `TFRS16`

### Actuals Data Load Strategy — Replace by Month
- ไม่มีวันปิดรับข้อมูล — สามารถ re-upload ข้อมูลเดือนที่ผ่านไปแล้วได้เสมอ
- วิธี: **Replace by Month** — ก่อน insert ให้ DELETE rows ที่ YEAR(posting_date) + MONTH(posting_date) ตรงกันก่อน แล้ว append ใหม่
- ทำใน Fabric Notebook รับ parameter: fiscal_year, month
- UI (Admin page): Budget dept เลือกปี+เดือน → แสดง warning → confirm → trigger Notebook
- ห้าม append ทับโดยไม่ลบก่อน — ข้อมูลจะซ้ำและยอดรวมผิด

### Actuals — Cost Center → Division Mapping
- ตาราง Accruals มี Cost Center แต่ไม่มี Division ตรงๆ
- ต้องทำ mapping Cost Center → Division เพื่อแสดงผลบน Dashboard ระดับสายงาน
- mapping table อาจเก็บใน Azure SQL หรือเป็น reference table ใน Lakehouse

### GL Account Groups (18 groups, 137 accounts) — from sheet 'GL Acct & Group'

> Note: "Oversea Trip" and "Fuel" are **sub-templates** (detail input sheets), NOT GL groups.

| # | Group Name | Accounts |
|---|-----------|---------|
| 1 | Bank Charge | 3 |
| 2 | Communication Expense | 8 |
| 3 | Electricity & Water | 3 |
| 4 | Employee benefits | 2 |
| 5 | Entertainment | 3 |
| 6 | Insurance Premium | 2 |
| 7 | Lease & Rental | 14 |
| 8 | Maintenance - License for software | 2 |
| 9 | Office expenses | 14 |
| 10 | Other admin. Expenses | 34 |
| 11 | Other manpower exp (Per diem, Health check, Uniform…etc) | 13 |
| 12 | Personal expenses | 3 |
| 13 | Professional & Legal Fee | 13 |
| 14 | Public Relation & Donation | 3 |
| 15 | Remuneration of director | 1 |
| 16 | Repair & Maintenance | 11 |
| 17 | Training & Seminar | 2 |
| 18 | Travelling Expense | 6 |

---

## ตารางข้อมูล Accruals (Fabric Lakehouse)

**คืออะไร:** ข้อมูล G/L Line Items จาก SAP (T-Code FAGLL03H) ระดับ transaction — ใช้เป็น Actuals เปรียบเทียบกับ Budget บน Dashboard โหลดลง Fabric Lakehouse รายเดือน

### ข้อเท็จจริงจากข้อมูลตัวอย่างจริง (verified จาก requirement_detail.xlsx)
- ข้อมูลตัวอย่าง: 2,437 rows, Fiscal Year 2026, สกุลเงิน THB, Company Code 1000
- Unique G/L Accounts ที่มีรายการ: 89 accounts (จาก 137 ทั้งหมดในระบบ — บาง GL อาจไม่มีรายการทุกเดือน)
- Unique Cost Centers: 141 cost centers

### ข้อควรระวังตอนสร้างระบบ
1. **Debit/Credit ind** — มีทั้ง `S` (Debit/รายจ่าย) และ `H` (Credit/reversal) ปนกัน ต้องตัดสินใจว่า dashboard จะ sum ทุก row หรือ filter เฉพาะ S
2. **Amount ติดลบได้** — reversal entries มียอดลบ ต้องระวังการรวมยอดใน dashboard
3. **Cost Center ≠ Division** — มี 141 cost centers แต่ user ในระบบแบ่งตาม division ต้องทำ mapping cost center → division
4. **group_exp ต้องใช้ชื่อจาก SAP เสมอ** — "Oversea Trip" และ "Fuel" คือ sub-template (ฟอร์ม input เท่านั้น) ไม่ใช่ GL group จริง GL accounts เหล่านั้นอยู่ใน Travelling Expense และ Other admin. Expenses ตามลำดับ

**จำนวนคอลัม:** 26 คอลัม

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

## Data Platform Layer — Bronze → Silver Mapping

**Spec file:** `docs/CMAN-DataPlatform_Mapping_Specification _V0.0.4.xlsx`

### Table Names

| Layer | Full Table Name | Col Count |
|-------|----------------|-----------|
| Landing (flat file) | `SAP_T_GL_TRANS_[COMPANY_CD]_YYYYMMDD.txt` | — |
| Bronze | `bronze_src.ACDOCA` | 93 (85 SAP data + 1 pipeline + 7 control) |
| Silver | `silver_src.sap_gl_trans` | 92 (85 data + 7 control) |

### Key Facts
- **Landing file naming:** `SAP_T_GL_TRANS_1000_YYYYMMDD.txt` — Company Code `1000` = CMAN TH, `2000` = CMAN AU
- **Silver filter:** `WHERE RLDNR = '0L'` — only Ledger 0L rows promoted from bronze to silver
- **Composite PK (5 cols):** `ledger + accounting_doc_number + company_code + fiscal_year + posting_item_number`
- **Bronze-only col (not in silver):** `PRCS_FILE_NAME` — pipeline constant storing source filename
- **2 cols with transform (not plain Move):** `exchange_rate` (BKPF_KURSF) and `group_exchange_rate` (BKPF_KURS2) — trailing `-` sign flipped to leading `-` before DECIMAL cast

### FAGLL03H 26 cols → Silver Mapping (cols used by this project)

| FAGLL03H Col | Silver col | Bronze col | Need |
|---|---|---|---|
| Company Code | `company_code` | `RBUKRS` | Filter `= '1000'` |
| G/L Account | `gl_account_number` | `RACCT` | Join GL group → dashboard |
| G/L Account: Long Text | **NO MAP** | — | ⚠️ Need `dim_gl_account` ref table |
| Posting Date | `posting_date` | `BUDAT` | Extract month → monthly actuals |
| Ledger | `ledger` | `RLDNR` | Filtered at silver already |
| Company Code Currency Key | `company_curr` | `RHCUR` | Verify = `THB` |
| Company Code Currency Value | `company_curr_amount` | `HSL` | **Main SUM amount for dashboard** |
| Cost Center | `cost_center` | `RCNTR` | Filter excluded CC + join division |
| Cost Center: Long Text | **NO MAP** | — | ⚠️ Need `dim_cost_center` ref table |
| Profit Center | `profit_center` | `PRCTR` | Reference display |
| Assignment | `assignment_number` | `ZUONR` | Filter `<> 'TFRS16'` |
| Document Number | `accounting_doc_number` | `BELNR` | Reference display |
| Document type | `doc_type` | `BLART` | Filter `<> 'CO'` |
| Transaction Code | `trans_code` | `BKPF_TCODE` | Reference display |
| Entry Date | **NO MAP** | `CPUDT` not in bronze | ⚠️ Gap — CPUDT not extracted into pipeline |
| Order: Short Text | **NO MAP** | — | Display only — show NULL acceptable |
| Text | `item_text` | `SGTXT` | Line item description display |
| Order | **NO MAP** | — | Display only — show NULL acceptable |
| Quantity | `quantity` | `MSL` | Reference display |
| Unit of Measure | `base_unit_measure` | `RUNIT` | Reference display |
| Purchasing Document | `purchase_order_number` | `EBELN` | Reference display |
| Invoice Reference | `ref_doc_number2` | `BKPF_XBLNR` | Reference display |
| G/L Account (dup col 23) | `gl_account_number` | `RACCT` | Duplicate — skip |
| Fiscal Year | `fiscal_year` | `GJAHR` | Group by year |
| Object Class | **NO MAP** | — | Display only — show NULL acceptable |
| Debit/Credit ind | `debit_credit_ind` | `DRCRK` | `S`=expense `H`=reversal — sign logic for SUM |

### Gaps — 4 Columns Missing from Pipeline

| FAGLL03H Col | SAP Field | Gap | Action |
|---|---|---|---|
| G/L Account: Long Text | — | Not in ACDOCA | Create `dim_gl_account` in Azure SQL |
| Cost Center: Long Text | — | Not in ACDOCA | Create `dim_cost_center` in Azure SQL (also needed for division mapping) |
| Entry Date | `CPUDT` | Not extracted into bronze | Request data platform team to add, or load from raw flat file in `nb_upload_actuals` |
| Order / Order: Short Text | — | Not in ACDOCA | Accept NULL on dashboard |

### Dashboard Query Pattern
```sql
SELECT
    fiscal_year,
    MONTH(posting_date) AS month,
    gl_account_number,
    cost_center,
    SUM(CASE WHEN debit_credit_ind = 'S' THEN company_curr_amount
             WHEN debit_credit_ind = 'H' THEN -company_curr_amount END) AS actuals_thb
FROM silver_src.sap_gl_trans
WHERE company_code = '1000'
  AND doc_type <> 'CO'
  AND cost_center NOT IN ('10SC012000','CMRY01','CMKK01','CMPB01','MNLB00-04')
  AND cost_center IS NOT NULL
  AND assignment_number <> 'TFRS16'
GROUP BY fiscal_year, month, gl_account_number, cost_center
```

---

## Budget Input Templates

| Template | Type | Who Fills | Notes |
|----------|------|-----------|-------|
| 1.1 Main | Budget per GL Account per month | Each dept user | Displays Budget & Actuals by business line (สายงาน) |
| 1.2 Oversea Trip | Detail breakdown | Dept user | Sub-template — extra detail required |
| 1.2 Lease & Rental | Detail breakdown | Dept user | Sub-template — extra detail required |
| 1.2 Fuel (ค่าน้ำมัน) | Detail breakdown | Dept user | Sub-template — extra detail required |
| 1.2 Professional & Legal Fee | Detail breakdown | Dept user | Sub-template — extra detail required |
| 2. Budget dept template | Batch upload | Budget dept only | "งบประมาณกำหนดเอง" |

> **Consolidation rule:** Data from Template 1.1 and Template 2 must be merged into a single combined data file ("ไฟล์รวม Data") for reporting and dashboards.

### ไฟล์รวม Data — Column Structure (27 cols, sheet: ไฟล์รวม Data)

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
| 25 | Remark (Explanation) | เบี้ยประกันภัย กท 52-3381 | Template 2 มี, Template 1.1 = NULL |

> **Template 2 monthly input:** user กรอก ม.ค.–ธ.ค. รายเดือนได้ Y2026 = auto-sum — ไม่ใช่ยอดรวมปีเท่านั้น (ตัวอย่าง row ที่ไม่มีรายเดือนคือ example data ที่ยังไม่กรอก)

### Template 1.1 Main — Column Structure (33 cols, sheet: ตัวอย่าง Template>>สายงาน.....)

**Template name:** งบทำการ - ค่าใช้จ่ายอื่น
**Header fields:** สายงาน (Business Line), หน่วยงาน (Department)

| Group | Column | Description | Editable |
|-------|--------|-------------|----------|
| Key | รหัสบัญชี | GL Account Code | No |
| Key | ชื่อบัญชี (ภาษาไทย) | GL Account Name (Thai) | No |
| Reference | Budget 2025 (บาท) | Prior year budget | No |
| Reference | Normalized 2025 (บาท) | Prior year normalized actuals | No |
| Reference | Actuals Jan-Aug 25 (บาท) | YTD actuals (auto from SAP) | No |
| Actuals | ม.ค.-ธ.ค. (12 cols) | Monthly actuals — auto-filled from SAP | No |
| **Budget Input** | **Template 2026 (บาท)** | **Next year total (auto-sum)** | **No** |
| **Budget Input** | **ม.ค.-ธ.ค. (12 cols)** | **Monthly budget — USER FILLS** | **Yes** |

**GL Account Groups in Template 1.1:**
| Group | Sub-template Link |
|-------|------------------|
| Communication Expense | — |
| Electricity & Water | — |
| Entertainment | — |
| Lease & Rental | → กรอกที่ชีท "Lease & Rental" |
| Office Expenses | — |
| Other Admin. Expenses | Fuel → กรอกที่ชีท "ค่าน้ำมันเชื้อเพลิง" |
| Other Manpower Expenses | — |
| Personal Expenses | — |
| Professional & Legal Fee | → กรอกที่ชีท "Professional & Legal Fee" |
| Repair & Maintenance | — |
| Travelling Expense | Oversea items → กรอกที่ชีท "Oversea Trip" |

### Template 1.2a Oversea Trip — Sheet Structure (rows 2-131)

**Header:** Template name + สายงาน + Exchange rate (USDTHB) — ใช้อัตราแลกเปลี่ยนแปลง USD → THB

Sheet แบ่งเป็น **1 ตารางหลัก + 4 ตารางย่อย**:

#### ตารางหลัก — Trip Planning (rows 6-27)
| คอลัม | รายละเอียด |
|-------|------------|
| หน่วยงาน | Department |
| ปลายทาง | Destination |
| รายชื่อผู้เดินทาง | Traveler name |
| วัตถุประสงค์การเดินทาง | Travel purpose |
| ค่าเบี้ยเลี้ยง/วัน (USD) | Daily allowance rate in USD |
| จำนวนวัน ต่อทริป | Days per trip |
| จำนวนทริป | Number of trips |
| ม.ค.–ธ.ค. | Monthly trip count (12 cols) |

#### 4 ตารางย่อย (คำนวณยอดเป็นบาท — GL Account + รวม + รายเดือน)
| ตาราง | Row | GL Account | คอลัมพิเศษ |
|-------|-----|-----------|------------|
| ค่าเบี้ยเลี้ยง | 30-54 | 6210400010 | — |
| ค่าตั๋วเครื่องบิน | 55-79 | — | Flight Details, ค่าตั๋ว/ทริป |
| ค่าที่พัก | 80-104 | 6210400030 | — |
| ค่าใช้จ่ายเดินทางอื่น | 105-131 | — | รายละเอียด (แทน รายชื่อผู้เดินทาง) |

> **DB Design Warning:** แต่ละตารางย่อยมี GL Account ของตัวเอง ต้องเก็บแยก row ตาม expense_type (เบี้ยเลี้ยง / ตั๋วเครื่องบิน / ที่พัก / อื่น) — ค่าตั๋วเครื่องบินมี "Flight Details" พิเศษ อาจต้องมี column เพิ่มใน DB

### การสร้าง Template Opex ใน React (หน้า Submit Budget)

**UI หลัก:** ตารางแบ่งตาม GL Group แสดง GL Account แต่ละตัวพร้อมข้อมูล reference และช่องกรอกงบรายเดือน

**การ implement:**
- React table component — lock read-only columns (รหัสบัญชี, ชื่อบัญชี, Budget prior year, Actuals)
- column ที่ user กรอกได้: ม.ค.-ธ.ค. (12 cols) เท่านั้น
- ยอดรวม Template 2026 = auto-sum ใน frontend ก่อน render
- GL ที่ลิงก์ sub-template → แสดงเป็น read-only + ปุ่ม navigate ไป sub-template route

**Draft vs Submit:**
- กด **Save** = POST to FastAPI → บันทึก draft ลง DB (status = DRAFT)
- กด **Submit** = POST to FastAPI → ส่งเข้า workflow อนุมัติ (status เปลี่ยนเป็น PENDING_VP)

**Deadline:**
- GET /api/deadline จาก FastAPI ทุกครั้งที่เปิดหน้า
- ถึงวันปิด → disable form อัตโนมัติ

---

## Pages / Routes Plan

### Frontend (React routes)
| Page | Route | Role |
|------|-------|------|
| Login | `/` | All |
| Submit Budget | `/submit` | User |
| VP Approval | `/approve/vp` | VP/AVP |
| Staff Approval | `/approve/staff` | Nipapornt |
| Manager Approval | `/approve/manager` | Warapornt |
| Dashboard | `/dashboard` | All |
| Admin Panel | `/admin` | Budget dept |

### Backend (FastAPI endpoints)
| Group | Prefix |
|-------|--------|
| Auth | `/api/auth` |
| Budget submission | `/api/budget` |
| Approvals | `/api/approval` |
| Dashboard data | `/api/dashboard` |
| Admin | `/api/admin` |

---

## Project Structure

```
c:\04.budget_management_web\
├── backend/                  ← FastAPI (Python)
│   ├── main.py
│   ├── routers/              ← auth, budget, approval, dashboard, admin
│   ├── db/                   ← connection.py (Azure SQL)
│   ├── utils/                ← auth.py (MSAL), email.py
│   ├── requirements.txt
│   └── .env
├── frontend/                 ← React + Vite
│   ├── src/
│   │   ├── main.jsx
│   │   ├── App.jsx
│   │   ├── components/
│   │   ├── pages/
│   │   └── services/         ← api.js (calls FastAPI)
│   ├── package.json
│   └── vite.config.js
├── Dockerfile
├── .github/workflows/deploy.yml
├── .gitignore
└── CLAUDE.md
```

## Deployment Flow

```
1. Write code → VS Code (local)
2. Test locally:
   - backend:  cd backend && uvicorn main:app --reload  (localhost:8000)
   - frontend: cd frontend && npm run dev               (localhost:5173)
3. Push code → git push → GitHub
4. Deploy → Azure Cloud Shell (portal.azure.com)
   git pull → docker build → docker push → az containerapp update
5. Users access → Azure Container Apps URL (browser)
```

---

## Current Progress

- [x] Requirements gathered from requirement_detail.xlsx
- [x] Architecture decided (Azure SQL + Lakehouse + React + FastAPI + Entra ID)
- [x] Tech stack finalized — **React + FastAPI** (Streamlit dropped)
- [x] Database decision confirmed — Azure SQL (transactional) + Fabric Lakehouse (medallion)
- [x] Developer machine: Python 3.14, Git, VS Code, ODBC Driver 17 installed
- [x] GitHub repo created — **https://github.com/cmanpowerbi-chememan-com/budget-management-web**
- [x] CLAUDE.md created and up to date
- [x] Azure Entra ID configured (`cman-fabric-write` app registration, redirect URI `http://localhost:8501` registered)
- [x] Azure SQL Database created and firewall configured (dev-open rule added)
- [x] Database tables created (5 tables: `user_division_map`, `budget_submissions`, `approval_status`, `approval_log`, `submission_deadline`)
- [x] Azure Container Registry created (`cmanbudgetacr.azurecr.io`)
- [x] Azure Container Apps created (`cman-budget-mngt-web`)
- [x] Fabric Workspace + Lakehouse ready (`budget_management_web`)
- [x] Fabric Notebooks created (`nb_upload_actuals`, `nb_send_email`)
- [x] `.env` file created with all credentials
- [x] `db/connection.py` — Azure SQL connection working (tested SUCCESS)
- [x] `mas_employee_data` — synced from C-POP HR API, 621 Active employees, incremental sync script ready (`setup/sync_employees.py`)
- [x] GitHub Actions daily sync — `.github/workflows/sync_employees.yml` running every 06:00 Bangkok, verified ✅
- [ ] Restructure project folders → `backend/` + `frontend/`
- [ ] `backend/main.py` — FastAPI app
- [ ] `backend/utils/auth.py` — MSAL login with Entra ID
- [ ] `frontend/` — React + Vite scaffold
- [ ] API routes built (auth, budget, approval, dashboard, admin)
- [ ] React pages built
- [ ] Approval workflow built
- [ ] Email notifications built
- [ ] Dashboard built
- [ ] Deployed to Azure Container Apps

---

## Employee Data (mas_employee_data)

- Table `mas_employee_data` created on `budget-mngt-web-db` ✅
- Script source: `c:\01.besties\cman-prd-chatbot-backend\docs\sql_migration\create_tables.sql`
- **Source: C-POP HR System API** ✅ (answered 2026-05-05)

### C-POP HR System API
| Field | Value |
|-------|-------|
| URL | `https://cman.ipop.iamconsulting.co.th/api/public/tenant/cman/employeedata` |
| Method | POST |
| Auth header | `Authorization: <api_key>` (no "Bearer" prefix) |
| Body | `{"keyDate": "YYYY-MM-DD", "empCode": ""}` |
| Env vars | `CPOP_HR_SYSTEM_API_URL`, `CPOP_HR_SYSTEM_API_KEY` in `.env` |
| Response | `{"success": true, "employeeList": [...]}` |
| Volume | ~799 total, ~621 Active, 87 fields per record |

### Table Schema Notes
- PK is on `id` (nvarchar(50), sequential number "1", "2", ...) — migrated from original empcode PK
- Natural unique key per row: `(empcode, poscode)` — verified no duplicates among Active records
- API field `hr status` (space) maps to DB column `hr_status` (underscore)
- Only Active employees (`hr status = "Active"`) are synced — Inactive are deleted from DB

### Sync Script: `setup/sync_employees.py`
- **Incremental sync** — diffs API vs DB by `(empcode, poscode)` composite key
- INSERT: new records in API not in DB
- UPDATE: records in both but any field changed (MD5 hash comparison)
- DELETE: records in DB no longer Active in API
- `--dry-run` flag: shows what would change without writing to DB
- Run: `python setup/sync_employees.py`

### Scheduling (1x/day) — GitHub Actions ✅
- Workflow: `.github/workflows/sync_employees.yml`
- Cron: `0 23 * * *` (UTC) = **06:00 Bangkok time** daily
- Runner: `ubuntu-22.04` (has Microsoft repo pre-installed — no need to add manually)
- Manual trigger: GitHub → Actions → Daily Employee Sync → Run workflow
- Secrets stored in GitHub repo Secrets (Settings → Secrets → Actions):
  `DB_SERVER`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `CPOP_HR_SYSTEM_API_URL`, `CPOP_HR_SYSTEM_API_KEY`
- **First verified run: 2026-05-05 23:03 Thai time** — Diff +0 ~0 -0 (621 rows in sync)
- Maintenance: แก้ sync logic → `git push` → มีผลทันที ไม่ต้อง rebuild อะไร

### Azure SQL Firewall
- Rule `dev-open`: `0.0.0.0 → 255.255.255.255` — allows GitHub Actions runner IP
- Safe เพราะยังต้องใช้ username/password เข้า DB ทุกครั้ง
- To lock down later: ใช้ Service Principal + dynamic whitelist runner IP (ต้องการ Azure Owner role)

### Table Ordering
- Rows ordered by `empcode` (id 1..N assigned in empcode sort order)
- `setup/reorder_emp_table.py` — one-time script to rebuild table in empcode order (run if table gets out of order)
- Daily sync preserves order for new inserts (API records sorted by empcode before insert)

---

## Next Steps (pick up from here)

1. ~~Answer pending question: employee data source~~ ✅ C-POP HR API
2. ~~Build employee data load/sync into `mas_employee_data`~~ ✅ `setup/sync_employees.py`
3. (Optional) Schedule daily sync — Windows Task Scheduler or Azure Container Apps Job
4. Check Node.js installed (`node -v`) — required for React
5. Restructure folders: create `backend/` and `frontend/`
6. Build `backend/main.py` — FastAPI entry point
7. Build `backend/utils/auth.py` — MSAL login with Entra ID
8. Scaffold React frontend with Vite

---

## คำถามที่ยังไม่ได้คำตอบ (Pending Questions)

| # | คำถาม | เกี่ยวกับ | ถามใคร |
|---|-------|---------|--------|
| 1 | ข้อมูล Actuals จาก SAP ดึงทุกวันที่เท่าไหร่ของเดือน? manual หรือ scheduled? มี cutoff date ไหม? | Accruals data pipeline | ทีม SAP / Budget dept |
| 2 | Validation ก่อน Submit — ใช้ Lean process (warn แต่ไม่ block ถ้า 1.2 ยังไม่ครบ) หรือ block Submit จนกว่า 1.2 จะครบ? แนะนำ Lean: 1.1 save แล้ว = Submit ได้, 1.2 แค่ warning ให้ user เลือกเอง, VP เป็น reviewer แทน | Approval workflow / Submit validation | ยืนยัน business decision |
| 3 | ยอด 0 ทุกเดือนใน 1.1 — นับว่ากรอกครบแล้วหรือไม่? | Submit validation | ยืนยัน business decision |

---

## Activity Tracking (Lean Approach)

ใช้ Azure Entra ID + existing tables — ไม่ต้องสร้าง audit log table แยก:

| Activity | Track ด้วย |
|----------|-----------|
| Login / Logout | Entra ID sign-in logs — ฟรี ไม่ต้องทำอะไร |
| Draft / Submit / แก้ไข | `budget_submissions` + columns `updated_by`, `updated_at` |
| Approve / Reject | `approval_log` — มีอยู่แล้ว |
| Upload / Download | เพิ่ม action type ใน `approval_log` |

> **Clever part:** เพิ่มแค่ `updated_by` + `updated_at` ใน `budget_submissions` — ได้ full history โดยไม่ต้องมี table ใหม่

---

## Important Notes for Claude

- Always use `ODBC Driver 17 for SQL Server` (not 18) in connection strings
- **NEVER attempt to install any tools, packages, or software on the developer machine** — machine has NO admin rights. This includes Docker, Azure CLI, winget, or any system-level installation. Any attempt will be blocked by UAC and trigger antivirus alerts.
- For tool installations, always direct the user to Azure Cloud Shell (portal.azure.com)
- For deployment always use Azure Cloud Shell approach
- Developer is familiar with Fabric/Lakehouse — can use that as analogy when explaining SQL concepts
- All monetary values in THB
- Fiscal year: January – December
- This is an internal company tool — security and RLS by division are non-negotiable
