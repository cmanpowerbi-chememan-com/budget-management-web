# SAP Actuals wrong on web — root cause + fix plan

Date: 2026-07-30 · Author: Claude (diagnosis session) · Task: `#actuals-month-mismatch`
Status: **PARTIALLY FIXED 2026-07-31** — Inteltion rebuilt `fact_gl_trans` overnight (3 FAILs,
then COMPLETE 00:23). Hole 1 (entry-days 2026-02-28→03-30) loaded → web Feb/Mar correct,
32-key parity clean (m02 16/16, m03 13/13). **Hole 2 remains: entry-days 2026-04-30→today**
→ web April still wrong (8/11 cells). FY2019 pre-03-27 = pre-go-live, not a hole.
Re-confirmed 2026-07-31 11:00 on 3 fixtures / 236 cells: FY2025 **0** real defects, FY2026
m01–m03 **0**, FY2026 m04 **9**, FY2026 m05–m12 **zero rows in gold** — details in
[db-web-actuals-parity-check.md](db-web-actuals-parity-check.md). Still open:
load Apr-30+ (§4.A.1) + enable the never-run daily schedule (§4.A.2) — `PLD_SAP_T_GL_TRANS_D`
has 0 runs, no month glob after `202606` registered.

## 1. Symptom

Web grid (SAP · ใช้จริง 2026) shows wrong monthly amounts vs SAP export
(`backend/tests/tests_data_sync/Book2 2.xlsx`, posting-date view, truth):

| key (cc / gl) | month | SAP export (truth) | web | delta |
|---|---|---|---|---|
| 10AC012000 / 6210900060 | Jan | 7,979.00 | 7,979 | 0 ✓ |
| 10AC012000 / 6210900060 | Feb | 8,623.00 | 7,979 | -644 |
| 10AC012000 / 6210900060 | Mar | 10,345.88 | 358 | -9,987.88 |
| 10AC012000 / 6210900060 | Apr | 3,507.00 | 8,981 | +5,474 |
| 10AC013000 / 5210600010 | Jan | 500.00 | 500 | 0 ✓ |
| 10AC013000 / 5210600010 | Feb | 500.00 | -500 | -1,000 |
| 10AC013000 / 5210600010 | Mar | 500.00 | 1,000 | +500 |
| 10AC013000 / 5210600010 | Apr | 500.00 | -500 | -1,000 |

## 2. What was ruled out (verified, do not re-check)

- **Backend query is CORRECT.** Running `SAP_ACTUALS_SQL` (backend/app/sap.py) against
  `cman_dw_wh_gold.gold.fact_gl_trans` reproduces the web numbers exactly
  (m01 7979 / m02 7979 / m03 358 / m04 8981). No filter bug, no month-shift, no sign bug.
- Not a doc_type / assignment_number / cost-center-exclusion filter effect.
- `gold_bi.fact_gl_trans` has ZERO FY2026 rows — no fresher sibling table exists.
- **The web/API layer is faithful to the DB.** `fetch_sap_actuals()` (the function the
  FastAPI backend actually serves) vs a direct SQL SUM: **0 mismatch across 32 keys × 12
  months, both FY2025 and FY2026** (measured 2026-07-30 on the `2025-04.2026.xlsx` key set).

### 2b. Three-fixture reconcile, 2026-07-30 (`2025-04.2026.xlsx`, 3 ฝ่าย, 32 cc/gl keys)

204 (year, cc, gl, month) cells compared → 30 DIFF. Split by cause:

| # cells | year | cause | verdict |
|---|---|---|---|
| 26 | FY2026 | missing docs (entry-day holes, §3) | **real DW defect** |
| 1 | FY2025 | Excel row is a `doc_type='CO'` posting (doc 8100014664, 5,300) that the app filter drops on purpose (ADR-0020) | expected — fixture is a raw export |
| 2 | FY2025 | Excel amount column holds **transaction currency (USD)** for FX docs while DW/web is THB — verified: doc 2810001487 trans_amount USD 275.00 × fx 32.6224 = **THB 8,971.16** (Excel said 275) | expected — fixture column, DW is right |
| 1 | FY2025 | doc-set differs only: `assignment_number='TFRS16'` lease pair (1110001848 / 1900002064) excluded by design; the pair nets to 0.00 so the **amount matched exactly** (-107.23) | expected |

→ **FY2025 has ZERO real DW errors** across all 32 keys / 3 ฝ่าย. Every FY2025 DIFF is an
intentional app filter or a fixture-column artifact. The defect is FY2026-only.

### 2c. Per-month breakdown — the defect starts in **February 2026**

Doc-presence based (currency-independent), same 32-key fixture:

| month | cells | cells DIFF | Excel docs | docs missing in DW | THB delta (Excel − DW) |
|---|---|---|---|---|---|
| FY2025 m01–m12 | 153 | 3 (all explained §2b) | 3,086 | 3 (CO + TFRS16 pair, by design) | 0.00 except the 2 FX cells |
| **2026-01** | 11 | **0** | 243 | **0** | **0.00** ✓ clean |
| 2026-02 | 16 | 8 | 236 | 64 | +366,641.91 |
| 2026-03 | 13 | 10 | 276 | 192 | +539,888.56 |
| 2026-04 | 11 | 8 | 239 | 79 | +394,750.20 |

FY2026 total shortfall on these 32 keys alone = **1,301,280.67 THB**. January 2026 is clean
because Jan-posted docs were entered Jan–mid-Feb (inside a loaded window) and no Jan-posted
doc in these keys was entered after 2026-04-30. Company-wide the Jan column can still lose
late-entered backdated postings — measured clean for these keys only.

**Consequence for any parity test** (fixtures are raw SAP exports, the app is not):
before comparing, the Excel side must (a) drop `doc_type='CO'` rows, (b) drop
`assignment_number='TFRS16'` rows, (c) either skip or FX-convert rows whose transaction
currency ≠ THB. Without this the test reports false failures on FY2025.

## 3. Root cause (confirmed with doc-level evidence)

`gold.fact_gl_trans` is **missing source documents**. For key 10AC012000/6210900060 the SAP
export has 14 rows; DW has only 8. Missing docs (0 rows in gold AND silver, any CC):
`1900000370, 1110000641, 3110001512, 3110001584, 1900000724, 1110001487`
(+ for key 10AC013000/5210600010: `3110001330, 1110000607, 1900000371, 3110003046, 1110001426`).

Why: the SAP→DW feed is **daily entry-date files** `SAP_T_GL_TRANS_<bukrs>_<YYYYMMDD>.TXT`
(file dated D contains docs ENTERED on day D-1, regardless of posting date), landing →
`bronze_src.ACDOCA` (transient, truncate per batch) → `silver_src.sap_gl_trans` (append per run)
→ `gold.fact_gl_trans` (full rebuild 2026-06-23, `prcs_data_dt` 2026-04-30).

Silver ingest runs, entry-day (utc_timestamp) coverage measured for company 1000:
2026-05-11 → entry-days 2026-01-31..02-27 (154,477 rows) · 2026-06-04 → 2026-01-01..02-19
(310,933) · 2026-06-05 → 2026-03-31..04-29 (216,411) · (2026-05-13 run: 35,424 FY2026 rows,
non-1000/old-year stamps).

**Coverage holes in the loaded entry-day windows (measured, exact):**
1. entry-days **2026-02-28 → 2026-03-30** (31 days) never loaded → Feb-close
   accruals/reversals (posted 28 Feb / 1 Mar) + mid-March invoices are absent.
2. entry-days **2026-04-30 → today** never loaded → Apr-close accruals/reversals +
   everything entered May onward (incl. backdated postings into Jan–Apr) absent.
3. **No load at all since 2026-06-05** → data frozen at entry-day 2026-04-29.

### 3b. Raw-file-layer proof (control-framework ledger, 2026-07-30)

The loader's own ledger lives in warehouse **`cman_dw_wh_cntlfw`** (note: the DB name carries a
trailing zero-width space — `'cman_dw_wh_cntlfw​'`; connect with the exact string from
`sys.databases`). SP `cman-fabric-write` can read it over SQL. (It CANNOT read the raw `.TXT`
bytes — OneLake DFS on lakehouse `cman_dw_lh_landing` / ws `302668d3` returns **403 Forbidden**
for this SP; byte-level inspection needs a OneLake role grant.)

What the ledger proves:

| evidence | value |
|---|---|
| `CNTL_CFG_FILE` registered SAP txn globs | `SAP_T_GL_TRANS_*_yyyyMMdd` (id 17, daily) · `*_202604*` (9015) · `*_202605*` (9018) · `*_202606*` (9021) — **no `*_202603*` glob exists at all** |
| `PLD_SAP_INIT_T_GL_TRANS_D_APR2026` | DATA_DT 2026-04-30, file `SAP_T_GL_TRANS_*_202604*.TXT`, SRC_ROW_CNT = INS_ROW_CNT = **223,146**, COMPLETE, ran 2026-06-05 16:12 |
| `..._MAY2026` / `..._JUN2026` processes | configured, streams `STM_INIT_T_SAP_MAY2026`/`JUN2026` exist — **zero runs**, DATA_DT never advanced past 2026-01-31 |
| `PLD_SAP_T_GL_TRANS_D` (the DAILY loader) | **zero runs in the entire log** (77 distinct process names, none is this one) |
| `bronze_src.ACDOCA` today | 223,146 rows, `PRCS_FILE_NAME` = only `SAP_T_GL_TRANS_{1000,2000}_202604{01..30}.TXT` → bronze is a 1:1 copy of the **April batch only** |
| `CNTL_CFG_PURGE` | **0 rows** → no purge configured, so nothing indicates the raw files were deleted (unverified — file listing blocked) |
| `CNTL_STREAM_LOG` | `STM_INIT_T_SAP_APR2026` 2026-06-05 16:11 → **FAIL "Fail at transform"**, even though its bronze + silver child processes reported COMPLETE. Worth a DW-team look. |

**So the load is not a schedule at all — it is hand-registered one-month-at-a-time backfills.**
March was never registered, May/June/July were registered but never executed, and the daily
process has never run once.

**Entry-date bracket for the two docs the user asked about** (1900000370, 1110000641 — the
`-7,979` and `+8,623` legs of the Feb cell): the Feb batch loaded entry-days through
**2026-02-27** and the April batch starts at entry-day **2026-03-31**. Both docs are absent
from both → their entry date is provably in **[2026-02-28, 2026-03-30]**, i.e. inside files
`SAP_T_GL_TRANS_1000_202603xx.TXT`, which no process ever read. They were never filtered out
and never deleted — **they were never ingested**.

Scale (FY2026, company 1000, distinct docs in gold): Jan 33,821 · Feb 26,901 · **Mar 8,640** ·
Apr 27,654 — vs FY2025 baseline 29–38k/month → March is ~70% missing; every month has holes.
This affects **every cost center / GL**, not just the two reported keys.

Docs POSTED in a month but ENTERED inside a hole are what makes cells "เพี้ยน":
web Mar 358 = 8,981 (accrual, entered 31 Mar ✓loaded) − 8,623 (reversal, entered 1 Mar file ✓)
while the DHL 1,123.88 + invoice 8,864 (entered mid-March = hole) are missing.

## 4. Fix plan

### A. DW pipeline (owner: DW workspace `cman-dw-ws` — outside this repo) — THE actual fix
0. **FIRST: confirm the raw files still exist, in BOTH places** (unresolved — see §3b, the SP
   is 403 on OneLake Files and 401 on `getDefinition`, so this could not be checked from here):
   (a) Fabric side — lakehouse `cman_dw_lh_landing` → `Files/PRD/` (the `FILE_PATH` values in
   `CNTL_CFG_FILE` are relative folders; `PRD/` resolving to that Files tree is an inference,
   not verified — the resolving pipeline is `10 - Pipeline - Ingest data from source`, unreadable
   with this SP). (b) SAP side — the export drop/share, because the copy-INTO-Fabric step is
   driven by the SAME `CNTL_CFG_FILE` registrations, so unregistered months (March, and July
   onward) may never have been copied into Fabric at all. If neither side still has them, SAP
   must re-extract before any reload.
   **→ RESOLVED 2026-07-30: no SAP re-extract needed.** The 19.dw lane's landing
   (`modern_lh_cman_dw` › `Files/landing/transaction/`, ws adeb7108) holds the complete daily
   series `SAP_T_GL_TRANS_1000_20260101..20260730.TXT` (211 files, zero gaps) and a raw scan
   found **326/326** of the docs missing from DW (m02 64 / m03 192 / m04 79 tuples,
   field-parsed doc+company+year). Company 1000 only — sufficient for the budget web
   (`company_code='1000'` filter). Inteltion can backfill from this path or their own SAP drop.
1. Re-extract / re-drop the missing daily files: entry-days 2026-02-26→2026-03-30 and
   2026-04-30→today (both companies 1000 + 2000), load through bronze→silver.
2. De-dup guard: silver append must not double-insert already-loaded docs
   (key = company, fiscal_year, doc, line item).
3. Rebuild `gold.fact_gl_trans`, verify `prcs_data_dt` advances.
4. Schedule the daily load (currently manual/ad-hoc — last run 2026-06-05).
5. Reconcile: per-month doc counts vs SAP TB / export; the two keys above must match Excel.

### B. This repo (budget app) — detection, not correction
1. **Parity test** (Kimi task below): `backend/tests/tests_data_sync/` gets a live-DB test
   that parses `Book2 2.xlsx` → expected (cc, gl, month) sums → compares against
   `fetch_sap_actuals()` output. Fails today (documents the gap); passes after DW reload.
   Re-run after every DW reload as verify-deploy-landed evidence.
   → **The harness now has its own owner doc: [db-web-actuals-parity-check.md](db-web-actuals-parity-check.md)**
   (fixture registry, artifact classifier, per-run verdict). Keep run results there, root cause here.
   2026-07-31 run: FY2025 + FY2026 m01–m03 clean; **9 real defects, all FY2026 April**; FY2026
   m05–m12 have zero rows in gold. The `Book2 2.xlsx` / `2026_1_4.xlsx` fixture was renamed to
   `A 2026_1_4.xlsx` (same data), which broke 4 unit tests — fix per that doc §P1.
2. (Later, optional) surface actuals freshness (`MAX(prcs_data_dt)`) in the UI so stale
   actuals are visible to users instead of silently wrong. NOT in scope for the Kimi task.

### C. Do-NOT list
- Do NOT "fix" numbers in backend/app/sap.py — the query is verified correct.
- Do NOT hand-patch amounts in gold/silver.
- Financial contract (company_code='1000', doc_type<>'CO', NULL-safe assignment_number,
  cost_center IS NOT NULL) stays untouched (ADR-0020).

## 5. Prompt for Kimi (copy-paste)

```
Read .claude/project-context.md and CLAUDE.md first. Run `python tracker/task.py list`,
then `python tracker/task.py add --id sap-parity-test --state doing --agent kimi
--ai "build Book2 parity test per plan/sap-actuals-dw-gap-fix.md §5"`.

TASK: create backend/tests/tests_data_sync/test_sap_actuals_parity.py — a data-parity
test proving web actuals == SAP export, so we can verify the DW reload lands.

Context: plan/sap-actuals-dw-gap-fix.md (read it). Root cause already found —
gold.fact_gl_trans is missing docs (entry-day file holes). Backend query is CORRECT;
do NOT modify backend/app/sap.py or any app code. Test-only change.

Spec:
1. Parser (pure function, unit-testable offline):
   read backend/tests/tests_data_sync/Book2 2.xlsx with openpyxl (header row 1:
   Cost Center, Account Number, Posting Date, year, month, Document Number,
   Amount in Company Code Currency). Return dict
   {(cost_center, gl_account, month:int): Decimal_sum} and doc-level rows.
   Month comes from the `month` column (= posting-date month). Use Decimal, not float,
   for sums; open workbook with data_only=True.
2. Live comparison (pytest, needs DB — follow the existing live-test conventions in
   backend/tests/test_integration_live.py; skip cleanly when env/DB absent):
   - conn = get_gold_conn() (backend/app/db.py), data = fetch_sap_actuals(conn, 2026).
   - For every (cc, gl) key in the Excel: compare m01..m12 vs Excel sums
     (months absent in Excel = expected 0 for that key's comparison scope: only compare
     months 1-4 which the export covers).
   - On mismatch, also query doc-level rows for that key from gold.fact_gl_trans and
     print which Document Numbers from Excel are MISSING in DW (set difference) —
     the report must name docs, not just amounts.
   - Assert all cells match; the failure report table goes to
     backend/tests/tests_data_sync/parity_report.txt (utf-8) AND the assert message.
3. EXPECTED RESULT TODAY: the live test FAILS with exactly these missing docs for
   key (10AC012000, 6210900060): 1900000370, 1110000641, 3110001512, 3110001584,
   1900000724, 1110001487 — if your run shows the same set, the test is working
   correctly (the bug is upstream in DW, currently unfixed). Do NOT weaken the assert
   to make it pass. Unit tests for the parser must PASS.
4. Run: parser unit tests offline (`python -m pytest backend/tests/tests_data_sync -k unit -v`
   or equivalent) and the live test once (backend/.env present, python -X utf8,
   ODBC Driver 17). Windows gotchas: every open() uses encoding="utf-8"; no inline
   python -c with control flow.
5. Log result: `python tracker/task.py done --id sap-parity-test --ai "<what you built,
   test run outcome incl. the missing-doc set observed, commit hash>"`. Commit with a
   clear message. Do not touch tracker/pending.json by hand.
```

## 6. Evidence trail (for re-verification)

Probes (scratchpad, session 4c7058fb): probe_gold (doc-level 8 rows + app aggregation),
probe_gold2 (0 FY2026 rows for missing docs table-wide; single full-load 2026-06-23),
probe_gold3 (per-month doc counts; gap shape), probe_silver/probe_bronze (silver runs,
bronze=ACDOCA transient), probe_ts (daily entry-date files SAP_T_GL_TRANS_*,
TIMESTAMP windows 2026-03-31→04-29 in last batch), probe_goldbi (gold_bi empty FY2026).
