# 30. Show SAP actuals as-is — supersedes ADR-0026's month mask

Date: 2026-09-14

Status: Accepted 2026-09-14 (jakkaritw). **Not yet implemented** — this ADR records the decision;
the build is a separate effort. Supersedes the display rule of ADR-0026. Relates to: ADR-0020
(the actuals read-through contract — **untouched**), ADR-0010 (row visibility — **unchanged**).

Decision record: `.scratch/sap-month-closed-rule/MAP.md` (wayfinder map, tickets D1–D15).
Implementation spec: `docs/specs/feature-sap-show-as-is.md`.

## Context

ADR-0026 hides a month of the SAP · ใช้จริง layer until the loaded entry-day watermark passes that
month's end by 23 days. It was written on 2026-08-01, when the SAP feed was **stalled**: entry-days
stopped at 2026-04-29, April sat at ~15% of a normal month, and nothing on the page could tell the
reader. Hiding was the only defence available.

Two things changed by 2026-09-14.

**The feed now runs daily.** `PTF_SAP_GL_TRANS_D` writes one-day batches (2026-09-11 carried
entry-day 09-10; 2026-09-12 carried 09-11), so the data is normally one day old rather than
arbitrarily stale.

**The constant was measured properly, and it does not work.** Two independent passes over
`gold.fact_gl_trans` (company 1000, ADR-0020 filters) found:

| measurement | result |
|---|---|
| months that still received rows after day 23 | **26 of 93** (2019-01..2026-09) |
| smallest constant with zero violations | **255 days** (company 1000) · **385** including company 2000 |
| structure of the violations | quarter-end: Mar/Jun/Sep/Dec **15 of 27** exceed day 23, vs **3 of 54** other months |
| money landing after day 23 (excl. the 2019 go-live year) | 23 months · 1,043 rows · **542,022,712.03 THB** gross cell movement |
| where it is concentrated | `doc_type` SM/SX = 977 of 1,043 rows · cost_center `10GE000000` = 354.3M · GL 6212* accrual/revaluation = 328.4M |
| two constants already violated in production | 2025-06 lost **−7,661,676.68 THB** (landed entry-day 2025-07-25 vs reveal 07-23; cell `10GE000000`/`6212000020` read ~40% low) and 2025-02 **+78,141.94** (03-24 vs 03-23) |

And the materiality curve shows what the 23 days actually buys — percentage of a month's FINAL
expense THB already present at day N after month-end, 20 months 2025-01..2026-08:

| day | median | worst | worst month |
|---|---|---|---|
| 0 | **20.5%** | 8.5% | 2026-03 (10.8M of 126.7M) |
| +3 | **98.5%** | 25.0% | 2025-12 |
| +5 | 99.4% | 35.2% | 2025-12 |
| +7 | 100.0% | 93.9% | 2025-12 |
| +10 | 100.0% | 99.4% | 2026-02 |

The danger window is **2–3 days wide** for an ordinary month and 7–10 days for December. The rule
charged every month roughly two extra weeks of blindness to cover it, and still missed. Aug-2026
is the worked example: complete on 2026-09-04, hidden until 2026-09-23 — 19 days of nothing.

(ADR-0026 reported March-2026 as 78.2% complete at month-end. That figure counts DOCUMENTS; the
20.5% above counts THB. Month-close accruals are few documents holding most of the money, so a
document-count completeness measure flatters a financially half-empty month. Use THB.)

Alternatives considered and rejected:

- **Tune the constant** (30/40/44/56 days). Rejected: 44 removes every violation of the last 48
  months but still misses 2023-12 by a day, punishes every fast-closing month, and cannot reach
  100% short of 255 days.
- **A data-driven "month is closed" rule** — reveal once K consecutive loaded entry-days add
  nothing to the month (ticket D1, full report in the map). Measured K = 4 with a margin of
  **one day**: K = 3 fires early on 2026-05 (−2,261,915.85 THB at 98.782% complete), 2026-02 and
  2025-11. Rejected on two grounds: the margin is no margin, and at K = 4 a silent partial loader
  failure is indistinguishable from "accounting finished" — the 2026-06 outage shape exactly.
- **Keep hiding but disclose better.** Rejected as strictly worse than not hiding plus disclosing.

## Decision

**The SAP · ใช้จริง layer renders `gold.fact_gl_trans` as it stands, every day. No month is hidden.**

1. `visible_sap_months` and `SAP_MONTH_VISIBLE_LAG_DAYS` are removed. `_sap_layer` becomes an
   identity map over the fetched actuals.
2. **ADR-0020's SQL contract is untouched.** `company_code='1000'`, `doc_type<>'CO'`, the
   cost-centre exclusion list, `cost_center IS NOT NULL`, the NULL-safe TFRS16 predicate and the
   `dbo.hide_document` anti-join all stay byte-identical. The GL-master visibility rule and
   ADR-0010 row visibility are likewise unchanged. "No filter" meant the month mask, nothing else.
3. **The entry-day watermark survives as a freshness signal, not a gate.** `entry_day_watermark`,
   `SAP_ENTRY_DAY_MAX_GAP_DAYS = 4`, `SAP_ENTRY_DAYS_SQL`, `SapCoverage` and
   `GET /budget/sap-coverage` all stay and finally get a consumer.
4. **The grid states its freshness in one string**, appended to the existing legend chip:
   `● SAP · ใช้จริง (2026) · ข้อมูลคีย์ถึง 11 ก.ย. 2026`. The date is the newest SAP **entry date**
   of the contiguous run — not a load date, not a posting date. No per-month marker.
5. **Stale feed warns, and mails the admins.** When the newest entry date is **3 or more days
   behind today**, the chip becomes `⚠ ข้อมูลคีย์ถึง <date> (ช้ากว่าปกติ)` and an alert goes to
   `ADMIN_EMAILS` (jakkaritw, nipapornt, warapornt). A healthy lag is 1 day. The threshold is an
   **operational freshness** constant — it says "the feed stopped", never "this month is finished".

   **Throttle: one mail per process per calendar day, NOT one per day — accepted knowingly
   (jakkaritw, 2026-09-14).** The marker lives in process memory, and prd runs 2 replicas ×
   `--workers 2` = 4 processes, so a stale day can produce up to 4 mails per recipient. A shared
   store (a `dbo` row) would make it exactly one; it was judged not worth the extra table and the
   extra write on a request path, because the alert only fires on days the feed is genuinely
   broken. If the volume ever becomes a nuisance, that is the fix — not a longer threshold.
   A data hole needs no separate rule: the watermark is the end of the contiguous run, so the
   2026-06 outage would have read `⚠ ข้อมูลคีย์ถึง 30 พ.ค. 2026` right through September.
6. **Nothing blocks on staleness.** The loud 502 remains only for an actual gold read failure —
   revoked grant, dead connection, unparsable `utc_timestamp` — per ADR-0020.
7. `total_year` becomes the plain Jan–Dec sum of the fiscal year, identical to
   `fetch_sap_actuals`' own total. The label "รวมเฉพาะเดือนที่ข้อมูลครบ" is removed: it becomes a
   false statement the moment nothing is hidden.

**Acceptance criterion, stated by jakkaritw three times: "data on db and web sync 100%."** The
executable form is the parity harness — see the spec.

## Consequences

- **Money changes on screen in the release that ships this.** Every SAP row's year total, both
  grand totals, and the Aug/Sep 2026 cells (watermark 2026-09-11 → FY2026 currently shows months
  1–7). **Corrected 2026-09-14 by the quality gate, measured through `get_budget_grid` itself:**
  the admin-wide SAP grand total on screen goes **210,143,094.26 → 243,395,400.91** (+33,252,306.65),
  and **Aug-2026 appears as 34,078,172.54 THB on screen**. The earlier figure of 131,428,306.25 was
  measured on the raw expense-GL basis before the `dbo.gl_group` master filter, which is not what a
  user sees — quote the on-screen numbers in any announcement.
- **The reader can now see an unfinished month and mistake it for final.** This is the accepted
  cost, taken knowingly: a month reads a median 20.5% of its final money on the day it ends. The
  freshness date is the whole mitigation — jakkaritw declined an in-flight-month marker.
- **The freshness chip must ship in the SAME release.** `read_model.py:652` is today's only
  fail-closed gate; removing the mask without the chip leaves an outage rendering understated
  money with HTTP 200 and no signal at all.
- ADR-0026's promised visual treatment for hidden months never existed: `GridTable.test.tsx:1301`
  asserts a `month-hidden` class for which **no CSS rule was ever written**. It goes with the rest.
- ~50 tests move (24 deleted, ~26 edited) — `backend/tests/test_sap.py` collects 63 today. Thirteen
  frontend tests hard-code `null` fixtures and would stay green while testing nothing; the
  mitigation is to delete the `visible_sap_months` parameter and narrow the types so stale
  fixtures fail to compile rather than pass.
- The rule no longer self-heals on its own the way ADR-0026 did — the alert mail is what makes a
  stalled feed someone's problem.
