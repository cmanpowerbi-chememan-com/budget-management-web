# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
This file is auto-read by Claude at the start of every conversation in this folder.
Do NOT delete this file.

---

## RTK — Token Saver (Use Selectively)

`rtk` is a CLI proxy that compresses command output before sending to Claude (saves 60–90% tokens).
Installed: `brew install rtk` + `rtk init --claude-code`

### Always use rtk (output summary is enough)

| Command | Use |
|---------|-----|
| `rtk pytest` | Need failures only — full log is noise |
| `rtk tsc` / `rtk lint` | Need errors only |
| `rtk git status` | Short summary is fine |
| `rtk git log` | Commit list — full output not needed |
| `rtk grep <symbol>` | File matches — compress fine |
| `rtk find "*.ipynb"` | File list — compress fine |
| `rtk err python notebook.py` | Spark errors only |

### Use rtk only when full content is NOT needed

| Command | When to skip rtk |
|---------|-----------------|
| `git diff` | Fixing bugs / reviewing changes — Claude needs full code context; use plain `git diff` |
| `cat` / `read` file | Understanding full content (schema.sql, pipeline.json) — use Read tool instead |
| Debugging deep errors | When the "noise" in output may contain the actual clue — use plain command |

---

## Developer Commands

```bash
# Run the Streamlit app locally (http://localhost:8501)
streamlit run app.py

# Test Azure SQL connection
python db/connection.py

# Employee sync — dry run (shows diff, no DB writes)
python setup/sync_employees.py --dry-run

# Employee sync — live write to Azure SQL
python setup/sync_employees.py

# Weekly update — download SharePoint → merge → re-upload
python setup/create_weekly_update.py

# Run all tests
pytest

# Run a single test file verbosely
pytest tests/test_budget.py -v
```

---

## Actual Code Structure (Current State)

The planned `backend/` + `frontend/` split has NOT happened yet. Current layout is Streamlit-based:

```
app.py                        ← Streamlit entry: checks auth, renders login or home
utils/
  auth.py                     ← MSAL OAuth flow; persists user dict in session_state["user"]
  styles.py                   ← Global CSS injected via st.markdown
  email.py                    ← Email helper (Fabric/Graph API)
db/
  connection.py               ← pyodbc connection factory (ODBC Driver 17); tested standalone
  schema.sql                  ← Canonical table definitions for Azure SQL
pages/                        ← Streamlit multi-page (each file = one auto-registered page)
  01_submit_budget.py         ← User: fill & submit budget (stub)
  02_approve_vp.py            ← VP/AVP approval (stub)
  03_approve_staff.py         ← Budget Staff approval (stub)
  04_approve_manager.py       ← Budget Manager approval (stub)
  05_dashboard.py             ← Budget vs Actuals dashboard (stub)
  06_admin.py                 ← Admin: users, deadlines, actuals upload (stub)
fabric/        ← PySpark scripts — copy-paste into Fabric Notebook UI only
  nb_landing_to_bronze.py     ← Files/00landing → Bronze Delta tables (uses spark session)
  nb_bronze_to_silver.py      ← Bronze → Silver with column mapping + sign-flip transforms
  ingest_to_landing.py        ← OneLake upload helper
setup/                        ← Operational scripts (run locally or via GitHub Actions)
  sync_employees.py           ← Incremental sync: C-POP HR API → mas_employee_data table
  create_weekly_update.py     ← Merge local rows + SharePoint file → re-upload to SP
  run_migration.py            ← DB schema migration runner
  check_emp_table.py          ← Verify mas_employee_data row counts + duplicates
.github/workflows/
  sync_employees.yml          ← GitHub Actions: daily 06:00 BKK — runs sync_employees.py
```

### Auth Flow (cross-file)

1. `app.py` calls `handle_auth_callback()` on every load
2. If `?code=` query param present → `utils/auth.py` exchanges it for an access token via MSAL
3. Token used to call Microsoft Graph `/me` → get email + display name
4. Email looked up in `user_division_map` (Azure SQL via `db/connection.py`) → returns division + role
5. Result stored in `st.session_state["user"]`
6. Pages call `require_login()` / `require_role("vp", ...)` to guard access

### Fabric Notebook scripts

`fabric/` scripts use `spark` (Fabric built-in) and `abfss://` paths — they **do not run locally**. Copy into a Fabric Notebook cell and attach the `lakehouse` Lakehouse.

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

See `requirements.txt` for full package list.

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
| Notebook (nb_upload_actuals, nb_send_email) | Deleted 2026-05-07 — IDs removed from `.env` |

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

**Confirmed workflow — verified from HR data 2026-05-23:**
```
L4 Submit → managerempcode (direct manager, any tier) → Nipapornt (Budget Staff) → Warapornt (Budget Manager)
```

**Key decisions confirmed:**
- **Submitter = L4 only** (Supervisor 1/2, Senior Supervisor 1/2) — L3 confirms, does NOT submit
- **Confirmer = managerempcode** (whoever direct manager is — L3, L4 Sr.Sup, or L2) — no walk-up logic needed
- **192/192 L4 have valid managerempcode** with email → no gaps, no special cases
- L5 (Operator/Driver/Maid) ไม่ใช้ระบบนี้เลย — ไม่กรอก, ไม่ approve, ไม่รับ email
- L3 role = Confirm เท่านั้น (ไม่ submit) → ไม่มี role conflict

**Why NOT L3+L4 submit:** ถ้า L3 submit ด้วย → role conflict 149/240 คน (L3 ต้อง submit เอง + confirm L4 ด้วย)

4-level chain (original design — superseded):
```
User → VP/AVP (of user's division) → Nipapornt (Budget Staff) → Warapornt (Budget Manager)
```

| Person | Role | Email variable |
|--------|------|----------------|
| Nipaporn Tongking | Budget Staff (3rd level) | `NIPAPORNT_EMAIL` in .env |
| Waraporn Tirasit | Budget Manager (final) | `WARAPORNT_EMAIL` in .env |

> **หมายเหตุ:** "Warapornt" ในโค้ด/env = Waraporn **T**irasit (email: warapornt@chememan.com) — ไม่ใช่ typo

### Special Case — Nipaporn กรอก budget ของตัวเอง

Nipaporn (empcode=101032) มี 2 roles: **L4 submitter** (orgcode 1142402) และ **Budget Staff approver**

```
ถ้า submitter = Nipaporn:
  L4 Submit → Waraporn Tirasit Confirm (skip Nipaporn step — self-approval)

ถ้า submitter = คนอื่น:
  L4 Submit → managerempcode Confirm → Nipaporn → Waraporn Tirasit
```

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

**Spec file:** `docs/05CMAN-DataPlatform_Mapping_Specification _V0.0.4.xlsx`

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
| Entry Date | `CPUDT` | Not extracted into bronze | **Ticket raised to SAP team** — adding to `sap_t_gl_trans` (2026-05-06) |
| Order / Order: Short Text | — | Not in ACDOCA | **Ticket raised to SAP team** — adding to `sap_t_gl_trans`; also separate `SAP_M_INTERNAL_ORDER` file (2026-05-06) |

### SAP Data Gap Resolution — 2026-05-06 Update

Ticket raised to SAP team to add **4 missing columns** to existing landing file `sap_t_gl_trans`:
- `entry_date` (CPUDT)
- `order` 
- `object_class`
- `order_short_text`

**Test approach (Ratima):**
- Ratima created test file `Ratima_test1` to validate the 4 new columns before switching to production
- Once data verified OK → switch back to original Inteltion file `sap_t_gl_trans`

**Separate Order master file (Ratima):**
- New file: `SAP_M_INTERNAL_ORDER` — collects Order + Short Text as a standalone reference table
- Useful for joining order descriptions without relying on transaction-level data

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

## Deployment Flow (current — Streamlit)

```
1. Write code → VS Code (local) → test: streamlit run app.py
2. Push → git push → GitHub
3. Deploy → Azure Cloud Shell:
   git pull → docker build → docker push cmanbudgetacr.azurecr.io/...
   → az containerapp update --name cman-budget-mngt-web
4. Users access via Azure Container Apps URL
```

> **Planned:** once `backend/` + `frontend/` exist, replace step 1 with `uvicorn main:app --reload` + `npm run dev`.

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
- [x] Fabric Notebooks deleted (`nb_upload_actuals`, `nb_send_email`) — IDs removed from `.env` (2026-05-07)
- [x] `.env` file created with all credentials
- [x] `db/connection.py` — Azure SQL connection working (tested SUCCESS)
- [x] `mas_employee_data` — synced from C-POP HR API, 621 Active employees, incremental sync script ready (`setup/sync_employees.py`)
- [x] GitHub Actions daily sync — `.github/workflows/sync_employees.yml` running every 06:00 Bangkok, verified ✅
- [x] `dim_cost_center` — source file analyzed (`docs/Cost center (Update 18 Mar 26) 1.xlsx`), 210 cost centers, schema defined, link to `mas_employee_data` via `orgcode` identified (pending verification)
- [x] SAP gap columns — ticket raised to add Entry Date, Order, Object Class, Order Short Text to `sap_t_gl_trans`; Ratima created `Ratima_test1` for validation; `SAP_M_INTERNAL_ORDER` created for Order master
- [x] `sap_m_cost_center` — cost center reference table already exists (confirmed 2026-05-06)
- [x] Weekly update Excel created — `weekly_update/budget management web.xlsx`, script: `setup/create_weekly_update.py`
- [x] SharePoint upload working ✅ — `Sites.ReadWrite.All` admin consent granted, upload verified (2026-05-06)
- [x] `ENTRA_CLIENT_SECRET` rotated — new secret `budget_managemnt_web_excel_to_sp` in `.env` (2026-05-06)
- [x] Weekly update script upgraded — now downloads SP file first, merges (upsert by Action name), preserves colleague rows, then uploads (2026-05-06)
- [x] `skill/` folder created — `skill/skill_weekly_update.md` defines weekly update skill trigger + algorithm
- [ ] Chatdanai: verify cost center → line officer link by `empcode` (in testing)
- [x] SharePoint auto-upload: admin consent granted ✅ — verified working (2026-05-06)
- [x] SAP test files created by Ratima — `SAP_T_GL_TRANS_1000_RATIMA_TEST1` + `SAP_M_INTERNAL_ORDER` ready for data verification (2026-05-06)
- [x] OneLake connection working ✅ — `azure-storage-file-datalake` installed, `setup/connect_onelake.py` created, `cman-fabric-write` added to workspace (2026-05-07)
- [x] `cman-dw-dev-conn-gateway` created — On-premises Data Gateway on E-SMARTISO server (2026-05-07)
- [x] Fabric Data Pipeline configured — File System connector from `D:\SAPDW\PRD` via gateway → `Files/00landing` (2026-05-07)
- [x] 3 files landed in `Files/00landing`: `SAP_T_GL_TRANS_1000_RATIMA_TEST1.TXT` (116MB, 233,372 rows), `SAP_M_COST_CENTER.TXT` (341 rows), `SAP_M_INTERNAL_ORDER.TXT` (2,543 rows) (2026-05-07)
- [x] `01nb_landing_to_bronze` — Bronze Delta tables loaded: `bronze_ACDOCA` (233,372), `bronze_sap_m_cost_center` (341), `bronze_sap_m_internal_order` (2,543) (2026-05-07)
- [x] `02nb_bronze_to_silver` — Silver tables: `silver_sap_gl_trans` (233,372), `silver_cost_center_master`, `silver_internal_order_master` (2026-05-07)
- [x] Bronze→Silver mapping: 88 cols (85 spec + POPER + BKPF_CPUDT/entry_date + AUFNR/order_number + SCOPE/object_class + object_class_desc lookup), sign-flip on 6 amount/FX cols (2026-05-07)
- [x] `entry_date` (BKPF_CPUDT) fixed ✅ — SAP date format = `yyyyMMdd` (no dash), `.cast("date")` ใช้ไม่ได้, แก้ `sc()` helper ให้ใช้ `to_date(c, "yyyyMMdd")` เมื่อ cast_type == "date" — fix ครอบคลุมทุก date col อัตโนมัติ (2026-05-07)
- [ ] **[NEXT]** Data consistency check bronze→silver — verify ไม่มี data loss: null counts per col, row counts match, date cols parse ถูก, amount sign-flip ถูก (planned 2026-05-08)
- [ ] Ratima: verify data in `SAP_T_GL_TRANS_1000_RATIMA_TEST1` + `SAP_M_INTERNAL_ORDER` — if OK → Jakkarit แจ้ง SAP Team ตั้ง Scheduled Job Run in Production
- [x] 1st Recap Project with Laddawan — scheduled Thu 14/05/2026 8:30–9:00 AM, MS Teams invite sent (2026-05-06)
- [ ] Meeting with user — template filling data (Cut-off TBC)
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

### Employee Hierarchy — Verified 2026-05-23 (from docs/08mas_employee_data.csv)

5-tier structure (Primary rows only, 585 people):

| Tier | joblevelnameen | คน | Company Email | หมายเหตุ |
|------|---------------|-----|:---:|---------|
| L1 | C-Level, CEO | 5 | 5/5 ✅ | ผู้บริหารสูงสุด |
| L2 | Vice President (MGR), Assistant Vice President (MGR) | 24 | 23/24 ✅ | หัวหน้า Division — ผู้ approve งบ |
| L3 | Department Head, Assistant Department Head (all variants) | 70 | 68/70 ✅ | หัวหน้าหน่วยงาน — Dept + Section รวมเป็น 1 layer |
| L4 | Supervisor 1/2, Senior Supervisor 1/2 (all variants) | 192 | 168/192 ✅ | หัวหน้างาน — **ผู้กรอก Budget Form** |
| L5 | Operator 1/2/3, Driver, Maid | 279 | 10/279 ⚠️ | ปฏิบัติการ — **ไม่กรอก Budget / ไม่ต้องรับ email** |

**L5 ไม่ใช้งานระบบนี้เลย** — confirmed 2026-05-23: Operator/Driver/Maid ไม่กรอก budget, ไม่ approve, ไม่รับ notification
**Budget actors:** L2–L4 เท่านั้น — L5 ไม่มีบทบาทใน budget workflow ทุกขั้นตอน

### Email Domain Rules — Verified 2026-05-23
- `@chememan.com` ✅ — company email หลัก
- `@cman...` ✅ — company email variant
- `@gritsman.com` ✅ — **acceptable** บริษัทในเครือ (subsidiary) — ส่ง email ได้, เข้าระบบได้
- personal email (gmail, hotmail ฯลฯ) ❌ — ไม่ใช่ Entra ID → login ไม่ได้
- L3 ที่ใช้ @gritsman.com: Wanidtha (empcode 400003), Siratuch (empcode 400028) — อยู่ใน approval workflow ได้ปกติ

### posstatus = Primary vs Acting
- Employee 1 คนมีได้หลาย rows (Primary + Acting) — ตัวอย่าง: Apichai มี 3 rows (CTO Primary + MD Acting + VP-DT Acting)
- **ใช้ `posstatus = 'Primary'` เสมอ** สำหรับ RLS และ CC visibility
- Acting ใช้ได้เฉพาะ approval workflow (รักษาการ approve แทน VP ได้) — ไม่ขยาย data scope

### Approval Email Loop (Budget System)
```
User (L4) กรอกและ Submit
  → EMAIL: VP/AVP ของ Division (L2) — trace managerempcode ขึ้นไปจนถึง VP
VP Approve → EMAIL: Nipapornt (Budget Staff)
VP Reject  → EMAIL: User
Nipapornt Approve → EMAIL: Warapornt (Budget Manager)
Nipapornt Reject  → EMAIL: User + VP/AVP
Warapornt Approve → EMAIL: User (Approved ✅)
Warapornt Reject  → EMAIL: User + VP/AVP + Nipapornt
```

**Special cases:**
- C-Level ไม่มี VP เหนือ → VP ของพวกเขา = ตัวเอง → ต้องทำ special case
- MD (orgcode `1410000`) ไม่อยู่ใน CC map → ต้องทำ rule พิเศษ: เห็นและ approve ได้ทุก division

---

## dim_cost_center (Reference Table)

**Source file:** `docs/Cost center (Update 18 Mar 26) 1.xlsx` — 210 cost centers, updated 18 Mar 2026

### Columns (6)
| Column | Description | Example |
|--------|-------------|---------|
| `Cost Ctr` | SAP cost center code | `10CM010000` |
| `Description` | English name | `Commercial Market 1 Division` |
| `C Level` | C-Level executive | `Chief Commercial Officer` |
| `สายงาน` | Division (Thai) | `Commercial Market 1` |
| `ฝ่าย` | Department (Thai) | `Commercial Market 1` |
| `ส่วน` | Section (Thai) | `Commercial Market 1` |

### Purpose
- Fills the **"Cost Center: Long Text" gap** — not available in `silver_src.sap_gl_trans` (ACDOCA)
- Provides **Cost Center → Division mapping** needed for dashboard RLS and reporting
- **Actual table name: `sap_m_cost_center`** ✅ — already exists in system (confirmed 2026-05-06)

### Link to mas_employee_data — VERIFIED 2026-05-15
- `mas_employee_data.orgcode` = C-POP numeric format (e.g. `1165403`) — does NOT match SAP cost center format
- Direct join `orgcode → cost_center` is **impossible without bridge table**
- Text match (orgnameen = CC desc) unreliable — only 33% coverage even after normalization, + ambiguous
- **Correct bridge:** `dim_orgcode_costcenter_map` (orgcode → cost_center) — data from Chatdanai API

### dim_orgcode_costcenter_map — VERIFIED MANY-TO-MANY (2026-05-23)

**Relationship: many-to-many** — verified from `docs/09orgcode & costcenter.xlsx` (729 rows, 183 orgcodes, 205 CCs)
- 88 orgcodes map to multiple CCs (e.g. orgcode `1120000` → 9 CCs)
- 190 CCs map to multiple orgcodes (e.g. CC `10SP010000` → 3 orgcodes)
- **Must use junction table with composite PK — NOT single-column FK**

```sql
CREATE TABLE dim_orgcode_costcenter_map (
    orgcode     NVARCHAR(20) NOT NULL,
    cost_center NVARCHAR(20) NOT NULL,
    PRIMARY KEY (orgcode, cost_center)
);
-- 729 rows from docs/09orgcode & costcenter.xlsx
```

**Coverage gaps (from data analysis):**
- 15 Silver CCs not in map (e.g. `CMKK01`, `10IT013000`, `10GE000000`) — no owner
- 13 employee orgcodes not in map → 75 out of 585 employees cannot trace to any actuals
- Source: `docs/09orgcode & costcenter.xlsx` — already available locally (NOT waiting for Chatdanai API)

**RLS implication:** joining `mas_employee_data.orgcode → dim_orgcode_costcenter_map` returns multiple CCs per employee — use `posstatus = 'Primary'` only

### RLS Chain — Verified 2026-05-23
```
login (email)
  → mas_employee_data (empcode, orgcode, posstatus='Primary')
  → dim_orgcode_costcenter_map (orgcode → 1 or more CCs)
  → silver_sap_gl_trans (filter WHERE cost_center IN user's CCs)
```

**CC access by tier (from data analysis):**
- L1 C-Level: 2–23 CCs (broad — entire division scope)
- L2 VP/AVP: 0–69 CCs (division/sub-division)
- L3 Dept Head: 0–20 CCs (mostly 1 CC)
- L4 Supervisor: 0–69 CCs (mostly 1–3 CCs)
- Higher tier sees MORE CCs — orgcode map naturally encodes hierarchy

**CC submitter gap — 10AC020000:**
- Maps only to Piyada (L2 / orgcode 1142101) — no L4 mapped
- ❌ No L4 can submit budget for this CC
- Decision pending: allow L2 to submit, or add L4 orgcode to map

**Email domain rules — confirmed 2026-05-23:**
- `@chememan.com` ✅ company email
- `@gritsman.com` ✅ acceptable — subsidiary company
- personal email (gmail etc.) ❌ — Entra ID login ไม่ได้
- L2 (23/24) + L3 (70/70 incl. gritsman) + L4 (187/192) have acceptable email

### dim_costcenter_division_map (ready to create — from Excel master)
```sql
CREATE TABLE dim_costcenter_division_map (
    cost_center NVARCHAR(20)  NOT NULL PRIMARY KEY,
    description NVARCHAR(100) NULL,
    c_level     NVARCHAR(100) NULL,
    division    NVARCHAR(100) NOT NULL,
    department  NVARCHAR(100) NULL
);
-- Source: 02docs/02cost center & department (master).xlsx — 210 rows
```

### Complete Link Chain
```
login (email)
  → mas_employee_data (empcode, orgcode)
  → dim_orgcode_costcenter_map (orgcode → cost_center)   ← รอ Chatdanai API
  → dim_costcenter_division_map (cost_center → division + department)
  → silver_sap_gl_trans (cost_center → gl_account actuals history)
  → GL master (gl_account → group_exp + thai_name)
```

---

## Budget Form Design — Decisions Made (2026-05-15)

### CC Hierarchy (verified from 02docs/02cost center & department (master).xlsx)
- **210 CCs → 109 departments → 38 divisions** (many-to-one)
- 1 dept can have >= 1 CC (e.g. Production KK = 33 CCs)
- Machine-level CCs (KKKK01, KKTRUCK) follow the same budget rules as other CCs

### User Form Rules (confirmed)
- **1 user = 1 dept** — no user covers multiple departments
- **1 dept = multiple users** — users in same dept can collaborate (fill different CCs)
- **1 user fills ALL CCs in their dept** (same rule regardless of dept type)
- Multi-user editing in same dept: pending decision on concurrent edit / submit authority

### Budget Form UX — What User Does (only 3 things)
1. **Select Cost Center** — dropdown (CCs in their dept, active, desc ≠ "Hold")
2. **Select GL Code** — dropdown (filtered by actuals history of selected CC)
3. **Enter budget Jan–Dec** — 12 number fields
- All other fields auto-fill: division, dept, GL Thai name, GL group, yearly total

### GL Code Dropdown Design (verified from 01requirement_detail.xlsx — 2,437 rows)
- GL prefix 52xxxxx vs 62xxxxx does NOT cleanly split Factory vs HQ
- Many CCs use BOTH prefixes (e.g. People Experience at plant sites uses 52 AND 62)
- **Correct approach: filter GL dropdown by actuals history of each CC**
  - Show GLs that CC actually used in previous periods (sort first)
  - Still allow user to add any GL not in history
- Cannot filter by division/dept — not granular enough

### Reference Tables Needed in Azure SQL
| Table | Status | Source |
|-------|--------|--------|
| `dim_costcenter_division_map` | ⬜ Not created | 02docs/02cost center & department (master).xlsx (210 rows) |
| `dim_orgcode_costcenter_map` | ⬜ Waiting | Chatdanai API (orgcode → cost_center) |
| `dim_gl_master` | ⬜ Not created | 02docs/04gl code & gl group & gl thai name (master).xlsx (137 rows) |
| `capps_m_employee` | ⬜ Not created | 02docs/10CAPPS_M_EMPLOYEE.txt (305 rows) — emp_no → cost_center mapping |

### CC Visibility Logic — get_visible_ccs (2026-05-16)

Determines which cost centers each employee can see in the budget form.

**CC Code Format (10 chars):**
```
10  IT  0  1  11  00
│   │   │  │   │   └─ section
│   │   │  │   └───── sub-dept
│   │   │  └───────── dept number
│   │   └──────────── separator (always 0)
│   └──────────────── division code (IT, AC, CM, SC, SP, CS...)
└──────────────────── company prefix
```

**Rule:**
```python
def get_visible_ccs(
    emp_no: str,
    cost_center: str,       # from capps_m_employee
    joblevel: str,          # joblevelnameen from mas_employee_data (posstatus='Primary')
    posnameen: str,         # posnameen from mas_employee_data (posstatus='Primary')
    all_ccs: list[str],     # all CCs from dim_cost_center (incl. Hold)
    cc_clevel_map: dict,    # {cost_center: "C Level"} from dim_cost_center
) -> list[str]:
    if 'C-Level' in joblevel:
        return [cc for cc in all_ccs if cc_clevel_map.get(cc) == posnameen]
    elif 'Vice President' in joblevel:
        prefix = cost_center[:5]
    else:
        prefix = cost_center[:8]
    return [cc for cc in all_ccs if cc.startswith(prefix)]
```

**Prefix rules:**
| Level | prefix ตัดที่ | ครอบ |
|-------|------------|------|
| C-Level | — | join `dim_cost_center."C Level"` = posnameen |
| VP / AVP (`Vice President` in joblevelnameen) | 5 | ทั้ง division |
| ต่ำกว่า AVP | 8 | เฉพาะ sub-dept ตัวเอง |

**Data sources:**
- `cost_center` → `capps_m_employee` (emp_no → CC, end_date='9999-12-31')
- `joblevel`, `posnameen` → `mas_employee_data` (posstatus='Primary')
- `all_ccs`, `cc_clevel_map` → `dim_cost_center` (ทุกตัว รวม Hold)

**Verified with:**
- Digital Technology: Apichai (C-Level/CTO→23 CCs), Arthid (AVP→7 DT CCs), staff (prefix 8→1 CC each)
- Accounting: Sarinthip (VP→5 AC CCs), Piyada (AVP→5 AC CCs), staff (prefix 8→1 CC each)
- Corporate Strategy: Lerssak (C-Level/CSO→7 CS CCs), AVPs (prefix 5 by CC prefix 10CS0 or 10SP0), staff (prefix 8→1 CC)

**Gap:** Data & Analytics (10IT0130000, 10IT011300) ไม่มีใน CAPPS — แก้ไขทีหลัง (manual insert)

---

## Next Steps (pick up from here)

1. **Chatdanai API** — get orgcode → cost_center mapping (API endpoint, auth, response format)
2. **Create `dim_costcenter_division_map`** — load from `02docs/02cost center & department (master).xlsx` (210 rows)
3. **Create `dim_gl_master`** — load from `02docs/04gl code & gl group & gl thai name (master).xlsx` (137 rows)
4. **Meeting with user** — template filling data (Cut-off TBC), confirm concurrent edit / submit authority rules
5. Check Node.js installed (`node -v`) — required for React
6. Restructure folders: create `backend/` and `frontend/`
7. Build `backend/main.py` — FastAPI entry point + `backend/utils/auth.py` — MSAL login with Entra ID
8. Scaffold React frontend with Vite

---

## Weekly Update Tracker

- **Folder:** `weekly_update/`
- **File:** `budget management web.xlsx` — sheet `action`
- **Script:** `setup/create_weekly_update.py` — downloads SP → merges → uploads
- **Run:** `python setup/create_weekly_update.py`
- **Skill:** `skill/skill_weekly_update.md` — invoke when user says "update weekly update"
- **SharePoint target:** `General/05 Data Analytics/03 Project/6.Budgeting and Management`
- **Status:** Fully working ✅ — upload verified (2026-05-06)
- **Secret used:** `budget_managemnt_web_excel_to_sp` in `cman-fabric-write` app registration
- **Merge rule:** upsert by Action name — local ROWS wins on match, colleague-only rows preserved

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

<!-- rtk-instructions v2 -->
# RTK (Rust Token Killer) - Token-Optimized Commands

## Golden Rule

**Always prefix commands with `rtk`**. If RTK has a dedicated filter, it uses it. If not, it passes through unchanged. This means RTK is always safe to use.

**Important**: Even in command chains with `&&`, use `rtk`:
```bash
# ❌ Wrong
git add . && git commit -m "msg" && git push

# ✅ Correct
rtk git add . && rtk git commit -m "msg" && rtk git push
```

## RTK Commands by Workflow

### Build & Compile (80-90% savings)
```bash
rtk cargo build         # Cargo build output
rtk cargo check         # Cargo check output
rtk cargo clippy        # Clippy warnings grouped by file (80%)
rtk tsc                 # TypeScript errors grouped by file/code (83%)
rtk lint                # ESLint/Biome violations grouped (84%)
rtk prettier --check    # Files needing format only (70%)
rtk next build          # Next.js build with route metrics (87%)
```

### Test (60-99% savings)
```bash
rtk cargo test          # Cargo test failures only (90%)
rtk go test             # Go test failures only (90%)
rtk jest                # Jest failures only (99.5%)
rtk vitest              # Vitest failures only (99.5%)
rtk playwright test     # Playwright failures only (94%)
rtk pytest              # Python test failures only (90%)
rtk rake test           # Ruby test failures only (90%)
rtk rspec               # RSpec test failures only (60%)
rtk test <cmd>          # Generic test wrapper - failures only
```

### Git (59-80% savings)
```bash
rtk git status          # Compact status
rtk git log             # Compact log (works with all git flags)
rtk git diff            # Compact diff (80%)
rtk git show            # Compact show (80%)
rtk git add             # Ultra-compact confirmations (59%)
rtk git commit          # Ultra-compact confirmations (59%)
rtk git push            # Ultra-compact confirmations
rtk git pull            # Ultra-compact confirmations
rtk git branch          # Compact branch list
rtk git fetch           # Compact fetch
rtk git stash           # Compact stash
rtk git worktree        # Compact worktree
```

Note: Git passthrough works for ALL subcommands, even those not explicitly listed.

### GitHub (26-87% savings)
```bash
rtk gh pr view <num>    # Compact PR view (87%)
rtk gh pr checks        # Compact PR checks (79%)
rtk gh run list         # Compact workflow runs (82%)
rtk gh issue list       # Compact issue list (80%)
rtk gh api              # Compact API responses (26%)
```

### JavaScript/TypeScript Tooling (70-90% savings)
```bash
rtk pnpm list           # Compact dependency tree (70%)
rtk pnpm outdated       # Compact outdated packages (80%)
rtk pnpm install        # Compact install output (90%)
rtk npm run <script>    # Compact npm script output
rtk npx <cmd>           # Compact npx command output
rtk prisma              # Prisma without ASCII art (88%)
```

### Files & Search (60-75% savings)
```bash
rtk ls <path>           # Tree format, compact (65%)
rtk read <file>         # Code reading with filtering (60%)
rtk grep <pattern>      # Search grouped by file (75%). Format flags (-c, -l, -L, -o, -Z) run raw.
rtk find <pattern>      # Find grouped by directory (70%)
```

### Analysis & Debug (70-90% savings)
```bash
rtk err <cmd>           # Filter errors only from any command
rtk log <file>          # Deduplicated logs with counts
rtk json <file>         # JSON structure without values
rtk deps                # Dependency overview
rtk env                 # Environment variables compact
rtk summary <cmd>       # Smart summary of command output
rtk diff                # Ultra-compact diffs
```

### Infrastructure (85% savings)
```bash
rtk docker ps           # Compact container list
rtk docker images       # Compact image list
rtk docker logs <c>     # Deduplicated logs
rtk kubectl get         # Compact resource list
rtk kubectl logs        # Deduplicated pod logs
```

### Network (65-70% savings)
```bash
rtk curl <url>          # Compact HTTP responses (70%)
rtk wget <url>          # Compact download output (65%)
```

### Meta Commands
```bash
rtk gain                # View token savings statistics
rtk gain --history      # View command history with savings
rtk discover            # Analyze Claude Code sessions for missed RTK usage
rtk proxy <cmd>         # Run command without filtering (for debugging)
rtk init                # Add RTK instructions to CLAUDE.md
rtk init --global       # Add RTK to ~/.claude/CLAUDE.md
```

## Token Savings Overview

| Category | Commands | Typical Savings |
|----------|----------|-----------------|
| Tests | vitest, playwright, cargo test | 90-99% |
| Build | next, tsc, lint, prettier | 70-87% |
| Git | status, log, diff, add, commit | 59-80% |
| GitHub | gh pr, gh run, gh issue | 26-87% |
| Package Managers | pnpm, npm, npx | 70-90% |
| Files | ls, read, grep, find | 60-75% |
| Infrastructure | docker, kubectl | 85% |
| Network | curl, wget | 65-70% |

Overall average: **60-90% token reduction** on common development operations.
<!-- /rtk-instructions -->