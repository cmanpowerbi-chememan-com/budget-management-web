# 10. Main-table row visibility — SAP-actual-led, three-source union

Date: 2026-06-12
Status: Accepted

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
