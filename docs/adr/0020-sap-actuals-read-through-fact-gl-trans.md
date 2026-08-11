# 20. SAP actuals are read live from the DW warehouse (`fact_gl_trans`) — no copy into the app's stores

Date: 2026-07-12
Status: Accepted
Amends: ADR-0010 — corrects the actuals **source table** and defines the **read
mechanism**; the row-visibility rule itself (SAP-actual-led union of 3 sources) is
unchanged. Also corrects CONTEXT.md "SAP / Actuals" and the transactional-model spec,
which referred to `gold_sap_gl_trans` in the app's own Lakehouse.
Amended 2026-08-11: a SIXTH mandatory filter — the `dbo.hide_document` anti-join —
added to the read-through (see "Amendment — hide_document anti-join" at the end).

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
    (**10SC012000 is KEPT** — user 2026-07-14, removed from the exclusion list),
    `(assignment_number IS NULL OR assignment_number<>'TFRS16')`, `fiscal_year=@year`.
    **CORRECTED 2026-07-16 (D2, exhaustive live verify):** the filter was originally a bare
    `assignment_number<>'TFRS16'`, which is NOT NULL-safe — in SQL, `NULL <> 'TFRS16'`
    evaluates to UNKNOWN, so the WHERE clause silently dropped every NULL-assignment row.
    Live impact: FY2025 lost 706 rows / −12,827,790.81 THB; FY2026 fabricated ~3.87M THB of
    PHANTOM actuals on balanced clearing accounts (e.g. GL 9110100020, CC 10QC011000 — the
    `+NULL` legs were dropped while the `-PO` legs were kept, so a cell whose true actual is
    ~0.00 showed a multi-million THB balance). This also undermined the "reversal pairs net
    to zero" claim below — the earlier live parity check only matched because it compared
    the shipped query to an IDENTICAL hand-written query that dropped NULLs the same way
    (self-consistency, not correctness). Fixed to explicitly keep NULL-assignment rows;
    confirmed by jakkaritw as the correct policy (balanced clearing accounts must net to 0).
    **⚠️ DO NOT apply that same NULL-safe fix to `cost_center NOT IN (...)`.** Audited live
    2026-07-16: `NULL NOT IN (...)` is UNKNOWN too, so NULL-cost_center rows are ALSO already
    dropped — and that is **correct and required**. The grid is keyed by `(cost_center,
    gl_account)`; a posting with no cost center belongs to no user's scope and cannot be shown.
    Live volume: FY2025 = 2,249,381 rows / **−1,138,962,985.31 THB**; FY2026 = 515,775 rows /
    −132,909,268.58 THB. "Fixing" this predicate the way `assignment_number` was fixed would pull
    ~1.1 **BILLION** THB of non-cost-center postings into the actuals and corrupt every cell.
    Prefer an explicit `AND cost_center IS NOT NULL` so the exclusion is deliberate rather than an
    accident of NULL semantics. `doc_type<>'CO'` is NULL-unsafe by the same rule, but live has
    **0** NULL-doc_type rows in FY2025/FY2026 — no impact today; re-check if the DW build changes.
    **No `doc_status` filter** — resolved 2026-07-14: only two
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

## Amendment — `hide_document` anti-join (2026-08-11)

**Defect closed:** the admin hide-document master was consumed by NOTHING. The sign-off
spec (hide-document v0.3, 2026-06-14) defined hide rules as a **query-time filter** on the
actuals SUM — but that intent predated this ADR and was dropped when the filter contract
above was frozen without it. Found via a real-user report (doc `1110000365`, GL
`5120300020`: 14 cost-center cells in fy2026 m01 whose ENTIRE value was the hidden doc,
e.g. KKCA01 +17,398.93). SIT case NEW-A6-26 had already documented the gap but was never
run. Grain-matched leak measured live 2026-08-11 (app-filtered, doc+year+month):
fy2023 344,564,787.13 / fy2024 415,188,454.99 / fy2025 **429,217,094.58** (grid-2026
reference) / fy2026 **106,698,916.11** (grid-2027 reference) — total 16,561 rows /
1,295,669,252.81 THB. Approved by jakkaritw 2026-08-11: filter in the APP layer (option A)
— the DW gold warehouse stays unfiltered so BI/other consumers keep full accounting truth.

**Rule (6th mandatory filter, same never-cut status as the five above):**

- Source: `dbo.hide_document` (transactional Fabric SQL DB; synced daily ~06:31 from
  SharePoint `ซ่อนเอกสาร.xlsx` per ADR-0022/0023). Grain = `(document_number, year,
  month)` — SAP doc numbers repeat across fiscal years, so the year+month match is
  load-bearing, never hide by doc number alone.
- Mechanism: the hide rows for the queried `fiscal_year` are fetched from the
  transactional connection (cross-store join is impossible — same reason as this ADR's
  core design) and applied to the gold query as a parameterized
  `NOT EXISTS (... VALUES ...)` anti-join on
  `(accounting_doc_number, CAST(period_month AS INT))`.
- **Empty hide list ⇒ the original frozen SQL runs byte-identical.** The five existing
  predicates are never edited.
- **Fails loud:** a broken hide-list read raises `SapActualsFetchError` → 502. A silent
  fallback to "nothing hidden" would un-hide ~1.3B THB and must never happen.
- **Watermark/coverage (`SAP_ENTRY_DAYS_SQL`, ADR-0026) is NOT filtered** — hidden docs
  still count as loaded entry-days; hiding is a display-amount concern, not freshness.
- The DB→web parity harness pins `hidden_doc_periods=None` — it verifies the frozen-SQL
  mirror property; hide-filtering has its own tests.
- TTL cache (600 s) applies to the filtered result; a hide-list edit becomes visible
  within ≤ 10 minutes + the daily SharePoint sync cadence — accepted.
