# DB → web actuals parity — verification harness + 2026-07-31 run

Date: 2026-07-31 · Author: Claude (verification session) · Task: `#sap-parity-3files-2026-07-31`
Owner doc for: **the repeatable check "does the web show the same actuals as SAP?"**
Companion doc: [sap-actuals-dw-gap-fix.md](sap-actuals-dw-gap-fix.md) — owns the *root cause + DW fix*
of the entry-day ingest holes. This doc owns the *detection harness* (that doc's §B.1) and the
verdict of each run. Do not duplicate root-cause analysis here; link to it.

---

## 0. Verdict (run of 2026-07-31, live `cman_dw_wh_gold`)

**Web actuals are CORRECT for all of FY2025 and for FY2026 January–March. The only wrong
column left is FY2026 April — and FY2026 May–July are empty (no rows in the DW at all).**

| scope | cells compared | real defects | verdict |
|---|---|---|---|
| FY2025 (3 fixtures, 33 keys, m01–m12) | 177 | **0** | ✅ clean — every DIFF is an intentional app filter or a fixture-column artifact (§3) |
| FY2026 m01–m03 | 33 | **0** | ✅ clean — Feb/Mar reload landed (was 18 DIFF on 2026-07-30) |
| FY2026 m04 | 26 | **9** | ❌ missing source documents (entry-day hole 2026-04-30→today) |
| FY2026 m05–m12 | not covered by fixtures | — | ⚠️ `gold.fact_gl_trans` has **zero FY2026 rows after m04** → web shows 0 for May onward |

- Net money error on FY2026 April, union of the fixtures' 33 (cost center, GL) keys:
  **−389,276.20 THB** (web − Excel; mixed signs because reversals are missing too).
- `gold.fact_gl_trans` company 1000: `MAX(prcs_data_dt)` = **2026-04-30**, 21,881,553 rows.
- Distinct-doc counts per month, company 1000 — the March recovery is visible, the April/May cliff is not fixed:

  | FY2026 | m01 | m02 | m03 | m04 | m05–m12 |
  |---|---|---|---|---|---|
  | 2026-07-30 (before reload) | 33,821 | 26,901 | 8,640 | 27,654 | 0 |
  | **2026-07-31 (now)** | 33,821 | **35,647** | **39,600** | 27,684 | **0** |

  FY2025 baseline for comparison: 29,409–38,002 docs/month. April 2026 at 27,684 is ~20% light;
  May–July are simply absent.

---

## 1. Fixtures — what each file is, and what it can prove

All live in `backend/tests/tests_data_sync/`. All are **raw SAP exports** (posting-date view),
one row per document line, header on row 1.

| file | rows | keys (cc/GL) | coverage | control total | role |
|---|---|---|---|---|---|
| `A 2026_1_4.xlsx` | 26 | 2 | FY2026 m01–m04 | 32,454.88 | the original 2-key regression fixture |
| `A 2026_1_12.xlsx` | 77 | 2 | FY2025 m01–m12 | 118,682.84 | **new** — prior-year control on the same 2 keys |
| `2025-04.2026.xlsx` | 4,281 | 32 | FY2025 m01–m12 + FY2026 m01–m04 | 10,352,735.23 | breadth: 3 ฝ่าย, 3 cost centers, 24 GLs |

Notes that matter:

- **`A 2026_1_4.xlsx` is byte-for-byte the same data as the deleted `2026_1_4.xlsx`** (verified:
  identical 26-row set, identical monthly sums). It was renamed, not re-exported — it carries no
  new truth. The *new* truth in this batch is `A 2026_1_12.xlsx` (FY2025 full year).
- `2025-04.2026.xlsx` has **14 columns** — it adds `Purchasing Document`; the two `A …` files have 13.
  A parser must locate columns **by header name**, never by position.
- The exports carry **no `doc_type`, no `assignment_number`, no currency column**. Every
  classification in §3 therefore requires a per-document lookup against `gold.fact_gl_trans` —
  it cannot be done from the spreadsheet alone.
- Union of all three = **33 distinct (cost center, GL) keys**; `10AC013000/5210600010` is the one
  key shared between `A 2026_1_4.xlsx` and `2025-04.2026.xlsx`, so its April defect must be counted once.

---

## 2. What the 2026-07-31 run actually found

Command used (read-only diagnostic, scratchpad — see §6 for the permanent version):
parse each fixture → sum `Amount in Company Code Currency` per (cc, GL, year, month) → compare
against `app.sap.fetch_sap_actuals(conn, year)` → on any DIFF, pull the document set from
`gold.fact_gl_trans` under the exact ADR-0020 filter and classify each missing document.

236 cells compared, 13 DIFF, **9 unique real defects** (one cell is double-counted across two fixtures):

| key | FY | month | Excel | web | delta | cause |
|---|---|---|---|---|---|---|
| 10AC012000/6210900060 | 2026 | 04 | 3,507.00 | 8,981.00 | +5,474.00 | 2 docs ABSENT (1110001487, 1900000724) |
| 10AC013000/5210600010 | 2026 | 04 | 500.00 | −500.00 | −1,000.00 | 2 docs ABSENT (1110001426, 3110003046) |
| 10AC013000/5211100060 | 2026 | 04 | 0.00 | −1,600.00 | −1,600.00 | 1 doc ABSENT (5100003647) |
| 10FN011000/6210900010 | 2026 | 04 | 7,371.16 | 1,804.13 | −5,567.03 | 1 doc ABSENT (1110001609) |
| 10FN011000/6210900060 | 2026 | 04 | 336.00 | 827.00 | +491.00 | 2 docs ABSENT |
| 10FN011000/6211400040 | 2026 | 04 | 119,501.00 | 80,578.61 | −38,922.39 | **65 docs ABSENT** |
| 10FN011000/6211900050 | 2026 | 04 | −526.06 | −2.33 | +523.73 | 6 docs ABSENT |
| 10FN011000/6510200010 | 2026 | 04 | 347,747.67 | 0.00 | −347,747.67 | 1 doc ABSENT (1110001454) |
| 10FN014000/6210900010 | 2026 | 04 | 1,391.76 | 463.92 | −927.84 | 1 doc ABSENT (1110001609) |

Every single one is FY2026 **April**, and every one is "document not in the DW at all" — never a
filter effect, never a sign or month shift. That is the signature of
[the entry-day ingest hole](sap-actuals-dw-gap-fix.md#3-root-cause-confirmed-with-doc-level-evidence),
not an app bug.

---

## 2b. Which landing files hold the missing documents (scanned 2026-07-31)

Scanned OneLake directly: workspace `cman-dw-ws` (`adeb7108-…`), lakehouse `modern_lh_cman_dw`
(`7dd0c6a5-a36f-46c7-8953-0248841dcdc8`), path `Files/landing/transaction/`. The service principal
CAN read this path (the 403 in the gap-fix doc was the *other* landing lakehouse, ws `302668d3`).

**Landing inventory:** 212 files `SAP_T_GL_TRANS_1000_YYYYMMDD.TXT`, 2026-01-01 → 2026-07-31,
763,398,960 bytes, **zero date gaps**. (Company 2000 files are not in this folder.)

**File-date ↔ entry-date rule — measured, not assumed.** Each file is pipe-delimited with a header
row (86 columns: `RLDNR|BELNR|RBUKRS|GJAHR|…|TIMESTAMP|…`). The `TIMESTAMP` column of every file
spans **exactly one day = filedate − 1**. So `…_20260502.TXT` contains precisely the documents
entered on 2026-05-01.

**Result — all 78 documents missing from the DW were located, field-exact on `BELNR`:**

| landing file | entry date | missing docs it holds |
|---|---|---|
| `SAP_T_GL_TRANS_1000_20260501.TXT` | 2026-04-30 | 12 |
| `SAP_T_GL_TRANS_1000_20260502.TXT` | 2026-05-01 | **40** |
| `SAP_T_GL_TRANS_1000_20260503.TXT` | 2026-05-02 | 23 |
| `SAP_T_GL_TRANS_1000_20260504.TXT` | 2026-05-03 | 3 |
| **total** | | **78 / 78 — none found in any other file** |

**Posting month of all 78: 202604 — 100%.** Textbook April-close behaviour: posted into April,
keyed 30 Apr–3 May. Example: document `1110001454` (the 347,747.67 THB cell) — 12 line items,
posting date 2026-04-30, entered 2026-05-01, sitting in `…_20260502.TXT`.

**Why the DW does not have them:** the April backfill was registered as the glob `*_202604*`, which
matches file names `20260401`–`20260430` = entry days 31 Mar–29 Apr. The four files that carry these
documents are named `202605xx`. A `*_202605*` glob **is** registered (`CNTL_CFG_FILE` id 9018) but
has never been executed. The cut is exactly one day wide, and the data has been sitting in landing
the whole time.

Caveat on method: a plain text search for `|<docnumber>|` also matches reference fields
(`AWREF_REV`, `AUGBL`), which put false hits in early-April files. Only the header-mapped `BELNR`
column counts — the table above uses that.

## 3. Excel-side normalization rules (mandatory — otherwise the test lies)

The fixtures are raw exports; the app is filtered (ADR-0020). Three classes of DIFF are **expected**
and must be classified, not reported as failures. All three were re-proved in this run:

1. **`doc_type='CO'` postings** — dropped by the app on purpose.
   Proof: `10AC013000/5211100060` FY2025 m04, Excel 6,500.00 vs web 1,200.00; the 5,300.00 gap is
   document `8100014664`, present in the DW with `doc_type='CO'`. Document numbers starting `8100`
   are the CO number range — useful as a hint, but classification must still be confirmed against the DW.
2. **`assignment_number='TFRS16'` lease pairs** — excluded by design; the pair nets to 0.00 so the
   amount usually still matches and only the doc set differs.
3. **Foreign-currency documents** — the export's "Amount in Company Code Currency" column holds the
   **transaction currency** amount for FX documents, while the DW holds THB. Proved exhaustively this
   run on `10FN011000/6211400040`:

   | cell | Excel docs | DW docs | Excel sum | DW sum (THB) | every DIFF doc |
   |---|---|---|---|---|---|
   | FY2025 m05 | 211 | 211 | 78,414.68 | 201,289.24 | Excel value == DW `trans_amount`, `trans_curr='USD'` |
   | FY2025 m07 | 181 | 181 | 39,976.00 | 64,564.39 | same — 27 USD documents |

   Example: document `2810001487` — Excel 275, DW `trans_amount` 275.00 USD, `company_curr_amount`
   8,971.16 THB. **The DW is right; the fixture column is the artifact.** Doc sets are identical
   (211 = 211, 181 = 181), so nothing is missing.

→ **FY2025 has zero real DW errors across all three fixtures.** Confirmed again today.

---

## 4. Blocker in this repo (found while checking)

`backend/tests/tests_data_sync/test_sap_actuals_parity.py` hardcodes
`EXPORT_PATH = .../2026_1_4.xlsx`. That file was renamed to `A 2026_1_4.xlsx`, so **4 of its 5 unit
tests now fail with `FileNotFoundError`** — the harness is dead until it is repointed:

```
FAILED TestParseSapExport::test_monthly_sums_match_sap_truth
FAILED TestParseSapExport::test_sums_are_decimal_and_exact
FAILED TestParseSapExport::test_doc_level_rows
FAILED TestParseSapExport::test_export_covers_exactly_the_two_reported_keys
4 failed, 1 passed, 1 deselected
```

It is also single-fixture, FY2026-only, and has no classifier for the §3 artifacts — so it cannot
consume the two new files as-is.

---

## 5. Plan of work

### P1 — Rebuild the parity harness as multi-fixture (this repo, test-only) — **do first**

Owner: 05-software-developer (inline). Scope: `backend/tests/tests_data_sync/` only.
Do **not** touch `backend/app/sap.py` — the query is verified correct.

1. Replace the single `EXPORT_PATH` with a fixture registry: `(filename, expected_years, expected_months)`
   for the three files, so adding a future export is one line.
2. Parser stays pure and offline: header-name lookup, `Decimal` only, `data_only=True`, tolerate the
   14-column variant. Unit tests pin each fixture's row count, key set, and **control total**
   (26/32,454.88 · 77/118,682.84 · 4,281/10,352,735.23) — a re-export that changes the file is then a
   loud failure, not a silent drift.
3. Live test compares every (cc, GL, year, month) cell the fixtures cover, both fiscal years.
4. Add the §3 classifier: on DIFF, look each missing document up in `gold.fact_gl_trans` and bucket it
   `ABSENT` / `CO` / `TFRS16` / `FX(trans_curr≠THB)`. **Only `ABSENT` fails the test**; the other three
   are reported as expected artifacts with their amounts.
5. Report to `parity_report.txt` (utf-8) with a per-(year, month) clean/dirty summary line, plus the
   control-total reconcile per year.
6. Expected result on today's DW: **FAIL with exactly the 9 April cells in §2, and zero DIFF anywhere
   else.** Do not weaken the assert to make it pass.

DoD: unit tests green offline; live test fails with exactly the §2 set; `pytest -m integration` still
skips cleanly with no `.env`.

### P2 — Pin today's verdict as the regression baseline (this repo)

Store the §0 verdict table as the expected state (a small JSON or a module constant next to the test)
so the *next* run reports "improved / unchanged / regressed" instead of a wall of numbers. Cheap, and
it turns the harness into deploy-landed evidence.

### P3 — DW load, the actual fix (owner: Inteltion / `cman-dw-ws` — outside this repo)

Unchanged from [sap-actuals-dw-gap-fix.md §4.A](sap-actuals-dw-gap-fix.md#4-fix-plan), now narrowed
by today's evidence to two items:

1. Load entry-days **2026-04-30 → today** (company 1000 + 2000), bronze → silver → rebuild gold.
   Source files exist and are complete — 212 files, 2026-01-01 → 2026-07-31, zero gaps (§2b), so
   **no SAP re-extract is needed**. This one load fixes the April column *and* makes May–July appear.
   **Minimum fix for the April column alone = 4 files** (`…_20260501` … `…_20260504.TXT`), which hold
   all 78 missing documents; register the `*_202605*` glob (already configured, never run) and
   continue with `*_202606*` / `*_202607*` for the empty months.
2. Turn on the daily loader `PLD_SAP_T_GL_TRANS_D` (still **zero runs**, and no month glob is
   registered after `202606`). Without it the same hole reopens next month.

Verification: re-run P1's harness; the expected outcome is 0 real defects across all 236 cells and
`MAX(prcs_data_dt)` advancing past 2026-04-30.

### P4 — Actuals-freshness signal in the UI (this repo, optional, after P1)

Surface `MAX(prcs_data_dt)` on the grid so users see "actuals as of 30 Apr 2026" instead of silently
trusting an empty May. Small, high value while P3 is out of our hands. Needs its own design pass —
not in the P1 scope.

### P5 — Re-run cadence

Run the harness after every DW reload and before any production deploy that changes the actuals path.
It is the `verify-deploy-landed` evidence for this data flow.

---

## 6. How to re-run

```bash
cd backend
python -X utf8 -m pytest tests/tests_data_sync -v                      # offline parser + control totals
python -X utf8 -m pytest tests/tests_data_sync -m integration -v       # live parity (needs backend/.env)
```

Live run needs `backend/.env` (Fabric service-principal credentials) and ODBC Driver 17. The run
behind this document used those exact credentials against `cman_dw_wh_gold` on 2026-07-31.

---

## 7. Do-NOT list

- Do **not** "fix" numbers in `backend/app/sap.py` — the query reproduces the DW exactly; the defect
  is upstream. Re-verified today: every FY2026 DIFF is a document that is absent from the DW.
- Do **not** hand-patch amounts in gold or silver.
- Do **not** treat an FX or CO DIFF as a DW error — classify it (§3) and move on.
- Do **not** compare months a fixture does not cover; a 0 == 0 cell proves nothing and a
  0 ≠ something cell is a false alarm.
- The financial contract (`company_code='1000'`, `doc_type<>'CO'`, NULL-safe `assignment_number`,
  `cost_center IS NOT NULL`, the 8 excluded cost centers) stays untouched — ADR-0020.
