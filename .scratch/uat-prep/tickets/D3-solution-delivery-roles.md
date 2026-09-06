# D3 — How does Solution Delivery get a UAT filler and a UAT approver?

Type: `wayfinder:grilling` · Status: **CLOSED 2026-09-06** · Blocked by: nothing

## Question

The ask is "Pornthip and Laddawan each carry 2 departments: Data Analytic and Solution
Delivery". Today neither of them touches Solution Delivery. What changes, and what does that do
to Suchanya and to Arthid?

## The direct answer to "does this affect Suchanya?"

**Fill scope is additive — Suchanya is not displaced.** `dbo.cc_filler_map`'s primary key is
`(cost_center, filler_email)`, and 153 cost centers already carry more than one filler (max 5).
`rls._FILL_SQL` is a per-email `SELECT DISTINCT` with no exclusivity check. Adding a filler row
leaves her row and her rights untouched.

**But "Laddawan can do it instead of Suchanya" as an *approver* is impossible by configuration.**
`approval.py:619` — `approver1_empcode = raw_manager or NIPAPORN_EMPCODE`, where `raw_manager`
comes straight from `dbo.v_employee_budget_01.manager_employee_code`. There is no
approver-assignment table, no admin UI, no override column. Approver 1 is always **the
submitter's HR manager**. And:

- Suchanya 101159 → **Arthid 101622**
- Laddawan 101431 → **Arthid 101622**
- Pornthip 101917 → **Laddawan 101431**

| If this person fills and submits Solution Delivery | approver1 becomes |
|---|---|
| Suchanya (today) | Arthid |
| **Laddawan** | **Arthid** — a real employee who is not attending, who gets a genuine unmarked approval email |
| **Pornthip** | **Laddawan** ← the only configuration that delivers the ask |

Proven by live audit rows: log #665 Laddawan approved after Pornthip submitted; log #674
**Arthid** rejected after **Laddawan** submitted.

**So the fill row to add is `(10IT012000, pornthipp@chememan.com)`, not Laddawan's.**

## The real collision, and it is not Suchanya's permissions

`pk_approval_status(department, fiscal_year)` — **one record per department per year**. Whoever
submits first freezes the chain and locks everyone else out (`invalid_approval_state` unless the
status is `REJECTED`), and ADR-0013's read-only lock makes **all** of Solution Delivery's rows
non-editable for Suchanya for as long as UAT holds it mid-chain. Row writes collide too:
`pk_pending_budget(cost_center, gl_account, fiscal_year)` is last-write-wins.

Solution Delivery FY2027 is currently pristine — 0 rows, no approval record, never submitted in
any year. **UAT would be the first thing ever written to it.**

## Costs of the change

- `dbo.cc_filler_map` is a **read-only daily sync** of SharePoint `cc dept.xlsx` (observed load
  stamp `2026-09-05 06:30:48`). A new row is not live until the next ~06:30 run, and removing it
  after UAT is equally delayed. Editing the DB directly gets overwritten by the next sync.
- It is a **production master edit** affecting the whole system while it stands.
- Removing the mapping afterwards does **not** revert any budget rows UAT wrote.

## Options

- **(a) Add `(10IT012000, pornthipp@chememan.com)` to `cc dept.xlsx`.** Pornthip fills and
  submits both departments; Laddawan approves both. Delivers the ask exactly. Needs a production
  master edit, a ~24 h sync wait, a recorded pre-change SharePoint version, and a dated revert.
- **(b) Add Laddawan as a Solution Delivery filler.** Reject — if she submits, a genuine unmarked
  approval request goes to Arthid, who is not in the room.
- **(c) Invite the real people** — Suchanya as filler, Arthid as approver 1. Zero master edits,
  maximally realistic, seven attendees instead of five.
- **(d) Pornthip or Laddawan submits, Nipaporn uses the admin step-override** (`POST
  /approval/override-step`, admin-only, position-1 only) to skip Arthid. No master edit, but
  Laddawan then approves nothing for that department, so the ask is not met.
- **(e) Drop the second department** and run a single-department round like SIT did.

## Recommendation

**(a)**, with **(c)** as the better answer if two more people can be in the room. Two conditions
on (a): record the pre-change SharePoint version of `cc dept.xlsx` and file the revert as a dated
tracker task the same day; and tell **Suchanya** in advance that her department will be written
to and locked during the round, and **Arthid** that he may receive mail. Reject (b) outright.

---

## RESOLUTION — CLOSED 2026-09-06

**jakkaritw chose (a): add Pornthip as a Solution Delivery filler.**

The row to add to SharePoint `cc dept.xlsx` is **`(10IT012000, pornthipp@chememan.com)`**.

The resulting UAT shape:

| Department | Filler | Approver 1 | Approver 2 | Approver 3 |
|---|---|---|---|---|
| `Data & Analytic` (`10IT011300`, `10IT013000`) | Pornthip 101917 | **Laddawan 101431** | Nipaporn 101032 | Waraporn 100427 |
| `Solution Delivery` (`10IT012000`) | Pornthip 101917 | **Laddawan 101431** | Nipaporn 101032 | Waraporn 100427 |

So Pornthip carries both departments as filler and Laddawan approves both — which is the ask,
reached the only way the code allows.

**Suchanya is not displaced.** Fill scope is additive (`pk_cc_filler_map(cost_center,
filler_email)`), her row stays, and her rights are unchanged.

**Two obligations this decision creates, both carried by T2:**
1. Record the pre-change SharePoint version and eTag of `cc dept.xlsx`, and **file the revert as
   a dated tracker task the same day** — the removal is equally sync-delayed and does not undo
   any budget rows UAT writes.
2. **Brief Suchanya before the round.** Her department will be written to, and while UAT holds
   `Solution Delivery / FY2027` mid-chain, ADR-0013's read-only lock makes *all* her rows
   non-editable and she cannot submit her own budget
   (`pk_approval_status(department, fiscal_year)` is one record per department per year).
   She will also receive the genuine reject and final-approve emails for her own department.

**Arthid is out of the chain** under this option and needs no briefing on mail — but only as
long as Pornthip, never Laddawan, is the one who clicks Submit on Solution Delivery. That
instruction belongs in the pack (T5) and the run plan (T6), not just in this ticket.
