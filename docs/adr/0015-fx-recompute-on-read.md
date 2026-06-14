# 15. Per-diem FX = recompute-on-read (supersedes ADR-0011 snapshot)

Date: 2026-06-14
Status: Accepted
Supersedes the **snapshot / `fx_rate_used`** decision of ADR-0011 (points 1, the
`fx_rate_used` column, and the "FX edit does not cascade" rule). ADR-0011's other parts —
subform auto-recompute on open, "only APPROVED flows to Gold", budget→Gold UNION shape —
still stand.

## Context

ADR-0011 froze overseas per-diem as a snapshot at save time and stored `fx_rate_used`, so a
later Currency-Master FX edit never changed an approved budget. Re-grilled 2026-06-14: the
user decided the opposite, and accepted every consequence explicitly.

Key facts that drove the flip:
- **Currency Master is ONE average rate per fiscal year** (`cfg_master.master_currency_rate`,
  e.g. 2025 = 35 THB/USD), maintained by Budget-dept admins, and **mutable** (admin may change
  their mind: 35 → 40 for 2025).
- Only **Budget-dept admins** can edit it (trusted authority — same trust basis as ADR-0013's
  admin-edits-APPROVED).
- Because there is exactly one rate per year, a per-trip `fx_rate_used` would *always* equal
  that single rate → redundant.

## Decision

- **Overseas per-diem is recompute-on-read, NOT stored as a snapshot.** `เบี้ยเลี้ยง = days ×
  rate(position, country-group) × FX(year)` is re-derived from the **current** year's Master FX
  every time it is read / rendered / flows to Gold. The trip's inputs (traveler, position,
  destination, days, months) are what's stored; the THB per-diem is always derived.
- **Editing the year's Master FX re-prices ALL overseas per-diem of that year immediately** —
  including budgets already `APPROVED`, across every department, with no per-budget review.
  Explicitly accepted (admin-controlled, one rate/year, deliberate).
- **Drop `fx_rate_used`** (ADR-0011's column) — redundant; the year's Master rate IS the rate.
- **Scope = the FX-derived part only.** Per-diem recomputes with FX. The other travelling types
  (transport, accommodation, other) are manually-entered THB and **do not** move with FX; normal
  (non-travelling) GLs are typed values — both remain stored/stable.
- The Gold/dashboard per-diem figure is therefore as-of the pipeline run's FX; **dashboard
  per-diem can change day-to-day without a new submission** — accepted.

## Consequences

- Simpler than snapshot in data terms (no `fx_rate_used`, no per-trip stamp), but the per-diem
  amount is now a *derived* value computed on read rather than a persisted number.
- **Accepted trade-offs (all confirmed 2026-06-14):**
  1. One FX edit re-prices dozens of approved per-diem budgets at once, no per-budget review.
  2. Approved/dashboard per-diem totals shift between Gold runs with no submission event —
     reconciliation must explain changes by "the year's FX was edited", not per-row.
  3. "Approved" no longer means the per-diem THB is frozen (it tracks the year's FX).
- Governance rests on: only Budget-dept admins edit the rate, it is one value per year, and the
  change is a deliberate Master-Currency edit (logged on `cfg_master`).
- Contrast with ADR-0013 (admin edits one APPROVED budget deliberately): that is a per-budget
  manual edit; this is the FX-derived per-diem tracking a single shared config. They coexist.
- **Single editor = the Master Currency page (Module 09), `cfg_master.master_currency_rate`.**
  The rate is edited in ONE place only; the OPEX page shows it **read-only** (with a link to
  Module 09) and recomputes per-diem from it. Avoids two editors for one value (decided
  2026-06-14 "option A"). In the mockup the two static pages share the rate via a `cm.masterFX`
  localStorage key: Module 09 writes it (on seed + edit + delete); OPEX reads it on load and
  on the `storage` event → re-derives every trip's per-diem and the per-diem GL rows live
  (realtime when both tabs are open). OPEX has no FX input.
