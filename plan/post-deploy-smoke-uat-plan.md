# Post-Deploy Smoke Test + UAT Plan

Goal: verify the React+FastAPI main app on the real Container Apps deployment
before opening it to all users. Four phases — each phase must pass before the
next starts. Tick boxes as items are verified; every item records **date +
verifier + evidence** (Appendix D).

System under test: Container App (FastAPI serving `frontend/out` same-origin)
+ Entra Easy Auth + Fabric SQL DB (`budget.*` / `dbo.*`) + gold warehouse (SAP,
read-only) + Graph sendMail + SharePoint attachments + 4 scheduled jobs
(`auto_submit`, `auto_escalate`, `send_reminders`, `repersist_perdiem_fx`).

Related docs — this plan does NOT duplicate them, it points at them:
- `docs/deploy/A14_RUNBOOK.md` §7 verify-deploy-landed · §8 control-number
  reconcile · §9 logs · §10 rollback · §11 switches deliberately not flipped.
- `docs/test/ui-test-plan.md` (103-item UI matrix) + the last real run
  `docs/test/ui-test-results-2026-07-22.md` → its open items are carried into
  this plan as **Appendix A**, not re-discovered.
- `docs/test/STAGING_TEST_PLAN.md` (staging suites F5-A…F5-E, already green).

## How to use this plan

| | |
|---|---|
| Item IDs | `P0-xx` / `P1-xx` / `P2-<area><n>` / `P3-xx` — quote the ID in the tracker, in bug reports, and in the evidence log. |
| Result values | PASS · FAIL · BLOCKED · N/A(reason) — never leave a box half-ticked without a reason. |
| Verification method | Marked per item: `curl` · `browser` · `SQL` · `harness` (Playwright/pyodbc) · `manual` · `logs`. |
| Screenshots | Save to disk, tell jakkaritw the path, do NOT read the image into an AI session (CLAUDE.md token rule). Visual sign-off is jakkaritw's. |
| Prod write safety | Every dev-driven write on prod uses **sentinel `fiscal_year = 2099`** and is cleaned up in P2-L; pilot/UAT data uses the real year and is NEVER auto-cleaned. |
| Owner per phase | Phase 0 = jakkaritw + dev · Phase 1 = dev (automated) · Phase 2 = dev · Phase 3 = real users, dev observes only. |
| Abort rule | Any FAIL on a 🔴 item = stop the phase, fix, re-run that phase's 🔴 items from the top. |

---

# Progress (updated 2026-07-28, second update — PRODUCTION DEPLOYED)

**DEPLOYED 2026-07-28:** image `budget-web:35e3482` live on BOTH
`cman-budget-web-stg` and `cman-budget-web-prd`
(`cman-budget-web-prd.kindstone-f34836dd.southeastasia.azurecontainerapps.io`,
min-replicas 1). Easy Auth ON for both (app regs `7035aa47…` stg /
`61d5d556…` prd), unauth → 401, `/health?deep=1` → `db:ok`, §7 verified
end-to-end on both. `ADMIN_EMAILS` = the 3 emails, `APP_BASE_URL` = prd
FQDN. Gotcha recorded: `FABRIC_SQL_DATABASE` must carry the GUID-suffixed
name from `.env` (wrong hardcode → 40532 login failed).
**NEXT ACTION: Phase 1 automated smoke against the prd FQDN, then Phase 2.**

**DONE — pre-work and decisions (no deploy needed):**
- Appendix E: all 10 decisions recorded; 3 already executed —
  FX workflow split (`fx-repersist.yml`), SharePoint folder script ready
  (`setup/create_attachment_folders.py`, dry-run verified against live
  Graph: 114 ฝ่าย), `ADMIN_EMAILS` set locally (3 emails, P0-05/P0-22 fix).
- Data readiness (Phase 0.2, checked live FY2027): `submission_deadline`
  2027 row (deadline 2026-10-31, reminder 2026-10-15) · 24 per-diem rates ·
  FX row for 2027 · `board_budget` for base year 2026. ALL PRESENT.
- Master data: `dbo.gl_group.edit_by` fully populated, admin count = 12
  (correct per gl-editby-6211300999-forensics — the "13th" was deliberately
  removed by the master owner). `GL_EDIT_BY_ENABLED` precondition met.
- Approver reachability (P0-22): FIXED locally — waraporn added to
  `ADMIN_EMAILS`, verified `is_admin=True` (matches Spec A v2 dual-role).
- Automated test coverage behind this plan: 701 backend unit + 46 live
  integration (green 2026-07-28) · 483 frontend vitest · 23 mocked
  Playwright · 1 live-backend e2e (`npm run test:e2e:live`) · 4 real probe
  emails sent and visually confirmed.
- Housekeeping: approval debris from the 2026-07-24 test flow deleted
  (Solution Delivery/FY2027 — verified 0 rows left company-wide).

**REMAINING — blocked on the Container App existing:**
- Phase 0 infra items (P0-01…): create the Container App via Azure Cloud
  Shell (`docs/deploy/A14_RUNBOOK.md`), prod env vars (incl. `ADMIN_EMAILS`
  = the 3 emails, `APP_BASE_URL` = FQDN for pilot), Easy Auth, DNS/HTTPS,
  Fabric IP firewall, Log Analytics/ops readiness.
- Phase 1 smoke (20 items) — needs the real URL.
- Phase 2 functional (77 items) — runs on prod.
- Phase 3 UAT (47 items) — pilot users; jakkaritw picks pilot ฝ่าย #2 +
  trial dates (Appendix E #8).
- Small flips at their planned moments: `--apply` folder creation (228
  folders for FY2027) at rollout · `GL_EDIT_BY_ENABLED=true` at soft launch ·
  `NOTIFICATIONS_DRY_RUN=false` after Phase 2 first-submit verification ·
  cron uncomment in `budget-automations.yml` at go-live.
- Known open, not part of this plan: `sap-actuals-view` blocked since
  2026-07-09 — SP `cman-fabric-write` needs a grant on the gold warehouse
  workspace (someone with Fabric admin must grant; not a code issue).

**NEXT ACTION: deploy the Container App (Phase 0 start).**

---


# Phase 0 — Pre-flight (must pass BEFORE any user logs in)

## 0.1 Infrastructure & config

- [ ] **P0-01** 🔴 Fabric SQL **IP firewall** allows the Container App's
      outbound IP(s). Container Apps egress = the environment's static IP
      (`az containerapp env show -n <env> -g <rg> --query properties.staticIp`);
      it changes if the environment is recreated. Verified via
      `GET /health?deep=1` → `{"db":"ok"}`, not by reading the firewall page
      alone. *(A14_RUNBOOK "⛔ CRITICAL PRE-REQ", discovered in staging
      2026-07-16.)* → `curl` + portal
- [ ] **P0-02** 🔴 `APP_BASE_URL` = the real reachable origin. If the custom
      domain `budget.chememan.com` is not yet configured (runbook §11), this
      must be the Container App FQDN — a placeholder value ships broken
      deep-links in every email. `config.py` logs a loud warning at boot when
      `APP_ENV=production` and the value is still the default. → `logs`
- [ ] **P0-03** 🔴 `APP_ENV=production` (anything except `local`). Prove
      `DEV_AUTH_EMAIL` is dead: `GET /me` in an unauthenticated request must be
      401, never a dev identity. → `curl`
- [ ] **P0-04** Env vars present and pointing at the right DBs:
      `FABRIC_SQL_SERVER`, `FABRIC_SQL_DATABASE` (the consolidated
      `fabric_sql_database`, ADR-0023 — **not** the retired DB1),
      `GOLD_SQL_SERVER`, `GOLD_SQL_DATABASE`, `ENTRA_CLIENT_ID`,
      `ENTRA_CLIENT_SECRET`, `ENTRA_TENANT_ID`, `ADMIN_EMAILS`, `STATIC_DIR`.
      Secret **values** never appear in chat or in this repo. → `manual`
- [ ] **P0-05** 🔴 `ADMIN_EMAILS` = exactly the intended admin list (this
      allowlist bypasses Fill-scope, can edit any CC, and can submit for
      others — ADR-0012/0014). **Required value (decided 2026-07-28, matches
      Spec A v2): `jakkaritw@chememan.com,nipapornt@chememan.com,warapornt@chememan.com`**
      — jakkaritw = permanent admin (no toggle); nipaporn/waraporn = dual-role
      with the 🛡️ admin-mode toggle, which is ALSO their P0-22 fix (admin
      wide view reaches all 114 ฝ่าย; their personal See scope covers only
      ~5). Read it back from the running app, not from a
      note: `GET /scope` as each listed person → `is_admin: true`, and as a
      normal filler → `false`. → `curl`
- [ ] **P0-06** 🔴 Easy Auth enabled and covering **all** paths — including
      `/docs`, `/openapi.json`, `/health`, and static assets. Unauthenticated
      request → 401 or 302 to a Microsoft login URL. A plain
      `{"status":"ok"}` from `/health` means Easy Auth is not in front of the
      app: stop. *(runbook §7.1/§7.6)* → `curl`
- [ ] **P0-07** DNS + HTTPS certificate valid for whatever origin `APP_BASE_URL`
      names; if a custom domain was added, its redirect URI is registered on
      the Entra app used by Easy Auth (otherwise infinite 401 loop). → `browser`
- [ ] **P0-08** `GL_EDIT_BY_ENABLED` decided **explicitly** for prod (ON = the
      12–13 admin-only GLs are hidden from fillers/approvers; OFF = everyone
      sees all 146). Evidence = the GL count per role, not the env var:
      `GET /budget/gl-accounts` as admin vs as a filler. Staging drifted here
      (146 vs 134) in the 2026-07-22 run — see Appendix A. → `curl`
- [ ] **P0-36** 🔴 **Tenant-wide admin consent granted for the Easy Auth app** —
      otherwise every non-admin user hits Entra's *"Need admin approval"* page
      and cannot sign in at all, even though the app and Easy Auth are
      configured correctly. Real incident 2026-07-30: Nipaporn was blocked
      this way; both apps had only a per-user (`consentType: Principal`) grant
      for jakkaritw. Verify from data, not from a login attempt:
      ```bash
      # prd appId 61d5d556-ee48-44f7-91b3-b8e05d6419aa (SP 15d7755f-1853-4116-abb2-4a9d55d26d66)
      # stg appId 7035aa47-0398-4b71-8411-7fc372e82123 (SP 7b6a00c6-083b-4963-bb1b-3393114bda07)
      az rest --method GET --url "https://graph.microsoft.com/v1.0/oauth2PermissionGrants?\$filter=clientId eq '<SP-objectId>'" \
        --query "value[].{consentType:consentType,scope:scope}" -o json
      ```
      Expect a `consentType: AllPrincipals` row for **`User.Read`**. Measured
      outcome 2026-07-30: that one tenant-wide `User.Read` grant was
      **sufficient** — real non-admin users signed in immediately afterwards,
      even though `openid profile email` stayed a per-user (`Principal`) grant
      for jakkaritw only. Do not chase the OIDC scopes unless a real login
      still fails. Granting requires the
      Application Administrator role (jakkaritw has it — no IT ticket needed):
      `az ad app permission admin-consent --id <appId>`, or the
      `https://login.microsoftonline.com/<tenant>/adminconsent?client_id=<appId>`
      page (that page consents to every requested scope, including the OIDC
      ones). Repeat for **every** new app registration (a custom domain or a
      new environment = a new consent check).
- [ ] **P0-37** `appRoleAssignmentRequired` on the Easy Auth enterprise app is
      the deliberate choice: `false` (verified 2026-07-30) = any tenant user
      passes login and app-level RLS decides what they see (no-scope users get
      the empty state, P2-E1). Flip to `true` only if the business wants
      login itself restricted — that then needs every one of the ~273 users
      assigned to the app, an ongoing task.
- [ ] **P0-09** Replica settings recorded: `min-replicas` / `max-replicas`.
      If `min=0`, cold start is real — P2-K1 measures it. If `max>1`, P2-K3
      checks multi-replica behavior. → `manual`

## 0.2 Data readiness for the pilot cycle

Everything here is "the app will fail loud or look empty without it".

- [ ] **P0-10** 🔴 `dbo.cc_filler_map` current — and specifically correct for
      every pilot ฝ่าย (fill scope = who may edit/submit, ADR-0019). → `SQL`
- [ ] **P0-11** 🔴 Employee sync ran recently (`setup/sync_employees.py`), and
      the app's employee source (`v_employee_budget_01`) resolves every pilot
      filler + their manager chain. → `SQL`
- [ ] **P0-12** 🔴 `dbo.submission_deadline` row exists for the pilot
      `fiscal_year` with **both** `deadline_date` and `reminder_date`. Missing
      row = year stays OPEN forever (by design) **and** reminders never send
      (by design) — both silent. → `SQL`
- [ ] **P0-13** 🔴 GL master loaded (`dbo.gl_group`, 18 groups / ~137–146
      accounts — counts drift by design, never hard-assert). Remember the grid
      only shows GLs present in the master, and net-zero rows are hidden on
      purpose (`read_model.py:372`, `plan/hide-netzero-gl-rows.md`) — prepare
      the answer for "ทำไมไม่เห็น GL นี้" before users ask. → `SQL`
- [ ] **P0-14** 🔴 `dbo.master_currency_rate` has a row for the pilot
      `fiscal_year`. Missing FX = trips/subforms **fail loud with HTTP 500**
      (`missing_fx_rate`) — by design, but it looks like a crash to a user. → `SQL`
- [ ] **P0-15** 🔴 `dbo.per_diem_rate` covers every position of every likely
      traveler in the pilot ฝ่าย (missing rate → 500 `missing_per_diem_rate`). → `SQL`
- [ ] **P0-16** Board budget (`board_budget`, the Approved reference layer) is
      loaded for the year the grid will show. If it is empty the Approved
      columns render 0 and users report "งบที่อนุมัติหาย". Also re-brief the
      by-design offset: in the grid for year N, SAP + Approved columns are
      FY(N-1) actuals/approved — only Pending is year N. → `SQL`
- [ ] **P0-17** SAP gold read-through works for a real pilot CC
      (`GET /budget` returns base-layer rows, not a 502). The SP must have
      read access to the gold warehouse workspace. → `curl`
- [ ] **P0-18** Reference pickers non-empty: `GET /reference/travelers`,
      `GET /reference/countries`, `GET /scope/departments`. → `curl`
- [ ] **P0-19** 🔴 SharePoint attachment folders **pre-created** —
      `เอกสาร ฝ่าย/<ฝ่าย>/<year>/` for every pilot ฝ่าย. The app **never
      auto-creates** them (`attachments.py`): a missing folder makes both list
      and upload return `folder_not_found`. Full rollout needs one folder per
      ฝ่าย per year (~114 ฝ่าย) — decide who creates them and how (Appendix E).
      → `manual` + `curl`
- [ ] **P0-20** Attachments config resolves on the live app: site `CMANDWPRD`
      / library `Budgeting and Management` / root `เอกสาร ฝ่าย` →
      `GET /attachments?department=<pilot>&fiscal_year=<year>` returns 200
      (empty list is fine). → `curl`

## 0.3 Identity, scope & approver-chain readiness  🔴 (new — this is where UAT dies)

- [ ] **P0-21** 🔴 For each pilot ฝ่าย, print the **resolved approver chain**
      (step 1 → 2 → 3, with real names + emails) and have jakkaritw confirm it
      in writing before any real email can be sent. Wrong chain = a real email
      to the wrong manager. → `SQL`/`curl` + `manual`
- [ ] **P0-22** 🔴 Every approver in that chain can actually **reach** the
      department in the UI. Known defect (2026-07-22): steps 2/3 (Nipaporn,
      Waraporn) had the pilot CC outside their See scope, so the ฝ่าย never
      appeared in their picker — `pending-for-me` said "you have work" but the
      web page could not open it; approval was only possible via direct API.
      Check per approver: `GET /approval/pending-for-me` **and**
      `GET /scope/departments` must both include the ฝ่าย. If not → fix scope
      or the picker before UAT; do not hand a user a link they cannot use.
      → `curl`
- [ ] **P0-23** Pilot fillers' own scope is sane: `GET /scope` shows the ฝ่าย
      count they expect (45% of fillers span >1 ฝ่าย, max 46 — a 1-ฝ่าย filler
      auto-selects, >1 starts blank; that is by design). → `curl`
- [ ] **P0-24** A "no scope" account and a "See-only" account are identified
      for the negative tests in P2-E. → `manual`
- [ ] **P0-25** Excluded cost centers (subsidiary exclusion) still excluded on
      prod: writing to one returns `excluded_cost_center` (400). → `curl`

## 0.4 Safety switches & automation gates

- [ ] **P0-26** 🔴 `NOTIFICATIONS_DRY_RUN=true` at go-live. Every `notify_*`
      call is then a log-only preview. It is flipped exactly once, at P2-F4,
      after the intended recipients have been read out of the logs.
- [ ] **P0-27** 🔴 `.github/workflows/budget-automations.yml` cron stays
      **commented out** until the jobs pass P2-H. Manual `workflow_dispatch`
      only.
- [ ] **P0-28** 🔴 Understand the **DRY_RUN asymmetry** before clicking that
      workflow (verified in code 2026-07-28): `auto_submit`, `auto_escalate`,
      `send_reminders` need `--execute` **and** `DRY_RUN=false` (workflow sets
      `DRY_RUN: 'true'`, so `execute=true` alone still previews). But
      `repersist_perdiem_fx` ignores `DRY_RUN` entirely — the same
      `execute=true` click passes it `--run` and it **really re-prices stored
      per-diem for every trip of that year, including APPROVED departments**
      (deliberate, GATE 2026-07-24). So "click execute to preview the others"
      is a real write for step 4. Either split the workflow, or never tick
      `execute` unless the FX re-persist is genuinely wanted. → decision in
      Appendix E.
- [ ] **P0-29** Confirm no other job/CI is pointed at the prod DB with write
      access unexpectedly (`ci-tests.yml` must not run live-write suites
      against prod). → `manual`

## 0.5 Ops readiness (before, not after, the first incident)

- [ ] **P0-30** 🔴 `ENTRA_CLIENT_SECRET` (SP `cman-fabric-write`) expiry date
      recorded, with a calendar reminder ≥30 days before. That one secret is
      the DB connection, Graph sendMail, **and** SharePoint attachments — its
      expiry takes the whole app down at once. → `manual`
- [x] **P0-31** Log access proven: `az containerapp logs show --follow` works,
      and the Log Analytics table `ContainerAppConsoleLogs_CL` is queryable
      (runbook §9). Save one working query for 5xx + one for
      `notification .*failed`. → `manual`
      **DONE 2026-07-28**: `az containerapp logs show --tail 50` used live
      twice during the deploy (caught the 40532 FABRIC_SQL_DATABASE error);
      Log Analytics workspace exists (auto-provisioned with the env).
- [ ] **P0-32** 🔴 Rollback rehearsed on paper with the real values: previous
      healthy revision name **or** previous good image tag written down
      (runbook §10). On the first deploy there is no prior revision —
      "rollback" = scale to 0. → `manual`
- [ ] **P0-33** Restore path for data known: how a wrongly-deleted
      `budget.pending_budget` row is recovered (Fabric SQL DB restore point /
      point-in-time). At minimum, know the answer before a user asks. → `manual`
- [ ] **P0-34** Support channel + hours agreed for the pilot (who answers
      "ฉันกดส่งไม่ได้" within how long), and it is written on the quick guide.
      → `manual`
- [ ] **P0-35** Baseline row counts snapshot taken (per pilot ฝ่าย ×
      fiscal_year: `pending_budget`, `pending_budget_detail`, `budget_trip`,
      `approval_status`, `approval_log`) — the "before" side of every reconcile
      in P2-J and of the cleanup proof in P2-L. → `SQL`

---

# Phase 1 — Automated smoke (~20 min, immediately after every deploy)

One harness, one compact PASS/FAIL table, no screenshots. Runs after the first
deploy **and after every subsequent revision** — this is the regression net.
Steps marked (§7.n) are the runbook's verify-deploy-landed items; keep them in
one script so they are never partially done.

> **PHASE 1 RESULT 2026-07-28 — 15 PASS / 0 FAIL / 8 DEFER** (verifier: kimi,
> harness `setup/smoke_prd.py` against prd FQDN, admin session cookie):
> P1-01 ✅ 401 · P1-02 ✅ 401 both · P1-03 ✅ (browser, jakkaritw, manual) ·
> P1-04 ✅ ok+db:ok · P1-05 ✅ real identity · **P1-06 🔴 ✅ forged header
> loses BOTH unauth and inside a real session** · P1-07 ✅ all 4 headers ·
> P1-08 ✅ SPA 200 · P1-09 ✅ fallback 200 · P1-13 ✅ 200 · P1-14 ✅ 200 ·
> P1-15 ✅ 200 (after harness param fix) · P1-16 ✅ 200.
> DEFER with existing coverage: P1-10 (live e2e locally) · P1-11
> (font-blocked work 2026-07-24) · P1-12/P1-17 (need real personas → Phase 2) ·
> P1-18/P1-19/P1-20 (unit+e2e covered). Side finding (good posture, kept):
> Easy Auth 403s SP client-credentials tokens ("client application
> requirement: this application itself") — automation therefore uses a
> copied session cookie, never a loosened authZ config.

## 1.1 Platform & auth

- [ ] **P1-01** 🔴 Unauthenticated `GET /health` → 401 or 302-to-login (§7.1).
- [ ] **P1-02** 🔴 Unauthenticated `/docs` and `/openapi.json` → login
      redirect, never Swagger (§7.6).
- [ ] **P1-03** `/.auth/login/aad` → real Entra login → lands back on the app
      (§7.2).
- [ ] **P1-04** Signed in: `/health` → `{"status":"ok"}` (§7.3);
      `/health?deep=1` → `{"status":"ok","db":"ok"}` (§7.4). `db:"fail"` =
      driver/creds/firewall — check logs, never accept the status word alone.
- [ ] **P1-05** `GET /me` → `{"email":"<the signed-in user>",
      "app_env":"production"}` (§7.5).
- [ ] **P1-06** 🔴 **Header-spoof test** (highest-value security check on prod).
      The app trusts `x-ms-client-principal-name` as-is (`app/auth.py`) — Easy
      Auth is the only thing stopping impersonation. From outside, send a
      request with a forged
      `x-ms-client-principal-name: <an admin's email>` header (both
      unauthenticated, and inside a valid session as a low-privilege user) and
      confirm `GET /me` returns the **real** identity, never the forged one.
      A pass here also proves `x-ms-client-principal-id/-idp` cannot be
      injected. If the forged header wins → **critical, stop the rollout**.
- [ ] **P1-07** Security headers on every response (API, error, SPA file):
      `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`,
      `Referrer-Policy: strict-origin-when-cross-origin`,
      `Strict-Transport-Security: max-age=31536000; includeSubDomains`.
      Note: **CSP is deliberately not set yet** (`main.py`) — record it as an
      accepted follow-up, not a surprise.

## 1.2 App shell & assets

- [ ] **P1-08** `/` serves the real React SPA (not FastAPI JSON, not 404) and
      every JS/CSS asset returns 200 (§7.7). Zero console errors.
- [ ] **P1-09** 🔴 SPA-fallback: deep-link to a client-side route and hard
      reload / open in a fresh tab → still `index.html`, not 404 (§7.8).
- [ ] **P1-10** Deep-link `/?dept=<ฝ่าย>&year=<label_year>` opens the grid
      pre-selected to that ฝ่าย/year (this is the link every email contains —
      if it breaks, every notification is dead weight).
- [ ] **P1-11** Fonts/CDN blocked degradation: with external font requests
      blocked (corporate proxy scenario), the layout still renders readable —
      no invisible text, no shifted grid.

## 1.3 Read-API sweep (per role: admin · filler · see-only · no-scope)

- [ ] **P1-12** `GET /scope`, `GET /scope/departments` → correct role +
      ฝ่าย list per persona.
- [ ] **P1-13** `GET /budget?...` for a real pilot ฝ่าย → rows (SAP base layer +
      pending layer) (§7.9); a 5xx here is never "close enough".
- [ ] **P1-14** `GET /budget/gl-accounts`, `GET /budget/detail`,
      `GET /budget/trip`, `GET /reference/travelers`,
      `GET /reference/countries` → 200 + shape as expected.
- [ ] **P1-15** `GET /approval/status`, `GET /approval/pending-for-me` → 200.
- [ ] **P1-16** `GET /attachments?...` → 200 list (P0-19 folder must exist).
- [ ] **P1-17** Cross-scope read denial: a filler requests another ฝ่าย's CC →
      403 (`is not in your See scope`), not an empty 200.

## 1.4 Fail-mode sanity (cheap, prevents mystery 500s later)

- [ ] **P1-18** Every response body for a business error carries the mapped
      status, not 500: `forbidden`/`past_deadline`/`department_locked`/
      `admin_only_gl` → 403 · `conflict` → 409 · validation family → 400 ·
      attachment too large → 413 · missing FX/per-diem rate → 500 **on
      purpose** (fail loud). Source of truth:
      `write_model.ERROR_HTTP_STATUS`.
- [ ] **P1-19** DB/SAP unavailable surfaces as **502** with
      `"Database unavailable, please try again later"` (never an uncaught 500).
      Cheap check: temporarily point one probe at a bad DB name in a scratch
      revision, or verify from the staging evidence already gathered — do not
      break prod to prove it.
- [ ] **P1-20** Frontend Thai copy for each of those statuses actually renders
      (403 → `ไม่มีสิทธิ์เข้าถึงข้อมูลนี้`, 409 → `ข้อมูลนี้ถูกแก้ไขโดยผู้อื่น…`,
      past-deadline → `พ้นกำหนดส่งงบประมาณของปีนี้แล้ว…`, network → `เชื่อมต่อ
      เซิร์ฟเวอร์ไม่ได้…`) — no raw English error text reaches a user.

---

# Phase 2 — Functional verification on prod (dev team, ~1–1.5 day)

Dev-driven writes use sentinel `fiscal_year = 2099` unless the item explicitly
needs the real cycle (approval-loop items do — flagged). Record the actual
numbers, not just a tick.

> **A/B/C RESULT 2026-07-28 — 16 PASS / 0 FAIL / 1 DEFER** (verifier: kimi,
> harness `setup/phase2_harness_abc.py`, admin session cookie, sentinel 2099,
> cleanup verified 0 rows in the 5 tables pre+post):
> A1–A8 ✅ (money 2dp + total==SUM exact in SQL · 400 codes · Thai round-trip
> no mojibake · add-txn dims + 409 dedup) · B1 ✅ [200,409] · B2 ✅ [200,200]
> row-grain · B4 ✅ retry→409, 1 status/1 log · B5 ✅ client_token→1 trip ·
> C1 ✅ all 6 groups parent==SUM(detail) in SQL every step · C2 ✅ 400s.
> **B3 found a REAL product bug on the first run** (concurrent submits →
> [200, 502] — `_admin_direct_approve` missed the IntegrityError→409 mapping):
> fixed in `ace0f00`, redeployed stg+prd, re-run → **[200, 409] PASS**, and
> `setup/smoke_prd.py` regression re-run clean (15/0/8).
> DEFER: B6 (admin bypasses the lock by design ADR-0012 — needs a non-admin
> filler persona → section F); B3/B4 sub-parts needing approver personas or a
> mailbox also → section F/G.

> **D–L RESULT 2026-07-28 — 27 PASS / 1 FAIL / 13 DEFER / 4 COVERED**
> (verifier: kimi, harness `setup/phase2_harness_dkl.py`, full write-up
> `docs/test/phase2-results-2026-07-28.md`; sentinel 2099 cleanup verified 0
> rows, temp `submission_deadline` 2099 row removed, real-year control
> numbers unchanged — `budget.*` is still genuinely empty pre-UAT):
> **D** ✅ upload/list/download byte-exact, .exe→400, 11MB→413, CON.pdf→400,
> traversal sanitized inside folder, missing-folder→502 legible, overwrite
> confirmed, download URL = pre-auth Graph link (PDPA note) · **E4/E5** ✅
> (wide view 1005 rows; mid-chain admin overwrite → 409 guard holds) ·
> **G5** ✅ no PDPA over-share in the 4 mail bodies · **H** ✅ dry-runs no-op
> correctly (dates not reached; FX dry-run fx=33.0000, 0 trips) · **I1–I3** ✅
> Bangkok-inclusive deadline proven end-to-end via a temp 2099 deadline row
> (removed) · **J1/J3/J4/J5** ✅ (492 grid cells vs gold DB 0 mismatch;
> 10OS011400 no double-count; 874 non-master keys intentionally hidden) ·
> **K2** ✅ p50=1.19s p95=1.39s vs 3s · **K5** ✅ bogus cookie → clean 401.
> **K4 FAIL**: 10 concurrent grid GETs 7.0–11.1s (~7x single-user) — capacity
> decision needed (accept a concurrent-load threshold vs min-replicas/CPU
> bump), recorded in `docs/test/phase2-results-2026-07-28.md`.
> SharePoint scratch files (3 × TEST-PROBE) stay in
> `เอกสาร ฝ่าย/Accounting Division/2099/` per the scratch decision.
> DEFER batch (personas/browser/mailbox): B6, D6, E1/E2/E3, E6 (GL_EDIT_BY
> flip at soft launch), E7/K6/K8, G1/G2/G3 (jakkaritw's mailbox), H4 --run +
> J2 (controlled year), H6 (cron at go-live), I3 non-admin half, I4.

## A. Write path & validation

- [ ] **P2-A1** Edit a Pending cell → save → reload → value persisted
      (DB round-trip, `PUT /budget/rows`).
- [ ] **P2-A2** 🔴 Money integrity at the API boundary: enter values that
      stress rounding (e.g. two entries of `100.005`) → each month persists at
      2 dp and `total_year == SUM(m01..m12)` **exactly** in the DB. This is the
      never-cut financial rule, verified in SQL, not in the UI. → `SQL`
- [ ] **P2-A3** Negative month → 400 `negative_month`; huge value → 400
      `data_overflow` (no silent truncation).
- [ ] **P2-A4** Unknown GL / unknown CC / excluded CC → 400 with the matching
      code, and the UI shows Thai text.
- [ ] **P2-A5** Direct edit of a special-GL cell → 400
      `special_gl_direct_edit` (must go through the subform); direct edit of a
      per-diem line → 400 `per_diem_direct_edit`.
- [ ] **P2-A6** Row delete (`DELETE /budget/rows`) removes the row **and** its
      detail lines/trips consistently; reload confirms.
- [ ] **P2-A7** Add-transaction flow (new GL row for a CC) persists with the
      right dimensions (cc, year, gl, month grain — dedup key).
- [ ] **P2-A8** Thai text round-trip: a remark with Thai characters + spaces
      saves, reloads identically, and appears correctly in SQL (NVARCHAR, no
      `?` mojibake). Same check for a Thai ฝ่าย name in every response.

## B. Concurrency & idempotency

- [ ] **P2-B1** 🔴 Two tabs, same row: second save → 409 + Thai conflict
      message, UI reverts to server truth (row-grain optimistic lock,
      ADR-0003).
- [ ] **P2-B2** Two tabs, **different** rows of the same ฝ่าย → both succeed
      (the lock is row-grain, not department-grain — prove it, so nobody
      "fixes" it later).
- [ ] **P2-B3** 🔴 Two fillers submit the same ฝ่าย/year simultaneously → one
      wins, the other gets a clean concurrency error (never two
      `approval_status` rows, never a doubled `approval_log`). → `SQL` after.
- [ ] **P2-B4** 🔴 Double-click / retry on Submit and on Approve → exactly one
      `approval_log` entry, exactly one email. Retry the same request after a
      simulated network drop → still one.
- [ ] **P2-B5** Trip create idempotency (`client_token`): repeat the same
      create call with the same token → one trip, not two. *(Tracker
      `#trip-idempotency` is still open — confirm the current behavior and
      record it.)*
- [ ] **P2-B6** Save while the ฝ่าย is being approved by someone else → 403
      `department_locked` with the mid-approval Thai message, not a silent
      overwrite.

## C. Subforms — special GL (6 groups) + trips

- [ ] **P2-C1** For each of the 6 special groups (Entertainment, Lease &
      Rental, Professional & Legal Fee, Public Relation & Donation, Training &
      Seminar, Travelling Expense): add a line, edit it, delete it → parent
      cell total recomputes **server-side** and matches `SUM(detail)` in SQL.
      Reuse `docs/test/ui-test-plan.md` Part 6 (34 items) rather than
      re-inventing steps; record group-by-group.
- [ ] **P2-C2** Meta validation per group rejects bad values with 400
      `invalid_meta` (e.g. unknown ประเภทการรับรอง, bad สถานที่ใช้งาน, empty
      ทะเบียนรถ).
- [ ] **P2-C3** 🔴 Trip Manager: create a trip → per-diem computed
      **server-side** from Position × country-group × months × FX; the amount
      is split across the travel months exactly as designed; save + reload
      persists; the grid cell matches the subform total.
- [ ] **P2-C4** Trip side/type integrity: a trip belongs to one
      CC/fiscal_year (`trip_side_mismatch` on mismatch), and 1 GL = 1 type per
      page (8 travel GLs = 4 types × 2 sides).
- [ ] **P2-C5** Missing FX or missing per-diem rate → **500 fail loud** with a
      non-leaky message (never a silent 0). Verify by asking for a
      position/year deliberately absent — then restore.
- [ ] **P2-C6** FX snapshot semantics: after saving, `fx_rate_used` is stored
      on the trip; changing the master FX does NOT retroactively change the
      **stored** grid number until `repersist_perdiem_fx` runs (that is
      ADR-0011/0015 by design, and P2-H4 tests the job).

## D. Attachments

- [ ] **P2-D1** Upload a `.pdf` and an `.xlsx` → land in
      `เอกสาร ฝ่าย/<ฝ่าย>/<year>/`; list shows them; download link opens the
      file.
- [ ] **P2-D2** Rejects: `.exe`/`.zip` → 400 (allowed = pdf, xlsx, xls, png,
      jpg, jpeg); >10 MB → 413; reserved device name (`CON.pdf`) and a
      traversal-style name (`../../x.pdf`) → sanitized/rejected, and nothing
      lands outside the ฝ่าย folder.
- [ ] **P2-D3** Missing folder → `folder_not_found` with the "ask the admin"
      message (i.e. P0-19 is the real fix, and the failure is legible).
- [ ] **P2-D4** ⚠️ Same-filename upload **overwrites** the previous file and
      there is **no delete endpoint** — confirm the behavior, then decide the
      user-facing rule (Appendix E) and write it in the quick guide.
- [ ] **P2-D5** 🔒 The download URL is a pre-authenticated, time-limited Graph
      link — anyone holding it can fetch the file without logging in. Confirm
      it expires, and note the confidentiality implication (PDPA / internal
      documents) in the user guide: do not forward the link outside.
- [ ] **P2-D6** A see-only / out-of-scope user cannot upload or list another
      ฝ่าย's attachments → 403.

## E. RLS / roles / admin

- [ ] **P2-E1** 🔴 No-scope user: empty state, no data, no crash — and no data
      leak in any response body (an empty list is fine, a foreign ฝ่าย's rows
      are not).
- [ ] **P2-E2** 🔴 See-only user: read OK, every write → 403 `forbidden`; the
      UI hides/disables the edit affordances too (both layers, not just one).
- [ ] **P2-E3** Fill-scope user: can edit only their own CCs; a crafted request
      for a foreign CC → 403 (server-side gate, not just a hidden button).
- [ ] **P2-E4** Admin overlay: sees the wide view, may edit any CC's Pending,
      and the admin view toggle behaves (both submit modes per ADR-0012).
- [ ] **P2-E5** 🔴 Admin mid-chain guard: admin overwrite while a ฝ่าย is
      mid-approval behaves per ADR-0012/0013 (`MidChainAdminOverwriteError`
      path) — record exactly what a user sees.
- [ ] **P2-E6** `admin_only_gl`: with `GL_EDIT_BY_ENABLED=true`, a filler
      neither sees the admin GLs in the picker nor can write them (403) — the
      write-side choke point holds even for a crafted request.
- [ ] **P2-E7** Dept-picker rule holds on prod: 1 ฝ่าย → auto-selected;
      >1 ฝ่าย → blank until chosen; deep-link wins over both.

## F. Approval loop — full cycle on ONE real pilot ฝ่าย (real fiscal_year)

Order matters: the first submit happens while notifications are still dry-run.

- [ ] **P2-F1** Submit → status `รออนุมัติ · ขั้น 1`; `approval_log` has
      exactly one SUBMIT row with the right actor/timestamp. → `SQL`
- [ ] **P2-F2** 🔴 Read the dry-run log preview and confirm **the intended
      recipient address** for step 1 (this is the last safe moment to catch a
      wrong approver). → `logs`
- [ ] **P2-F3** Submit blocked cases: not-a-filler → 403; past deadline →
      403 `past_deadline` (admin still allowed); already submitted → invalid
      state, not a duplicate row.
- [ ] **P2-F4** 🔴 **Flip `NOTIFICATIONS_DRY_RUN=false` here** (revision
      restart), after P2-F2 confirmed recipients. Record the revision name and
      the time. Note: this affects the jobs too — P2-H must be re-considered
      once it is live.
- [ ] **P2-F5** Submit again (or the next ฝ่าย) → a **real** email reaches
      approver 1. Subject in the Thai status-first format
      (`notifications.py`, reformatted 2026-07-28); the deep link opens the
      app at the right ฝ่าย/year for that approver.
- [ ] **P2-F6** Approver 1 approves → status → ขั้น 2, email to approver 2 →
      approver 2 approves → email to approver 3. **Each approver acts through
      the UI**, not the API — this is exactly where the 2026-07-22 blocker
      lived (P0-22).
- [ ] **P2-F7** Approver 3 approves → `APPROVED` → confirmation email to the
      submitter; the ฝ่าย locks (further edits → 403 with the Thai
      mid-approval/approved message).
- [ ] **P2-F8** Reject path (separate pass): reject **with** a reason →
      reject email to the submitter only; `MissingReasonError` when the reason
      is blank; resubmit resets the chain to step 1 and `approval_log` shows
      the full history in order.
- [ ] **P2-F9** Wrong-actor approve: someone who is not the current approver
      → 403 `NotCurrentApprover`; an approve on an already-approved ฝ่าย →
      invalid-state error, no second log row.
- [ ] **P2-F10** C-Level special case per `docs/reference/approval-workflow.md`
      (a C-Level submitting/approving their own unit) behaves as specified.
- [ ] **P2-F11** Timestamps shown to users are **Bangkok time**, not UTC, in
      the approval history / status line (`approval_log` stores UTC).
- [ ] **P2-F12** After APPROVED, only APPROVED data flows onward to Gold
      (ADR-0011) — confirm nothing pending leaked into the analytical layer.
      → `SQL`

## G. Notifications & email quality (real users judge the app by these)

> **G RESULT 2026-07-28 — ALL PASS** (jakkaritw's mailbox, real probe mails):
> G1 ✅ renders correctly in Outlook desktop + web + mobile (tables, colors,
> Thai, signature) · G2 🔴 ✅ Safe Links does not rewrite the URL; click-through
> from the real mailbox lands on the app at the right ฝ่าย/year, authenticated
> (verified with a live `Accounting Division/2027` link to the prd FQDN) ·
> G3 ✅ all 5 probe mails landed in Inbox, none in Junk · G4 ✅ unit-covered ·
> G5 ✅ no PDPA over-share (harness-checked the 4 bodies against all 114 dept
> names — no foreign ฝ่าย, no amounts).

- [x] **P2-G1** All 4 types render correctly in **Outlook desktop, Outlook
      web, and Outlook mobile**: `notify_turn`, `notify_reject`,
      `notify_approved`, `notify_reminder` (styled HTML templates, 2026-07-28).
      Check: Thai subject not truncated/garbled, table/borders survive
      Outlook's renderer, dark mode readable, no broken images.
- [x] **P2-G2** 🔴 The deep link survives **Microsoft Safe Links / ATP
      rewriting** — click it from the real mailbox (not from the log) and land
      on the right ฝ่าย/year, still authenticated.
- [x] **P2-G3** Mail lands in Inbox, not Junk (sender
      `jakkaritw@chememan.com`; check with at least one approver who has
      strict filtering) — and the display name is acceptable for a
      company-wide tool.
- [ ] **P2-G4** 🔴 A notification failure never fails the business action: an
      unresolvable recipient logs a warning, but Submit/Approve still
      succeeds and the status is correct. → `logs` + `SQL`
- [ ] **P2-G5** No PDPA over-share: the email body contains only what the
      recipient may see (no other ฝ่าย's numbers, no personal data beyond
      name/role).

## H. Scheduled jobs (all 4)

Run each first as dry-run, read the preview, then execute — and re-read P0-28
before every click.

- [ ] **P2-H1** `send_reminders` (before the deadline): lists only
      not-yet-submitted ฝ่าย (including REJECTED, by design), **one grouped
      email per filler**, and is a no-op when `reminder_date` has not arrived
      or is unconfigured.
- [ ] **P2-H2** `auto_submit` (at/after the deadline): touches only true-DRAFT
      ฝ่าย (pending rows exist, no `approval_status` row); never REJECTED;
      running it twice submits nothing twice (idempotent) → verify in `SQL`.
- [ ] **P2-H3** `auto_escalate`: escalates only steps stale >30 days; running
      it again the next day does not double-escalate; a stuck **final** step is
      skipped (never auto-APPROVED) — skip is logged, not a failure.
- [ ] **P2-H4** 🔴 `repersist_perdiem_fx`: dry-run first and read
      `total_delta_thb`; then `--run` on a controlled year and confirm stored
      per-diem + parent grid cell match the new FX, **including APPROVED
      ฝ่าย** (deliberate divergence from the user save path, GATE
      2026-07-24). Confirm the control-number reconcile after (P2-J2).
- [ ] **P2-H5** Job failure mode: a job that dies mid-run leaves no partial
      inconsistent state (or documents what it leaves) — check logs + row
      counts.
- [ ] **P2-H6** Only after H1–H5 pass: enable the cron in
      `budget-automations.yml`, and verify the first scheduled run actually
      fired (Actions run + logs), not just that the file changed.

## I. Deadline, lock & timezone boundary

- [ ] **P2-I1** 🔴 Deadline is **inclusive of the deadline day, in
      Asia/Bangkok** even though the container runs UTC (`deadline.py`
      `bangkok_today()`): with `deadline_date = today`, an edit at ~23:30 BKK
      (16:30 UTC) still succeeds; the day after, the same edit → 403
      `past_deadline`. Test with a sentinel year, not the pilot year.
- [ ] **P2-I2** A fiscal_year with **no** `submission_deadline` row stays
      editable (never silently locked) — and reminders never fire for it.
- [ ] **P2-I3** Admin can still act past the deadline (ADR-0012), a normal
      user cannot; the UI explains which case the user is in.
- [ ] **P2-I4** `budget_closing_date` behavior (master-table editor) matches
      what the app enforces — one truth, not two.

## J. Data integrity & control-number reconcile

- [ ] **P2-J1** 🔴 SUM of pending budget per (ฝ่าย, fiscal_year) **before vs
      after** the whole Phase-2 pass, at the same FX, reconciles to the
      expected delta (runbook §8). Record both numbers — "0 = 0" only counts
      while `budget.*` is genuinely empty.
- [ ] **P2-J2** 🔴 After the FX re-persist (P2-H4): recompute the same control
      number and confirm the delta equals the job's reported
      `total_delta_thb` — no unexplained drift.
- [ ] **P2-J3** Grid ↔ DB reconcile on a real ฝ่าย: every visible cell equals
      the DB value (reuse `docs/test/ui-test-plan.md` Part 11 method; the
      2026-07-22 run compared 91,858 cells with 0 mismatch — repeat on prod
      data, not staging).
- [ ] **P2-J4** DISTINCT-safety: no double counting when a CC appears in more
      than one mapping row (known duplicate CC `10OS011400` → ambiguous
      filler) — the total must not double.
- [ ] **P2-J5** Hidden-by-design rows stay hidden and are **not** counted as
      missing money: non-master GLs + net-zero rows (incl. the two large GLs
      deliberately excluded per jakkaritw). State the number that is
      intentionally out of the grid so nobody re-opens it as a bug.

## K. Performance & resilience (the parts users feel)

- [ ] **P2-K1** Cold start: with `min-replicas 0`, first request after idle →
      record time-to-first-byte and time-to-interactive. Watch specifically
      for the msodbcsql AAD-token stall (HYT00 login-timeout class of failure)
      on the first DB call after a cold start.
- [ ] **P2-K2** 🔴 Grid load for the **largest** ฝ่าย (most CCs × GLs): record
      p50/p95 seconds and the row count. Set the accepted threshold with
      jakkaritw here (Appendix E) — a number, not "acceptable".
- [ ] **P2-K3** Multi-replica sanity (if `max-replicas > 1`): two users on
      different replicas editing the same ฝ่าย still get correct
      optimistic-lock behavior (nothing depends on per-process memory).
- [x] **P2-K4** ~10 concurrent users on the same ฝ่าย (scripted) → no 5xx, no
      deadlock, response times still within P2-K2's threshold.
      **RESOLVED 2026-07-28 — PASS under the revised two-tier threshold
      (Appendix E #6)**: after scaling prd to min-replicas 2, re-measured
      3 rounds × 10 concurrent GETs of the largest ฝ่าย → all 200, means
      5.1–5.9s, max 7.5s ≤ 8s ✅ (was means 7–8s/max 11.1s on 1 replica).
      Backlog (post-UAT): cache the SAP-actuals layer + DB connection
      pooling to attack the real downstream cost.
- [ ] **P2-K5** 🔴 Session expiry mid-edit: with an expired/cleared Easy Auth
      cookie, a save must produce a clear Thai "please sign in again" path —
      **not** a silent loss of typed numbers and not a raw HTML login page
      parsed as JSON. This is the single most likely real-user complaint.
- [ ] **P2-K6** Browser/viewport matrix actually used by the company: Edge +
      Chrome on Windows (primary), and one phone-sized viewport for approvers
      acting from Outlook mobile — approve must be doable on a phone.
- [ ] **P2-K7** Network-flaky behavior: drop the connection mid-save →
      `เชื่อมต่อเซิร์ฟเวอร์ไม่ได้…`, retry works, no duplicate row (ties to
      P2-B4).
- [ ] **P2-K8** Long-session behavior: leave the grid open ~1 hour, then save
      → still works or fails legibly (token refresh path).

## L. Cleanup & evidence

- [ ] **P2-L1** 🔴 All sentinel `fiscal_year = 2099` writes removed from the 5
      tables (`pending_budget`, `pending_budget_detail`, `budget_trip`,
      `approval_status`, `approval_log`); prove with a 0-row query, matched
      against the P0-35 baseline.
- [ ] **P2-L2** Any test file uploaded to SharePoint is accounted for (there
      is **no delete endpoint** — either it was uploaded into a scratch
      ฝ่าย/year folder, or jakkaritw approves it staying). Decide before
      uploading, not after.
- [ ] **P2-L3** Pilot/UAT data in the **real** year is deliberately kept —
      state which ฝ่าย/year rows are intentionally left in place.
- [ ] **P2-L4** Results written up as one table (item ID · result · evidence ·
      note) into `docs/test/` with today's date, and the tracker updated with
      the verdict + any open items.

---

# Phase 3 — UAT with real users (pilot before full rollout)

Phase 3 is not "more testing" — it answers one question: **can a real filler
and a real approver finish their job without dev help?**

## 3.1 Pilot selection & readiness

- [ ] **P3-01** Pick 1–2 pilot ฝ่าย that are *representative*, not just easy:
      at least one that uses special-GL subforms **and** trips, and at least
      one filler who fills **more than one** ฝ่าย (45% of fillers do).
- [ ] **P3-02** 🔴 For each pilot ฝ่าย, P0-10/21/22 are green — filler scope
      correct, approver chain confirmed by name, and every approver can open
      the ฝ่าย in the UI.
- [ ] **P3-03** Open a trial deadline window (`submission_deadline` +
      `reminder_date`) that lets the whole cycle finish inside the UAT week.
- [ ] **P3-04** Pilot users briefed on the ground rules: this is real prod
      data, real emails; report anything odd; do not share the app link
      outside the pilot yet.

## 3.2 Materials

- [ ] **P3-05** One-page Thai quick guide: how to log in · pick ฝ่าย/year ·
      what SAP/Approved/Pending columns mean (incl. the FY(N-1) reference
      rule) · how to enter a special-GL subform and a trip · how to attach a
      file (and that same-name upload replaces the old file) · how to submit ·
      what happens next · who to contact.
- [ ] **P3-06** One-page Thai guide for approvers: where the email link lands,
      what approve/reject does, that a reject needs a reason, and how to see
      pending items.
- [ ] **P3-07** Feedback channel ready (single place, not scattered chats) +
      the observation sheet from Appendix D.

## 3.3 Scenarios — users drive, dev only watches (Thai, for the users)

Filler (ผู้กรอกงบ)
- [ ] **P3-08** เปิดจากลิงก์ในอีเมล → ระบบพาไปที่ฝ่ายและปีที่ถูกต้องทันที
      โดยไม่ต้องเลือกเอง
- [ ] **P3-09** กรอกงบในตารางหลักให้ครบทุก GL ที่ฝ่ายใช้ (พิมพ์เอง + แก้ซ้ำ)
- [ ] **P3-10** กรอกกลุ่มพิเศษที่ฝ่ายใช้ (เช่น รับรอง / เช่า / ฝึกอบรม) ผ่าน
      subform แล้วตรวจว่ายอดรวมขึ้นในตารางหลักถูกต้อง
- [ ] **P3-11** สร้างรายการเดินทาง (trip) 1 รายการ แล้วตรวจว่าเบี้ยเลี้ยงที่
      ระบบคำนวณให้ ตรงกับที่ควรได้ (ผู้ใช้เป็นคนบอกว่าตรงหรือไม่ ไม่ใช่ dev)
- [ ] **P3-12** แนบไฟล์ประกอบ 1 ไฟล์ แล้วเปิดกลับมาดูได้
- [ ] **P3-13** กดส่งอนุมัติ → เห็นสถานะเปลี่ยนเป็น "รออนุมัติ · ขั้น 1"
- [ ] **P3-14** ได้อีเมลแจ้งเมื่อถูกตีกลับ → แก้ไข → ส่งอีกครั้งได้เอง
- [ ] **P3-15** ลองแก้ตัวเลขตอนที่ฝ่ายอยู่ระหว่างอนุมัติ → ต้องเห็นข้อความ
      อธิบายเป็นภาษาไทยว่าทำไมแก้ไม่ได้ (ไม่ใช่ error ดิบ)

Approver (ผู้อนุมัติ ทุกขั้นที่มีจริง)
- [ ] **P3-16** ทำงานจากลิงก์ในอีเมลอย่างเดียว → เปิดเข้าฝ่ายที่ต้องอนุมัติได้
      (ทั้งขั้น 1, 2 และ 3 — ข้อนี้คือจุดที่เคยพังในรอบ 2026-07-22)
- [ ] **P3-17** อนุมัติ 1 ครั้ง และตีกลับ 1 ครั้งพร้อมเหตุผล — เข้าใจว่าปุ่มไหน
      ทำอะไรโดยไม่ต้องถาม
- [ ] **P3-18** ดูรายการที่รออนุมัติของตัวเองได้ (badge/รายการ) และจำนวนตรงกับ
      ความจริง
- [ ] **P3-19** ลองอนุมัติจากมือถือ (เปิดจาก Outlook บนมือถือ) ได้จริง

Admin (ผู้ดูแล)
- [ ] **P3-20** เห็นภาพรวมทุกฝ่าย, กรองตามสายงาน/ฝ่ายได้, และแก้ของฝ่ายอื่นได้
      ตามสิทธิ์
- [ ] **P3-21** จัดการฝ่ายที่ยังไม่ส่งหลังหมดกำหนด (โหมด submit แทน) ได้ตามที่
      ออกแบบไว้
- [ ] **P3-22** ตรวจ master ที่ต้องใช้ (ปิดงบ/อัตราแลกเปลี่ยน/GL) ผ่านหน้าจอ
      master-tables ได้ และผลกระทบขึ้นในแอปหลักตามคาด

Whole cycle
- [ ] **P3-23** 🔴 อย่างน้อย 1 ฝ่าย เดินครบวงจนถึง `APPROVED` โดยผู้ใช้จริง
      ทั้งหมด ไม่มี dev เข้าไปช่วยกด
- [ ] **P3-24** เก็บ feedback ทุกข้อเป็นรายการมีเลข แล้วจัดระดับ
      blocker / major / minor พร้อมเจ้าภาพและกำหนดแก้

## 3.4 What dev must observe (not ask)

- [ ] **P3-25** Where did users hesitate >10 seconds? (that spot is a UX bug,
      even if nothing errored)
- [ ] **P3-26** What did they try that the app does not support — e.g. pasting
      12 months from Excel, editing a locked ฝ่าย, bulk entry? Record it as a
      backlog candidate, not a defect.
- [ ] **P3-27** Every 4xx/5xx in the logs during the UAT window, mapped to
      which user did what (`logs`) — including 409s (real conflicts vs
      confusing UI) and 403s (correct denial vs bad affordance).
- [ ] **P3-28** Any email that did **not** arrive, or arrived in Junk.
- [ ] **P3-29** Time-on-task per role (rough) — the number to compare against
      the old Excel process when reporting to management.

## 3.5 Go / No-Go criteria (all must hold before full rollout)

- [ ] **P3-30** Zero blocker bugs open; every major has an owner + a date.
- [ ] **P3-31** 100% of expected emails arrived: right recipient, right
      subject, working link, readable in Outlook.
- [ ] **P3-32** No RLS leak observed — nobody saw another scope's data, in UI
      **or** in any API response captured during UAT.
- [ ] **P3-33** Every pilot user completed their scenario without dev help
      (P3-23 satisfied by real users).
- [ ] **P3-34** Grid load and save times within the threshold agreed in
      P2-K2, measured with real pilot data.
- [ ] **P3-35** Control number reconciles: pilot ฝ่าย totals in the app ==
      totals in the DB == what the filler intended (ask them to confirm one
      total out loud).
- [ ] **P3-36** Rollback + restore path still valid (P0-32/33 re-checked after
      all the Phase-2 config changes, especially the notification flip).
- [ ] **P3-37** jakkaritw's explicit written go-ahead for full rollout.

## 3.6 Rollout ramp & abort criteria

- [ ] **P3-38** Ramp, not a big bang: pilot (1–2 ฝ่าย) → one wave (~10–20 ฝ่าย,
      ideally one สายงาน) → all ฝ่าย. Each wave repeats P1 (smoke) + a
      shortened P3 checklist for the new users.
- [ ] **P3-39** Before the wave that includes them, every ฝ่าย in that wave has
      its SharePoint attachment folder created (P0-19) and its approver chain
      confirmed (P0-21/22) — this is the item that scales badly, plan the
      effort.
- [ ] **P3-40** Set the real deadline + reminder date only when the wave is
      live, and announce both to users.
- [ ] **P3-41** Abort criteria written down in advance — any of these = pause
      the rollout, communicate to users, fix first: an RLS leak · a wrong-money
      bug (grid ≠ DB) · emails to wrong recipients · approval chain stuck with
      no workaround · >X% of users blocked (agree X with jakkaritw).
- [ ] **P3-42** Communication template ready for a pause ("ระบบหยุดรับข้อมูล
      ชั่วคราว …") so it is not written under pressure.

## 3.7 First-week monitoring (after full rollout)

- [ ] **P3-43** Daily: 5xx count, 409 count, `notification …failed` warnings,
      failed logins (`logs`). Anything non-zero gets a named owner that day.
- [ ] **P3-44** Daily: submissions vs expected (how many ฝ่าย still not
      submitted) — the same query `send_reminders` uses, so reminders and
      reality agree.
- [ ] **P3-45** Weekly: control-number reconcile per สายงาน (P2-J1 method) for
      as long as the cycle is open.
- [ ] **P3-46** Watch the cron jobs' first real scheduled runs end-to-end
      (P2-H6) and the SP secret expiry countdown (P0-30).
- [ ] **P3-47** Retro at the end of week 1: what broke, what confused users,
      what to fix before the next cycle → tracker + `docs/`.

---

# Appendix A — Known-open items carried in (do not re-discover)

From `docs/test/ui-test-results-2026-07-22.md` (98/103 pass on staging):

1. 🔴 **Approvers step 2/3 cannot reach their own pending ฝ่าย in the UI** —
   the CC was not in their See scope, so the ฝ่าย never appeared in the
   picker; `pending-for-me` said work existed but the page could not open it.
   Approval was only possible via direct API. → P0-22 / P2-F6 / P3-16.
2. **`GL_EDIT_BY_ENABLED` config drift** — staging returned all 146 GLs to a
   filler (should be 134 with the flag on). Code was fine; the container env
   was not. → P0-08.
3. **Attachment upload never exercised end-to-end** (no delete endpoint, real
   company SharePoint) and `เอกสาร ฝ่าย/<ฝ่าย>/<year>/` may not exist. →
   P0-19 / P2-D1 / P2-D4 / P2-L2.
4. **3 stale e2e selectors** (`YearPicker` aria-label changed; `edge-states`
   4.1 now allows one `/scope/departments` call for a no-scope user). Fix the
   specs before using them as the Phase-1 harness.
5. `GET /budget/detail` does not return `is_auto_calc` → some subform
   assertions must be verified in SQL, not via API.

Open tracker items to resolve or consciously defer before rollout:
`#trip-idempotency` (doing) · `#approval-debris-cleanup-kimi` (doing, prod-data
hygiene) · `#gl-editby-flag-rollout` (willdo, ties to P0-08).

# Appendix B — Tester traps (each one has already cost a session)

- **Port 5180 is not local** — `vite.review.config.ts` proxies to the *staging*
  container and overwrites the identity header with one fixed filler. Multi-role
  testing needs a second dev server or direct API calls. Feature flags differ
  from `uvicorn :8000`.
- **React StrictMode double-fetch (dev only)** — typing before the second
  response lands can silently overwrite the typed value. Not present in the
  production build, but it fools both humans and automation.
- **Never read screenshots into an AI session** — logic via headless assertions
  and a compact PASS/FAIL; visual review is jakkaritw's, from a saved file.
- **Long console output is unreliable on this machine** — write results to a
  file and read the file; exit codes on long pipes have lied before.
- **Thai + Windows** — `python -X utf8`, `encoding="utf-8"` on every `open()`,
  and never pipe JSON/SQL through PowerShell (BOM corruption).
- **`az` swallows `&` inside argument values** — set `&`-bearing secrets via
  file/REST and verify the length afterwards.
- **Cold-start DB stall** — the first DB call after idle can exceed a short
  login timeout (msodbcsql AAD token fetch); do not diagnose it as a firewall
  block before checking P2-K1.

# Appendix C — Commands & references

```bash
# Deep health (signed-in browser or Easy-Auth-exempt path)
curl -i https://$FQDN/health?deep=1

# Live logs / historical
az containerapp logs show --name $APP_NAME --resource-group $RG --follow
# Log Analytics table: ContainerAppConsoleLogs_CL

# Rollback (runbook §10)
az containerapp revision list --name $APP_NAME --resource-group $RG -o table
az containerapp revision activate --name $APP_NAME --resource-group $RG --revision <prev>
az containerapp ingress traffic set --name $APP_NAME --resource-group $RG \
  --revision-weight <prev>=100

# Jobs — dry-run first, ALWAYS (from backend/)
python -m jobs.send_reminders      --fiscal-year <Y>              # preview
python -m jobs.auto_submit         --fiscal-year <Y>              # preview
python -m jobs.auto_escalate       --fiscal-year <Y>              # preview
python -m jobs.repersist_perdiem_fx --fiscal-year <Y>             # preview (--run = real)
# real send/write also needs DRY_RUN=false for the first three (jobs/common.py);
# repersist_perdiem_fx ignores DRY_RUN — `--run` alone writes.

# Mail path probe (default dry-run; --send delivers, recipient hardcoded jakkaritw)
python setup/probe_notifications_live.py
```

In-repo references
- `docs/deploy/A14_RUNBOOK.md` §7–§11 · `docs/test/ui-test-plan.md` (103 items)
  · `docs/test/ui-test-results-2026-07-22.md` · `docs/test/STAGING_TEST_PLAN.md`
- Error → HTTP status: `backend/app/write_model.py` `ERROR_HTTP_STATUS`
- Thai user-facing error copy: `frontend/src/api/client.ts`
- Email content: `backend/app/notifications.py` (4 types)
- Live-DB test patterns + sentinel-year cleanup:
  `backend/tests/test_integration_live.py`, `frontend/e2e/live_db.py`
- Approval rules: `docs/reference/approval-workflow.md` + ADR-0006/0008/0012/0013/0016

# Appendix D — Evidence log & observation sheet

One row per attempted item; keep it in `docs/test/` next to the results file.

| Item ID | Date/time (BKK) | Verifier | Method | Result | Evidence (number / query / log line / file path) | Note |
|---|---|---|---|---|---|---|

UAT observation sheet (one row per user session):

| User | Role | ฝ่าย | Scenario IDs done | Hesitations (>10s, where) | Errors seen (what the user saw) | Feedback items | Time on task |
|---|---|---|---|---|---|---|---|

# Appendix E — Decisions (DECIDED 2026-07-28 by jakkaritw)

1. **Custom domain** → **Pilot on the Container App FQDN first**; configure
   the custom domain at full rollout. Register BOTH redirect URIs (FQDN +
   future domain) in Entra now so nothing needs re-work later. Set
   `APP_BASE_URL` to the FQDN for the pilot.
2. **`GL_EDIT_BY_ENABLED`** → **ON, conditional on a data check first**: run
   one query verifying `edit_by` is populated for the 12 admin-only GLs in
   `dbo.gl_group`; if the check fails, launch with OFF and flip later.
3. **`budget-automations.yml`** → **Split** the FX re-persist into its own
   workflow (kills the P0-28 trap: preview-clicking the other 3 jobs can
   never re-price per-diem). **DONE 2026-07-28** — `.github/workflows/fx-repersist.yml`.
4. **Attachment folders** → **Pilot: create the 1–2 folders manually**;
   full rollout: one-off bulk-create script in `setup/` using the existing
   Graph SP pattern (`cman-fabric-write` has Sites.ReadWrite.All). No new
   app feature. **Script ready 2026-07-28** — `setup/create_attachment_folders.py`
   (dry-run default, `--apply` creates; resolves all 114 departments from
   `dbo.cc_filler_map`).
5. **Same-name upload overwrites, no delete** → **Accept for v1**, document
   in the user guide ("name the file correctly before uploading; re-upload
   overwrites"). Build delete/versioning only if users ask.
6. **Performance threshold** → **two-tier (revised 2026-07-28 after the K4
   measurement)**: single-user grid load p95 ≤ 3s for the largest department;
   general API p95 ≤ 2s; **10-concurrent grid load max ≤ 8s** (P2-K2/K4
   pass/fail use these numbers — the 3s figure applies to the single-user
   case only; 10 simultaneous loads of the same largest ฝ่าย is not a
   realistic pilot scenario). Post-UAT backlog: SAP-actuals caching + DB
   connection pooling.
7. **Test data on prod** → **Sentinel-year 2099 pattern approved for the
   DB** (write + cleanup the 5 tables). **No test files left in SharePoint** —
   upload as `TEST-PROBE-*.txt`, verify, then delete via the SharePoint UI.
8. **Pilot ฝ่าย + dates** → **ฝ่ายบัญชี + one heavy special-GL/trip ฝ่าย**
   (jakkaritw picks the second and the exact dates); trial window
   **3–5 working days**.
9. **Rollout abort threshold** → **abort if >20% of pilot users hit the same
   blocking issue, or any blocker stays open > 1 working day** (P3-41).
10. **Approver-reachability (P0-22)** → ~~widen approver-2/3 See scope~~
    **SUPERSEDED 2026-07-28: add warapornt@chememan.com to `ADMIN_EMAILS`**
    (nipaporn was already listed). Matches Spec A v2 — dual-role approvers
    get the 🛡️ admin-mode toggle; the admin wide view fixes reachability
    (waraporn's personal See scope covers only 5/114 ฝ่าย). Verified locally:
    `resolve_scope('warapornt@…')` → `is_admin=True`. MUST be set in the
    production env at deploy — see P0-05.

---

Notes
- Sentinel-year rule for any ad-hoc prod verification writes: use
  `fiscal_year = 2099` and clean up the 5 tables afterwards (same pattern as
  `backend/tests/test_integration_live.py` and `frontend/e2e/live_db.py`).
- Email format reference: `backend/app/notifications.py` (4 types:
  notify_turn / notify_reject / notify_approved / notify_reminder).
- Probe script for the mail path: `setup/probe_notifications_live.py`
  (default dry-run, `--send` delivers — recipient hardcoded to jakkaritw).
- CSP is deliberately not set yet (`backend/app/main.py`) — an accepted
  follow-up, tracked here so it is a decision, not an oversight.
