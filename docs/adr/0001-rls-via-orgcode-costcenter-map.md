# 1. Row-Level Security resolves through the orgcode↔CostCenter map only

Date: 2026-06-06
Status: Accepted

## Context

Two different RLS designs existed in the docs for deciding which Cost Centers a
logged-in user may see and fill:

1. **orgcode↔CC map** — `login email → mas_employee_data.orgcode →
   cfg_master.orgcode_costcenter_map → cost_center(s)`. A many-to-many junction
   table (file 09), with real code, SQL, and a deployed admin editor.
2. **`get_visible_ccs` prefix-match** — read the user's CC from a
   `capps_m_employee` table, then string-prefix match (VP = `cc[:5]`, lower =
   `cc[:8]`, C-Level via a "C Level" column). Documented in CLAUDE.md (2026-05-16),
   but **never implemented** — no code, no `capps_m_employee` table.

Having two access mechanisms means two sources of truth for permissions; only one
can ship.

## Decision

RLS resolves through the **orgcode↔CostCenter map only**. The map (file 09) is the
single master for see + fill + submit scope. Wrong permissions are fixed by editing
file 09, never by hard-coding logic. The `get_visible_ccs` prefix design and
`capps_m_employee` are dead and removed from the project's guidance.

## Consequences

- One auditable source of truth for access; supports the many-to-many reality
  (190 CCs map to multiple orgcodes).
- Admin "see all" is a role overlay outside the map, not part of the chain.
- The prefix design's implicit hierarchy encoding is lost — acceptable, the map
  already encodes who-sees-more by listing more CCs for higher tiers.
- CLAUDE.md must be scrubbed of the prefix logic so future agents don't rebuild it.
