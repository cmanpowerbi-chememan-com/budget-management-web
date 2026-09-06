# T1 — Apply and verify the environment configuration for the round

Type: `wayfinder:task` (AFK, with jakkaritw approval per mutating step) · Status: OPEN
Blocked by: ~~D1~~ closed · **D5, D6**

## Question

Make the chosen container match what D1, D5 and D6 decided, prove it landed, and write down how
to put it back.

## Work

1. Read the current `authConfigs/current` and the full env var set of the chosen container, and
   record them verbatim as the revert baseline.
2. Apply only what was decided. Candidate changes, each conditional on its decision:
   - session cookie lifetime (D5) — `az containerapp auth update … --set login.cookieExpiration.convention=FixedTime --set login.cookieExpiration.timeToExpiration=<hh:mm:ss>`
   - remove `SIT_IMPERSONATE` (D1, if staging)
   - remove `DEV_AUTH_EMAIL` (D1, if staging) — this one is a security fix regardless
   - mail label or redirect (D6)
   - raise `minReplicas` from 0 if staging, so cold starts do not distort the round
3. Verify each change by reading it back, not by trusting the command's exit code.
4. Record the exact revert commands in the ticket's resolution and in `plan/uat/uat-run-plan.md`.

## Constraints

- `authConfigs/current` is a per-app ARM child resource — a staging change cannot reach
  production. Confirm the resource path before every call.
- `az containerapp update --set-env-vars` was verified safe for a single variable on this app
  (env NAME sets on revisions 0000066/67/68 were identical, nothing dropped). Still re-read the
  full name set afterwards.
- Changing the auth config creates a new revision. Existing sessions are not invalidated, so a
  cookie-lifetime change only takes effect for **logins made after it lands** — testers must
  re-login for the new value to apply.
- Never set `SIT_IMPERSONATE` or `DEV_AUTH_EMAIL` on production.

## Definition of done

Every applied value read back and quoted · the revert commands written down · the running
revision and image recorded · jakkaritw's approval quoted for each mutating call.

---

## AMENDMENT 2026-09-06 — D1 chose production, so this ticket shrank

Production needs no hardening: it already has no `SIT_IMPERSONATE`, no `DEV_AUTH_EMAIL`,
`APP_ENV=production`, `minReplicas=2` and a 14 h cookie. Of the five candidate changes listed
above, only two survive, and both are conditional:

- the session cookie, **if and only if D5 says so** — and on production, so read D5's amendment
  about blast radius and about reverting the same day;
- a mail label or redirect, **if and only if D6 says so**.

The three staging-only items (`SIT_IMPERSONATE` removal, `DEV_AUTH_EMAIL` removal, raising
`minReplicas`) are no longer part of this round. **Removing staging's
`DEV_AUTH_EMAIL=pornthipp@chememan.com` is still worth doing as a standing security fix** — it is
armed the moment Easy Auth is ever toggled off, at which point any anonymous caller on the
internet becomes Pornthip with write rights against the production database — but it belongs to a
separate effort now, not to UAT prep.
