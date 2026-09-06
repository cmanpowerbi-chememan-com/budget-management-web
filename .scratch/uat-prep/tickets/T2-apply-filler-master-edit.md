# T2 — Put the agreed filler mapping live, and tell the people it touches

Type: `wayfinder:task` (HITL — a human edits SharePoint) · Status: **DONE 2026-09-06 except the two briefings** — the mapping is LIVE in `dbo.cc_filler_map` and proven by `resolve_scope` · Blocked by: ~~D3~~ closed

## Question

Make `dbo.cc_filler_map` reflect the D3 decision, prove the sync landed, file the revert, and
brief the two people whose department and inbox this touches.

## Work

1. **Record the pre-change state first**: the current SharePoint version number and eTag of
   `cc dept.xlsx`, a saved copy of the file, and the exact `dbo.cc_filler_map` rows for
   `10IT012000`, `10IT011300` and `10IT013000` with their `_load_dttm`.
2. Edit `cc dept.xlsx` on SharePoint per D3 (expected: add the row for cost center `10IT012000`).
   Edit the Excel, never the table — `dbo.cc_filler_map` is a read-only sync target and a direct
   DB write is overwritten by the next run.
3. Wait for the ~06:30 sync, then verify the new row is present with a fresh `_load_dttm`, and
   that no other row changed. Re-run `resolve_scope` for both Pornthip and Laddawan and confirm
   the Fill and See sets are exactly what D3 predicted.
4. **File the revert as a dated tracker task the same day** — the removal is equally
   sync-delayed, and removing the mapping does not revert any budget rows UAT wrote.
5. **Brief the non-attendees.** Suchanya (`suchanyay@`) — her department will be written to and
   locked read-only while UAT holds it mid-chain. Arthid (`arthids@`) — he may receive a genuine,
   unmarked approval email. Both messages must say the round's dates.

## Constraints

- The whole SharePoint library is off-limits to the app except `เอกสาร ฝ่าย` — this edit is a
  human action on a master file, not an app action.
- `openpyxl` saves strip the sensitivity label. If a script touches the file, the
  `docMetadata/LabelInfo.xml` + `customXml` parts must be spliced back (the fix is already
  implemented in `setup/update_sit_test_cases.py`). Prefer editing in Excel by hand.
- A SharePoint 423 means the file is open in Excel somewhere.

## Definition of done

The new row live in `dbo.cc_filler_map` with evidence before / after · `resolve_scope` output
for both testers quoted · the revert task filed with its id · both briefing messages sent and
quoted.

---

## PROGRESS 2026-09-06 — step 2 done, steps 3 to 5 outstanding

jakkaritw ordered it directly: *"(10IT012000, pornthipp@chememan.com) — ai do"*.

### What the master actually looked like (this changed the plan)

`cc dept.xlsx` is **one row per cost center**, with the fillers as a **comma-separated list in a
single cell** (`Cost Ctr | Description | C Level | สายงาน | ฝ่าย | คนกรอกข้อมูล`), 213 data rows,
153 of them already carrying more than one filler. So this was a **cell append, not a new row** —
the ticket originally assumed a row insert, and that assumption was wrong.

### Done

| | |
|---|---|
| Baseline recorded | version **58.0**, eTag `…,244`, size 24,528, last modified 2026-09-05 by Jakkarit |
| Backup | `../ccdept_BEFORE_20260905-215634Z.xlsx` (4 identical copies were taken across dry runs; 3 removed after an md5 check) |
| Change | row 15 / `10IT012000` / Solution Delivery: `'suchanyay@chememan.com'` → `'suchanyay@chememan.com, pornthipp@chememan.com'` |
| Result | version **59.0**, eTag `…,245` |
| Verified by re-download | **exactly 1 cell differs** from the pre-change backup across the whole 214 × 6 sheet; 19 sensitivity-label parts present including `docMetadata/LabelInfo.xml`; Pornthip now on 3 cost centers, Laddawan still 2, **Suchanya still on `10IT012000`** |

The script is `setup/ccdept_add_filler.py` — dry-run by default, `--apply` to write, `--remove
--apply` to undo. It refuses to write an email that is absent from `dbo.v_employee_budget_01`,
and it refuses a removal that would leave a cost center with no filler at all.

**The RLS integrity guard was checked before writing and passed.** That guard is not theoretical:
28 consecutive sync runs failed with `rows_out=0` between 2026-08-26 and 08-31 because one email
in this file was missing from that view, which froze every cc-filler update for six days. The
script had to read the server and database from the **production container**, because the repo
`.env` still points at the retired DB1 where the view does not exist — the first attempt failed
closed with "Invalid object name", which is the guard working correctly.

### Not done

1. **The sync has not run yet.** `dbo.cc_filler_map` still shows Solution Delivery with one
   filler until the next ~06:30 pass. Someone must confirm the run **succeeded** — a failure
   leaves the table frozen and silently un-changed — and then re-read `resolve_scope` for
   Pornthip and Laddawan to prove the Fill and See sets match what D3 predicted.
2. **Suchanya has not been told.** She needs to know her department will be written to, that
   ADR-0013 will lock all her rows read-only while UAT holds it mid-chain, and that she will
   receive the genuine reject and final-approve emails.
3. **Arthid has not been told.** He is out of the chain under this option, but only for as long
   as Pornthip and never Laddawan clicks Submit on Solution Delivery. If that slips, he gets a
   real, unmarked approval request.
4. The revert is filed as ledger task `ccdept-revert-pornthipp-solution-delivery`.

---

## SYNC VERIFIED 2026-09-06 — the mapping is live

jakkaritw asked for the sync on demand rather than waiting. Two things happened:

1. **The scheduled run had already picked it up.** By the time the on-demand run started,
   `_load_dttm` was already `2026-09-06 06:31:07` and row count had gone **466 → 467**, so the
   normal 06:31 pass had synced the edit that morning.
2. **The on-demand run confirmed it idempotently.** `NB_budget_masters_sync` (DW workspace
   `cman-dw-ws`, notebook `c2908a41-…`) was triggered with `only_spec="Budget_Masters_cc_filler_map"`
   so exactly one master was processed and the other seven were untouched. Job
   `f8f792e8-d9c6-4417-b357-79fa37c08612`, **Completed in 202 s**, `_load_dttm` advanced to
   `2026-09-06 21:21:18`, row count **467 → 467**.

Per gotcha C1 the status was not trusted on its own — the table was re-read and the row confirmed
present. The reusable trigger is `setup/run_ccfiller_sync.py`, which fails loudly if the job says
Completed while the row is absent (the shape an RLS-guard failure takes).

### `resolve_scope` run live against production — matches D3 exactly

| Person | role | FILL | Departments fillable | SEE | empcode → manager |
|---|---|---|---|---|---|
| Pornthip | filler | **3 CC** `10IT011300`, `10IT012000`, `10IT013000` | **`Data & Analytic` + `Solution Delivery`** | 3 | 101917 → **101431 (Laddawan)** |
| Laddawan | filler | 2 CC (unchanged) | `Data & Analytic` | **3** (was 2) | 101431 → 101622 (Arthid) |
| Suchanya | filler | 1 CC (unchanged) | `Solution Delivery` | 1 | 101159 → 101622 (Arthid) |

Pornthip's manager is Laddawan, so **approver 1 for both departments resolves to Laddawan** the
moment Pornthip submits — which is the whole point of choosing this option.

**One side effect worth naming:** Laddawan's See scope grew from 2 to 3 cost centers. She can now
see `10IT012000` (Solution Delivery) through the manager-see-add rule, because she manages
Pornthip and Pornthip now fills it. She gains **See only, never Fill** — but it does mean a
department she could not previously open is now visible to her. That is a real RLS change, and it
persists until the revert.

### Still outstanding — the two briefings

Neither has been sent. They are the last thing standing between this ticket and closed:
- **Suchanya** — her department will be written to; ADR-0013 will lock all her rows read-only
  while UAT holds it mid-chain; she will receive the genuine reject and final-approve emails.
- **Arthid** — out of the chain, but only while Pornthip and never Laddawan clicks Submit on
  Solution Delivery.
