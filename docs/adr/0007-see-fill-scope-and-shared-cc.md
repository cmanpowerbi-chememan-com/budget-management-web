# 7. See-scope vs Fill-scope, and shared Cost Centers

Date: 2026-06-09
Status: Partially superseded by ADR-0019 (2026-07-11) — the See-scope/Fill-scope
*derivation mechanism* below (orgcode→file09→ฝ่าย→CC) is replaced by the Cost
Center↔Filler map. The shared-CC / approval-unit reasoning that this ADR fed into
ADR-0008 is UNCHANGED and still stands.
Builds on: ADR-0001 (RLS via orgcode↔CC map), ADR-0003/0006 (per-CC approval)

## Context

`orgcode → cost_center` (file 09) is **many-to-many**: one CC is reachable from many
orgcodes, so the same CC appears for many people across departments and even divisions.
Data (254 submitters): 178/201 CCs are seen by ≥2 submitters; 161/178 cross department;
61/178 cross division; 160/178 of the sharers have different `managerempcode`. A naive
"my CCs" definition therefore over-shares, and a report-level approval unit would route one
shared CC to several different managers (conflicting status). We needed a clean rule for
(a) what a user can SEE, (b) what a user can FILL, and (c) how a shared CC is approved
without conflict — without inventing new ownership data we don't have.

Investigated joining the user's org-unit name to the cost-center department by string —
it fails: `mas_employee_data.orgnameen` ("Technology Division") and `file02.ฝ่าย`
("Maintenance", "CTO Office"…) use different vocabulary/granularity (LIKE coverage ~75-80%
with false matches). That approach (and a proposed `orgunit_dept_map` table) was dropped.

**Key data finding:** `docs/09orgcode & costcenter_cleaned.xlsx` has a `Cost Center Name`
column that **equals `file02.ฝ่าย` for all 205 CCs (100%)**. So file 09 already carries the
department per CC — no fuzzy matching, no extra table.

## Decision

- **See-scope (visibility)** = `(orgcode → file09 → cost_center) ∪ (ฝ่าย → file02 → cost_center)`
  — the CCs your orgcode maps to (broad, many-to-many roll-up) **UNION** the CCs of your
  ฝ่าย (your fill-scope). The union is required: file09 (orgcode↔CC) and file02 (ฝ่าย↔CC)
  are **divergent mappings** — without the union, 29/253 users could fill a CC they cannot
  see, and 1 user (orgcode absent from file09) would see nothing while still able to fill.
  Proven 2026-06-09: `see = org∪ฝ่าย` → FILL⊆SEE holds for 253/253, 0 empty-see.
  **The orgcode lookup MUST include both Primary AND Acting posstatus** (per the
  2026-05-27 RLS decision) — an Acting role grants see of that orgcode's CCs. Filtering
  to Primary-only silently drops Acting-based visibility (e.g. นันทพร sees a People-Care CC
  via her Acting orgcode 1155304). Reusable chain-trace tool: `docs/trace_cc_chain.py`.
- **Fill-scope (who may edit/submit a CC)** = gated by TWO things:
  1. **Role** — only the submitter set (254: L3 + L4 + 3 special L2 + Nipaporn + Waraporn)
     get an editable form; `approver1_only` (L1/L2 managers) can see but not fill.
  2. **ฝ่าย (department)** — `user → orgcode → file09 → ฝ่าย-set (Cost Center Name)`;
     fill scope = every CC whose ฝ่าย is in the user's ฝ่าย-set. 78% of submitters resolve
     to exactly one ฝ่าย; ~91% to ≤3; legit multi-ฝ่าย = cross-plant functions and
     dept-heads. No mapping table — file09's `Cost Center Name` is the source.
- **Approval unit = (ฝ่าย/department, fiscal_year)** per **ADR-0008** (was (cost_center,
  fiscal_year) per-CC first-wins; superseded — CC→ฝ่าย is 1:1 so ฝ่าย is a clean unit):
  a shared CC's first submitter owns its single approval record (routes to that person's
  managerempcode); once PENDING it is locked, so a second submitter's batch simply SKIPS
  that CC (no edit, no recall) and submits only their other CCs. One CC = one status, no
  conflict — regardless of how many people/divisions share it. The "submit the whole
  report" UX is a batch over per-CC records, not a (submitter, year) unit.

## Consequences

- No fuzzy matching, no `orgunit_dept_map` (deleted) — file09 already has ฝ่าย.
- Cross-division sharing is benign: see is broad, fill is ฝ่าย-gated, approval is per-CC.
- A handful of genuinely over-broad orgcodes (≈3: แคทรียา = whole TKK factory; ฐานิยา +
  เจนจิรา = CTO empire incl Maintenance) make those users' ฝ่าย-set too wide. The rule still
  runs; trimming their scope is a **file09 data-cleanup with the business**, NOT a logic
  change. Open task: review the ~23 submitters with ≥4 ฝ่าย (most legit).
- New submitter org-units absent from file09 → empty fill scope until file09 is updated;
  surface a "this orgcode has no CC mapping" alert.
