# A14 — First Production Deploy Runbook (Budget Management Web)

Paste-ready Azure Cloud Shell sequence. The dev machine has **no admin rights,
no az CLI, no Docker** — every command below runs in **Azure Cloud Shell**
(portal.azure.com → Cloud Shell icon, Bash mode). Nothing here is executed by
Claude Code; this is a script for **jakkaritw** to run by hand, step by step,
verifying the output at each checkpoint before moving on.

No secret **values** appear anywhere in this file — only variable/secret
**names**. Fill in real values only inside Cloud Shell, never in chat or in
this repo.

---

## 0. สรุปสำหรับอนุมัติ (deploy plan + rollback, ภาษาไทย)

**กำลังจะทำอะไร:** ขึ้นระบบ Budget Management Web เวอร์ชันแรกสู่ production
จริง — เป็น container ตัวเดียวที่รวม backend (FastAPI, ทำหน้าที่ตอบ API และ
คำนวณ RLS/approval) กับหน้าเว็บ (React) ไว้ด้วยกัน รันบน Azure Container Apps
ต่อจาก Fabric SQL Database ที่มีอยู่แล้ว (`fabric_sql_database`) ตอนนี้ตาราง
`budget.*` ยังว่างเปล่า (ยังไม่มีใครกรอกงบจริง) ความเสี่ยงจากข้อมูลจึงต่ำมาก

**ผลกระทบ:** ผู้ใช้ยังเข้าไม่ได้จนกว่าจะได้ URL จริง (ยังไม่ผูกโดเมน
`budget.chememan.com` — ทำเป็นขั้นถัดไป) การ deploy รอบนี้คือการเปิดระบบขึ้น
ครั้งแรก ยังไม่กระทบผู้ใช้งานคนอื่นเพราะไม่มีใครใช้อยู่ก่อน

**ก่อนเริ่ม (บังคับ):**
1. ผ่านการตรวจสอบความปลอดภัย (07-security-checklist) แล้ว — ไม่มีข้อ FAIL
   ระดับวิกฤต (secrets / injection / auth)
2. **jakkaritw อนุมัติแผนนี้อย่างชัดเจน** ก่อนรันคำสั่งใน production
   (ขั้น staging รันได้ก่อนโดยไม่ต้องรออนุมัติ เพราะเป็นแค่การทดสอบ)

**ถ้าพัง จะทำอย่างไร (rollback):** ระบบมี "revision" เก่าเก็บไว้ในตัว
Container App เอง — สั่ง activate revision ก่อนหน้ากลับมาได้ภายในไม่กี่วินาที
ไม่ต้อง build ใหม่ (รายละเอียดคำสั่งอยู่ส่วนที่ 8) ถ้าเป็นการ deploy ครั้งแรก
(ยังไม่เคยมี revision ก่อนหน้า) การ "rollback" คือปิดระบบชั่วคราว (scale เป็น 0)
ระหว่างแก้ไข แล้ว deploy ใหม่

**ตัวอย่างเหตุการณ์จริงที่อาจเกิด:** ถ้า Easy Auth (ระบบล็อกอินของ Container
App) ตั้งค่าไม่ครบ หน้า `/health` หรือ `/docs` อาจเปิดดูได้โดยไม่ต้องล็อกอิน —
นี่คือช่องโหว่ ต้องตรวจพิสูจน์ด้วยขั้นตอนที่ 6 ก่อนถือว่า deploy สำเร็จ

---

## 1. Pre-flight gates (do not skip)

- [ ] 07-security-checklist run on this build — no critical (secrets/
      injection/auth) FAIL
- [ ] Backend test suite green (`cd backend && pytest`)
- [x] `backend/requirements.txt` pinned (done 2026-07-16: all 7 direct deps
      exact-pinned, incl. the A13.5 CVE bumps fastapi 0.139.0 /
      python-multipart 0.0.32; keep it pinned)
- [ ] jakkaritw has read section 0 and approved this plan
- [ ] Staging deploy (section 5) completed and smoke-tested BEFORE production
      (section 6) — never skip staging without jakkaritw's explicit logged
      acceptance

---

## ⛔ CRITICAL PRE-REQ (discovered in staging 2026-07-16): Fabric SQL IP firewall

The staging deploy proved the image runs, but **every DB call timed out** (`pyodbc HYT00
Login timeout`). Root cause: the Fabric tenant has `ConfigureWorkspaceLevelIPFirewallRules`
enabled, and the Container Apps environment egresses from ONE static public IP that is not on
the workspace allow-list. The identical connection string works from the corporate network,
so this is a **network allow-list gap, not a code/credential problem**.

**Action (Fabric/DATA workspace admin, before the app is useful):** in the Fabric portal →
workspace `budget_management_web` → Settings → **Network security / IP firewall** → add the
Container Apps environment's outbound static IP. For the existing env
`managedEnvironment-CMANBUDGETMNGTW-b33f` that IP is **`40.119.206.243`**
(`az containerapp env show -n <env> -g <rg> --query properties.staticIp`). Because staging and
production share this same environment, **allow-listing this one IP unblocks BOTH**. The same
must be done for the GOLD warehouse workspace (`cman_dw_wh_gold`) if it enforces the same
firewall. Re-test with `curl https://<fqdn>/health?deep=1` → expect `{"db":"ok"}`.

## Confirmed live resource names (staging, 2026-07-16 — no more discovery guessing)

| Resource | Confirmed value |
|---|---|
| Resource group | `CMAN-BUDGET-MNGT-WEB-RG` (southeastasia) |
| ACR | `cmanbudgetacr` (reused) |
| Container Apps env | `managedEnvironment-CMANBUDGETMNGTW-b33f` (reused; vnet=null; static egress IP `40.119.206.243`) |
| Staging app | `cman-budget-web-stg` → `cman-budget-web-stg.kindstone-f34836dd.southeastasia.azurecontainerapps.io` |
| Image | `cmanbudgetacr.azurecr.io/budget-web:<git-sha>` |

## 2. Resource discovery (confirm before creating anything new)

Run these first — reuse whatever already exists, only create what's missing.
(The table above is what staging actually found; the commands below are how to re-confirm.)

```bash
# Confirm subscription/tenant context
az account show --output table

# Find the resource group that already hosts the master-tables Static Web App
# (CLAUDE.md: prod URL witty-meadow-01107f500.7.azurestaticapps.net)
az staticwebapp list --output table
# -> note the "resourceGroup" and "location" columns for that app.
RG=<resource-group-from-above>
LOCATION=<location-from-above>   # expected: southeastasia — confirm, don't assume

# Check whether the old ACR still exists (CLAUDE.md: archived Streamlit
# deploy used ACR "cmanbudgetacr")
az acr list --output table
```

**Decision:**
- If `cmanbudgetacr` exists → reuse it (`ACR_NAME=cmanbudgetacr`).
- If not → create it:
  ```bash
  az acr create --name cmanbudgetacr --resource-group $RG --sku Basic --location $LOCATION
  ```
  ⚠️ ACR names are globally unique across ALL of Azure, not just this
  subscription. If creation fails with "name not available", pick a
  variant (e.g. `cmanbudgetacr2`) and use that name consistently below.

Register the Container Apps resource providers + CLI extension once per
subscription (safe to re-run, no-op if already registered):

```bash
az extension add --name containerapp --upgrade
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights
```

**Naming decisions (this deploy):**

| Resource | Name | Notes |
|---|---|---|
| Resource group | `$RG` | reused from the SWA (see above) |
| ACR | `cmanbudgetacr` | reused if present, else created |
| Container Apps environment | `cman-budget-web-env` | one environment hosts BOTH apps below |
| Container App — staging | `cman-budget-web-stg` | smoke-test target, deployed first |
| Container App — production | `cman-budget-web-prd` | the real target, per the task spec |
| Image repo | `budget-web` | tagged by git short SHA, e.g. `budget-web:a1b2c3d` |

Create the shared environment (skip if `az containerapp env list -g $RG` shows
a suitable one already):

```bash
ENV_NAME=cman-budget-web-env
az containerapp env create --name $ENV_NAME --resource-group $RG --location $LOCATION
```
⚠️ Recent `az containerapp env create` auto-provisions a Log Analytics
workspace if you don't pass `--logs-workspace-id/--logs-workspace-key`. If
your Cloud Shell's az CLI version is older and this errors/prompts, create a
Log Analytics workspace via the portal first, then pass those two flags.

---

## 3. Build the image once (staging and production deploy the SAME image)

```bash
git clone https://github.com/cmanpowerbi-chememan-com/budget-management-web.git
cd budget-management-web

IMAGE_TAG=$(git rev-parse --short HEAD)
echo "Building image tag: $IMAGE_TAG"   # write this down — you need it for rollback too

ACR_NAME=cmanbudgetacr

az acr build \
  --registry $ACR_NAME \
  --image budget-web:$IMAGE_TAG \
  --file backend/Dockerfile \
  .
```

Notes:
- The trailing `.` = build context is the **repo root** (not `backend/`) —
  required because the Dockerfile copies both `frontend/` and `backend/`.
  Wrong context fails fast with "frontend": not found.
- `az acr build` is a **cloud build** — nothing installs or runs locally.
- Watch the build log for the ODBC-driver install step (marked ⚠️ in
  `backend/Dockerfile`) — that's the step most likely to need adjustment if
  Microsoft's apt-repo config changed since this runbook was written.
- `backend/requirements.txt` is pinned (as of 2026-07-16) — the build installs
  those exact versions; still note the resolved transitive versions from the
  build log for the record.

---

## 4. Env vars + secrets checklist (mapped from `backend/.env.example`)

Values only exist in Cloud Shell / Container Apps secrets — never in this
repo, never pasted into chat.

| Var | Type | Source |
|---|---|---|
| `APP_ENV` | plain env var | literal `production` |
| `FABRIC_SQL_SERVER` | plain env var | Fabric SQL DB host (re-pointed per ADR-0023 — get from the DATA team, do not invent) |
| `FABRIC_SQL_DATABASE` | plain env var | `fabric_sql_database` |
| `GOLD_SQL_SERVER` | plain env var | SAP gold warehouse host |
| `GOLD_SQL_DATABASE` | plain env var | `cman_dw_wh_gold` |
| `ADMIN_EMAILS` | plain env var | `jakkaritw@chememan.com,nipapornt@chememan.com,warapornt@chememan.com` (decided 2026-07-28 — matches Spec A v2 dual-role; also the approver-reachability fix, see post-deploy plan P0-05) |
| `APP_BASE_URL` | plain env var | the Container App's own FQDN (fetched in section 5/6 below) — **not** `budget.chememan.com` yet |
| `ENTRA_CLIENT_ID` | **containerapp secret** | Service Principal `cman-fabric-write` |
| `ENTRA_CLIENT_SECRET` | **containerapp secret** | Service Principal `cman-fabric-write` |
| `ENTRA_TENANT_ID` | **containerapp secret** | tenant ID |
| `ATTACHMENTS_*` | not set | defaults in `config.py` already match the confirmed SharePoint site/library/folder — only override if the target changes |
| `DEV_AUTH_EMAIL` | **do not set** | local-only override; leaving it unset is the safety, not `APP_ENV` alone |
| `NOTIFICATIONS_DRY_RUN` | **do not set** | leave unset -> stays at its safe default `true` (dry-run/preview only for all Graph sendMail calls). Do **not** set this to `false` as part of this deploy. |

The exact `az containerapp update --set-env-vars ... --secrets ...` commands
are given per-environment in sections 5 and 6 (APP_BASE_URL needs the FQDN,
which only exists after the app is created).

---

## 5. Deploy STAGING first (smoke test — no jakkaritw approval needed for this step)

```bash
APP_NAME=cman-budget-web-stg
ACR_NAME=cmanbudgetacr

az containerapp create \
  --name $APP_NAME \
  --resource-group $RG \
  --environment $ENV_NAME \
  --image $ACR_NAME.azurecr.io/budget-web:$IMAGE_TAG \
  --registry-server $ACR_NAME.azurecr.io \
  --registry-identity system \
  --target-port 8000 \
  --ingress external \
  --min-replicas 0 \
  --max-replicas 2 \
  --cpu 0.5 \
  --memory 1.0Gi
```

⚠️ **Least-certain step in this runbook.** `--registry-identity system` asks
the CLI to create a system-assigned managed identity for the app AND grant it
`AcrPull` on the registry in one shot (avoids storing the ACR admin
username/password as a secret — least privilege, 07-security-checklist #7).
If your Cloud Shell's az CLI version doesn't support this flag or the create
fails on image pull (revision stuck unhealthy), fall back to the manual
bootstrap:
```bash
# 1. create with a public placeholder image + system identity
az containerapp create --name $APP_NAME --resource-group $RG --environment $ENV_NAME \
  --image mcr.microsoft.com/k8se/quickstart:latest --target-port 80 --ingress external \
  --system-assigned --min-replicas 0 --max-replicas 2 --cpu 0.5 --memory 1.0Gi

# 2. grant AcrPull to that identity
PRINCIPAL_ID=$(az containerapp show --name $APP_NAME --resource-group $RG --query identity.principalId -o tsv)
ACR_ID=$(az acr show --name $ACR_NAME --query id -o tsv)
az role assignment create --assignee $PRINCIPAL_ID --role AcrPull --scope $ACR_ID

# 3. wire the registry + swap in the real image
az containerapp registry set --name $APP_NAME --resource-group $RG \
  --server $ACR_NAME.azurecr.io --identity system
az containerapp update --name $APP_NAME --resource-group $RG \
  --image $ACR_NAME.azurecr.io/budget-web:$IMAGE_TAG --target-port 8000
```

Fetch the FQDN (needed for `APP_BASE_URL` and the Easy Auth redirect URI):

```bash
FQDN=$(az containerapp show --name $APP_NAME --resource-group $RG --query properties.configuration.ingress.fqdn -o tsv)
echo $FQDN
```

Set env vars + secrets (replace the `<...>` placeholders with real values in
Cloud Shell only):

```bash
az containerapp secret set \
  --name $APP_NAME --resource-group $RG \
  --secrets \
    entra-client-id=<ENTRA_CLIENT_ID_VALUE> \
    entra-client-secret=<ENTRA_CLIENT_SECRET_VALUE> \
    entra-tenant-id=<ENTRA_TENANT_ID_VALUE>

az containerapp update \
  --name $APP_NAME --resource-group $RG \
  --set-env-vars \
    APP_ENV=production \
    FABRIC_SQL_SERVER=<value> \
    FABRIC_SQL_DATABASE=fabric_sql_database \
    GOLD_SQL_SERVER=<value> \
    GOLD_SQL_DATABASE=cman_dw_wh_gold \
    ADMIN_EMAILS=jakkaritw@chememan.com,nipapornt@chememan.com,warapornt@chememan.com \
    APP_BASE_URL=https://$FQDN \
    ENTRA_CLIENT_ID=secretref:entra-client-id \
    ENTRA_CLIENT_SECRET=secretref:entra-client-secret \
    ENTRA_TENANT_ID=secretref:entra-tenant-id
```

**⚠️ Staging shares the SAME `fabric_sql_database` as production** — there is
no separate staging DB in this project. This is an accepted risk ONLY because
`budget.*` is empty pre-go-live (no real user data to corrupt) and staging is
read-mostly for this smoke test. Flag to jakkaritw explicitly if a truly
isolated staging DB is wanted before real data entry begins.

### Easy Auth (staging) — do this in the portal, not blind CLI

Portal → the `cman-budget-web-stg` Container App → **Authentication** (left
nav) → **Add identity provider** → **Microsoft**:
1. App registration: let Azure **auto-create** one for you (simplest — avoids
   the "reuse existing registration?" question; Azure sets the redirect URI
   automatically). ⚠️ Confirm with the tenant admin only if your tenant
   restricts self-service App Registration creation.
2. Restrict access → **Require authentication**.
3. Unauthenticated requests → **HTTP 302 Found redirect: recommended for
   websites**.
4. Save.
5. Confirm under the created App Registration → Authentication → Redirect
   URIs: `https://<staging-FQDN>/.auth/login/aad/callback` is listed.

### Verify staging (do all of section 7 against the staging FQDN first)

Only proceed to section 6 (production) once every check in section 7 passes
on staging.

---

## 6. Deploy PRODUCTION (**requires jakkaritw's explicit approval — section 0 — before running this**)

Same image, same steps, new app name:

```bash
APP_NAME=cman-budget-web-prd

az containerapp create \
  --name $APP_NAME \
  --resource-group $RG \
  --environment $ENV_NAME \
  --image $ACR_NAME.azurecr.io/budget-web:$IMAGE_TAG \
  --registry-server $ACR_NAME.azurecr.io \
  --registry-identity system \
  --target-port 8000 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 2 \
  --cpu 0.5 \
  --memory 1.0Gi
```

**min-replicas = 1 (not 0) for production** — unlike staging, this avoids a
cold-start delay for approvers near a submission deadline; cost at 0.5
CPU/1Gi idle is low. If cost matters more than that at this pilot stage,
`--min-replicas 0` is a defensible lean alternative — flag the tradeoff to
jakkaritw rather than deciding silently.

Repeat the FQDN fetch, secret set, and env-var update from section 5 with
`APP_NAME=cman-budget-web-prd`, and repeat the Easy Auth portal steps against
`cman-budget-web-prd`'s Authentication blade (either let Azure auto-create a
SECOND app registration, or reuse the one from staging by adding a second
redirect URI `https://<prod-FQDN>/.auth/login/aad/callback` to it — simpler
to manage long-term, pick one approach and note it here).

Then repeat every check in section 7 against the **production** FQDN.

---

## 7. verify-deploy-landed (run against staging first, then production)

Success prints from `az containerapp create/update` do **not** prove the app
actually works — verify every step below.

1. **Unauthenticated check (proves Easy Auth is on):**
   ```bash
   curl -i https://$FQDN/health
   ```
   Expect `401` or a `302` redirect to a Microsoft login URL. If you instead
   see `{"status":"ok"}` in plain text, **Easy Auth is NOT covering this
   path — stop, do not proceed, fix the Authentication config first.**

2. Open `https://$FQDN/` in a real browser signed in as
   `jakkaritw@chememan.com` → should redirect through Microsoft login → land
   back on the React app.

3. After login, in the same browser tab: `https://$FQDN/health` → `200
   {"status":"ok"}`.

4. `https://$FQDN/health?deep=1` → `200 {"status":"ok","db":"ok"}`. If
   `"db":"fail"`, the ODBC driver/connection string/creds are wrong — check
   container logs (section 9), never trust the client-facing status word
   alone (it deliberately never leaks connection details).

5. `https://$FQDN/me` → `{"email":"jakkaritw@chememan.com","app_env":"production"}`.

6. **`https://$FQDN/docs` must ALSO be behind the login redirect** — this is
   the org's explicit "Easy Auth covers ALL paths incl. /docs" requirement.
   If `/docs` renders the Swagger UI without a login prompt, Easy Auth is
   misconfigured — stop and fix before calling this deploy done.

7. `https://$FQDN/` loads the actual React SPA (not FastAPI's default JSON
   root, not a 404).

8. **Deep-link / SPA-fallback check:** navigate to any client-side route,
   then hard-reload the browser tab (or open a fresh tab directly to that
   path). It must still return the SPA's `index.html`, not a 404 — this
   proves the parallel StaticFiles+SPA-fallback change in `app/main.py`
   actually works in the built image.

9. `https://$FQDN/budget?year=<current planning year>` → `200` with a JSON
   array (empty is fine — `budget.*` has no real rows pre-go-live). A `5xx`
   here means the SAP read-through failed loud (expected/by-design per
   BUILD_PLAN's never-cut rule) or RLS scope resolution errored — check logs,
   do not treat a 500 as "close enough".

Steps 2–9 need a real signed-in browser tab — Easy Auth's session is a
browser cookie, so `curl` alone can only prove step 1 (the unauthenticated
case).

---

## 8. Control-number reconcile

The never-cut deploy gate is: SUM of pending/board budget per (ฝ่าย,
fiscal_year) must match, at the SAME FX rate, before vs after any change.

At this first deploy, `budget.*` is empty (no submissions yet) — the check is
**trivially 0 = 0**. This is not a shortcut being taken; there is simply
nothing to reconcile against yet. The real check starts mattering the moment
real budget data is entered, and must be re-run for real at that point — do
not treat this deploy's "0=0" as having proven the reconcile logic works.

---

## 9. Logs and health

- Live tail: `az containerapp logs show --name $APP_NAME --resource-group $RG --follow`
- Historical/queryable: portal → Container App → **Log stream** or **Logs**
  (Log Analytics table `ContainerAppConsoleLogs_CL`).
- Health endpoint: `GET /health` (shallow) and `GET /health?deep=1` (Fabric
  SQL round-trip) — both are behind Easy Auth from the public FQDN by design
  (section 7 step 1/6); Container Apps' own internal TCP probe against the
  container's target port is what keeps the revision "Healthy" and is
  unaffected by the Easy Auth layer.

---

## 10. Rollback

**From the second deploy onward** (a previous healthy revision exists):
```bash
az containerapp revision list --name $APP_NAME --resource-group $RG --output table
# pick the previous healthy revision name, then:
az containerapp revision activate --name $APP_NAME --resource-group $RG --revision <previous-revision-name>
az containerapp ingress traffic set --name $APP_NAME --resource-group $RG --revision-weight <previous-revision-name>=100
```
Alternative (if revision history was pruned): redeploy the previous known-good
image tag directly — this is why every `git rev-parse --short HEAD` tag from
section 3 should be written down, not just the latest:
```bash
az containerapp update --name $APP_NAME --resource-group $RG \
  --image $ACR_NAME.azurecr.io/budget-web:<previous-good-tag>
```

**For THIS first deploy specifically** — there is no prior revision to fall
back to. "Rollback" here means taking the broken version offline while you
fix and redeploy:
```bash
az containerapp update --name $APP_NAME --resource-group $RG --min-replicas 0 --max-replicas 0
```

---

## 10b. Incident — a session cookie leaked (or a laptop walked off)

Logging the user out does **not** help. Easy Auth's `/.auth/logout` clears the
browser's cookie and nothing else: the same `AppServiceAuthSession` value
replayed from any other HTTP client keeps returning 200 on `/me` and `/scope`
until it expires on its own (proven on staging 2026-08-18, ADR-0028 amendment).

Do this instead, in order:

1. **Revoke in Entra ID** — Entra ID → Users → *(the user)* → **Revoke sessions**
   (`revokeSignInSessions`). This is the only action that invalidates the issued
   session and refresh tokens immediately. Requires an admin who can act on that
   user object.
2. **Confirm it took** — replay the leaked cookie against the app and expect
   401/redirect, not 200:
   ```bash
   curl -s -o /dev/null -w '%{http_code}
'      -H "Cookie: AppServiceAuthSession=<the leaked value>"      "https://<fqdn>/me"
   ```
3. **Do not rely on the clock alone.** Without a revoke, the exposure window is
   the full cookie lifetime from the moment that cookie was minted:
   production `14:00:00`, staging `00:20:00` since 2026-08-18 (was the Azure
   default ~8 h). Working in the app does not extend it; logging out does not
   shorten it.
4. **Rotate anything else that leaked with it.** A cookie pasted into a chat,
   ticket or screenshot usually travels with other secrets — check for
   `ENTRA_CLIENT_SECRET`, connection strings and SAS URLs in the same paste and
   rotate those per section 4.

Never record "user logged out" as the remediation for a leaked session. It is
not one.

---

## 11. Post-deploy switches deliberately NOT flipped

- `NOTIFICATIONS_DRY_RUN` — left unset (stays `true`/dry-run). All Graph
  sendMail calls remain log-only previews until a deliberate go-live config
  change.
- `.github/workflows/budget-automations.yml` — cron stays commented out
  (`workflow_dispatch` manual-only). This container app deploy does **not**
  touch that file; auto-submit/reminders only go live per the separate
  A11/A12 go-live decision. (The 30-day auto-escalate job is retired,
  ADR-0027 — its replacement, the manual admin step-override, is an
  on-demand endpoint, not a scheduled job, so there is nothing here for it
  to go live.)
- Custom domain `budget.chememan.com` — **not configured in this deploy**.
  `APP_BASE_URL` points at the Container App's auto-generated FQDN for now.
  Follow-up when ready: `az containerapp hostname add` + DNS CNAME/TXT
  verification with whoever manages `chememan.com` DNS + a managed
  certificate, **plus** adding the custom-domain redirect URI to the Entra
  app registration used for Easy Auth (it will 401/loop without that).
- Old master-tables editors — per BUILD_PLAN A14, decommission only once the
  DATA sync is proven (ADR-0018); not part of this deploy.

---

## What jakkaritw needs ready before starting

1. Azure Cloud Shell access with rights to create resources in `$RG` (or
   confirm which RG to use — section 2).
2. The real values for: `FABRIC_SQL_SERVER`, `GOLD_SQL_SERVER`,
   `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET`, `ENTRA_TENANT_ID` (Service
   Principal `cman-fabric-write`) — from wherever they're currently stored
   (not this repo).
3. A decision on the Easy Auth app registration: let Azure auto-create one
   (simplest), or confirm with the tenant admin whether reusing the existing
   `budget-mgmt-app` registration (currently only has a `localhost:8501`
   redirect URI from the old Streamlit setup) is acceptable.
4. Confirmation this deploy is happening AFTER a 07-security-auditor pass
   with no critical FAILs (hard rule — do not skip).
