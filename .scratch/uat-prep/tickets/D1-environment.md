# D1 — Does UAT run on staging or on production?

Type: `wayfinder:grilling` · Status: **CLOSED 2026-09-06** · Blocked by: nothing (**this is the first decision — everything else branches off it**)

## Question

Which URL do the five testers open, and therefore which container gets hardened for the round?

## Why this is not obvious

The instinct is "test on staging". Measured, staging is **less** realistic than production, not
more, and buys no safety at all:

| | staging `cman-budget-web-stg` | production `cman-budget-web-prd` |
|---|---|---|
| Image | `budget-web:72affd9` | **the same** `budget-web:72affd9` |
| Database | `fabric_sql_database-a42ef9f3-…` | **byte-identical** |
| Mail | `NOTIFICATIONS_DRY_RUN=false`, no label, no redirect | **the same** |
| `SIT_IMPERSONATE` | 5 targets, from `jakkaritw` | absent |
| `DEV_AUTH_EMAIL` | `pornthipp@chememan.com` | absent |
| `APP_ENV` | `local` | `production` |
| Session cookie | none set → platform default ≈8 h | `14:00:00` |
| minReplicas | **0** — ~25 s cold start | 2, always warm |
| Entra app registration | `7035aa47-…`, `isAutoProvisioned:false` | `61d5d556-…` |

So staging adds three distortions and removes none:
- **jakkaritw cannot be himself on staging.** `auth._select_sit_target` returns `targets[0]` when
  no `sit_as` cookie is set — that is Pornthip. Every write he makes is signed `pornthipp@`.
  Two proposed admin cases (admin bypasses the seminar-GL restriction; the admin step-override
  confirm dialog) silently test a non-admin filler instead.
- **`DEV_AUTH_EMAIL` is armed, not disarmed.** `auth.py:45` — the instant Easy Auth is toggled
  off for convenience, any anonymous caller on the internet becomes Pornthip with full write
  rights against the production database.
- **Cold starts** make every perf and timeout observation non-transferable.

Against that, production needs **zero** config changes and matches what was already promised to
management in `monthly_update/project_status_report_2026-08.html` ("pilot on production, 1–2
departments, 3–5 working days"). SIT itself ran its click-through on the production URL
(`plan/sit/sit-test-plan.md:150`) even though the workbook's Info sheet names the staging URL —
that contradiction has never been reconciled.

## What the answer changes

- Whether **D5** (1-hour session) and **T1** (apply env config) exist at all, or are deleted.
- Whether `SIT_IMPERSONATE` and `DEV_AUTH_EMAIL` must be removed for the window.
- Whether one attendee must pre-test login against the staging Entra registration (**T7**) —
  this project has a recorded incident where non-admin logins hit "Need admin approval" until a
  tenant-wide consent was granted per Easy Auth app, and the staging registration's consent
  state was never probed.
- Which URL goes on the pack's Info sheet.

## Options

- **(a) Production.** Zero prep, everyone is themselves, warm replicas, 14 h session.
- **(b) Staging.** Requires removing `SIT_IMPERSONATE` + `DEV_AUTH_EMAIL`, setting the cookie,
  warming the container, and probing Entra consent — for no safety gain.
- **(c) Staging as a rehearsal for the testers, production for the recorded acceptance cases.**

## Recommendation

**(a) Production**, keeping staging as the place to rehearse the script. It deletes four prep
items and is the only reading under which "everyone is themselves" holds.

---

## RESOLUTION — CLOSED 2026-09-06

**jakkaritw chose (a) Production.** UAT runs on
`cman-budget-web-prd.kindstone-f34836dd.southeastasia.azurecontainerapps.io`.

Consequences, applied to the rest of the map:

- **No environment hardening is needed for the round.** Production already has no
  `SIT_IMPERSONATE`, no `DEV_AUTH_EMAIL`, `APP_ENV=production`, `minReplicas=2` and a 14 h
  cookie. Everyone is themselves and the audit log records the real actor.
- **T1 shrinks to almost nothing.** Its only remaining candidate change is whatever D5 decides
  about the session, and that now lands on *production*, which is a materially different risk
  from staging — D5's framing has changed and the ticket says so.
- **T7 drops from blocker to confirmation.** Production's Entra app registration
  `61d5d556-…` is `isAutoProvisioned: true`, unlike staging's `7035aa47-…`, so the
  "Need admin approval" failure mode that T7 exists to catch is far less likely. One login
  check still happens, but it no longer gates the round.
- **The pack's Info sheet carries the production URL**, and `_validate_uat_pack.py` asserts the
  staging URL does **not** appear. This also settles the old contradiction where the SIT
  workbook named staging while `plan/sit/sit-test-plan.md:150` recorded the click-through as
  production.
- **Staging keeps its job as the rehearsal environment**, and removing its
  `DEV_AUTH_EMAIL=pornthipp@chememan.com` remains a standing security fix worth doing on its
  own merits — it is armed the moment Easy Auth is ever toggled off. That is now unrelated to
  UAT and belongs to a separate effort.
