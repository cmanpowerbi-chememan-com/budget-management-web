# 11. FX-rate snapshot on budget, subform auto-recompute, budget→Gold flow

Date: 2026-06-12
Status: Accepted
Extends: ADR-0003 (budget data model), ADR-0005 (special-GL detail + trip linkage),
ADR-0006 (approval routing)

## Context

The Currency Master (Module 09, `cfg_master.master_currency_rate`, one avg USD→THB
rate per fiscal year) feeds the Oversea-Trip per-diem calc: overseas
`เบี้ยเลี้ยง = days × rate(position, country_group) × FX`. The computed THB lands in
`budget.working_budget_detail` and aggregates up to `budget.working_budget`.

An admin can edit a year's FX rate at any time. Open questions this ADR closes:
1. If a budget was APPROVED at FX=30 and the admin later changes the year's rate to 35,
   does the approved amount mutate? Realtime? On read?
2. When a user re-opens the trip subform after a rate change, recompute automatically or
   prompt first?
3. How does an approved budget reach the Lakehouse Gold layer that the dashboard reads?

## Decision

- **Stored as snapshot, never recomputed on read.** `working_budget` /
  `working_budget_detail` monthly amounts are persisted DECIMAL values fixed at save
  time. An FX edit does **not** cascade to already-saved rows, and never changes an
  APPROVED budget automatically or in realtime. Approved budget stays immutable until a
  human edits + re-submits (ADR-0006). Governance: an approved number must never change
  without passing approval again. (Rejected the "recompute-on-read" and
  "cascade-on-FX-edit" alternatives — both bigger to build AND break immutability.)
- **An FX edit is realtime to `cfg_master.master_currency_rate` only** (single config
  table). It affects only the *next* recompute that a user triggers by opening a trip
  subform.
- **Opening the Oversea-Trip subform auto-recomputes per-diem with the current FX
  immediately** (no prompt) — confirmed by user 2026-06-12. The per-diem THB is a
  derived value the user never types, so the user simply sees the refreshed number.
  Persisting it still requires **Save** (→ DRAFT) then **Submit** (→ re-approval chain);
  there is no silent path that makes the new rate official.
- **Store `fx_rate_used` on `budget.budget_trip`** (the rate applied when the trip's
  per-diem was last computed/saved). Audit (explains why the amount is 30-based not
  35-based) and drift safety. New column vs ADR-0005's trip header.
- **Only `status = APPROVED` working_budget flows to Lakehouse Gold** (`gold_budget`).
  DRAFT / PENDING must never reach the dashboard. The dashboard reads Gold (R/O,
  `.datawarehouse.` endpoint), NOT `working_budget` directly.
- **Dashboard source at Gold = UNION of** approved `working_budget` + `board_budget`
  (board-approved import, ADR-0003) **vs** SAP actuals (`silver_sap_gl_trans`).

## Consequences

- Two lag layers, both intentional:
  1. **Approval lag** — a new FX value is not a real budget number until re-approved.
  2. **Pipeline lag** — a newly approved amount reaches the dashboard only on the next
     Gold pipeline run.
- Minimal build: snapshot is the do-nothing path; only adds one `fx_rate_used` column.
  No recompute job, no cascade trigger, no approval-engine change.
- Open / deferred (NOT decided here):
  - **Gold pipeline cadence** — scheduled (e.g. nightly) vs triggered on approve. Drives
    the dashboard lag window. To be set when the dashboard/pipeline is built (Phase 2).
  - Exact `gold_budget` schema + the UNION view shape.
