# 19. RLS (See + Fill) resolves via the Cost Center↔Filler map; supersedes ADR-0001, amends ADR-0007

Date: 2026-07-11
Status: Accepted
Supersedes: ADR-0001 (RLS via orgcode↔CostCenter map)
Amends: ADR-0007 — only the *derivation mechanism* for See-scope/Fill-scope is
replaced. The See ⊇ Fill invariant, approval unit = ฝ่าย (ADR-0008), and approval
routing (ADR-0006) are unaffected — see Decision below.

## Context

ADR-0001/0007 resolved both See-scope and Fill-scope by deriving them from
`mas_employee_data.orgcode` through the many-to-many orgcode↔CC map (file09) union
the CC→ฝ่าย map (file02). That design was chosen because at the time it was the only
real, populated data available — ADR-0007 explicitly rejected inventing a new
"ownership" table the business didn't have.

That constraint no longer holds. An admin-maintained Excel workbook (`cc dept.xlsx`,
SharePoint site `CMANDWPRD`, see ADR-0018) already exists and already lists, per Cost
Center, the real person(s) who fill its budget. Grilled 2026-07-11: given real
per-CC ownership data now exists, a direct list is simpler than a 3-hop org-chain
derivation. This decision is made **before** the main app's RLS layer is coded — a
repo-wide grep (2026-07-11) found no shipped code implementing the orgcode-chain
resolution, only design docs and `docs/trace_cc_chain.py` — so the reversal cost of
this decision is low.

## Decision

- **New master table: Cost Center ↔ Filler map**, synced from `cc dept.xlsx` into
  Fabric (`cman-dw-ws` / `modern_lh_cman_dw`, per ADR-0018). One row per Cost Center;
  the Filler column holds ≥1 email, comma-separated in that single cell.
- **Fill-scope** = every Cost Center where the logged-in user's email appears in that
  CC's Filler column — **full stop, no additional role/level check** (confirmed
  2026-07-11: being listed IS sufficient regardless of HR position level). Replaces
  ADR-0007's `ฝ่าย → file02 → cost_center` derivation AND the old L3/L4/special-L2
  actor-table role gate entirely.
- **See-scope** = a CC's Filler(s) **∪ each Filler's direct manager**
  (`mas_employee_data.managerempcode`, looked up per Filler). Replaces
  ADR-0001/ADR-0007's `(orgcode→file09→CC) ∪ (ฝ่าย→file02→CC)` union entirely.
- **Approval routing is UNCHANGED** (ADR-0006 stands as-is): `approver1 = the
  submitter's managerempcode`, then Nipaporn, then Waraporn. The Filler map only
  decides who CAN submit a CC, not who approves it afterward.
- **Approval unit is UNCHANGED** (ADR-0008 stands as-is): still `(ฝ่าย, fiscal_year)`,
  via the separate CC→ฝ่าย map (file02) — this ADR does not touch that map.
- **Sync tolerance:** a CC row with a blank Filler cell is skipped individually at
  sync — the rest of the file still lands. A CC with zero Fillers has nobody who can
  fill/see it until an email is added; treat it the same as ADR-0009's "orphan ฝ่าย"
  — it falls to the Admin fallback (`ADMIN_EMAILS` overlay, unaffected by this ADR).
- `orgcode_costcenter_map` (file09) keeps existing as its own admin-edited dataset
  (item #2 in ADR-0018) — it is simply no longer read for RLS. Any other use of it is
  out of scope here.

## Consequences

- Simpler mental model: one direct lookup beats a 3-hop derivation — "who fills CC X"
  is one glance at the map, not a chain trace.
- Loses the org-chain's implicit hierarchy roll-up for See beyond one manager level —
  ADR-0001's "higher tiers see subordinates' CCs because the map lists more CCs for
  them" no longer applies. A manager **two** levels above a Filler does NOT
  automatically see that Filler's CCs under this rule (only the DIRECT manager does).
  Revisit if a wider roll-up turns out to be needed.
- Open question (flag for the data-engineering session that builds the sync): does
  the direct-manager lookup for See-scope need the same "Primary AND Acting
  posstatus" nuance ADR-0007 required for orgcode lookups? Not yet decided.
- No cold-start migration problem: `cc dept.xlsx` already contains real data
  (confirmed 2026-07-11) — the existing file becomes authoritative as-is once the
  sync exists, no need to seed ~200 blank rows.
- Any future code (FastAPI backend, not yet built — ADR-0002) implementing RLS must
  resolve against the Cost Center↔Filler map, not the orgcode chain. This ADR is the
  design-of-record for that not-yet-written code.
