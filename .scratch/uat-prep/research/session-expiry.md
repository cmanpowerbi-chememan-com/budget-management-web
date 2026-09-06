**VERDICT: staging currently has NO `login.cookieExpiration` block at all → it runs the Container Apps Easy Auth platform default (`FixedTime` / `08:00:00`, ~8 h). Production is explicitly `14:00:00`. Setting staging to 1 h is ONE `az containerapp auth update` call against a per-app ARM child resource; prod is a physically different resource and cannot be touched by it. The blocker nobody has logged yet: the expiry dialog's Thai copy hardcodes "14 ชั่วโมง" and would lie to every UAT tester.**

---

## 1. Where the lifetime lives — CURRENT VALUES, VERBATIM

ARM resource type: `Microsoft.App/containerapps/authconfigs`, one child named `current` per app.
Subscription `b92b1763-cfa4-4e9f-ab74-e21dbb8e5b21`, RG `CMAN-BUDGET-MNGT-WEB-RG`.

**STAGING** — `/subscriptions/b92b1763-cfa4-4e9f-ab74-e21dbb8e5b21/resourceGroups/CMAN-BUDGET-MNGT-WEB-RG/providers/Microsoft.App/containerApps/cman-budget-web-stg/authConfigs/current` (read via `az containerapp auth show` AND raw `az rest ...?api-version=2024-03-01` — identical):
```json
"login": { "preserveUrlFragmentsForLogins": false }
```
There is **no `cookieExpiration` key, no `nonce`, no `routes`, no `tokenStore`**. Absent `cookieExpiration` = platform default. ADR-0028:16-18 records that default as `FixedTime` / `08:00:00`, measured on this platform. So **staging ≈ 8 hours, fixed from login, non-sliding**.
Other staging auth facts: `globalValidation.unauthenticatedClientAction = RedirectToLoginPage`, `redirectToProvider = azureactivedirectory`, `platform.enabled = true`, AAD `clientId = 7035aa47-0398-4b71-8411-7fc372e82123`, `isAutoProvisioned: false`, audience `api://7035aa47-...`, no `globalValidation.excludedPaths`, no `defaultAuthorizationPolicy`.

**PRODUCTION** — `.../containerApps/cman-budget-web-prd/authConfigs/current`:
```json
"login": {
  "cookieExpiration": { "timeToExpiration": "14:00:00" },
  "nonce": {},
  "preserveUrlFragmentsForLogins": false,
  "routes": {}
}
```
**14:00:00 = 14 hours.** AAD `clientId = 61d5d556-ee48-44f7-91b3-b8e05d6419aa`, `isAutoProvisioned: true`, `globalValidation.excludedPaths: []`, `defaultAuthorizationPolicy.allowedApplications: ["61d5d556-..."]`. Note the two apps use **different Entra app registrations** → a stg cookie is useless on prd and vice versa.

Neither app has `login.tokenStore` → `/.auth/refresh` is unusable, there is **no sliding expiry** in either environment (ADR-0028:19-21).

Current revisions (only one survives in history per app): `cman-budget-web-stg--0000068` created `2026-09-05T17:23:08Z`, image `budget-web:72affd9`; `cman-budget-web-prd--0000033` created `2026-09-05T18:35:13Z`, image `budget-web:72affd9`. Same image both sides.

## 2. Application-level session lifetime — NONE EXISTS

Grepped `backend/app/**/*.py` for `cookie|session|max_age|expiry|expires|ttl`. Findings:

- **The app sets exactly ONE cookie, and it is not a session cookie for auth.** `backend/app/routers/sit.py:57` — `_COOKIE_FLAGS = {"httponly": True, "samesite": "lax", "secure": True, "path": "/"}`. The comment at `sit.py:55-56` states "Session cookie (no max_age)". It holds the SIT impersonation target (`sit_as`, name at `backend/app/auth.py:28`), dies when the browser closes, and carries **no lifetime of its own**.
- No FastAPI `SessionMiddleware`, no `itsdangerous` signing, no server-side session store, no JWT the app mints. `backend/app/auth.py:53` reads identity from Easy Auth's injected headers plus that cookie; the platform owns the session entirely.
- Every other `ttl`/`expires` hit is unrelated: `backend/app/config.py:191 sap_cache_ttl_seconds: int = 600` (SAP gold read cache), `backend/app/cache.py` (generic TTLCache), `backend/app/notifications.py:182-184 _GRAPH_TOKEN_TTL_SECONDS = 3600` + `_TOKEN_EXPIRY_MARGIN_SECONDS = 60` (Graph sendMail token), and `backend/app/db.py` msal token acquisition (self-refreshing).

**Conclusion: there is nothing to change in the app. The Easy Auth platform session is the only lever.** No env var on either container controls it.

## 3. Frontend session-expiry UX — exact mechanics

**Trigger** — `frontend/src/api/client.ts:232-235`:
```ts
if (response.type === 'opaqueredirect' || response.status === 0) {
  raiseSessionExpired()
  throw new ApiError(0, SESSION_EXPIRED_MESSAGE)
}
```
`fetch` is issued with `redirect: 'manual'` (`client.ts:222`, deliberately placed after `...init` so no caller can override it). A dead Easy Auth session answers a **browser-UA** request with a **302** to `login.windows.net`, not a 401 (measured, ADR-0028:24-33). `redirect:'manual'` turns that 302 into an opaque response (`type:'opaqueredirect'`, `status:0`), which is the *only* shape Easy Auth's redirect produces. That branch **must** run before the 401 and `!response.ok` checks, because an opaque redirect is also `ok:false`.
A literal HTTP **401** does NOT raise the dialog — `client.ts:237-240` calls `defaultOnUnauthorized()` → hard navigate to `/.auth/login/aad`, no dialog. That is correct behavior (a 401 only happens for non-browser UAs).

**Single-dialog latch** — `frontend/src/api/sessionExpiry.ts:20-28`: module-level `expired` boolean, first-call-wins, `Set<Listener>` notified once. The grid fires many concurrent calls; N simultaneous failures raise exactly ONE dialog.

**The dialog** — `frontend/src/auth/SessionExpiredDialog.tsx`:
- `role="alertdialog"`, `aria-modal`, `data-testid="session-expired-dialog"`, mounted unconditionally high in `App.tsx` outside the `ready` gate.
- Title `หมดเวลาการเข้าใช้งาน`; body = `SESSION_EXPIRED_MESSAGE` (`sessionExpiry.ts:15-16`), verbatim:
  `หมดเวลาการเข้าใช้งาน (ระบบให้ล็อกอินได้ครั้งละ 14 ชั่วโมง) กรุณา login ใหม่อีกครั้ง`
- **ONE exit, by design**: no ✕, no backdrop-click, no Escape (`SessionExpiredDialog.tsx:9-19`). Focus goes to the container, not the button (`:24-29`), so a stray queued Enter can't fire it.
- The only action is the button `เข้าสู่ระบบใหม่` → `navigate(buildLoginRedirectUrl(currentHref()))` → `/.auth/login/aad?post_login_redirect_uri=<encoded current href>` (`client.ts:47-49`).

**What it preserves / does NOT preserve:**
- **Preserved:** the URL, including deep-link query params, via `post_login_redirect_uri` → the user lands back on the same dept+year page. Also the digits already typed stay visibly on screen until they click the button (React state is untouched).
- **NOT preserved:** typed-but-unsaved cell values. `grep localStorage frontend/src` shows the only persisted keys are **column widths** (`grid/model.ts:136 COLUMN_WIDTHS_STORAGE_KEY`) and toggles via `platform/usePersistedToggle.ts` (theme / admin toggle). **No draft of budget figures is ever written to browser storage.** ADR-0028 "Decision" bullet 3 records this as a deliberate, priced decision by jakkaritw (2026-08-04), with the three reasons the draft-restore alternative was reversed. Blast radius is one cell, because the grid auto-saves per row on blur (`MonthCell.tsx` → `BudgetGrid.tsx` `persistRow`) — there is no bulk Save button.

## 4. The 20-minute episode — HOW it was done, and it WAS reverted

Two tracker entries own this. Quoting the `ai` fields.

**APPLY — task `sit-session-expiry-5min`** (state `done`, created `2026-08-17T16:01:17+0700`, updated `2026-08-18T10:33:43+0700`, agent `claude`):
> "APPLIED TO STAGING 2026-08-18, jakkaritw released the freeze and ordered 4-5-3. Command run: `az containerapp auth update -n cman-budget-web-stg -g CMAN-BUDGET-MNGT-WEB-RG --set login.cookieExpiration.convention=FixedTime --set login.cookieExpiration.timeToExpiration=00:20:00`. VERIFIED AFTER: login block now `{cookieExpiration:{timeToExpiration:'00:20:00'}, preserveUrlFragmentsForLogins:false}`; unauthenticatedClientAction still RedirectToLoginPage, platform.enabled still true, AAD registration clientId unchanged 7035aa47-0398-4b71-8411-7fc372e82123 -> the login config was NOT damaged (that was the stated risk); anonymous curl on the FQDN returns 401 = Easy Auth still enforcing. NOTE: 'convention' does not persist in the stored config (Azure omits it and defaults to FixedTime) -- that is the desired behaviour anyway per ADR-0028, the cookie lifetime is stamped at login and does NOT slide with activity. FULL PRE-CHANGE BACKUP for revert: `scratchpad/stg_auth_backup_before_20min.json` (login had NO cookieExpiration at all = platform default ~8h). REVERT = remove the cookieExpiration block, not set it to 8h. TESTER INSTRUCTIONS UNCHANGED: must log in FRESH AFTER this change for the 20 min to apply … prd untouched (still 14:00:00)."

**REVERT — task `stg-revert-session-and-sit-impersonate`** (state `done`, created+updated `2026-08-20T20:58:45+0700`):
> "REVERTED ON STAGING 2026-08-20 per jakkaritw ('คืนค่า staging: อายุ session 20 นาที -> ค่าเดิม · ลบ SIT_IMPERSONATE'). (1) SESSION LIFETIME: the login.cookieExpiration block is GONE, so staging is back on the Container Apps platform default (~8h) exactly as it was before 2026-08-18 -- it never had a cookieExpiration, which is why the revert had to REMOVE the block, not set it to 8h. `az containerapp auth update --set` could not delete a node and `az rest --method patch` returns **405 Method Not Allowed** on authConfigs, so the working route was: GET the authConfig via az rest, strip `properties.login.cookieExpiration` in python, **PUT the whole object back (api-version 2024-03-01)**. Verified after: login = {preserveUrlFragmentsForLogins:false} only; unauthenticatedClientAction still RedirectToLoginPage; platform.enabled still true; AAD clientId still 7035aa47-... -> the login config was NOT damaged. (2) SIT_IMPERSONATE env var REMOVED via `az containerapp update --remove-env-vars SIT_IMPERSONATE` … That rolled a new revision cman-budget-web-stg--0000055 (image budget-web:52e60d8, same image as 0000054) … CONSEQUENCE FOR SIT: testers now get the ~8h session again (TC-005's 20-minute expiry check can no longer be exercised on staging without re-applying the setting) … PRODUCTION untouched throughout (still image 77308d7, cookie 14:00:00, no SIT_IMPERSONATE)."

**The revert is confirmed by live config today** (§1: staging has no `cookieExpiration`). Corroborating entries: `sit-tc041-run-scoped` (2026-08-19) — "staging Easy Auth now has login.cookieExpiration.timeToExpiration=00:20:00 (TC-005 unblocked)"; `sit-round-closed-2026-08-19` — "staging still has the 20-minute cookieExpiration and the 4-persona SIT_IMPERSONATE set (both should be reverted after the human round)"; `deploy-1b537f9-stg` (2026-08-21) — "PRODUCTION UNTOUCHED (still 77308d7, cookie 14:00:00…)".

**Git history: no commit records the change** — it is pure Azure config, never in the repo. `git log --all --grep` for session/cookie/expir returns only code/doc commits (`ff67b25 fix(auth): show a session-expiry dialog…`, `82ac689 feat(userbar): add ออกจากระบบ`, `bc734eb docs: … logout revokes nothing`). The ONLY history of the config change is the tracker.

**The backup file is GONE**: `scratchpad/stg_auth_backup_before_20min.json` does not exist (`ls` → No such file). Take a fresh backup before touching anything.

**STALE DOCS you will trip over** (all still claim staging = 20 min or 14 h, none true):
- `docs/deploy/A14_RUNBOOK.md:483` — "production `14:00:00`, staging `00:20:00` since 2026-08-18" → **wrong since 2026-08-20**.
- `plan/sit/sit-test-plan.md:178` — "cookie **20 นาที** (ตั้ง 2026-08-18…)" → **wrong**.
- `docs/adr/0028-...md:126-128` "Amendment 2026-08-18 — … Staging is now 20 minutes" → **wrong**, the revert was never amended in.
- `plan/sit/sit-run-log.md:37`, `plan/sit/evidence/SIT-000/step3_auth_cman-budget-web-stg.txt:3` — "timeToExpiration=14:00:00" for stg → frozen pre-2026-08-18 evidence.

## 5. EXACT command shape for 1 hour (NOT RUN)

**Step 0 — backup first (read-only, do this):**
```bash
SUB=b92b1763-cfa4-4e9f-ab74-e21dbb8e5b21
az rest --method get \
  --url "https://management.azure.com/subscriptions/$SUB/resourceGroups/CMAN-BUDGET-MNGT-WEB-RG/providers/Microsoft.App/containerApps/cman-budget-web-stg/authConfigs/current?api-version=2024-03-01" \
  -o json > "$TEMP/stg_auth_backup_before_1h_$(date +%Y%m%d).json"
```

**Step 1 — apply (the proven shape, from `sit-session-expiry-5min`, only the value changed):**
```bash
az containerapp auth update -n cman-budget-web-stg -g CMAN-BUDGET-MNGT-WEB-RG \
  --set login.cookieExpiration.convention=FixedTime \
  --set login.cookieExpiration.timeToExpiration=01:00:00
```

**Step 2 — verify (read-only):** `az containerapp auth show -n cman-budget-web-stg -g CMAN-BUDGET-MNGT-WEB-RG` must show `login.cookieExpiration.timeToExpiration = "01:00:00"`, and unchanged: `platform.enabled=true`, `globalValidation.unauthenticatedClientAction=RedirectToLoginPage`, `identityProviders.azureActiveDirectory.registration.clientId=7035aa47-0398-4b71-8411-7fc372e82123`. Then `curl -s -o /dev/null -w '%{http_code}' https://cman-budget-web-stg.kindstone-f34836dd.southeastasia.azurecontainerapps.io/health` must still be **401**.

**Step 3 — revert after UAT (harder than the apply — plan for it now):** you must **delete** the node, not set it to `08:00:00`. `--set` cannot remove a node and `az rest --method patch` returns **405** on authConfigs. Working route (recorded): `az rest --method get` the whole authConfig → strip `properties.login.cookieExpiration` in a python file (`python -X utf8 script.py`, `encoding='utf-8'`) → `az rest --method put` the whole object back at `api-version=2024-03-01`.

### RISKS — every one

| # | Risk | Evidence / verdict |
|---|---|---|
| R1 | **Is authConfig per-app?** | **YES, separate ARM resources.** stg = `.../containerApps/cman-budget-web-stg/authConfigs/current`, prd = `.../containerApps/cman-budget-web-prd/authConfigs/current`. Different `id`, different clientId, different audience. A staging-scoped `-n cman-budget-web-stg` command **cannot** reach prd. |
| R2 | **Does it restart the app / roll a revision?** | **Almost certainly no revision.** `authconfigs` is a child ARM resource, not part of `properties.template`, so it is outside the revision hash. The `sit-session-expiry-5min` entry documents the 08-18 auth update and records **no new revision** — while the 08-20 entry explicitly attributes revision `--0000055` to the `az containerapp update --remove-env-vars` step, not to the auth PUT. **Caveat I cannot close read-only:** revision history is purged (only `--0000068` remains), so I could not empirically re-prove zero restart today. Easy Auth reloads its sidecar config platform-side; assume a brief config reload, not an app restart. |
| R3 | **Does it invalidate existing sessions?** | **NO — and that is the trap.** Convention is `FixedTime`: the lifetime is **stamped into the cookie at login** and does not slide. Cookies already minted keep their old ~8 h expiry. **Every UAT tester must log out and log in FRESH after the change**, or they will not get 1 hour. Recorded twice (`sit-session-expiry-5min`, ADR-0028:135-137, `plan/sit/sit-test-plan.md:178`). Conversely, existing 8 h cookies stay valid for their full remaining life — a shorter setting does not kill anything already issued. |
| R4 | **UI copy will lie to every UAT tester.** | `frontend/src/api/sessionExpiry.ts:16` hardcodes `ระบบให้ล็อกอินได้ครั้งละ **14 ชั่วโมง**`. On a 1 h staging that number is false. ADR-0028:129-133 already flagged this for the 20-min window and explicitly says: "revert staging … **or fix the copy before staging is used to demonstrate the real limit to anyone**." Fixing it is a code change + rebuild + deploy: `frontend/src/api/sessionExpiry.ts:16` plus 3 tests that assert the literal string — `frontend/src/api/client.test.ts`, `frontend/src/auth/SessionExpiredDialog.test.tsx`, `frontend/src/grid/BudgetGrid.test.tsx:162` — and it would also change **production's** copy unless made env-driven. **This is a real UAT decision, not a footnote.** |
| R5 | **1 h is fixed, not sliding — it will cut testers off mid-session.** | No `tokenStore` on either app → `/.auth/refresh` unusable; working in the app does not extend the clock. A UAT session lasting >1 h from each person's login **will** hit the dialog for real, repeatedly. If UAT runs 2–3 hours, expect 2–3 forced re-logins per attendee. That may be exactly what you want (it exercises TC-005 for free) — but it must be in the UAT script, not a surprise. |
| R6 | **Unsaved input is lost on expiry, by accepted design.** | ADR-0028 Decision bullet 3. Loss is bounded to ONE cell (per-row autosave on blur), and the URL/dept/year is preserved via `post_login_redirect_uri`. Not a defect — do not let a UAT tester file it as one. |
| R7 | **Revert is the risky half, not the apply.** | Baseline is "no `cookieExpiration` key at all". Setting `08:00:00` is functionally equivalent but **not** state-identical. The delete path needs a full-object PUT — and staging's object shape differs from prd's (staging has no `globalValidation.excludedPaths`, no `login.nonce`, no `login.routes`, no `defaultAuthorizationPolicy`). **Never PUT a prd-shaped body onto stg.** Round-trip the GET output; the backup from Step 0 is the safety net (the 2026-08-18 backup no longer exists on disk). |
| R8 | Stated risk from last time: damaging the login config. | Did not materialize on 2026-08-18; the verification list in Step 2 is exactly the one that proved it. Reuse it. |
| R9 | Unaffected by this change (but still live UAT hazards) | Shared Fabric SQL DB between stg and prd, and unsandboxed/unlabelled staging mail. Session lifetime touches neither. |

## 6. Is production untouched by a staging-only change? — YES

Evidence, three independent layers:

1. **Different ARM resources.** Read live today: `id: /subscriptions/b92b1763-cfa4-4e9f-ab74-e21dbb8e5b21/resourceGroups/CMAN-BUDGET-MNGT-WEB-RG/providers/Microsoft.App/containerApps/**cman-budget-web-stg**/authConfigs/current` vs `.../containerApps/**cman-budget-web-prd**/authConfigs/current`. `az containerapp auth update -n cman-budget-web-stg` addresses only the first; there is no shared or inherited auth object.
2. **Different Entra app registrations** — stg `7035aa47-0398-4b71-8411-7fc372e82123` vs prd `61d5d556-ee48-44f7-91b3-b8e05d6419aa`, different audiences, `isAutoProvisioned` false vs true. `plan/sit/sit-run-log.md:37` records the consequence: "cookie ของ stg ใช้กับ prd ไม่ได้".
3. **Historical proof of the same operation.** The 20-min change on 2026-08-18 and its removal on 2026-08-20 both left prd at `14:00:00` — asserted in the apply entry ("prd untouched (still 14:00:00)"), in the revert entry ("PRODUCTION untouched throughout … cookie 14:00:00"), and again in `deploy-4bf1d82-stg` and `deploy-1b537f9-stg`. **And prd still reads `"timeToExpiration": "14:00:00"` in the live config I pulled today**, which is the direct end-to-end confirmation that a full apply+revert cycle on staging moved prd by zero.

Caveat: this holds only if the command is scoped with `-n cman-budget-web-stg`. There is no guard rail — the same command with `-n cman-budget-web-prd` would silently change production. Nothing prevents that but the operator.

---
**NOT verifiable read-only:** (a) that the 08:00:00 platform default is currently in force on stg — an absent key is documented-default, not an observed value; only a real login+wait or a cookie-expiry inspection proves it; (b) that an auth-only update creates zero revision, since revision history is purged; (c) `scratchpad/stg_auth_backup_before_20min.json` no longer exists, so the 2026-08-18 pre-change snapshot is unrecoverable — take a new backup.