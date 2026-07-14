# 20. SAP actuals are read live from the DW warehouse (`fact_gl_trans`) — no copy into the app's stores

Date: 2026-07-12
Status: Accepted
Amends: ADR-0010 — corrects the actuals **source table** and defines the **read
mechanism**; the row-visibility rule itself (SAP-actual-led union of 3 sources) is
unchanged. Also corrects CONTEXT.md "SAP / Actuals" and the transactional-model spec,
which referred to `gold_sap_gl_trans` in the app's own Lakehouse.

## Context

Design docs (ADR-0010, CONTEXT.md, `docs/specs/budget-transactional-data-model.md`)
named the SAP actuals source as `gold_sap_gl_trans` in the app's Lakehouse
(`budget_management_web` / `lakehouse`). Confirmed with jakkaritw 2026-07-11: the real
production source is the **central DW gold warehouse** owned by the separate DW project —
`[cman_dw_wh_gold].[gold].[fact_gl_trans]`, workspace `cman-dw-prod-ws`
(`302668d3-a84c-4410-9933-65ccae989620`) — transaction-grain GL postings.

The budget app's transactional tables live in Fabric SQL Database (ADR-0017): a
**different engine and workspace**, so one cross-store SQL JOIN is not possible (no
linked-server / elastic-query equivalent between Fabric SQL DB and a Warehouse).

Two options were grilled 2026-07-11:
- **(A) read-through** — query the DW live on page load; no copy kept.
- **(B) copy/snapshot** — a pipeline lands a monthly aggregate into the app's store;
  reads are local but data goes stale between runs and the pipeline must be owned.

## Decision

- **Read-through (A).** No copy of SAP actuals is stored in Fabric SQL DB or the app
  Lakehouse. `fact_gl_trans` in the DW is the single source of truth.
- **Aggregation is pushed to the DW side** (columns + filters VERIFIED 2026-07-13/14
  against live data AND the DW mapping spec `Gold-Transaction` sheet):
  `SELECT cost_center, gl_account_number, fiscal_year, period_month,
  SUM(company_curr_amount) … GROUP BY the first four` — display-grain, not 23.7M raw rows.
  - `company_curr_amount` is **already correctly signed** (debit `S`=+ / credit `H`=−) —
    **do NOT apply any sign flip** (the old `data-sources.md` "flip on H" rule was for a
    different manual export; double-flipping corrupts ~97% of rows).
  - **Mandatory WHERE filters (never-cut financial correctness):** `company_code='1000'`
    (CMAN-TH / THB only), `doc_type<>'CO'` (CO postings double-count the FI side — 19% of
    rows, 2.15M carry cost_center), excluded CCs `CMRY01, CMKK01, CMPB01, MNLB00..04`
    (**10SC012000 is KEPT** — user 2026-07-14, removed from the exclusion list), `assignment_number
    <>'TFRS16'`, `fiscal_year=@year`. **No `doc_status` filter** — resolved 2026-07-14: only two
    values exist (`NULL` = the real actuals, net −981k THB; `'U'` = 4.55M rows that net to
    **exactly 0.00 THB at every grain**, so including or excluding them never moves a SUM). `'U'`
    is ~98% `doc_type='CO'` (already excluded) plus reversal pairs — likely statistical/CO/MM memo
    postings; ask DW for the definitive SAP meaning but it has zero total impact. None of these
    filters are applied at the DW build stage — they are 100% the app's responsibility.
  - **`company_code='1000'` is TRIPLY load-bearing:** `fact_gl_trans` is a UNION of 3 blocks
    with DIFFERENT sign conventions — the SAP-native block (companies 1000/2000) keeps SAP's
    signed value, but the HLL (9001) and GMAN (4000) manual-entry blocks apply `× -1 if 'S'`
    (opposite). Filtering to `1000` gives THB-only **+** no cross-company double-count **+** a
    single consistent sign, all in one predicate. Removing/loosening it corrupts totals — never do so.
  - `period_month` is DW-derived (`format(posting_date,'MM')`, zero-padded) — used as-is.
  - Reversal pairs (`reversing_flag`/`reversed_flag`/`true_reversal_flag`) net to exactly
    zero when summed — **no reversal filter needed**.
- **Table identity risk:** the live `gold.fact_gl_trans` is an older pre-"CORRECTION 3" build
  the DW dev-repo no longer tracks (it plans to rename gold → `sap_gl_trans`, currently
  dormant). Confirm the refresh owner/job with the DW team before prod dependence.
- **The FastAPI backend merges** that aggregate with `budget.pending_budget` /
  `dbo.board_budget` on `(cost_center, gl_account, fiscal_year)` in app code —
  the same split-connection pattern the deployed master-tables backend already uses
  (`get_lakehouse_conn()` separate from the transactional connection).
- **Service-principal access**: `cman-fabric-write` needs at least Viewer on workspace
  `302668d3` (known gotcha — was once blocked there and required a portal grant).
  Verify the grant before the first backend integration test.

## Consequences

- Actuals are always fresh; no copy pipeline, cadence, or reconcile job to own; no
  duplicated financial data.
- Page reads now depend on DW availability and on an SP grant in a workspace this
  project does not own. A revoked grant must surface as a **loud backend error**, not
  a silently empty green layer (silent-empty would look like "no actuals" and corrupt
  budget decisions).
- The 3-source union (ADR-0010) is computed in FastAPI, not in a DB view — the merge
  code must be covered by the financial SUM rules (COST `5xxx` and SG&A `6xxx` totals
  never cross; grouping by `gl_account` preserves this naturally).
- Phase-2 dashboard may instead read the Fabric SQL DB OneLake mirror + a shortcut
  UNION view entirely inside OneLake — out of scope here; this ADR governs the live
  app read path only.
