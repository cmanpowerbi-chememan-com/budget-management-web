# Spec — SAP actuals shown as-is (remove the ADR-0026 month mask)

Status: **Ready to build.** Decided 2026-09-14 by jakkaritw. Decision record: ADR-0030.
Wayfinder map: `.scratch/sap-month-closed-rule/MAP.md` (tickets D1–D15).
Removal inventory: `.scratch/sap-month-closed-rule/research/D15-removal-impact-inventory.md`.

Every decision below is settled. A build session should not re-litigate them; it should slice
this into tickets and implement.

---

## 1. What changes, in one sentence

The SAP · ใช้จริง layer stops hiding months and renders `gold.fact_gl_trans` as it stands, with a
freshness date on the legend chip and an admin alert when the feed goes stale.

## 2. Scope

**In scope**

| # | Change |
|---|---|
| 2.1 | Remove the month mask: `visible_sap_months`, `SAP_MONTH_VISIBLE_LAG_DAYS`, and the mask application in `_sap_layer` |
| 2.2 | Keep the watermark as a freshness signal and expose it: `● SAP · ใช้จริง (2026) · ข้อมูลคีย์ถึง 11 ก.ย. 2026` |
| 2.3 | Stale state on that chip: `⚠ ข้อมูลคีย์ถึง <date>` when the newest entry date is ≥ 3 days behind today |
| 2.4 | Admin alert mail on the stale condition, throttled to one per day |
| 2.5 | `total_year` becomes the plain Jan–Dec sum; the "รวมเฉพาะเดือนที่ข้อมูลครบ" label is removed |
| 2.6 | Turn `test_sap_actuals_parity.py` into the executable form of "db and web sync 100%" |
| 2.7 | Delete/repair the ~50 affected tests so none stays green while testing nothing |

**Out of scope — do not touch**

- `SAP_ACTUALS_SQL` and every ADR-0020 filter (`company_code='1000'`, `doc_type<>'CO'`, the
  cost-centre exclusion list, `cost_center IS NOT NULL`, the NULL-safe TFRS16 predicate).
- The `dbo.hide_document` anti-join, GL-master visibility, ADR-0010 row visibility, RLS scope.
- The Approved · งบอนุมัติ and Pending · รออนุมัติ layers.
- The DW loader, its schedule, and the cntlfw configuration.

## 3. Behaviour

### 3.1 The layer

`_sap_layer` returns every month it receives from `fetch_sap_actuals`, unmasked. A month with no
postings behaves exactly as it did before ADR-0026 — see §6 open item (a).

### 3.2 The freshness chip

Source: `resolve_sap_coverage(...).watermark_date` — the newest SAP **entry date**
(`MAX(LEFT(utc_timestamp,8))`) at the end of the contiguous loaded run. Not a load date, not a
posting date. Wording is `ข้อมูลคีย์ถึง` ("keyed through"), matching the string already drafted in
`backend/app/routers/budget.py:61`.

```
healthy : ● SAP · ใช้จริง (2026) · ข้อมูลคีย์ถึง 13 ก.ย. 2026
stale   : ● SAP · ใช้จริง (2026) · ⚠ ข้อมูลคีย์ถึง 11 ก.ย. 2026
```

The frontend wiring exists and is unused: `sapFreshnessLine` (`frontend/src/grid/model.ts:946`)
is referenced only by its own tests, and `GET /budget/sap-coverage`
(`backend/app/routers/budget.py:54`) has no caller. Use them.

### 3.3 Stale threshold

`today - watermark_date >= 3 days`.

Basis, not a guess: under the daily loader a batch stamped day D carries entry-day D−1, so a
healthy lag is **1 day** (silver batch 2026-09-12 carried entry-day 2026-09-11). On 2026-09-14 the
lag was 3 days because `STM_FACT_D` failed twice on 2026-09-13 (22:10 and 23:18).

A data hole needs no extra rule: the watermark is the end of the **contiguous** run
(`SAP_ENTRY_DAY_MAX_GAP_DAYS = 4` stays), so a gap makes the date fall back by itself.

### 3.4 The alert mail

- Path: `backend/app/notifications.py`; sender `cmanpowerbi@chememan.com`; recipients
  `ADMIN_EMAILS` — today jakkaritw, nipapornt, warapornt. Precedent: the board_budget ingest alert
  (2026-08-13).
- **Throttle: one mail per PROCESS per calendar day.** The check sits on a request path;
  un-throttled it sends one mail per page load. The marker is process-local and prd runs
  2 replicas × `--workers 2` = 4 processes, so the real worst case is 4 mails per recipient on a
  broken day. **jakkaritw accepted this on 2026-09-14** rather than add a shared store; say so in
  the code comment so the next reader does not "fix" it silently.
- **Set the marker only AFTER a send succeeds.** Otherwise one transient Graph 500 consumes the
  day's only alert and nobody is told the feed stopped.
- **Coupling to know:** `ADMIN_EMAILS` also defines who is an app admin
  (`backend/app/config.py:225 admin_emails_set`), so anyone added for alerting gains admin rights.
  The prd/stg container values have never been read — confirm them, do not trust the local `.env`.

### 3.5 Nothing blocks

Remove the fail-closed staleness gate at `backend/app/read_model.py:652` / the
`watermark is None` raise at `backend/app/sap.py:371-376`. Keep the pyodbc-level raise loud: a
revoked grant, dead connection or unparsable `utc_timestamp` is still a 502 (ADR-0020).

> **Release constraint, not a preference:** §3.2 must ship in the **same release** as §3.1. The
> gate being removed is the only thing standing between a silent DW outage and understated money
> rendered as fact.

## 4. Removal inventory

From D15 — 19 files, ~50 tests. Full table in the research file; the load-bearing entries:

| File | Today | After |
|---|---|---|
| `app/sap.py:288-303, 253` | `visible_sap_months`, `SAP_MONTH_VISIBLE_LAG_DAYS` | deleted |
| `app/sap.py:306-326, 260` | `entry_day_watermark`, gap constant | **kept** — freshness signal |
| `app/sap.py:371-376` | raises when watermark is None | returns an unknown-freshness state |
| `app/read_model.py:305-326` | `_sap_layer` masks | identity map |
| `app/read_model.py:378,442,545,552,694` | `visible_sap_months` parameter | parameter deleted, types narrowed |
| `app/read_model.py:648-652` | coverage call gates the grid | coverage call feeds the chip only |
| `app/routers/budget.py:54-75` | endpoint with no caller | kept, consumed |
| `frontend/src/grid/model.ts:946` | `sapFreshnessLine` dead | live |
| `frontend/src/grid/model.ts:501-507` | `blankSapTotals` null-inits months | **fix: the only remaining `null` producer** |
| `frontend/src/grid/GridTable.tsx:1106,1467` | `sapCoverageLabel` → "รวมเฉพาะเดือนที่ข้อมูลครบ" | removed |

**Two corrections found during the build (2026-09-14) — the inventory above was wrong on both:**

1. **The legend chip is in `frontend/src/grid/BudgetGrid.tsx`, not `GridTable.tsx`.** The chip with the
   green dot carries `data-testid="status-legend"` and lives there; the two `GridTable.tsx` lines named
   above are the grand-total label and its tooltip, which are DELETED, not extended. The freshness
   string was added in `BudgetGrid.tsx` accordingly.
2. **"Narrow the types so stale fixtures fail to compile" does not work in this repo.** `tsconfig`
   excludes `*.test.ts(x)` from `next build`'s type-check (deliberately — see the container-build
   gotcha). Test fixtures carrying `null` therefore compile fine and had to be found and deleted by
   hand. Any future plan that relies on the compiler to catch stale test fixtures is wrong here.

| `frontend/src/grid/GridTable.tsx` | `month-hidden` class | removed — **no CSS rule ever existed** |

Delete the `visible_sap_months` parameter outright rather than defaulting it, so stale fixtures
fail to compile instead of passing.

## 5. Tests

- `backend/tests/test_sap.py` — 63 collected today; the mask tests go, the watermark tests stay.
- `backend/tests/test_integration_live.py` — `test_sap_coverage_live_hides_only_a_trailing_run_of_months`
  is replaced by a freshness assertion.
- `frontend/src/grid/model.test.ts`, `GridTable.test.tsx` — 13 tests hard-code `null` fixtures and
  would stay green forever; `GridTable.test.tsx:1301` asserts the non-existent `month-hidden` CSS.
- **New:** the stale-threshold boundary (2 days healthy / 3 days stale), the throttle, and
  `blankSapTotals` rendering an empty section's grand total.
- **`backend/tests/tests_data_sync/test_sap_actuals_parity.py` — the acceptance test.** Today it
  calls `fetch_sap_actuals` only, months 1–4, and is integration-deselected. Three changes make it
  jakkaritw's criterion: widen `COMPARE_MONTHS` to 12, route the comparison through `_sap_layer`
  (the display layer, not the fetch), and assert no month is `None`.

## 6. Open items for the build session

Three calls were deliberately left to implementation, all flagged at D15:

- (a) whether a month with no postings returns `0.00` or `None`, and what the grid renders;
- (b) whether the staleness verdict is computed server-side (in `SapCoverage`) or client-side;
- (c) whether the SAP total keeps any qualifier text at all once §2.5 removes the old one.

## 6b. The parity contract — what "db and web sync 100%" actually means

Measured live 2026-09-14 in-process through the app's own functions against prd gold plus the
transactional Fabric SQL DB (run `wf_4f2ec55a-76b`). **Read this before writing the parity test:
an unqualified "web equals the database" is false today and stays false after this change.**

The month mask is not the largest divergence. It is not even the second largest.

### FY2026 (= grid planning year 2027), THB to 2 dp

| layer | total | delta | note |
|---|---|---|---|
| raw gold, ADR-0020 frozen SQL | 1,197,679,168.17 | — | 11,069 cells · 2,224 (cc,gl) keys |
| − `dbo.hide_document` (102 docs) | 942,888,831.94 | −254,790,336.23 | admin-maintained, deliberate |
| − GL-master membership (`dbo.gl_group`, 145 codes) | 243,395,400.91 | **−699,493,431.03** | **the largest divergence**, 58.4% |
| − net-zero row hide (ADR-0010) | 243,395,400.91 | −0.00 | 30 keys, row count only |
| − admin-GL strip, non-admin caller | 228,854,897.43 | −14,540,503.48 | 12 GLs, `GL_EDIT_BY_ENABLED=true` on prd |
| − the ADR-0026 mask (what we are removing) | — | −111,689,362.10 | full-population basis |

So for a non-admin the raw-gold-to-screen gap is **968,824,270.74 THB (80.89%)**, and removing the
mask closes 111,689,362.10 of it. FY2025: the mask delta is **0.00** — its watermark already
cleared all twelve months, so that year does not move at all.

### The contract sentence (use this, not "web == db")

> For one caller, one ฝ่าย, one planning year, every SAP cell and every total above it equals
> `SUM(company_curr_amount)` over `gold.fact_gl_trans` under the five frozen ADR-0020 predicates,
> **in all twelve months with no month withheld**, restricted to that ฝ่าย's cost centres inside
> the caller's See scope and to GL accounts in `dbo.gl_group`, minus every `dbo.hide_document`
> entry for that year+month, and minus the twelve `edit_by='admin'` GLs when the caller is not an
> admin; rows whose every month rounds to 0.00 with no Approved and no Pending row are not drawn;
> and the figure may be up to 600 s behind gold (TTL cache), independently per replica.

The words this change is responsible for are **"in all twelve months with no month withheld"**.
The rest is pre-existing and deliberate.

### Three measured facts that break intuitive assertions

1. **There is no `web <= db` invariant.** FY2026 month 08 is 132,084,647.78 in raw gold but
   135,016,913.79 after the hide anti-join — hiding a net-negative document set RAISES the figure.
2. **A month can be legitimately negative.** FY2026 m09 = −23,327,551.69. Months 10–12 have no
   gold rows at all. `0.00` and negative are valid; `None` is the only defect.
3. **Float precision is not a divergence.** Per-cell `|float − Decimal|` = 0 across all 11,069
   FY2026 cells; a frontend-style left-to-right accumulation over 1,111 keys drifts by 1e-7 THB.

### The test must exercise the production wiring

The mask is NOT inside `_sap_layer`; it is injected by the caller at `read_model.py:694`. A parity
test that calls `_sap_layer(months, None)` directly passes identically with the mask live — proven:
it reports 942,888,831.94 == 942,888,831.94 while the app serves 831,199,469.84 with 10,795 `None`
cells. **Assert against the payload the router's own path produces.**

### BEFORE numbers to reconcile the release against

```
FY2026 served today        831,199,469.84
  + mask removal          +111,689,362.10   (m08 +135,016,913.79 · m09 −23,327,551.69 · m10-12 0.00)
  = after this change      942,888,831.94   == the post-hide_document total, exactly
FY2025 served today      1,429,498,028.77   unchanged by this release (mask delta 0.00)
```

### Cleanup spotted, not part of this change

14 of the 172 FY2025 `dbo.hide_document` entries match **zero** gold rows (documents 1110000336,
1110000755, 1110001141, 1110001537, 1110001922, 1110002309, 1110002683, 1110003045, 1110003442,
1110003830, 1110003848, 1110004192, 1110004582, 1900002922). Dead list entries, harmless, worth a
separate ticket. Also: cost centres `10DM999999`, `10MN016100`, `10OS012000`, `PBWELO` are absent
from `dbo.cc_filler_map`, leaving 5,798.10 THB (FY2026) and 3,118,747.39 THB (FY2025) reachable by
nobody, admin included.

## 7. Rollout

0. **Before the staging deploy, point staging's alert mail at one person.** Both containers today
   have `NOTIFICATIONS_DRY_RUN=false` with no environment label and no redirect, so a staging test
   would mail three real colleagues unmarked — and the feed is stale right now
   (`days_behind = 3` on 2026-09-14), so the alert fires on the first page load. jakkaritw's call,
   2026-09-14: set `NOTIFICATIONS_REDIRECT_ALL_TO=jakkaritw@chememan.com` on
   `cman-budget-web-stg` for the test window, and revert it afterwards. Record the revert in the
   tracker the moment it is set.
1. Build the image, deploy to `cman-budget-web-stg` first, verify the chip and the totals there.
2. Reconcile against the BEFORE control totals captured pre-release (parity run
   `wf_4f2ec55a-76b`) — the numbers must differ only by the months the mask used to hide.
3. Deploy to `cman-budget-web-prd` **only after explicit approval from jakkaritw**, then
   verify-deploy-landed. Both containers run the same image.
4. **Warn users before the prd deploy:** the SAP year totals and both grand totals visibly grow in
   that release. **On-screen figures (measured through `get_budget_grid`, admin-wide, 2026-09-14):**
   the SAP grand total goes **210,143,094.26 → 243,395,400.91** (+33,252,306.65) and **Aug-2026
   appears as 34,078,172.54 THB**. Do NOT quote 942,888,831.94 or 131,428,306.25 to users — those
   are reference-population figures from before the `dbo.gl_group` master filter, which is what
   §6b compares against. Reconcile the release against §6b; announce the on-screen numbers.
