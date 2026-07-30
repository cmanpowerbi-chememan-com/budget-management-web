# Handoff → Kimi: deploy `95dfd64`, then finish the open items

Written 2026-07-30 by the Claude Code session. Everything below is either
verified today or explicitly marked as unverified. Do not treat any command in
here as safe to run until you have re-checked the values it names — one of the
sequences handed over earlier contained three wrong values (details in §1.2).

Reference docs — read, do not duplicate:
- `docs/deploy/A14_RUNBOOK.md` §3 build · §5 staging · §6 production · §7
  verify-deploy-landed · §8 control-number reconcile · §9 logs · §10 rollback
- `plan/post-deploy-smoke-uat-plan.md` — the 179-item post-deploy test plan
  (Phase 0 pre-flight → Phase 1 smoke → Phase 2 functional → Phase 3 UAT).
  **This is the test script for after the deploy. Do not invent a new one.**
- `tracker/pending.json` via `python tracker/task.py list` — the ledger is the
  only hand-over channel; log before you start and when you finish.

---

## 0. Where things stand right now

- `origin/main` = `95dfd64`, local and remote in sync, both sessions' work
  landed and pushed:
  | commit | what |
  |---|---|
  | `95dfd64` | grid 3-layer grand totals + รวมทั้งปี column (Kimi) |
  | `b07765d` | gitignore the prod Easy Auth cookie + review screenshots |
  | `8618a7f` | tracker: visual sign-off for the no-scope message |
  | `059ebe0` | no-scope users now get an actionable access message |
  | `2a07036` / `24c97ce` | plan items P0-22 / P0-36 / P0-37 / P0-38 |
- **Nothing is deployed.** Production still serves the pre-`95dfd64` image, so
  neither the grid totals nor the new no-scope message is live yet.
- Verified today: `setup/_auth_cookie.tmp.txt` (a LIVE production Easy Auth
  session cookie) is **not** in `origin/main`'s tree or history — it is now
  gitignored. Keep it that way; never `git add -A`.
- Entra login for normal users was broken this morning and is fixed: tenant-wide
  admin consent was granted on both Easy Auth apps. Details + appIds in plan
  item **P0-36**. Every NEW app registration in this tenant will hit the same
  "Need admin approval" wall — relevant if a custom domain gets added.

---

## 1. Deploy `95dfd64` (staging first, then production)

### 1.0 Verified live facts (checked read-only against Azure on 2026-07-30 — use these, do not re-guess)

| thing | verified value |
|---|---|
| Registry | `cmanbudgetacr` (`cmanbudgetacr.azurecr.io`), Basic, in `CMAN-BUDGET-MNGT-WEB-RG` |
| Image repository | **`budget-web` — the ONLY repo in that registry. There is no `budget` repo.** |
| Currently live image (BOTH apps) | `cmanbudgetacr.azurecr.io/budget-web:ace0f00` (pushed 2026-07-28) |
| Tag `95dfd64` | does **not** exist yet — the build has not been run |
| Resource group | `CMAN-BUDGET-MNGT-WEB-RG` for **both** apps — staging is in the SAME RG as production, sharing env `managedEnvironment-CMANBUDGETMNGTW-b33f` |
| App names | `cman-budget-web-stg` (rev `--0000010`, minReplicas **0** → cold start on the first smoke request) · `cman-budget-web-prd` (rev `--0000005`, minReplicas 2) |
| Registry auth | system-assigned managed identity with **AcrPull** on the registry, verified for both apps' principals — no secret to touch, no admin creds in use |
| Your Azure rights | jakkaritw is **Owner + Contributor at subscription scope**, so `az acr build` and `containerapp update` are both covered |
| Env vars / secrets | **already configured** on both apps from the `ace0f00` deploy → this is an image-only update; do NOT re-run the runbook §5/§6 `secret set` / `--set-env-vars` blocks |
| `backend/Dockerfile` | 2-stage and it **does** build the frontend in-image (`node:24-alpine` → `npm ci` → `npm run build:ci` → `COPY --from=frontend-build /fe/out ./static`, `STATIC_DIR=/app/static`). Host `frontend/out` is dockerignored, so a stale local build can never leak in. **Build context must be the repo root.** |
| The old `tsc`-sweeps-tests trap | not a risk here: the root `.dockerignore` excludes `docs/` and `**/*.md`, and the test that imports a `docs/` fixture is excluded from the production build |
| GitHub repo | **PUBLIC** — the unattended `git clone` in Cloud Shell will not prompt for credentials (and this is why the gitignored prod cookie mattered) |

### 1.1 Gates that are NOT optional
1. **jakkaritw's explicit approval before the production step.** A "yes" to
   staging is not a yes to production. Ask as a direct question and wait.
2. **Staging must pass `A14_RUNBOOK.md` §7 before production is touched.**
3. **Have the rollback line ready BEFORE you deploy.** ⚠️ The rollback method
   circulated in chat (`az containerapp revision activate` +
   `ingress ic set --revision-weight`) **CANNOT WORK HERE**: production runs in
   `activeRevisionsMode = Single` with exactly ONE revision
   (`cman-budget-web-prd--0000005`), and in Single mode traffic always follows
   the latest revision, so a revision-weight command is rejected. The working
   rollback is to redeploy the last good tag:
   ```bash
   az containerapp update -n cman-budget-web-prd -g CMAN-BUDGET-MNGT-WEB-RG \
     --image cmanbudgetacr.azurecr.io/budget-web:ace0f00
   ```
   `ace0f00` is the image both apps are running today — keep it in front of you
   before you touch anything.
4. Both container apps pull the SAME image tag. Build once, deploy twice.
5. `07-security-checklist` before production. Today's changes are frontend
   display-only, so this is a short pass — but it is on the never-cut list, so
   run it and record the verdict in the tracker `ai` field.

### 1.2 Four errors in the sequence handed over earlier — all confirmed against live Azure

| line | problem (verified) | fix |
|---|---|---|
| `az acr build ... --image budget:95dfd64` | **BLOCKER, and it fails LATE.** The registry has only the repo `budget-web`. This command would *succeed* and quietly create a second repo `budget`, so the build looks fine — then both `containerapp update` lines pull `budget-web:95dfd64`, which does not exist → image-pull failure, revision stuck unhealthy, after you were told the build passed. It also contradicts Kimi's own deploy lines, `backend/Dockerfile`'s header comment, and runbook §3, which all say `budget-web`. | `--image budget-web:95dfd64` |
| `-g CMAN-BUDGETNGT-WEB-RG` (staging) | **BLOCKER.** That resource group does not exist in the subscription (missing the `M` of `MNGT`). Staging lives in the same RG as production. Fails instantly with `ResourceGroupNotFound`. | `-g CMAN-BUDGET-MNGT-WEB-RG` |
| `az containerapp update -n cman-budget-web-prd -g ... -- cmanbudgetacr.azurecr.io/...` | **BLOCKER.** `--` instead of `--image`; az rejects/misparses it. | `--image cmanbudgetacr.azurecr.io/budget-web:95dfd64` |
| rollback via `revision activate` / `ingress traffic set` | **BLOCKER.** Production is `activeRevisionsMode = Single` with exactly one revision, so traffic always follows the latest revision and a revision-weight command is rejected. | redeploy the previous tag — see §1.1 item 3 (`budget-web:ace0f00`) |

### 1.3 Corrected, paste-ready sequence (Cloud Shell or local `az` — every value verified)

```bash
# --- 0) get the code at the exact commit -------------------------------------
git clone https://github.com/cmanpowerbi-chememan-com/budget-management-web.git
cd budget-management-web
git rev-parse --short HEAD          # MUST print 95dfd64 — stop if it does not

# --- 1) build ONCE, repo root as context, repo name budget-web ---------------
az acr build --registry cmanbudgetacr \
  --image budget-web:95dfd64 \
  --file backend/Dockerfile .
az acr repository show-tags --name cmanbudgetacr --repository budget-web \
  --orderby time_desc -o table      # 95dfd64 must now be listed

# --- 2) STAGING first (runbook forbids skipping this) ------------------------
az containerapp update -n cman-budget-web-stg -g CMAN-BUDGET-MNGT-WEB-RG \
  --image cmanbudgetacr.azurecr.io/budget-web:95dfd64

# >>> STOP. Run A14_RUNBOOK.md §7 against the STAGING FQDN, plus Phase 1 of
#     plan/post-deploy-smoke-uat-plan.md. Staging has minReplicas=0, so the
#     first request is a cold start — do not read a slow first response as a
#     failure. Only continue when every §7 item passes.

# --- 3) PRODUCTION — only after jakkaritw says yes to THIS step --------------
az containerapp update -n cman-budget-web-prd -g CMAN-BUDGET-MNGT-WEB-RG \
  --image cmanbudgetacr.azurecr.io/budget-web:95dfd64

# --- 4) verify prod, then rollback line kept ready --------------------------
# repeat §7 + Phase 1 against the prod FQDN. If it is bad:
az containerapp update -n cman-budget-web-prd -g CMAN-BUDGET-MNGT-WEB-RG \
  --image cmanbudgetacr.azurecr.io/budget-web:ace0f00
```

Notes on verifying: `/health` sits behind Easy Auth, so `curl` alone can only
prove the unauthenticated 401/302 case (§7 step 1) — the rest needs a signed-in
browser tab. Do **not** dump the container's env to a file to "check config";
query only the field you need. A subagent doing that today triggered a
credential-materialization warning, and the app keeps its secrets as
`secretRef` anyway, so there is nothing to read.

If any command's output contradicts this document, trust the live resource, stop,
and record the discrepancy in the tracker — this file is a 2026-07-30 snapshot.

---

## 2. Test AFTER the deploy — use the existing plan, in order

`plan/post-deploy-smoke-uat-plan.md` is the script. Run it against **staging
first, then production**, and tick the boxes in the file with date + verifier as
you go (that file is git-tracked; commit the ticks).

1. **Phase 1 (P1-01 … P1-20), ~20 min, every revision.** This is the regression
   net: unauthenticated 401/302, `/docs` behind login, `/health?deep=1` →
   `{"db":"ok"}`, `/me`, SPA fallback on hard reload, deep-link
   `/?dept=<ฝ่าย>&year=<year>`, security headers, the header-spoof
   impersonation test (**P1-06**, the highest-value security check — a forged
   `x-ms-client-principal-name` must never win), and the error→status contract.
   Note `/health` is behind Easy Auth (`excludedPaths=[]`), so `curl` alone can
   only prove the unauthenticated case; the rest needs a signed-in browser.
2. **Then the Phase 2 items that today's two changes actually touch** — do not
   run all 77 blindly:
   - **P2-E1** no-scope user: the NEW message must render (heading + their own
     email + contact + `cc dept.xlsx`), with no data leak. This is the change
     from `059ebe0`.
   - **P2-E2 / P2-E3 / P2-E7** see-only, fill-scope and dept-picker behaviour —
     prove the new message does NOT appear for users who do have scope.
   - **P2-A2** money integrity: `total_year == SUM(m01..m12)` exactly, in SQL.
     The new grand-total rows and รวมทั้งปี column make this the load-bearing
     check for `95dfd64` — a display total that disagrees with the DB is a
     financial bug, not a cosmetic one.
   - **P2-J3** grid ↔ DB reconcile on a real ฝ่าย (Part 11 method).
   - **P2-K1** cold start and **P2-K5** session expiry mid-edit.
3. **Control-number reconcile (P2-J1)** before/after, same FX. Production's
   transactional tables were empty as of today (0 rows in `approval_status` and
   `pending_budget`), so this is currently a trivial 0 = 0 — say so explicitly
   rather than claiming the reconcile logic was proven.
4. Any prod write you make for verification uses sentinel `fiscal_year = 2099`
   and is cleaned up per **P2-L1**, proven with a 0-row query.

---

## 3. CSS polish — now unblocked, small

`059ebe0` shipped the markup with class hooks `no-scope-empty` and
`no-scope-empty-heading` but **no CSS**: the three rules were written and then
reverted, because `frontend/src/styles/global.css` was your in-flight file at
the time. That file has now landed in `95dfd64`, so the collision is over.

Add (near the existing `.grid-empty` block, ~line 795):
```css
.no-scope-empty p { margin: 0 0 6px; }
.no-scope-empty p:last-child { margin-bottom: 0; }
.no-scope-empty-heading { font-weight: 600; color: var(--ink-2); }
```
Then tick the open checkbox in `.claude/plan.md` under "No-scope empty state
made actionable". Today the three lines render on browser-default paragraph
margins — readable (jakkaritw reviewed screenshots and passed it), just looser
than intended.

Optional, same theme, one line of work now that
`SCOPE_ACCESS_CONTACT_EMAIL` / `SCOPE_ACCESS_SOURCE_FILE` are exported from
`frontend/src/grid/BudgetGrid.tsx`: the ฝ่าย-picker's empty text is still the
bare `ไม่พบฝ่ายในสิทธิ์ของคุณ` (`frontend/src/picker/DeptPicker.tsx`). Ask
jakkaritw before changing user-facing copy he has not seen.

---

## 4. P0-22 — the real open risk, needs a decision then code

Verified against production today: the "approver cannot open their own pending
ฝ่าย" defect from the 2026-07-22 run is **not fixed**. Nipaporn only escapes it
because she is on the `ADMIN_EMAILS` allowlist (the admin overlay
short-circuits the status-view check, and `pending-for-me` filters purely on
the frozen approver's employee code with no See-scope filter). Her own See
scope is 7 cost centers / 5 of 114 ฝ่าย.

So **any non-admin step-2/3 approver** gets "you have items pending" and no way
to open the ฝ่าย. Tracker: `#approver-nonadmin-scope-risk`. Three options,
jakkaritw picks:
(a) widen those approvers' See scope in the scope model ·
(b) let the ฝ่าย-picker include any ฝ่าย where the caller is a frozen approver,
regardless of See scope (recommended) ·
(c) put every step-2/3 approver on the admin allowlist (weakest — grants far
more than approving needs).

This blocks Phase 3 UAT for any pilot ฝ่าย whose approvers are not admins. Do
not start the rollout waves before it is closed.

---

## 5. Decisions still open (ask jakkaritw, do not assume)

1. **P0-38** — `/health` sits behind Easy Auth (`excludedPaths=[]`), so no
   external uptime monitor can probe it. Accept and rely on the platform probe +
   log alerts, or exclude `/health` from auth?
2. **`GL_EDIT_BY_ENABLED`** — ON (hide the ~12 admin-only GLs from
   fillers/approvers) or OFF for go-live? Staging drifted on this in July;
   evidence is the GL count per role, not the env var (plan item P0-08).
3. **Custom domain** `budget.chememan.com` vs the Container App FQDN. Needs DNS
   + cert + an Entra redirect URI **and** a fresh admin consent (P0-36).
   `APP_BASE_URL` and every email deep-link depend on the answer.
4. **`setup/_auth_cookie.tmp.txt`** — a live prod session cookie on disk, used
   by `setup/smoke_prd.py` and `phase2_harness_*.py`. Gitignored now. Delete it
   when the Phase-2 harness work is done, or keep and re-paste when it expires?
5. **`budget-automations.yml`** — split the FX re-persist job into its own
   workflow. As it stands, ticking `execute=true` to "preview" the three
   scheduled jobs performs a REAL FX re-persist, because
   `repersist_perdiem_fx` ignores `DRY_RUN` and is gated only by `--run`
   (plan item P0-28). Recommended: split.
6. **`NOTIFICATIONS_DRY_RUN`** stays `true` until the Phase-2 first-submit
   verification (P2-F2 → P2-F4). Do not flip it as part of this deploy.
7. **Two hardening items surfaced while verifying the deploy path** (neither
   blocks this deploy, both are jakkaritw's call): the GitHub repo
   `cmanpowerbi-chememan-com/budget-management-web` is **public** — fine for
   code, unforgiving about anything secret ever being committed; and the ACR
   `cmanbudgetacr` has `adminUserEnabled = true` while the apps authenticate by
   managed identity, so the admin credential path is unused and could be turned
   off.

---

## 6. Working rules that apply to you in this repo

- `python tracker/task.py list` FIRST, `add --state doing` before you start,
  `done` with commit hashes when finished. Never hand-edit `pending.json`.
  Update sibling tasks whose `ai` field your change makes stale.
- `.claude/plan.md` sync is mandatory in the same commit as the work.
- Commit with explicit paths. Never `git add -A` / `git commit -a` — a second
  session's uncommitted work and the gitignored cookie file both live in this
  tree.
- Windows shell: `python -X utf8`, `encoding="utf-8"` on every `open()`, never
  pipe JSON/SQL through PowerShell, long output → file → read the file.
- Verification screenshots: save to disk, tell jakkaritw the path, do **not**
  read the image into the model. He is the visual reviewer.
- Money rules never get waived: SUM/DISTINCT/currency checks and the
  control-number reconcile apply to every change that touches amounts —
  including a display-only total row.
- Staging and production share the SAME Fabric SQL database. Any query you run
  is a production query; any write is a production write.

## 7. Suggested skills

| when | skill |
|---|---|
| routing this whole handoff | `00-team-workflow` (this is DEPLOY + testing, lean track) |
| before the production step | `10-deploy-checklist`, `07-security-checklist` |
| running the post-deploy test plan | `08-test-checklist`, `35-webapp-testing` |
| the CSS polish + any copy change | `11-code-standards`, `34-frontend-design` |
| if the deploy or a test breaks | `40-diagnose` |
| P0-22 design options | `21-grill-me` with jakkaritw before writing code |

## 8. Definition of done for this handoff

1. `95dfd64` image built once, deployed to staging, §7 verified, then deployed
   to production with jakkaritw's explicit approval and §7 verified again.
2. Phase 1 (P1-01…P1-20) green on production, ticked in
   `plan/post-deploy-smoke-uat-plan.md` with date + verifier, committed.
3. The Phase-2 subset in §2.2 run, including the money invariant P2-A2 and the
   no-scope message P2-E1, with real numbers recorded.
4. CSS polish committed and the `plan.md` checkbox ticked.
5. P0-22 decision captured in the tracker (and implemented if jakkaritw picks
   an option now).
6. Tracker entries closed with commit hashes; anything left open stated
   explicitly rather than dropped.
