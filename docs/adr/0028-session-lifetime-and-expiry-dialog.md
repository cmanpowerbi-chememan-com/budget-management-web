# 28. Login session = 14 h, with an expiry dialog; unsaved input not preserved

Date: 2026-08-04

Status: Accepted and implemented 2026-08-04. The 14 h cookie is live on staging and
production; the expiry dialog and the opaque-redirect detection are in the frontend.

## Context

Authentication is Container Apps built-in auth ("Easy Auth") + Entra ID (ADR-0004).
Three facts about it were established by probing the live production app on 2026-08-04,
none of which were previously written down anywhere:

1. **The session cookie is fixed-length, not sliding.** `az containerapp auth show
   -n cman-budget-web-prd` returns `login.cookieExpiration = {}` — i.e. the Container
   Apps default, `FixedTime` / `08:00:00`. The clock starts at **login**, not at last
   activity. Working in the app does not extend it. `login.tokenStore` is `null`, so
   `/.auth/refresh` cannot renew anything either.
   Consequence: a Filler who logs in at 08:30 is cut off at **16:30** — the end of the
   working day, every day, exactly when budget season has people entering numbers.

2. **Easy Auth answers an expired session with a 302, not a 401 — and it branches on
   `User-Agent`.** Measured against `cman-budget-web-prd`:

   | request | response |
   |---|---|
   | `GET /api/me`, no cookie, browser UA (even `Sec-Fetch-Mode: cors`) | **302** → `login.windows.net/.../authorize?...response_mode=form_post` |
   | `GET /api/me`, no cookie, non-browser UA | 401 (`www-authenticate: Bearer`) |
   | `GET /`, no cookie, browser UA | 302 → same authorize URL |
   | `GET /`, no cookie, non-browser UA | 401, empty body |

3. **Therefore the app's 401 handling never runs in a real browser.**
   `frontend/src/api/client.ts` treats `response.status === 401` as "session gone →
   redirect to login". In a browser the request instead gets the 302, `fetch` follows it
   cross-origin, CORS blocks the response, `fetch` rejects, and the code lands in the
   generic network `catch` — telling the user
   *"เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ กรุณาตรวจสอบอินเทอร์เน็ต"*. The user is told their
   **internet** is broken, is never sent to log in, and any typed-but-unsaved grid cells
   are stranded. Curl-based smoke tests never caught this because curl sends no browser
   `User-Agent` and so takes the 401 branch.

Navigation is unaffected: opening or refreshing a page after expiry gets the 302 and
lands on the Entra login normally. Only in-app `fetch` calls are broken. Email
deep-links (ADR-0016) therefore also keep working — they are plain navigations.

## Decision

Three parts, decided together by jakkaritw on 2026-08-04:

- **Session lifetime 8 h → 14 h.** `login.cookieExpiration.timeToExpiration = 14:00:00`
  (convention stays the default `FixedTime`; the API elides default values, so it does
  not appear in `auth show` output). A login at 08:30 now survives to 22:30, covering a
  normal day plus overtime, so the expiry stops being a daily event.

- **An explicit session-expiry dialog.** When the app detects that the session is gone,
  it shows a dialog reading, verbatim:

  > หมดเวลาการเข้าใช้งาน (ระบบให้ล็อกอินได้ครั้งละ 14 ชั่วโมง) กรุณา login ใหม่อีกครั้ง

  Its primary action sends the user to `/.auth/login/aad?post_login_redirect_uri=<current
  href>`, preserving the page they were on (same deep-link mechanism as ADR-0016).
  Detection must key off the **fetch rejection / redirect** path, not off HTTP 401.

- **Unsaved input is NOT preserved. The loss is accepted.** Typed-but-unsaved cells are
  gone once the session expires; nothing is written to browser storage and nothing is
  restored after re-login. Reaching the expiry at all now means the tab was left open
  well past a working day (14 h from login), so the case is rare by construction — and
  the alternative cost was high: confidential budget figures sitting in browser storage
  on a possibly-shared workstation, a draft key that has to survive a cross-origin login
  round-trip, and an auto-replay path that can silently overwrite another user's edit
  through ADR-0003 optimistic locking. jakkaritw weighed those against the rare loss and
  chose the loss (2026-08-04, after an adversarial review surfaced all three).

### Alternatives rejected

- **Keep 8 h and ship only the dialog.** Rejected: a well-worded message every single
  day at 16:30 is still a daily interruption for every Filler. The dialog was always
  meant for the rare overnight case, not the normal one.
- **Enable a token store and refresh the session with `/.auth/refresh` (true sliding
  expiry).** Rejected: Container Apps token store needs a blob container plus a SAS
  secret, and the app would need periodic refresh calls — more infrastructure and more
  moving parts for the same practical outcome as a longer fixed window. Contrary to the
  project's lean philosophy.
- **Persisting unsaved drafts locally and restoring them after re-login.** Decided on
  first, then reversed on 2026-08-04 once an adversarial review priced it honestly: the
  draft key needs the fiscal year and ฝ่าย, which this app never puts in the URL, so the
  key would not have matched after the login round-trip and the restore would have failed
  *silently*; the replay path could not carry the original optimistic-lock token and so
  could overwrite a colleague's edit; and the conflict case had no honest wording. Against
  a loss that only happens after 14 h of an open tab, the complexity and the confidential-
  data-at-rest exposure were not worth it.
- **A second close/dismiss control on the dialog.** Rejected: dismissing leaves the user
  on a page where every request still fails, with no way back except the button they just
  dismissed.
- **Wording "ถูกตัดออกจากเซิร์ฟเวอร์" (the first draft).** Rejected: a non-technical
  accountant reads it as "the system is down" and raises a support call, when in fact
  nothing is wrong. The accepted wording names the cause and the limit.

## Amendment 2026-08-18 — logout does not end the session, and staging is no longer 14 h

Two facts established after this ADR was accepted. Both change what the numbers above
mean in practice.

**1. `/.auth/logout` clears the browser cookie only — it does not revoke anything.**
Proven live on staging: after calling `/.auth/logout` (which redirects to
`login.microsoftonline.com/.../oauth2/v2.0/logoutsession`, and reloading the app then
bounces to the Microsoft authorize endpoint, so the browser session really is gone), the
**same `AppServiceAuthSession` value replayed from a plain HTTP client still returned
200** on `/me` and `/scope` as that user. The cookie stays valid for its full remaining
lifetime no matter how many times anyone logs out.

Consequences, in order of how likely they are to bite:

- A leaked or copied `AppServiceAuthSession` cookie **cannot be killed by logging out**.
  Treat it as live until it expires on its own, or until an admin revokes explicitly.
- The only real revocation is **Entra ID → Users → *(the user)* → Revoke sessions**
  (`revokeSignInSessions`), which invalidates issued session and refresh tokens.
- The ออกจากระบบ button added on 2026-08-18 (`frontend/src/userbar/UserBar.tsx`) is
  therefore a *convenience for the person at the keyboard*, not a security control. Its
  UI copy deliberately promises nothing beyond leaving; do not add reassuring wording
  like "ออกจากระบบเรียบร้อย" that implies the session is dead.
- Shortening the cookie lifetime is the only lever that bounds the exposure window,
  because it is the expiry — not any logout — that ends a stolen session.

**2. Staging is now 20 minutes, not 14 hours.** On 2026-08-18 staging was set to
`login.cookieExpiration.timeToExpiration = 00:20:00` so SIT can exercise the expiry
dialog inside a test session instead of waiting out a working day. Production is
unchanged at `14:00:00`.

- The dialog's Thai copy still says **14 ชั่วโมง**, so on staging the message now states
  a number that does not match that environment. Accepted for the SIT window because the
  dialog's job there is to prove it appears at all; revert staging (remove the
  `cookieExpiration` block — staging never had one before, its default was ~8 h) or fix
  the copy before staging is used to demonstrate the real limit to anyone.
- A tester must **log in fresh after the change** for 20 minutes to apply: cookies
  already minted keep the expiry they were issued with, per the Consequences below.

## Consequences

- The window in which a lost or borrowed laptop holds a live session grows from 8 h to
  14 h. Accepted knowingly: internal tool, company devices, and every request is still
  scoped by RLS to the user's own Cost Centers (ADR-0019).
- **The number 14 appears in Thai UI copy.** If the cookie lifetime is ever changed, the
  dialog text must change in the same commit, or the app will state a false limit.
- Changing the auth config does not shorten or lengthen sessions already issued; existing
  cookies keep the expiry they were minted with. The new lifetime applies from each
  user's next login.
- `client.ts`'s `status === 401` branch is kept, not deleted: it is still the real path
  for non-browser callers (the pytest/httpx harnesses under `setup/`, `smoke_prd.py`) and
  for any environment where Easy Auth returns 401.
- The 8 h figure was only ever the documented Azure default and was never observed;
  the 14 h figure likewise needs a real long-session soak to confirm (tracker task
  `#k8-long-session-soak`, the never-run P2-K8 test that would have caught the dead 401
  branch in the first place).
- Applied to staging `cman-budget-web-stg` and then production `cman-budget-web-prd` on
  2026-08-04 with jakkaritw's approval (previous configs backed up first). Verified after
  the change: the identity provider, allowed audiences and
  `unauthenticatedClientAction` are unchanged and the production revision stayed healthy.
  Note that `convention: FixedTime` is not echoed back by `az containerapp auth show` —
  the API elides default values, which is expected and not a failed write.
- Detection is implemented as `fetch(..., { redirect: 'manual' })` plus a branch on
  `response.type === 'opaqueredirect'`. A **rejected** promise still means only
  offline / server-down and keeps the existing connectivity message, so a flaky network
  never claims the session ended. The pre-existing `status === 401` branch is retained —
  it is still the live path for the non-browser callers under `setup/`.
