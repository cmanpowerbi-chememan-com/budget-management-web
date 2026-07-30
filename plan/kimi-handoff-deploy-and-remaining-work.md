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

### 1.1 Gates that are NOT optional
1. **jakkaritw's explicit approval before the production step.** A "yes" to
   staging is not a yes to production. Ask as a direct question and wait.
2. **Staging must pass `A14_RUNBOOK.md` §7 before production is touched.**
3. **Have the rollback line ready BEFORE you deploy**, with the current revision
   name already filled in — not looked up after something breaks. The prd app's
   revision as of today is `cman-budget-web-prd--0000005`; confirm it is still
   the active one, then keep it in front of you (§10).
4. Both container apps pull the SAME image tag. Build once, deploy twice.
5. `07-security-checklist` before production. Today's changes are frontend
   display-only, so this is a short pass — but it is on the never-cut list, so
   run it and record the verdict in the tracker `ai` field.

### 1.2 Three errors in the sequence handed over earlier — fix before running
The version circulated in chat cannot work as written:

| line | problem | fix |
|---|---|---|
| `az acr build ... --image budget:95dfd64` then `--image .../budget-web:95dfd64` | the build tags **`budget`** but both deploys pull **`budget-web`** — the deploy fails on image pull (or silently keeps the old image) | pick ONE repository name and use it in all three commands; confirm which one the live apps already pull (command below) |
| `-g CMAN-BUDGETNGT-WEB-RG` (staging) | looks like a typo — production is `CMAN-BUDGET-MNGT-WEB-RG` | discover staging's real resource group, do not guess |
| `az containerapp update -n cman-budget-web-prd -g ... -- cmanbudgetacr.azurecr.io/...` | `--` instead of `--image`; az will reject or misparse it | `--image cmanbudgetacr.azurecr.io/<repo>:95dfd64` |

Also unverified and worth one command each before you build:
- Does registry `cmanbudgetacr` still exist and is it the registry these apps
  actually pull from? (`CLAUDE.md` records the old Streamlit-era ACR as
  archived, and `A14_RUNBOOK.md` §2 has a step to check exactly this.)
- Does `backend/Dockerfile` build the Next.js frontend inside the image, and
  does the repo-root build context reach `frontend/`? If it expects a
  pre-built `frontend/out`, an `az acr build` from a clean clone ships an image
  WITHOUT today's frontend changes and the deploy will look successful while
  changing nothing visible. Read the Dockerfile and any `.dockerignore` before
  building, and compare against the runbook's own §3 build command.
- Repo trap on record: a production `tsc -b` once swept in `*.test.ts` that
  imported a `docs/` fixture and broke `az acr build` while the local build
  passed. Tests were added to `frontend/src` today — if the image build fails on
  type-checking test files, that is the known cause, not a mystery.

Read-only discovery commands (run these, then write the real sequence):
```bash
az containerapp list -o table                       # both app names + real RGs
az containerapp show -n cman-budget-web-prd -g <rg> --query "properties.template.containers[].image" -o tsv
az containerapp show -n cman-budget-web-prd -g <rg> --query "properties.configuration.registries" -o json
az acr list -o table
az acr repository list --name <registry> -o table    # is the repo budget or budget-web?
```
Do **not** dump the container's full env to a file — query only the fields you
need. A subagent doing that today triggered a credential-materialization
warning; the app keeps its secrets as `secretRef`, so there is no reason to
read them at all.

### 1.3 Deploy is the ONE place where a wrong value is expensive
If any discovery command contradicts something in this document, trust the live
resource and say so in the tracker — this document is a snapshot, the live
resource is the truth.

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
