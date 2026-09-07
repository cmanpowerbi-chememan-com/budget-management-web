# Map — UAT round for the budget web app

Label: `wayfinder:map` · charted 2026-09-06 · tracker id `wayfinder-uat-prep`
Tickets: `tickets/` · Raw chart-time research: `research/` (6 agent reports + a completeness critique)

## Destination

A UAT round can start and be signed off. Four things true:

1. **Environment settled and configured** — one of staging / production is chosen, and the
   chosen container carries the agreed session lifetime, impersonation posture and mail
   behaviour, each with a written revert.
2. **Two-department role assignment live** — Pornthip and Laddawan each carry BOTH
   `Data & Analytic` and `Solution Delivery` in `dbo.cc_filler_map`, with Suchanya's and
   Arthid's exposure explicitly handled and agreed.
3. **The pack exists** — `requirement_spec/5_uat/` holds the test-case workbook, the two
   1-page Thai guides, the entry/exit criteria and the acceptance sign-off sheet;
   `plan/uat/` holds the engineering companion (waves, safety rules, run log, restore SQL).
4. **The blast radius has a way back** — every row UAT writes to the shared production
   database has a pre-written, pre-reviewed restore.

The round itself running, and fixing whatever it finds, are the NEXT effort, not this map.

## Notes

**Execution is IN the map.** Like `.scratch/other-travel-gl-move`, this map does not stop at a
spec — it ends when the round is ready to run. Wayfinder's plan-don't-do default is overridden.
Every mutating step still needs jakkaritw's written approval before it runs (CLAUDE.md
never-cut: deploy approval · verify-deploy-landed · verify-target + explicit confirm before any
destructive action · PDPA-touching changes get the 07 checklist).

**Skills each session should consult:** `00-team-workflow` routing · `10-deploy-checklist`
before any container or master change · `07-security-checklist` on anything touching identity,
`SIT_IMPERSONATE`, `DEV_AUTH_EMAIL` or traveller PII.

**Prior art to read before re-deriving anything:**
- `plan/sit/sit-test-plan.md` — 1198 lines. Already absorbed the deleted `post-deploy-smoke-uat-plan.md`
  and `uat-quick-guide.md`. Lines 69–136 = safety rules · 137–250 = environment + personas ·
  913–946 = entry/exit criteria · 1011–1035 = the 1-page filler guide · 1105–1152 = the
  2026-08-07 UAT pilot decision.
- `requirement_spec/4_sit/Budget_SIT_Test_Cases_10.08.2026.xlsx` — 61 cases, 4 sheets.
- `research/` in this folder — the verified ground truth below, in full.

### Ground truth verified at chart time (2026-09-06, live `az` + SELECT-only DB reads)

| Fact | Value |
|---|---|
| Code on both containers | **identical image `cmanbudgetacr.azurecr.io/budget-web:72affd9`** (stg rev `0000068`, prd rev `0000033`). The memory note "prd still 55e0753" is STALE. |
| Database | stg and prd read **byte-identical** `FABRIC_SQL_SERVER` + `FABRIC_SQL_DATABASE` (`fabric_sql_database-a42ef9f3-…`). **There is no sandbox.** |
| Mail | `NOTIFICATIONS_DRY_RUN=false` on BOTH · no label · no redirect on either. Staging mail is byte-identical to production mail and reaches real colleagues. |
| Session cookie | stg has **no `cookieExpiration` block at all** → Container Apps default ≈8 h. prd is explicitly `14:00:00`. Neither has a `tokenStore`, so expiry is fixed from login, never sliding. |
| Staging-only identity risks | `APP_ENV=local` + `DEV_AUTH_EMAIL=pornthipp@chememan.com` (armed: if Easy Auth is ever switched off, any anonymous caller becomes Pornthip) · `SIT_IMPERSONATE` with 5 targets, from-email `jakkaritw` only. On staging **jakkaritw silently defaults to being Pornthip**, and the audit log records the impersonated person. |
| Entra app registrations | different per app (stg `7035aa47-…`, prd `61d5d556-…`), so a staging cookie is useless on prd and tenant consent is per-registration. |
| Open fiscal year | **FY2027 only.** `dbo.submission_deadline` holds one row: deadline `2026-10-07`, reminder `2026-09-22`. Every other year is `NOT_OPEN` for everyone, admin included. |
| `Data & Analytic` | 2 cost centers `10IT011300` + `10IT013000` · fillers `laddawank@` + `pornthipp@` (both, both CCs) · FY2027 = **REJECTED**, reason `test`, rejected by Arthid 2026-09-05 · 3 rows / 42,040.00 THB. |
| `Solution Delivery` | 1 cost center `10IT012000` · **one filler only, `suchanyay@chememan.com`** · FY2027 = **0 rows, no approval record, never submitted in any year.** |
| Approver chain | `approver1_empcode` = the **submitter's HR manager**, frozen at submit. Positions 2 and 3 are compile-time constants: Nipaporn `101032`, Waraporn `100427`, for every department. There is no approver-assignment table. |
| Manager facts | Pornthip 101917 → Laddawan 101431 → **Arthid 101622** ← Suchanya 101159. |
| Admins | `jakkaritw`, `nipapornt`, `warapornt` (+ `cmanpowerbi` in code). **Pornthip and Laddawan are not admins. `piyadad` is not either** — `.claude/project-context.md`'s 4-admin line is stale. |
| Since SIT closed (2026-08-20) | **12 user-visible changes shipped with zero workbook coverage**, all LIVE on both environments: CI-green repaint · per-diem tier 3 (29 countries) · searchable destination combobox · real EN approver titles · hundreds-rounding legend note · Training & Seminar GL restricted to Talent & Culture · a brand-new toast surface · trip `รายละเอียด` now editable · other-travel GL pair out of the trip form · the whole approval module in English incl. the dept-picker badge. |
| Stale SIT cases | 15 cases still say `รออนุมัติ`, 11 say `ตีกลับ`; TC-061 expects a 4-row trip table and a greyed-out remark; TC-057 uses a seminar GL a Data & Analytic filler can no longer pick. |

### The two facts that dominate every decision on this map

1. **There is no test environment.** Staging and production run the same image against the same
   database and send the same unmarked mail. Choosing staging buys zero safety — it only adds
   impersonated identities, a latent whole-app identity override, and cold starts.
2. **UAT must write the live FY2027 planning cycle**, 31 days before the real deadline, and the
   app has **no reopen route** — `APPROVED` is terminal. Only a direct DB write can undo it.

## Ticket index

This tracker is the filesystem, so the frontier is read here rather than queried. A ticket is
takeable when every ticket named in its `Blocked by` line is closed. Claim one by writing
`Claimed by: <session>` under its status line **before** doing any work.

| Ticket | Blocked by | Takeable now |
|---|---|---|
| [D2 — What is UAT allowed to write, and how does it get undone?](tickets/D2-write-scope-and-rollback.md) | — | **yes** |
| [D6 — What do UAT emails look like, and who may receive one?](tickets/D6-mail-blast-radius.md) | — | **yes** |
| [T2 — Put the agreed filler mapping live, and tell the people it touches](tickets/T2-apply-filler-master-edit.md) | ~~D3~~ closed | **DONE except 2 briefings — mapping LIVE, `resolve_scope` proves Pornthip on both departments** |
| [T7 — Prove the testers can actually sign in](tickets/T7-verify-tester-login.md) | ~~D1~~ closed | **yes — now a 5-minute confirmation, no longer a blocker** |
| [D7 — When does UAT run, and what does "UAT passed" mean?](tickets/D7-window-and-gate.md) | D2 | no |
| [T3 — Export the baseline and pre-write the restore](tickets/T3-baseline-and-restore.md) | D2 | no |
| [T1 — Apply and verify the environment configuration](tickets/T1-apply-env-config.md) | ~~D5~~ closed · **D6** | no |
| [T4 — Prepare the field: clean the leftovers, seed enough to click](tickets/T4-prep-uat-field-data.md) | D2, T3 | no |
| [T5 — Build the UAT pack in `requirement_spec/5_uat/`](tickets/T5-build-uat-pack.md) | **SPLIT 09-07** — part A none, part B D7 | **part A in progress · part B no** |
| [T6 — Write the engineering companion in `plan/uat/`](tickets/T6-uat-run-plan.md) | D2, D6, D7, T3 | no |
| ~~[D1 — staging or production?](tickets/D1-environment.md)~~ | — | **CLOSED 2026-09-06** |
| ~~[D3 — Solution Delivery filler and approver](tickets/D3-solution-delivery-roles.md)~~ | — | **CLOSED 2026-09-06** |
| ~~[D4 — What goes into the UAT pack?](tickets/D4-pack-scope.md)~~ | — | **CLOSED 2026-09-06** |
| ~~[D5 — the session lifetime](tickets/D5-session-lifetime.md)~~ | — | **CLOSED 2026-09-06 · APPLIED to prd · REVERT OWED** |

**T5 split on 2026-09-07.** The test script itself depends only on closed decisions, so part A
(the workbook + the Thai companion + the generator + the validator) is being built now; part B
(entry/exit criteria, the two 1-page guides, the sign-off sheet, any SharePoint upload) stays
blocked on D7. Details in the ticket.

**Start T2 first.** The `cc dept.xlsx` edit is the only item with a hard ~24-hour latency (the
SharePoint → `dbo.cc_filler_map` sync runs ~06:30), so every day it waits is a day the round
cannot start. D2 is the next decision, because T3, T4, D7 and T6 all hang off it.

> ### ⚠️ OUTSTANDING PRODUCTION CHANGE — must be reverted when UAT ends
>
> Production's Easy Auth session cookie was lowered **`14:00:00` → `01:00:00`** on 2026-09-06 per
> jakkaritw. It affects **every** production user, not only the five testers. Tracked as
> `prd-session-1h-revert-after-uat` in the ledger. Revert is one command:
>
> ```bash
> az containerapp auth update -n cman-budget-web-prd -g CMAN-BUDGET-MNGT-WEB-RG >   --set login.cookieExpiration.convention=FixedTime >   --set login.cookieExpiration.timeToExpiration=14:00:00
> ```
>
> Baseline backup: `prd_auth_backup_before_3h_20260906.json`. **This map is not closed until that
> revert has run and been verified.**
>
> ### ⚠️ OUTSTANDING PRODUCTION GUARD REMOVAL — must also be reverted when UAT ends
>
> `APP_ENV` on `cman-budget-web-prd` went **`production` → `uat`** and `SIT_IMPERSONATE` was
> added (6 targets) on 2026-09-06, so the impersonation picker works on the same link the
> testers use. This deliberately removes the guard `auth.py:106` describes as "identity-rewrite
> can never run on PRD no matter what the other settings hold". Tracked as
> `prd-appenv-uat-revert-after-uat`. Verified narrow: `app_env` is read in only four places and
> `DEV_AUTH_EMAIL` stays absent, so nothing else was unlocked. Revert (jakkaritw must run it —
> Claude's safety classifier blocks it):
>
> ```bash
> az containerapp update -n cman-budget-web-prd -g CMAN-BUDGET-MNGT-WEB-RG \
>   --set-env-vars APP_ENV=production --remove-env-vars SIT_IMPERSONATE
> ```
>
> ### ⚠️ OUTSTANDING MASTER-DATA CHANGE — must also be reverted when UAT ends
>
> SharePoint `cc dept.xlsx` row 15 (`10IT012000`, Solution Delivery) went from
> `suchanyay@chememan.com` to `suchanyay@chememan.com, pornthipp@chememan.com` on 2026-09-06
> (version 58.0 → 59.0). Tracked as `ccdept-revert-pornthipp-solution-delivery`. Revert:
> `python -X utf8 setup/ccdept_add_filler.py --remove --apply`. Note the removal is equally
> sync-delayed, and it does **not** undo any budget rows UAT wrote.

## Decisions so far

- [D1 — Does UAT run on staging or on production?](tickets/D1-environment.md): **production**.
  Staging buys zero safety (same image `72affd9`, same database, same real unlabelled mail) and
  adds three distortions, so the round runs where everyone is themselves. Deletes the whole
  staging-hardening branch; T1 shrinks to D5's outcome alone and T7 stops being a blocker.
- [D3 — How does Solution Delivery get a UAT filler and a UAT approver?](tickets/D3-solution-delivery-roles.md):
  **add `(10IT012000, pornthipp@chememan.com)` to `cc dept.xlsx`**. Pornthip fills both
  departments, Laddawan approves both — the only configuration that yields the ask, because
  approver 1 is always the submitter's HR manager. Suchanya keeps her row (fill is additive) but
  must be briefed: her department gets locked read-only while UAT holds it mid-chain. Arthid
  stays out of the chain only as long as Pornthip, never Laddawan, clicks Submit there.
- [D5 — The 1-hour session](tickets/D5-session-lifetime.md): **1 hour for the whole round, applied
  to production 2026-09-06, revert owed.** Verified at apply time that only `timeToExpiration`
  moved — ten other auth fields byte-identical, Easy Auth still returning 401 to anonymous
  callers, staging untouched. It takes effect only for logins made after the change and does not
  slide with activity. The dialog copy still hardcodes "14 ชั่วโมง" and is therefore false while
  the cookie is 1 hour — **jakkaritw accepted that as-is on 2026-09-06, so it is not to be fixed**;
  it self-heals the moment the cookie is reverted. The trade is that the run plan and the pack MUST
  carry it as a known issue (T6), or five testers will each report it.
- **ONE URL, impersonation enabled on production** (2026-09-06, FINAL — supersedes the two-URL
  split first recorded in ledger `uat-two-url-lane-split`): all five testers use the
  **production** URL and sign in as themselves, and jakkaritw gets the impersonation picker at
  `/sit/impersonate` on that same URL. The deciding factor was that switching URLs mid-round is
  where a tester goes wrong, and this round has five real people in it. Applied by setting
  `APP_ENV=uat` and `SIT_IMPERSONATE` (6 targets: pornthipp, laddawank, nipapornt, warapornt,
  arthids, suchanyay) on the production container. jakkaritw ran the command himself because
  Claude's safety classifier refused it twice — correctly, since it removes a deliberate
  production guard. Cost: a third outstanding revert, `prd-appenv-uat-revert-after-uat`.
  Staging keeps its own picker and stays the rehearsal environment, but the round no longer
  needs it. **Note the route is `/sit/impersonate` on both machines** — the `sit` in the path is
  the page's name, not the environment's, and there is no `/prd/impersonate`.
- [D4 — What goes into the UAT pack?](tickets/D4-pack-scope.md): **a business-acceptance subset
  (~30) plus the ~25 new-behaviour cases**. Security, Data Integrity, SQL-judged cases and TC-027
  are dropped; TC-061, TC-057, TC-013, TC-035 and TC-005 are rewritten because they now assert
  behaviour the app no longer has.

## Not yet specified

- **The go-live gate.** The only recorded target (end of August 2026) has passed with nothing
  superseding it. Whether a clean UAT *is* the go-live gate, and what date follows, is not
  askable until the round's shape exists.
- **Defect turnaround inside the window.** How a UAT finding gets triaged, fixed, redeployed and
  re-tested without restarting the round.
- **Whether a second round is needed** after fixes, and who decides.
- **The English-UI / Thai-email mismatch.** `backend/app/notifications.py` was never translated
  (120 Thai lines) while the whole approval UI went English on 2026-09-05. Whether that is
  acceptable at go-live is a product call UAT will surface, not a prerequisite for it.
- **Erratum for the signed spec docs.** `signoff-spec-b-stale-accepted` deliberately left Spec B
  and the special-GL spec describing a 4-row trip table that no longer exists. Whether UAT
  testers reading them need a one-line erratum, or nothing, is unresolved.
- **The uncommitted SIT workbook edit.** `requirement_spec/4_sit/…xlsx` carries an uncommitted
  2026-08-20 modification jakkaritw has not decided about; it is the seed for the UAT pack.

## Out of scope

_(nothing ruled out yet)_
