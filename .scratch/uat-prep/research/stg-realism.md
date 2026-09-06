## 1. Container env — full side-by-side (`az containerapp show … properties.template.containers[0].env`, read 2026-09-06)

Both apps are in RG `CMAN-BUDGET-MNGT-WEB-RG`, env `kindstone-f34836dd`, **same image `cmanbudgetacr.azurecr.io/budget-web:72affd9`** (stg rev `--0000068` created 2026-09-05T17:23Z, prd rev `--0000033` created 2026-09-05T18:35Z, both 100% traffic). Code is therefore IDENTICAL; every difference below is config.

| Var | staging (`cman-budget-web-stg`) | production (`cman-budget-web-prd`) | same? |
|---|---|---|---|
| `APP_ENV` | `local` | `production` | **DIFF** |
| `FABRIC_SQL_SERVER` | `v5o4qez3u4cupase7cogkwvyke-bby6xlm3ncqexly4ozejod2vqe.database.fabric.microsoft.com` | identical string | same |
| `FABRIC_SQL_DATABASE` | `fabric_sql_database-a42ef9f3-f190-464a-8d5e-c0d41ef9ce42` | identical string | same |
| `GOLD_SQL_SERVER` | `v5o4qez3u4cupase7cogkwvyke-2nucmmcmvaiejgjtmxgk5gewea.datawarehouse.fabric.microsoft.com` | identical string | same |
| `GOLD_SQL_DATABASE` | `cman_dw_wh_gold` | `cman_dw_wh_gold` | same |
| `ADMIN_EMAILS` | `jakkaritw@,nipapornt@,warapornt@chememan.com` | identical | same |
| `APP_BASE_URL` | `https://cman-budget-web-stg.kindstone-f34836dd…io` | `https://cman-budget-web-prd…io` | DIFF (expected) |
| `ENTRA_CLIENT_ID` | secretRef `entra-client-id` (value empty in API) | secretRef `entra-client-id` | **values NOT readable** — `az containerapp secret show` was blocked by the permission classifier, so I did **not** verify the two SPs are the same principal |
| `ENTRA_CLIENT_SECRET` | secretRef `entra-client-secret` | same ref name | not verifiable |
| `ENTRA_TENANT_ID` | secretRef `entra-tenant-id` | same ref name | not verifiable |
| `GL_EDIT_BY_ENABLED` | `true` | `true` | same |
| `NOTIFICATIONS_DRY_RUN` | `false` | `false` | same — **both send real mail** |
| `DEV_AUTH_EMAIL` | `pornthipp@chememan.com` | **absent** | **DIFF** |
| `SIT_IMPERSONATE` | `jakkaritw@chememan.com:pornthipp@,laddawank@,nipapornt@,warapornt@,arthids@chememan.com` | **absent** | **DIFF** |

Full-object diff (everything, not just env) returned only: `APP_ENV`, `DEV_AUTH_EMAIL`, `SIT_IMPERSONATE`, `APP_BASE_URL`, `scale.minReplicas` (**stg 0 / prd 2**; maxReplicas 2 both), plus names/FQDN/managed-identity principalId. CPU/mem identical (0.5 vCPU / 1Gi / 2Gi ephemeral). `ipSecurityRestrictions`: stg `[]`, prd `null` → **neither has any IP restriction; both are `external: true` on the public internet.**

NOT set on either container (so the `config.py` default applies to both): `NOTIFICATIONS_ENVIRONMENT_LABEL`, `NOTIFICATIONS_REDIRECT_ALL_TO`, `NOTIFICATIONS_AUDIT_CC_EMAIL`, `NOTIFICATIONS_SENDER_EMAIL`, `REMINDER_INTERVAL_MINUTES`, `REMINDER_*`, `SAP_CACHE_TTL_SECONDS`, `ATTACHMENTS_*`, `STATIC_DIR`(baked in image), `LOG_LEVEL`, `WARMUP_ENABLED`.

`backend/.env` is excluded from the image by `.dockerignore` (`.env`, `**/.env`), so container env vars are the ONLY config source. `backend/Dockerfile:85` bakes `APP_ENV=production` as the image default — staging deliberately overrides it.

## 2. `backend/app/config.py` — every setting, staging vs production effect

| Setting (field) | stg effective | prd effective | Behavioural delta |
|---|---|---|---|
| `app_env` (`config.py:47`) | `local` | `production` | `is_local`→True on stg (`config.py:216-218`). Unlocks (a) the `DEV_AUTH_EMAIL` fallback (`auth.py:45`), (b) the SIT impersonation hard gate (`auth.py:106`). Also leaks into the API: `GET /me` returns `{"app_env":"local"}` (`routers/me.py:15`). No other code reads it — grep found exactly 3 non-config sites. |
| `dev_auth_email` | `pornthipp@chememan.com` | unset | Only consulted when the Easy Auth header is blank (see §5). Currently **inert** while Easy Auth is on — but it is a loaded gun: the instant Easy Auth is disabled or bypassed on stg, every anonymous request on the public internet becomes Pornthip with her full Filler write scope. |
| `sit_impersonate` | 5 targets from `jakkaritw@` | unset | See §4/§5. On stg, jakkaritw's identity is **always** rewritten. |
| `fabric_sql_server` / `_database` | identical to prd | — | Same transactional DB. See §3. |
| `gold_sql_server` / `_database` | identical to prd | — | Same SAP gold warehouse (read-only). |
| `entra_*` | secretRefs, values unread | same names | Unverified, see §1. |
| `admin_emails` → `admin_emails_set` (`config.py:220-229`) | `{jakkaritw, nipapornt, warapornt, cmanpowerbi}` | identical | No delta. Nipaporn + Waraporn carry the admin overlay in BOTH envs — an admin can write any department, in any fiscal-year state, including PAST_DEADLINE/NOT_OPEN. |
| `notifications_dry_run` (`config.py:112`) | **false** | **false** | Staging performs real Graph `sendMail`. No delta — this is the dangerous parity. |
| `notifications_sender_email` (`config.py:120`) | `cmanpowerbi@chememan.com` | same | Staging mail is indistinguishable from production mail by sender. |
| `notifications_environment_label` (`config.py:130`) | **""** | "" | `_mark_test_environment` (`notifications.py:279-313`) returns subject+body untouched when blank → **staging mail carries NO "ทดสอบ" banner and no subject prefix**. Deliberate (2026-08-17 SIT decision), and the reason the SIT guard no longer keys off it. |
| `notifications_redirect_all_to` (`config.py:139`) | **""** | "" | `_apply_redirect` (`notifications.py:316-329`) is a no-op → **staging delivers to the REAL resolved recipient**, no catcher mailbox. |
| `notifications_audit_cc_email` (`config.py:148`) | `cmanpowerbi@chememan.com` | same | Every staging mail also cc's the shared mailbox (`_with_audit_cc`, `notifications.py:261-278`). |
| `reminder_send_delay_seconds` / `_max_sends_per_run` | 2.0 / 150 | same | No delta; jobs-only. |
| `reminder_interval_minutes` (`config.py:154`) | **10080** (default) | 10080 | **Clean** — the SIT compression aid (e.g. `2`) is NOT left set on staging. |
| `app_base_url` | stg FQDN | prd FQDN | Deep links in staging mail point at staging (good); also feeds the `/sit/impersonate` CSRF same-origin check (`routers/sit.py:112-135`). |
| `attachments_site_hostname/site_name/library_name/root_folder` | `chememan.sharepoint.com` / `CMANDWPRD` / `Budgeting and Management` / `เอกสาร ฝ่าย` | identical (defaults) | **Staging uploads/deletes write into the REAL production SharePoint library.** Path guard `_is_inside_attachments_root` (`attachments.py:55-62`) only confines writes to `เอกสาร ฝ่าย/` — it does not separate environments. |
| `gl_edit_by_enabled` | `true` | `true` | No delta (12 admin-only GLs hidden from non-admins in both). |
| `sap_cache_ttl_seconds` | 600 | 600 | Same value, but see perf note: stg has 0–1 replicas vs prd 2, so cache warmth differs. |
| `warmup_enabled` | True | True | Runs per replica start; on stg that means **every cold start after 300s idle** (minReplicas=0). |
| `log_level` | INFO | INFO | Same. |
| `static_dir` | `/app/static` (image ENV) | same | Same. |
| `_warn_if_production_placeholder_base_url` | n/a | not triggered (real URL set) | No delta. |

## 3. Same database? — CONFIRMED, by value not hash

- Both containers carry the byte-identical `FABRIC_SQL_SERVER` **and** `FABRIC_SQL_DATABASE` strings above, and the identical `GOLD_SQL_SERVER` + `GOLD_SQL_DATABASE=cman_dw_wh_gold`.
- I connected to that exact server/database with the SP (ODBC 17, `ActiveDirectoryServicePrincipal`): `SELECT DB_NAME(), SUSER_SNAME()` → `fabric_sql_database-a42ef9f3-f190-464a-8d5e-c0d41ef9ce42`, login `de4b353f-876e-419e-beb7-ae2e21bfab68@13c85daf-…`. One database, one `budget` schema: `approval_log, approval_status, budget_trip, pending_budget, pending_budget_detail, reminder_log`.
- The repo `.env` is **stale/wrong** and must not be used: it points at `…-w4l3zd35yzkuzfgnonsogpi55e.database.fabric.microsoft.com,1433` / `fabric sql db-036a3270-82dd-40f4-aea4-6c27f55cff07` (the retired DB1). Only the container values are real.

**What that means for UAT — this is not theoretical, real production data is already in there:**

`dbo.submission_deadline` holds exactly **one** row: `fiscal_year 2027, deadline_date 2026-10-07`. Today is 2026-09-06 → FY2027 is **OPEN**, every other year is `NOT_OPEN` and refuses non-admin writes (`deadline.py` 3-state gate). So UAT can only be run against the live FY2027 planning cycle.

`budget.pending_budget` (FY2027, 17 rows total) already contains **real, non-test budget entry by real users**:

| department | cost_center | last writer | last write |
|---|---|---|---|
| Budgeting & Cost Accounting | 10AC020000 (6 rows) | nipapornt@ | 2026-08-30 13:26 |
| Budgeting and Management | 10FN012000 (3 rows) | warapornt@ / nipapornt@ | 2026-08-24 03:27 |
| CTO Office | 10BP010000 (2 rows) | nipapornt@ | 2026-08-28 13:51 |
| Accounting / Accounting Division | 10AC012000, 10AC010000 | warapornt@ | 2026-08-21 |
| Data & Analytic | 10IT011300, 10IT013000 (3 rows) | pornthipp@ / jakkaritw@ | 2026-09-05 18:25 |

`budget.approval_status`: `Budgeting and Management / 2027 = APPROVED` (submitted by nipapornt 08-24, approved by warapornt) — **a genuine approved department sitting in the same table UAT will act on**; `Data & Analytic / 2027 = REJECTED` (test, 09-05). `budget.approval_log` runs to `log_id 674`; 3 live trips in `budget_trip` (ids 43/48/50), 9 `pending_budget_detail` rows. `reminder_log` = 0 rows.

## 4. What `APP_ENV=local` unlocks, and the current Easy Auth / ingress state

`backend/app/auth.py` in full — only two branches key off env:

1. **`auth.py:45-46`** — `if settings.is_local and settings.dev_auth_email: return settings.dev_auth_email`. Reached ONLY from `_resolve_raw_identity` and ONLY after `auth.py:42-43` found the header blank. On prd `is_local` is False, so a header-less request 401s (`auth.py:48`).
2. **`auth.py:106`** — `_sit_guard_ok` returns False when `app_env == "production"`. Exact SIT guard, all three must hold: (1) `app_env != production` (`:106`), (2) caller ∈ `admin_emails_set` (`:108`), (3) `sit_impersonate` non-empty (`:110`); **plus** a fourth check outside the guard — caller must equal the configured `from_email` (`auth.py:185-187` in `sit_targets_for`, `auth.py:205-207` in `_apply_sit_impersonation`). So on staging only `jakkaritw@chememan.com` can impersonate; nipapornt/warapornt (also admins) are refused, and `/sit/impersonate` 404s for them.

**Easy Auth is ENABLED on staging.** `az containerapp auth show` for stg: `platform.enabled: true`, `globalValidation.unauthenticatedClientAction: RedirectToLoginPage`, `redirectToProvider: azureactivedirectory`, AAD clientId `7035aa47-0398-4b71-8411-7fc372e82123`, issuer `sts.windows.net/13c85daf-…/v2.0`, allowedAudiences `api://7035aa47-…`. Empirical probe: unauthenticated `GET /` and `GET /me` on staging both return **401** (prd `/me` also 401) — if Easy Auth were off, `/me` would have returned 200 with `pornthipp@chememan.com` via the DEV override. So `DEV_AUTH_EMAIL` is currently inert.

Differences in the auth config itself (stg vs prd): different app registrations (`7035aa47…` vs `61d5d556-ee48-44f7-91b3-b8e05d6419aa`); prd has `defaultAuthorizationPolicy.allowedApplications:[itself]` and `login.cookieExpiration.timeToExpiration: 14:00:00`, staging has **neither** (stg falls back to the platform default session lifetime — I did not verify that default's value); stg `isAutoProvisioned: false`, prd `true`. Neither restricts `allowedPrincipals`, so **any account in tenant 13c85daf can sign in to staging.**

**No IP/ingress restriction on either app** (`ipSecurityRestrictions` empty/null, `external: true`). There is no network fence around staging.

## 5. What a real UAT tester logging in with their own Entra account gets

**They get their own identity — `DEV_AUTH_EMAIL` does NOT override it.** Deciding line: **`backend/app/auth.py:62-64`** —

```python
if x_ms_client_principal_name and x_ms_client_principal_name.strip():
    email = x_ms_client_principal_name.strip()
    return _apply_sit_impersonation(email, settings, cookie_target=sit_as)
```

The header wins unconditionally; `dev_auth_email` is only reachable at `auth.py:45` after the header tested blank at `auth.py:42`. Easy Auth always injects `x-ms-client-principal-name` (§4), so Pornthip, Laddawan, Nipaporn and Waraporn each see themselves.

**The one exception is jakkaritw.** Because `SIT_IMPERSONATE`'s `from_email` is `jakkaritw@chememan.com` and all three guard conditions hold on staging, `_apply_sit_impersonation` rewrites him on **every** request. With no `sit_as` cookie, `_select_sit_target` (`auth.py:137-154`) returns `targets[0]` = **`pornthipp@chememan.com`**. The "หยุดสวมสิทธิ์ (clear)" button (`routers/sit.py:172-174`) only deletes the cookie — the next request falls back to `targets[0]` again. **On staging today, jakkaritw can never act as jakkaritw**; he is Pornthip by default and one of {pornthipp, laddawank, nipapornt, warapornt, arthids} at best. On production he is himself, with the admin overlay (he has NO row in `dbo.v_employee_budget_01` and NO `dbo.cc_filler_map` rows — verified — so his only production power is the `ADMIN_EMAILS` overlay).

Scope facts for the UAT cast (live `dbo.cc_filler_map` / `dbo.v_employee_budget_01`):

- `pornthipp@` (101917) — Filler on 10IT011300 + 10IT013000, dept **Data & Analytic**; manager = `laddawank@`.
- `laddawank@` (101431) — Filler on the same 2 CCs (Data & Analytic); manager = `arthids@` → **arthids is Approver-1 for Data & Analytic and is NOT a UAT attendee**.
- `nipapornt@` (101032) — Filler on 7 CCs incl. Budgeting & Cost Accounting, CFO, COO; admin; fixed step-2 approver.
- `warapornt@` (100427) — Filler on the same 7 CCs; admin; fixed step-3 approver.
- **Solution Delivery has exactly ONE filler: `suchanyay@chememan.com` (CC 10IT012000)** — neither Pornthip nor Laddawan has any scope there, and `suchanyay@` is not in the `SIT_IMPERSONATE` target list. Giving them that department requires either an env edit (add her as a SIT target) or an edit to `cc dept.xlsx` on SharePoint — which is the **shared production master** and syncs into the shared DB.

## 6. Every side effect a UAT click can have on real production data / real colleagues

1. **DB writes land in production.** Grid saves → `budget.pending_budget` / `pending_budget_detail`; trips → `budget.budget_trip`; submit/approve/reject/admin-override → `budget.approval_status` + `budget.approval_log` (append-only, ids are consumed permanently). Same rows real users are filling for FY2027 right now. Optimistic row-grain locking (ADR-0003) means a UAT save can also clobber/conflict with a real concurrent edit.
2. **Real, unlabelled emails to real people.** `notifications_dry_run=false`, label blank, redirect blank → `send_mail` (`notifications.py:330-369`) does a live Graph `POST /users/cmanpowerbi@chememan.com/sendMail` to the recipient the app resolved from `dbo.v_employee_budget_01`, cc `cmanpowerbi@`. A UAT submit of Data & Analytic mails **arthids@** a genuine-looking approval request; final-approve/reject mails cc the frozen approver-1; a Solution Delivery test would mail suchanyay's chain. Nothing in the subject, body, or sender distinguishes it from production — the only tell is the deep link's staging FQDN.
3. **SharePoint writes to the production library.** `POST /attachments/upload` and `DELETE /attachments` operate on `chememan.sharepoint.com / CMANDWPRD / "Budgeting and Management" / เอกสาร ฝ่าย/<ฝ่าย>/<year>/` — the real 114-department folder tree. Delete is real and permanent within that path.
4. **Master-data edits made to enable UAT propagate to production.** `cc dept.xlsx` / the deadline workbook / country / per-diem masters live on SharePoint and are synced daily (06:31, notebook `NB_budget_masters_sync` in workspace `cman-dw-ws`, outside this repo) into the `dbo.*` tables **both** apps read. Adding Pornthip/Laddawan to Solution Delivery, or adding a sandbox `submission_deadline` year, changes production permissions/behaviour within a day.
5. **Scheduled jobs.** Only ONE cron exists in this repo: `.github/workflows/budget-automations.yml`, `cron: "0 20 * * *"` = **03:00 Bangkok daily**, running `jobs.auto_submit` then `jobs.send_reminders` for `AUTOMATION_FISCAL_YEAR=2027`. It is **dry-run on three independent gates**: no `--execute` on a scheduled run, `DRY_RUN: 'true'` in the workflow env, and `jobs/common.py:46-50` requires both. Last 5 nightly runs all `success` (33924245764 on 2026-09-04, …). So **it will fire during the UAT window but write nothing and send nothing** — unless someone runs it via `workflow_dispatch` with `execute=true` AND flips `DRY_RUN`. Note the repo variable `APP_BASE_URL` still points at the **staging** FQDN, so any real reminder round would mail production users staging links. `fx-repersist.yml` is `workflow_dispatch`-only (no schedule) and re-prices per-diem THB for real with `execute=true`. `ci-tests.yml` is push/PR only. No `sync_employees` workflow exists any more; no in-process scheduler/APScheduler exists in `backend/app` (grep clean) — `backend/jobs/{auto_submit,send_reminders,repersist_perdiem_fx}.py` run only from Actions/CLI.
6. **Audit-trail contamination.** With `SIT_IMPERSONATE`, actions are recorded as the impersonated person. Already in the live log: `approval_log #674 — REJECT, Data & Analytic 2027, action_by_email=arthids@chememan.com, 2026-09-05 18:03, comment "test"` — arthids almost certainly never touched it. There is no column recording the real actor.
7. **Perf numbers are not comparable.** stg `minReplicas=0` (currently 0 replicas, 300s cooldown) → the first UAT click of the day pays a full cold start (container boot + ODBC + startup warmup thread) that production (2 always-on replicas) never pays; per-replica SAP TTL cache (600s) is also cold. Any "the app is slow" UAT finding is untrustworthy, in both directions.
8. **Session lifetime differs** (stg = platform default, prd = 14h explicit) → any session-expiry finding from UAT does not reflect production timing.
9. **Different staging app registration** (`7035aa47…`) → a tester who has never signed into the staging app may hit a tenant-consent prompt that does not exist on prd (the "Need admin approval" class of failure). Consent state not verifiable from here — flagged, unverified.

## 7. Blast radius ranking + mitigations that exist TODAY (no new code)

| # | Risk | Radius | Mitigations available now |
|---|---|---|---|
| 1 | **UAT writes into live FY2027 production budget/approval rows** (incl. the APPROVED `Budgeting and Management` dept) | Irreversible-ish corruption of the only open planning cycle; `approval_log` ids permanently consumed | (a) Take a pre-UAT SELECT-export snapshot of all 6 `budget.*` tables + a written restore procedure (SP has write access); (b) confine UAT to CCs `10IT011300 / 10IT013000 / 10IT012000` and forbid admin-mode use by nipapornt/warapornt (they can write ANY department in ANY state); (c) open a **sandbox fiscal year** by adding one row to the deadline master (the 2097/2099 sentinel precedent) so testers type into e.g. FY2099 instead of FY2027 — caveat: that year then also appears in production for everyone, and the row arrives via the daily SharePoint sync |
| 2 | **Real unlabelled approval emails to real colleagues** (arthids, suchanyay's chain, anyone the app resolves) | Non-attendees act on a fake request; reputational | Env-only change on the staging container: set `NOTIFICATIONS_REDIRECT_ALL_TO=<catcher mailbox>` (all mail to one box, all cc dropped, banner prints the real To/cc) and/or `NOTIFICATIONS_ENVIRONMENT_LABEL="UAT ทดสอบ"` (red banner + subject prefix); or `NOTIFICATIONS_DRY_RUN=true` to kill sending entirely (cost: the email test cases become unverifiable). All three are existing code paths, config only. Note the label was deliberately removed for SIT — re-adding it changes what UAT is testing |
| 3 | **`SIT_IMPERSONATE` contaminates the audit trail and misrepresents who can do what** — and blocks jakkaritw from ever being himself on staging | Every UAT verdict about identity/permissions is suspect; `#674` already shows a wrong actor | Remove `SIT_IMPERSONATE` from the staging container for the UAT window → every attendee logs in with their own Entra account and the identity path becomes production-identical (`app_env=local` alone unlocks nothing else once `DEV_AUTH_EMAIL` is also removed). Alternative if kept: forbid its use during UAT and reconcile `approval_log` afterwards against the attendee list |
| 4 | **`DEV_AUTH_EMAIL=pornthipp@` + no IP restriction + public ingress** | Latent: if Easy Auth is ever toggled off "for convenience", the whole internet becomes a Filler who can write real FY2027 data | Remove `DEV_AUTH_EMAIL` from the staging container (it is inert today and buys nothing while Easy Auth is on); optionally add an `ipSecurityRestrictions` allowlist to staging for the UAT window |
| 5 | **Attachment upload/delete hits the production SharePoint library** | Test files visible to real departments; a delete inside `เอกสาร ฝ่าย/` is permanent | Point staging at a different folder via the existing settings, e.g. `ATTACHMENTS_ROOT_FOLDER=<a UAT folder>` (config-only; verify the folder-creation path works before relying on it), or skip attachment cases, or clean up afterwards through the app's own DELETE route |
| 6 | **Master edits made to give testers 2 departments each leak into production** (Solution Delivery has only `suchanyay@` as filler) | Real production see/fill grants after the next 06:31 sync | Prefer adding `suchanyay@chememan.com` to `SIT_IMPERSONATE` (staging-env-only, invisible to prd) over editing `cc dept.xlsx`; if the master must change, record the pre-change SharePoint version and revert immediately after UAT |
| 7 | **Nightly automations fire at 03:00 BKK during the UAT window** | Currently zero writes/sends (3 gates) — but one `workflow_dispatch` with `execute=true` would mail production users staging-linked reminders | Change nothing; explicitly bar manual dispatch of `budget-automations.yml` and `fx-repersist.yml` during the UAT window; if reminders must be tested, do it via the app, not the workflow |
| 8 | **Cold start / 0-vs-2 replicas and shorter session cookie** | Perf and session-expiry findings are not transferable to prd | Warm staging with a request before each session, or raise stg `minReplicas` to 2 for the UAT day (`az containerapp update` — a mutating command I did not run); otherwise mark all perf/timeout findings as "not evidence about production" |

**Bottom line on trustworthiness:** the code is identical (`72affd9` on both) and the data plane is identical (one Fabric SQL DB, one gold warehouse), so functional UAT results transfer to production *except* where identity is faked. The three differences that make a UAT verdict untrustworthy are `SIT_IMPERSONATE` (wrong actor recorded, jakkaritw cannot be himself), `DEV_AUTH_EMAIL` (silent whole-app identity override if Easy Auth ever drops), and `minReplicas=0` (perf). The three that make UAT *unsafe* rather than untrustworthy are the shared FY2027 production rows, the real unlabelled email path, and the production SharePoint library.