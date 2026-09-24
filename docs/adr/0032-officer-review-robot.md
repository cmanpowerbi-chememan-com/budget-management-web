# 32. Officer-review robot: weekly SharePoint write exception + three-way reconcile gate

Date: 2026-09-24

Status: Accepted (jakkaritw, 2026-09-24, PRD issue #34). Implemented 2026-09-24 (backend, TDD via a
live-DB reconcile property, not yet deployed — schedule inert until pushed to `main`).

## Context

Budget officers (Nipaporn, Waraporn) review every department's FY budget once its approval loop
finishes, plus the detail behind every special-GL line (trips, entertainment, consulting, ...).
Today that file is an ad-hoc prototype the developer runs by hand
(`playdata/excel-export-preview/build_preview.py` + `build_officer_extract.py`) — the officers
cannot get a fresh copy without asking him, and during the submission window (30 Sep-15 Oct 2026)
the approved picture changes weekly.

The prototype is the layout/control **specification** only (jakkaritw passed it 2026-09-24; the
officer extract went through a combined 06+07+08 gate twice, APPROVE-WITH-SUGGESTIONS) — it is not
imported by production code. The production port lives in `backend/app/` + `backend/jobs/`, reusing
the backend's own read model, SAP module and special-GL definitions instead of copying their rules
(issue #34 story 32), so the file can never drift from the app the way a hand-copied SQL constant
could.

Publishing requires writing to SharePoint. The 2026-08-10 rule "ทุกไฟล์บน Path ห้ามยุ่ง ยกเว้นเอกสาร
ฝ่าย" (every file on the library path is off-limits except `เอกสาร ฝ่าย/`) exists to stop the web
app from ever touching the eight admin master workbooks, `approved budget/`, or `pending budget/`.
This robot needs an explicit, narrow exception.

## Decision

**Scope.** A department whose `budget.approval_status` is APPROVED for the planning year, UNION
every `pending_budget` row with `template='ADMIN'` (Template 2, instant-approve) — APPROVED always
wins the status label on a key that is both. A row whose department cannot be resolved at all stays
visible as `(ไม่ทราบฝ่าย)`, never silently dropped.

**Layout.** Sheet 1 is the same summary layout the upcoming web "ดาวน์โหลด Excel" button will use —
`backend/app/budget_xlsx.py` is the ONE shared writer (issue #34 story 33); whichever effort lands
first owns it, the other reuses it as-is. Sheets 2-7 are one per special-GL topic (Travelling
Expense, Professional & Legal Fee, Entertainment, Training & Seminar, Public Relation & Donation,
Lease & Rental), one row per `pending_budget_detail` line, officer-only code in
`backend/app/officer_workbook.py`.

**The gate: file = web = Fabric (D4).** Three independent sources are compared at cents on every
run, dry-run included:

- **FILE** — the saved xlsx bytes, read back with `openpyxl` (never the in-memory rows).
- **WEB** — `app.read_model.get_budget_grid`, the same function `GET /budget` calls, run once per
  in-scope department in the admin view, plus one extra unfiltered admin-wide pass to recover
  `(ไม่ทราบฝ่าย)` rows a per-department call can never return.
- **FABRIC** — hand-written SQL in `backend/app/officer_reconcile.py`, run fresh (never reusing
  `get_budget_grid`/`merge_budget_rows`/`fetch_sap_actuals` — that would make the compare a
  self-consistency check, not an independent one).

Any FAIL means no publish and no mail. On a FAIL the job rebuilds and re-reconciles ONCE after a
sleep (default 300s) — a live save during the submission window, or a SAP load landing mid-run, can
cause one honest transient mismatch; a second FAIL is treated as real.

**PDPA (jakkaritw 2026-09-24, "ไม่เป็นไร grant personal info").** The traveller NAME is allowed, but
ONLY in the travel sheet's ชื่อผู้เดินทาง column. System-sourced columns (codes, names, status,
headers) FAIL on an email address, a traveller name outside that one column, or a traveller
employee code. User free-text columns (Remark, รายละเอียด, meta_json-sourced topic columns, trip
project/purpose/remark/destination) get the same three checks at WARN level only — a typed email
inside a free-text field must never be able to block the weekly file by itself.

**Publisher — the SharePoint write exception.** Site `CMANDWPRD`, library `Budgeting and
Management`, folder `officer review/` (created if missing), file
`budget_FY<yyyy>_officer_latest.xlsx`, overwritten in place (`conflictBehavior=replace`, so the
SharePoint item id — and its version history — never changes). The publisher resolves the folder
explicitly and verifies every published item's `parentReference.id` equals that folder id before
trusting the write; it never deletes anything, and the filename is asserted never to match
`approved_budget_<yyyy>.xlsx` or any of the eight master filenames. Only the Graph token and
site/drive resolution (`app.attachments._get_graph_token` / `_resolve_site_and_drive`) are shared
with the attachments module — `backend/app/attachments.py` is unedited, and its own write-scope
guard (limited to `เอกสาร ฝ่าย/`) is unchanged. **This is the explicit, owner-approved exception to
the 2026-08-10 rule, scoped to `officer review/` and this robot only.**

**Notifier.** Thai HTML mail built in `backend/app/officer_notify.py` (not inside
`notifications.py` — that module is not edited by this change), sent via the existing
`app.notifications.send_mail` seam, one call per recipient in `OFFICER_REVIEW_RECIPIENTS` (a repo
variable, comma/semicolon-separated). Link only, no attachment.

**Schedule + kill switch.** A new, separate workflow (`.github/workflows/officer-review.yml`),
`cron: "10 0 * * 5"` (Friday 07:10 Bangkok) + `workflow_dispatch`. Real publish+mail requires the
repo variable `OFFICER_REVIEW_LIVE=true` **on a scheduled run**, or a manual dispatch with
`execute=true` — deliberately NOT coupled to `budget-automations.yml`'s `REMINDERS_LIVE` /
`NOTIFICATIONS_DRY_RUN` (PRD story 29: reminders are armed for real sends 30 Sep-15 Oct 2026, and
this robot must never be able to disturb that). Deleting the variable, or setting it to false, is
the kill switch — no commit, no redeploy.

**Credentials.** The CI service principal (`FABRIC_AAD_*` secrets) now also needs
`GOLD_SQL_SERVER` / `GOLD_SQL_DATABASE` secrets and Viewer on the DW gold workspace — **neither
existed as of this change** (confirmed via `gh secret list` / `gh variable list`, 2026-09-24).
`--probe` (`python -m jobs.officer_review --probe`) is the first-slice read-only check: Fabric
read, gold read, Graph token roles (`Sites.ReadWrite.All` + `Mail.Send`), and a read-only
site/drive/`officer review/` folder resolution.

## Considered Options

- Reuse `app.attachments.upload_attachment` for the publish — rejected: it builds its path under
  `เอกสาร ฝ่าย/<ฝ่าย>/<year>` and maps a 404 to `FolderNotFoundError`; this robot needs its own
  folder identity and creation flow, never that path.
- Widen `app.attachments._is_inside_attachments_root` to also allow `officer review/` — rejected:
  that guard's only callers are the attachments download/delete path; widening it would also widen
  what the WEB APP itself can reach. The publisher gets its own guard instead.
- Add `NOTIFICATIONS_DRY_RUN` / `REMINDERS_LIVE` forwarding to this workflow (matching the
  reminders' pattern) — rejected per PRD story 29: a rehearsal or kill action on the shared reminder
  variables must never redirect or silence officer mail, and vice versa.
- Compare the Fabric side by re-calling `app.sap.fetch_sap_actuals` / `app.read_model.merge_budget_rows`
  — rejected: that is what makes the ADR-0030 acceptance test's own docstring warn about
  self-consistency ("proves cell values, not correctness"); the whole point of a THIRD source is
  independence.

## Consequences

- The CI service principal now holds `Sites.ReadWrite.All` on the SAME site the eight admin masters
  live on. The write-scope guarantee (PRD story 26, "physically unable to write anywhere else") is
  **code-level only** (the publisher's own folder-id check) — a true physical scope would need
  `Sites.Selected`, not evaluated here. Do not represent this as a Graph-permission-level guarantee.
- GitHub Actions `schedule:` triggers only fire from the default branch after this workflow file is
  pushed to `main`, and GitHub may delay (~5-30 min, accepted) or occasionally drop a scheduled run
  under platform load — `workflow_dispatch` is the fallback, not a bug to chase.
- `GOLD_SQL_SERVER` / `GOLD_SQL_DATABASE` must be added as repo secrets, and the DW gold workspace
  Viewer grant confirmed for the CI principal, before the schedule or any `--execute` run can
  succeed — both are jakkaritw's call, not made by this change.
- `openpyxl` moves from a "TEST-only" `requirements.txt` comment to a stated runtime dependency
  (already installed in the production image either way).
