# 10. Main-table row visibility — SAP-actual-led, three-source union

Date: 2026-06-12
Status: Accepted
Amended by: ADR-0020 (actuals source = DW `cman_dw_wh_gold.gold.fact_gl_trans`
read-through, not `gold_sap_gl_trans` in the app Lakehouse; the 3-source union rule
itself is unchanged)
Amended 2026-08-11: the net-zero SAP row-hide (2026-07-24, previously recorded ONLY in
code comments + a now-deleted plan doc) is written down below and refined to a PER-MONTH
rule — see "Amendment — net-zero SAP row-hide" at the end; that section is the canonical
spec for the hide rule.
Resolved 2026-07-12 (grill): the 3 layers carry DIFFERENT fiscal years (SAP=Y,
Approved=Y, Pending=Y+1), so the visible-row union key is `(cost_center, gl_account)`,
NOT the `(cc, gl, year)` triple. Approved-Y is a REFERENCE column beside the planned
Pending-Y+1; the requested-vs-granted comparison (Pending-Y+1 vs Approved-Y+1) is a
Phase-2 dashboard, not this table. Merge = board+pending joined inside Fabric SQL DB,
SAP merged cross-store in FastAPI (only 1 of 3 layers crosses stores).

## Context

The main budget table shows one row per `(cost_center, gl_account, fiscal_year)` triple
(a "Transaction" row in the UI), stacking three layers: SAP · Actuals, Approved · งบ
(`board_budget`), and Pending · รออนุมัติ (`pending_budget`). There are ~137 GL accounts ×
many CCs, so we cannot render every possible GL row — most would be empty noise. We need a
rule for **which `(CC, GL, year)` rows appear**.

Grilling 2026-06-12 surfaced the user's intent and two facts:

- **SAP actuals are the natural starting set.** A CC's real spend already exists in SAP
  (`gold_sap_gl_trans`), so the GLs that CC actually used that year are the meaningful rows to
  pre-populate — Approved and Pending then sit alongside, waiting to be filled.
- **But some GLs/CCs have no prior actual yet will be budgeted this year** — a new activity,
  or a brand-new GL/CC introduced by an Approved CSV import. These must still be reachable and,
  once they hold data, must not disappear.

Naïve "show only rows with a SAP actual" fails the second case: a GL the user added by hand, or
a new GL/CC in an Approved import, would vanish on the next page load and the entered/imported
budget would appear lost.

SAP itself has **no orgcode** (verified against `docs/11SAP_T_GL_TRANS_1000_RATIMA_TEST1.xlsx`:
it has `RACCT`=gl_account and `RCNTR`=cost_center, no HR org field) — so visibility is filtered
by RLS (login orgcode → file09 → CC set) and joined to SAP rows by cost_center, per ADR-0001.

## Decision

The visible row set for a `(cost_center, fiscal_year)` is the **union of three sources**:

```
visible(CC, year) = SAP-actual rows            (gold_sap_gl_trans — the leader/most common)
                  ∪ Approved rows              (board_budget — incl. new GL/CC from a CSV import
                                                 that has no SAP actual)
                  ∪ Pending rows               (pending_budget — incl. a GL/CC the user added
                                                 by hand via "+ เพิ่ม transaction")
```

- **SAP actual is the leader** — the row set a CC opens with. The other two layers display
  alongside (Approved filled if imported, Pending waiting for the user / budget dept).
- **A row appears if it has data in ANY layer**, and once it exists it **persists** — it
  reappears on every later open. "No SAP actual" is therefore just *one* reason a GL must be
  added by hand, not the whole rule.
- **`+ เพิ่ม transaction`** is the manual door: the user picks CC + GL freely from the
  cost-center / GL masters (CC list constrained to their fill-scope). If the picked GL is a
  Special GL group, the new row routes into its subform / Trip Manager exactly like a seeded
  special row (ADR-0005, data-model §4a/§4b).
- **RLS applies to every source** — a user sees only their own CCs; an Approved import of a new
  CC surfaces only to whoever has that CC in scope (admins see all).
- No new table or column — purely a read/display query unioning the three already-modelled
  sources keyed by the same `(cost_center, gl_account, fiscal_year)` triple.

## Consequences

- The table opens with meaningful, non-empty rows (SAP-led) instead of ~137 blank GL rows, and
  never silently drops a budgeted row (persistence via the Pending/Approved entry).
- The display query is a 3-way union/outer-join on `(cost_center, gl_account, fiscal_year)`
  across `gold_sap_gl_trans` + `board_budget` + `pending_budget`, filtered by the RLS CC set.
- "+ เพิ่ม transaction" is required precisely for the no-actual / future-use case; the
  sign-off spec (Doc 01 §11) states this to the user so an absent GL is understood as
  "add it", not "broken".
- An Approved CSV import can introduce a `(CC, GL)` with no actual; it is visible immediately
  (Approved filled, SAP empty, Pending waiting) — consistent with board_budget being a separate
  whole-year import (data-model §1c).

## Amendment — net-zero SAP row-hide (2026-07-24, refined 2026-08-11)

This section is the **canonical spec** for the hide rule. The original spec
(`plan/hide-netzero-gl-rows.md`, approved 2026-07-24) was deleted in the SIT doc
consolidation (`48ebacb`); until this amendment the rule lived only in code comments —
`plan/sit/sit-test-plan.md:873` flagged exactly that gap.

History:

- **2026-07-24** (commit `81eac93`, approved by jakkaritw — "ซ่อน"): a `(cost_center,
  gl_account)` key whose SAP layer nets to **0.00 over the full year** and that has no
  board_budget and no pending_budget row is hidden. Trigger: 51 reversal-style keys rendered
  as all-"—" rows that looked broken (e.g. CC `10GE000000` GL `6210500010`, +1,648.13 /
  −1,648.13 both in m01 FY2026). Grid 1041→1007 rows; every grid total unchanged by
  construction. This narrowing of the 3-source union above was never recorded here at the
  time — recorded now.
- **2026-08-11** (approved by jakkaritw, after a real-user report): SAP doc `1110001154`
  (accrual +13,150 posted m03 FY2026, reversed −13,150 in m04 by doc `1900000600`, same
  CC × GL) was invisible under the full-year rule; the user expected the posting-period
  view SAP itself shows ("ถ้าโชว์ตาม posting date เดือน 3 ก้อควรโชว์ตัวเลข"). Decision:
  **hide only when EVERY individual month nets to 0.00 (2dp)**.

Rule (canonical):

```
hide(CC, GL) ⟺ every month m01..m12 of the SAP year rounds (2dp) to 0.00
             AND no board_budget row AND no pending_budget row for the key
```

Consequences (measured live 2026-08-11):

- Same-month reversal pairs — the 2026-07-24 trigger population — still net 0.00 in their
  month and **stay hidden** (FY2025: 52 master-GL keys, FY2026: 29). The original noise
  problem stays solved.
- Cross-month reversal pairs (SM/SX accruals, KR/KX invoice reversals) now **show both
  legs**, matching SAP's posting-period view: grid 2026 +11 rows, grid 2027 +12 rows;
  max single-month amount 62,939.01 THB; grid totals move by exactly 0.00.
- The rule is still computed on the **full pre-mask year** (ADR-0026 requirement,
  unchanged): a key whose only non-zero months are ADR-0026-masked is VISIBLE — its masked
  cells render blank, and `total_year` (visible-months sum, coverage-labelled) may
  temporarily show one leg of a reversal pair until the offsetting month unmasks. This is
  the same answer SAP gives for the same date range — accepted explicitly at the
  2026-08-11 decision.
- The board/pending **presence-not-value safeguard is untouched**: a genuinely all-zero
  board or pending row still forces the row visible (a blank or deliberately-zeroed
  "+ เพิ่ม transaction" row must never vanish).
