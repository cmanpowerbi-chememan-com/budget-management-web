# Reference — GL Account Groups (GL Master)

What this is: the canonical list of GL Account groups from sheet `GL Acct & Group` — a snapshot of
**18 groups, 137 accounts** (see staleness note below). Source of truth for `group_exp` / GL group
names. The group names must match SAP exactly (used to join Accruals → dashboard grouping). Master
file: `02docs/04gl code & gl group & gl thai name (master).xlsx` (owner-edited on SharePoint,
synced into `dbo.gl_group` daily ~06:31 — counts drift by design, never hard-assert them in tests).

> **Staleness note (2026-09-04):** this table is a manually-maintained snapshot, not live-synced —
> the live master currently has **19 groups / ~146 accounts**, ahead of the 18/137 counted here.
> The group breakdown below is not being republished this pass (no verified source for the extra
> group in this session); treat the per-group "Accounts" column as indicative, not exact.

> **Note:** "Oversea Trip" and "Fuel" are **sub-templates** (detail input sheets in the budget
> form), **NOT GL groups**. Their GL accounts live under existing groups — Oversea Trip items
> under *Travelling Expense*, Fuel under *Other admin. Expenses*. Never treat them as a GL group.

---

## GL Account Groups (18-group snapshot, see staleness note above)

| # | Group Name | Accounts |
|---|-----------|---------|
| 1 | Bank Charge | 3 |
| 2 | Communication Expense | 8 |
| 3 | Electricity & Water | 3 |
| 4 | Employee benefits | 2 |
| 5 | Entertainment | 3 |
| 6 | Insurance Premium | 2 |
| 7 | Lease & Rental | 14 |
| 8 | Maintenance - License for software | 2 |
| 9 | Office expenses | 14 |
| 10 | Other admin. Expenses | 34 |
| 11 | Other manpower exp (Per diem, Health check, Uniform…etc) | 15 |
| 12 | Personal expenses | 3 |
| 13 | Professional & Legal Fee | 13 |
| 14 | Public Relation & Donation | 3 |
| 15 | Remuneration of director | 1 |
| 16 | Repair & Maintenance | 11 |
| 17 | Training & Seminar | 2 |
| 18 | Travelling Expense | 6 |

> **2026-09-04 reclassification:** GL `5210400999` (COST) / `6210400999` (SGA), Thai name
> "ค่าใช้จ่ายเดินทางอื่น (รวมในประเทศ และ ต่างประเทศ)", moved from *Travelling Expense* to
> *Other manpower exp* — jakkaritw decided they are a recurring monthly cost (parking/fuel/tolls),
> not a per-trip cost. The row counts above (Travelling Expense 6, Other manpower exp 15) already
> reflect this move — the SharePoint master was edited same-day; `dbo.gl_group` (the live DB table
> the app reads) picks it up on the next daily sync (~06:31). App code
> (`backend/app/write_model.py`'s `TRAVEL_GL_BY_TYPE_SIDE`, `frontend/src/subform/glDropdownConstants.ts`)
> was updated in the same change so Trip Manager stops offering/saving these two GLs — see
> `.claude/plan.md` for the full changeset.
