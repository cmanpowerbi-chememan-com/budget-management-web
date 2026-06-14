# Reference — Data Platform Layer (Bronze → Silver Mapping)

What this is: the medallion landing→Bronze→Silver mapping for the SAP G/L feed — table names,
composite PK, the FAGLL03H 26-col → Silver column mapping, the 4 gap columns, and the canonical
dashboard query. Source of truth for the ETL column map. Spec file:
`docs/05CMAN-DataPlatform_Mapping_Specification _V0.0.4.xlsx`.

> **Canonical names (current state):** Bronze/Silver tables live in the Fabric **Lakehouse**
> under schema `dbo` — the `bronze_`/`silver_`/`gold_` prefix is part of the table *name*. The
> dashboard reads `dbo.gold_sap_gl_trans`. The `silver_src.sap_gl_trans` / `bronze_src.ACDOCA`
> names below are the original mapping-spec names; the deployed Lakehouse tables are
> `dbo.silver_sap_gl_trans` and `dbo.bronze_ACDOCA`.

---

## Table Names

| Layer | Mapping-spec name | Deployed Lakehouse name | Col Count |
|-------|-------------------|--------------------------|-----------|
| Landing (flat file) | `SAP_T_GL_TRANS_[COMPANY_CD]_YYYYMMDD.txt` | — | — |
| Bronze | `bronze_src.ACDOCA` | `dbo.bronze_ACDOCA` | 93 (85 SAP data + 1 pipeline + 7 control) |
| Silver | `silver_src.sap_gl_trans` | `dbo.silver_sap_gl_trans` | 92 (85 data + 7 control) |
| Gold (dashboard read) | — | `dbo.gold_sap_gl_trans` | — |

### Key Facts
- **Landing file naming:** `SAP_T_GL_TRANS_1000_YYYYMMDD.txt` — Company Code `1000` = CMAN TH, `2000` = CMAN AU
- **Silver filter:** `WHERE RLDNR = '0L'` — only Ledger 0L rows promoted from bronze to silver
- **Composite PK (5 cols):** `ledger + accounting_doc_number + company_code + fiscal_year + posting_item_number`
- **Bronze-only col (not in silver):** `PRCS_FILE_NAME` — pipeline constant storing source filename
- **2 cols with transform (not plain Move):** `exchange_rate` (BKPF_KURSF) and `group_exchange_rate`
  (BKPF_KURS2) — trailing `-` sign flipped to leading `-` before DECIMAL cast

---

## FAGLL03H 26 cols → Silver Mapping (cols used by this project)

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
| Entry Date | **NO MAP** (was gap; fixed) | `CPUDT` / `BKPF_CPUDT` | Date col — parse `yyyyMMdd` |
| Order: Short Text | **NO MAP** | — | Display only — NULL acceptable |
| Text | `item_text` | `SGTXT` | Line item description display |
| Order | **NO MAP** (was gap; fixed) | `AUFNR` | Display only |
| Quantity | `quantity` | `MSL` | Reference display |
| Unit of Measure | `base_unit_measure` | `RUNIT` | Reference display |
| Purchasing Document | `purchase_order_number` | `EBELN` | Reference display |
| Invoice Reference | `ref_doc_number2` | `BKPF_XBLNR` | Reference display |
| G/L Account (dup col 23) | `gl_account_number` | `RACCT` | Duplicate — skip |
| Fiscal Year | `fiscal_year` | `GJAHR` | Group by year |
| Object Class | **NO MAP** (was gap; fixed) | `SCOPE` | Display only |
| Debit/Credit ind | `debit_credit_ind` | `DRCRK` | `S`=expense `H`=reversal — sign logic for SUM |

---

## Gap Columns — 4 Missing from Pipeline (resolution)

Ticket raised to SAP team to add 4 columns to the landing file `sap_t_gl_trans`. Status: validated
via Ratima's test file `SAP_T_GL_TRANS_1000_RATIMA_TEST1`; a separate `SAP_M_INTERNAL_ORDER` master
file carries Order + Short Text.

| FAGLL03H Col | SAP Field | Original Gap | Resolution |
|---|---|---|---|
| G/L Account: Long Text | — | Not in ACDOCA | Create `dim_gl_account` ref table |
| Cost Center: Long Text | — | Not in ACDOCA | Use `dbo.gold_sap_m_cost_center` (also division mapping) |
| Entry Date | `CPUDT` / `BKPF_CPUDT` | Not extracted into bronze | Added to landing; parsed `to_date(c, "yyyyMMdd")` — SAP date has no dash, plain `.cast("date")` fails |
| Order / Order: Short Text | `AUFNR` | Not in ACDOCA | Added to landing + `SAP_M_INTERNAL_ORDER` master file |

Bronze→Silver mapping deployed: 88 cols (85 spec + POPER + entry_date + order_number + object_class +
object_class_desc lookup), sign-flip on 6 amount/FX cols.

---

## Dashboard Query Pattern

```sql
SELECT
    fiscal_year,
    MONTH(posting_date) AS month,
    gl_account_number,
    cost_center,
    SUM(CASE WHEN debit_credit_ind = 'S' THEN company_curr_amount
             WHEN debit_credit_ind = 'H' THEN -company_curr_amount END) AS actuals_thb
FROM dbo.gold_sap_gl_trans          -- mapping-spec name: silver_src.sap_gl_trans
WHERE company_code = '1000'
  AND doc_type <> 'CO'
  AND cost_center NOT IN ('10SC012000','CMRY01','CMKK01','CMPB01','MNLB00-04')
  AND cost_center IS NOT NULL
  AND assignment_number <> 'TFRS16'
GROUP BY fiscal_year, month, gl_account_number, cost_center
```
