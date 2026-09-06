## 1. How Fill / See scope and the approver chain are derived

**Fill scope** — `backend/app/rls.py:35-39` (`_FILL_SQL`):
```sql
SELECT DISTINCT cost_center FROM dbo.cc_filler_map WHERE LOWER(filler_email) = LOWER(?)
```
Pure lookup in `dbo.cc_filler_map`. No manager logic, no admin logic. Applied at `rls.py:132-133`.

**See scope** = union of three sets (`rls.py:139`):
1. Fill (above).
2. Manager-see-add, `rls.py:41-46` (`_MANAGER_SEE_ADD_SQL`): CCs of every filler whose `dbo.v_employee_budget_01.manager_email` = caller. One level only — not transitive.
3. ADR-0029 approver see-overlay, `rls.py:59-92` (`_pending_approval_overlay`): CCs of every department currently `PENDING_*` **on the caller as frozen current approver**, any fiscal_year. Recomputed per call, never cached.

**Role** (`rls.py:141-148`): `admin` if email ∈ `settings.admin_emails_set` (`config.py:225-232` = `ADMIN_EMAILS` ∪ `cmanpowerbi@chememan.com`) → else `filler` if Fill non-empty → else `see_only` → else `none`. Admin is checked at `rls.py:126`, before any scope membership.

**Write gate** — `write_model.py:331-343` (`_ensure_write_scope`): admin bypasses entirely (only `_ensure_cost_center_exists`); a non-admin is refused unless `cost_center in scope.fill_cost_centers`.

**Approver chain** — `approval.py:608-626` (`resolve_chain`), frozen at SUBMIT time onto `budget.approval_status.approver1_empcode`:
- `approval.py:619`: `approver1_empcode = raw_manager or NIPAPORN_EMPCODE`, where `raw_manager` = `resolve_submitter()` → `SELECT employee_code, manager_employee_code FROM dbo.v_employee_budget_01 WHERE LOWER(email)=LOWER(?)` (`approval.py:381-396`).
- Positions 2 and 3 are **compile-time constants**: `NIPAPORN_EMPCODE = "101032"`, `WARAPORN_EMPCODE = "100427"` (`approval.py:59-60`), resolved by `_occupant_for_position` (`approval.py:348-353`).
- Approve/reject authorization is empcode identity only, **no admin bypass**: `approval.py:1049-1060`, `if actor_empcode is None or actor_empcode != current_occupant: raise NotCurrentApproverError`.
- Submit authorization: `approval.py:690`, `is_filler = bool(dept_ccs & set(scope.fill_cost_centers))` — any filler of ≥1 CC of the ฝ่าย may submit the whole ฝ่าย.
- Approval unit = `(department, fiscal_year)`, PK `pk_approval_status(department, fiscal_year)` — verified live. **One record per department per year, first submitter freezes the chain for everyone.**

## 2. Exact department strings + cost centers + fillers (LIVE `dbo.cc_filler_map`, `_load_dttm 2026-09-05 06:30:48.932628`)

Only **two** departments match Data/Analytic/Solution/Delivery:

| department (exact) | cost_center | description | filler_email |
|---|---|---|---|
| `Data & Analytic` | `10IT011300` | Hold | `laddawank@chememan.com` |
| `Data & Analytic` | `10IT011300` | Hold | `pornthipp@chememan.com` |
| `Data & Analytic` | `10IT013000` | Data & Analytic | `laddawank@chememan.com` |
| `Data & Analytic` | `10IT013000` | Data & Analytic | `pornthipp@chememan.com` |
| `Solution Delivery` | `10IT012000` | Solution Delivery | `suchanyay@chememan.com` |

Note the ampersand: `Data & Analytic` (singular "Analytic", `&` not "and"). Both are `division='Digital Technology'`, `c_level='Chief Technology Officer'`. **Solution Delivery has exactly ONE filler and ONE cost center.** Full Digital Technology division = 9 rows / 5 departments (also Application Services `10IT011100`/passakornh, Infrastructure Services `10IT011200`/ittipolu, Digital Technology `10IT010000`+`10IT011000`/karnjanaporns).

Table totals: 466 rows, 213 cost_centers, 73 fillers, 114 departments. `PK_cc_filler_map = (cost_center, filler_email)` — composite.

## 3. The five UAT people

| Person | empcode | in `v_employee_budget_01`? | Fill scope | See scope | ADMIN_EMAILS? | Chain role |
|---|---|---|---|---|---|---|
| Pornthip `pornthipp@` | **101917** | yes, mgr=101431 (Laddawan) | 2 CC (`10IT011300`,`10IT013000`) / `Data & Analytic` | 2 CC (0 manager-add) | **no** | never approver; her submit ⇒ approver1 = Laddawan |
| Laddawan `laddawank@` | **101431** | yes, mgr=**101622 arthids** | 2 CC / `Data & Analytic` | 2 CC (manager-add = Pornthip's same 2) | **no** | approver1 for `Data & Analytic` **only when Pornthip submits** |
| Jakkarit `jakkaritw@` | **none** | **NOT in view; 0 rows in `dbo.employee_master`** | 0 | 0 | **yes** | can never be approver1/2/3; admin-only |
| Nipaporn `nipapornt@` | **101032** | yes, mgr=100427 | 7 CC / 5 depts (`10AC020000, 10FN012000, 10FA000000, 10FA010000, 10CO000000, 10GE000000, 10IB000000`) | 7 + overlay | **yes** | **hardcoded position 2, every department** |
| Waraporn `warapornt@` | **100427** | yes, mgr=101218 piyadad | same 7 CC / 5 depts | 7 (manager-add = Nipaporn's identical 7) + overlay | **yes** | **hardcoded position 3, every department** |

`ADMIN_EMAILS` on **both** stg and prd = `jakkaritw@chememan.com,nipapornt@chememan.com,warapornt@chememan.com` (+ `cmanpowerbi@chememan.com` injected in code). **piyadad@chememan.com is NOT an admin any more** — the project-context.md line listing 4 admins incl. piyadad is stale.

Neither Pornthip nor Laddawan is an admin. Neither can use `admin_view_enabled`, the admin step-override, or the SIT picker.

## 4. Suchanya — found

- `suchanyay@chememan.com`, employee_code **101159**, สุชัญญา ยุปา (Suchanya Yupa), nickname ปาล์ม
- `employee_master`: position `Assistant Department Head - Solution Delivery`, position_code `1165304F01`, org `1165304 / Solution Delivery Section`, job_level `Assistant Department Head (MGR)`, company_code 1000, Primary/Active, Kangkoi Plant
- **manager_employee_code = 101622 = arthids@chememan.com (อาทิตย์ สาหร่าย)** — *not* Laddawan
- `cc_filler_map`: exactly one row — `10IT012000 / Solution Delivery / suchanyay@chememan.com`

**Her role today for Solution Delivery: the sole Filler.** She is *not* approver1 for it (her own submit routes to her manager Arthid). She is not manager of anyone in the filler set. Her Fill = 1 CC, See = 1 CC, role = `filler`, **not** admin, and **not** a SIT_IMPERSONATE target.

Relevant bystander — **Arthid `arthids@chememan.com` / 101622** (`Assistant Vice President - Digital Technology`, 5 "Acting" dept-head rows incl. Solution Delivery and Data & Analytics): Fill = 0, See = 7 CC / 5 depts via manager-add (he manages ittipolu, karnjanaporns, laddawank, passakornh, suchanyay), role = `see_only`, not admin, **but IS a SIT_IMPERSONATE target**.

## 5. KEY QUESTION — Laddawan on Solution Delivery

**Verdict: fill scope is ADDITIVE, so she does not displace Suchanya — but she also CANNOT become approver1 for Solution Delivery, because approver1 is derived from the submitter's HR manager and both women report to the same person (Arthid 101622).**

Evidence, mechanism by mechanism:

**(a) Fill is additive, never exclusive.** PK is `(cost_center, filler_email)`, so a CC accepts unlimited fillers. Proven live: **153 cost centers already have >1 filler** (max 5: `10SC011000`, `10HR011000`, `10HR012000`). `_FILL_SQL` (`rls.py:35`) is a per-email `SELECT DISTINCT` with no exclusivity check anywhere. Adding `(10IT012000, laddawank@chememan.com)` to the master leaves Suchanya's row intact and her rights unchanged. **Parallel actor, not a replacement.**

**(b) Approver1 is NOT configurable.** `approval.py:619` — `approver1_empcode = raw_manager or NIPAPORN_EMPCODE`, `raw_manager` read straight from `dbo.v_employee_budget_01.manager_employee_code`, which is a view over `dbo.employee_master` (C-POP HR sync, view def confirmed: `record_status='active' AND company_code='1000'`, Primary row wins). There is **no** approver-assignment table, no admin UI, no override column. Live manager facts:
- Suchanya 101159 → 101622 arthids
- Laddawan 101431 → 101622 arthids
- Pornthip 101917 → 101431 laddawank

So for `Solution Delivery`:
| submitter | frozen approver1 | then |
|---|---|---|
| Suchanya (today) | **101622 Arthid** | → Nipaporn → Waraporn |
| Laddawan (if given fill) | **101622 Arthid** | → Nipaporn → Waraporn |
| **Pornthip** (if given fill) | **101431 Laddawan** | → Nipaporn → Waraporn |

**Giving Laddawan Fill on Solution Delivery does the opposite of what's wanted** — she becomes a second *filler*, and if she submits, approver1 lands on **Arthid, a real employee who is not in the UAT group**. The only HR-neutral way to make Laddawan approve Solution Delivery is to give **Pornthip** the fill row and have Pornthip submit it. This is already proven by live audit rows: log #665 Laddawan approved at PENDING_APPROVER1 after Pornthip submitted (#662); log #674 **Arthid** rejected at PENDING_APPROVER1 after **Laddawan** submitted (#673).

**(c) The one genuine conflict is the approval unit, not the fill row.** `pk_approval_status(department, fiscal_year)` = ONE record for `Solution Delivery/2027`. Whoever submits first freezes `submitter_empcode` + `approver1_empcode`, and every other filler is then locked out: `evaluate_submit_eligibility` refuses with `invalid_approval_state` unless status is `REJECTED` (`approval.py:693-697`), and ADR-0013's read-only lock (`LOCKED_APPROVAL_STATUSES = PENDING_* ∪ {APPROVED}`) makes **all** of Solution Delivery's rows non-editable for Suchanya while UAT holds it mid-chain. Row-level writes collide too: `pk_pending_budget(cost_center, gl_account, fiscal_year)` — one row per GL per CC per year, so a UAT edit and a Suchanya edit of the same GL are last-write-wins.

**(d) No safe sandbox.** stg and prd both point at `FABRIC_SQL_SERVER=v5o4qez3u4cupase7cogkwvyke-bby6xlm3ncqexly4ozejod2vqe.database.fabric.microsoft.com` / `FABRIC_SQL_DATABASE=fabric_sql_database-a42ef9f3-f190-464a-8d5e-c0d41ef9ce42` — byte-identical, re-verified this session. Both run image `cmanbudgetacr.azurecr.io/budget-web:72affd9` (stg rev `--0000068`, prd rev `--0000033`).

**(e) Mail is real and unlabelled on staging.** stg has `NOTIFICATIONS_DRY_RUN=false` and **no** `NOTIFICATIONS_REDIRECT_ALL_TO`, **no** `NOTIFICATIONS_ENVIRONMENT_LABEL`. `notify_turn` (`notifications.py:436-479`) resolves the current approver's real mailbox. A Solution Delivery submit therefore sends a genuine, unmarked approval request to `arthids@chememan.com` from `cmanpowerbi@chememan.com`, cc `cmanpowerbi@chememan.com`.

**(f) Rollout latency.** `dbo.cc_filler_map` is a daily SharePoint→Fabric sync of `cc dept.xlsx` (observed load stamp `2026-09-05 06:30:48`). A new filler row is not live until the next ~06:30 run, and removing it after UAT is equally delayed. Written budget rows are not reverted by removing the mapping.

## 6. Current FY2027 state for both departments (LIVE)

`dbo.submission_deadline` holds **exactly one row: fiscal_year 2027**, `deadline_date=2026-10-07`, `reminder_date=2026-09-22`, `closing_date=7/closing_month=10/closing_year=2026`. Today = 2026-09-06 → FY2027 is the **only** writable year (`write_model._ensure_year_open_for_write`: any other year = `YEAR_NOT_OPEN`, refused for **everyone including admin**). **UAT is forced onto the live production cycle, 31 days before the real deadline.**

`budget.approval_status` — all rows for the two departments:

| department | FY | status | submitter | submitted_at | approver1 | rejected_by | _updated_at |
|---|---|---|---|---|---|---|---|
| `Data & Analytic` | 2027 | **REJECTED** | 101431 laddawank | 2026-09-05 17:15:26 | 101622 arthids | 101622 | 2026-09-05 18:03:39 (reason `test`) |
| `Solution Delivery` | — | **no row at all — never submitted** | | | | | |

Whole-company FY2027 approval_status = **2 rows only**: `Budgeting and Management` = APPROVED, `Data & Analytic` = REJECTED. **Nothing is mid-approval right now** (zero PENDING_*).

`budget.pending_budget` FY2027:
- `10IT011300` (Data & Analytic): 1 row, `total_year` **1,000.00**, template USER, `_user=pornthipp@chememan.com`, written 2026-09-05 18:25:17
- `10IT013000` (Data & Analytic): 2 rows, **41,040.00** (38,400.00 by pornthipp + 2,640.00 by jakkaritw), template USER, last write 2026-09-05 12:37:57
- **Data & Analytic total = 3 rows / 42,040.00 THB**
- `10IT012000` (Solution Delivery): **0 rows** — the department is currently EMPTY, so `evaluate_submit_eligibility` would refuse a submit today with `department_empty` (`approval.py:688`)
- Company-wide FY2027: **17 rows, 7 cost centers, 6 departments, 147,140.00 THB**

`budget.budget_trip`: 1 row, trip_id **43**, `10IT013000`/2027, traveler 101431 ลัดดาวัลย์, China, country_group 2, 1 day, month 01, side SGA, project `test`, remark `test111`, `_user=jakkaritw@chememan.com`.

`budget.approval_log`: 11 rows for `Data & Analytic` (log_id 662-670, 673, 674), **0 rows for `Solution Delivery`**. Note log #673 records `previous_status=NULL` on a SUBMIT although #670 had left it REJECTED — the `approval_status` row was deleted out-of-band between 2026-08-20 and 2026-09-05 (cleanup, not a code path). `budget.reminder_log` is **empty (0 rows)**.

## 7. Every way to act as someone else on staging

**(A) SIT impersonation — `SIT_IMPERSONATE` + `/sit/impersonate`.** Live stg value:
```
jakkaritw@chememan.com:pornthipp@chememan.com,laddawank@chememan.com,nipapornt@chememan.com,warapornt@chememan.com,arthids@chememan.com
```
5 targets. **Not present on prd at all.** Who may use it — three conjunctive conditions in `auth._sit_guard_ok` (`auth.py:83-112`): `app_env != "production"` (stg is `local`, prd is `production` → dead on prd), caller ∈ `admin_emails_set`, and `SIT_IMPERSONATE` set — **plus** a fourth in `sit_targets_for`/`_apply_sit_impersonation` (`auth.py:185-186`, `auth.py:206-207`): caller must equal the configured `from_email`. Net: **only jakkaritw@chememan.com**. Nipaporn and Waraporn are admins but are refused (they are targets, not the from). Target selected by the httponly/secure/SameSite=Lax `sit_as` cookie, set by `POST /sit/impersonate` with an Origin same-origin check (`sit.py:112-135, 153-182`); GET renders a picker, 404 (never 403) for a refused authenticated caller.
**Audit:** the impersonated identity is what gets written. `budget.approval_log.action_by_email`/`action_by_empcode` and `budget.pending_budget._user` record the TARGET, not jakkaritw — proven by log #674 (`arthids@chememan.com`/101622). The only trace of the real actor is the container-log INFO line `auth: SIT impersonation %s -> %s` (`auth.py:210`).
**Suchanya is NOT a target** — jakkaritw cannot act as her, so the current Solution Delivery filler cannot be simulated.

**(B) `DEV_AUTH_EMAIL` — live on stg = `pornthipp@chememan.com`, with `APP_ENV=local`.** `_resolve_raw_identity` (`auth.py:33-48`) falls back to it whenever the `x-ms-client-principal-name` header is absent. Easy Auth is currently ON (`az containerapp auth show`: `platform.enabled=true`, `unauthenticatedClientAction=RedirectToLoginPage`, clientId `7035aa47-0398-4b71-8411-7fc372e82123`), so no unauthenticated request reaches the app today. **But this is armed, not disarmed**: the instant Easy Auth is toggled off (as it was during earlier test windows), *any anonymous caller on the internet becomes Pornthip*, with her full Fill scope and write rights, and every write records `_user=pornthipp@chememan.com`. SIT impersonation deliberately does **not** apply on this path (`auth.py:62-66`), so there is no additional guard. Not present on prd.

**(C) Admin overlay — `?admin_view_enabled=true`.** Not impersonation: a query parameter on `GET /scope`, `GET /scope/departments`, `GET /budget/*` (`routers/scope.py:19`, `routers/reference.py:107-118`, `routers/budget.py:29-45`) that, when `scope.is_admin` is also true, drops the CC filter and returns the whole company (`read_model.py:508`, `read_model.py:636`). Usable by **jakkaritw, nipapornt, warapornt, cmanpowerbi** on BOTH stg and prd. Separately, admin privilege on the write side (`write_model.py:339`) lets an admin write **any** existing cost center regardless of Fill scope, bypass the past-deadline lock, write `template='ADMIN'` rows, and edit admin-only GLs (12 of 146 in `dbo.gl_group` have `edit_by='admin'`). Admin also gets the ADR-0027 one-step override (`routers/approval.py:341-357`, admin-only, position 1 only, never lands APPROVED), logged as `ACTION_ADMIN_STEP_OVERRIDE` — live precedent: log #669 by nipapornt.
**Audit:** the admin's own real email is recorded — no identity rewrite. Admin does **not** grant approve/reject rights: `_authorize_current_step` (`approval.py:1049-1060`) has no admin branch.

---

### Bottom line for the UAT plan
- **"Laddawan carries Solution Delivery" as an approver is impossible via configuration.** approver1 = the submitter's HR manager. Both Laddawan and Suchanya report to Arthid 101622. Only `Pornthip` submitting Solution Delivery yields Laddawan as approver1 — so the fill row to add is `(10IT012000, pornthipp@chememan.com)`, **not** Laddawan's.
- Adding Laddawan as a Solution Delivery *filler* is harmless to Suchanya's permissions (additive PK) but drags Arthid into the chain if Laddawan ever clicks Submit, and sends him a real unlabelled email.
- The genuine collision is the shared `(department, fiscal_year)` approval record and the shared FY2027 `pending_budget` rows in the **production** database — Solution Delivery FY2027 is currently pristine (0 rows, no approval record), and UAT will be the first thing ever written to it.
- Nipaporn (101032) and Waraporn (100427) are steps 2 and 3 for **both** departments unconditionally — that part needs no configuration.