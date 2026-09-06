# T7 — Prove the testers can actually sign in

Type: `wayfinder:task` (HITL — one real person, one browser) · Status: OPEN (**downgraded** — see the amendment) · Blocked by: ~~D1~~ closed 2026-09-06

## Question

Before day 1, can a non-admin attendee open the chosen URL and reach the grid as themselves?

## Why this earns a ticket

Staging and production use **different Entra app registrations** — staging `7035aa47-…` with
`isAutoProvisioned: false`, production `61d5d556-…` with `isAutoProvisioned: true`. This project
has a recorded incident where non-admin logins hit **"Need admin approval"** until one
tenant-wide `User.Read` consent was granted, per Easy Auth app. The staging registration's
consent state has never been probed, and it is not checkable read-only from a terminal.

If it bites, it bites all five testers in the first five minutes and the day is lost.

## Work

1. Have **Pornthip** (a non-admin) open the chosen URL in a normal browser and sign in with her
   own account. Not jakkaritw — he is an admin and would not reproduce the failure.
2. Confirm she reaches the grid as herself: the user bar shows her name, her division and her
   department count, and the department picker offers the departments D3 established.
3. If UAT runs on staging, confirm she is **not** silently Pornthip-by-default via
   `DEV_AUTH_EMAIL` but genuinely authenticated — the distinction matters, and T1 should have
   removed that variable.
4. Note the cold-start delay if staging (~25 s at minReplicas 0) so it is expected, not reported.

## If it fails

jakkaritw can grant the tenant-wide consent himself for that app registration; the earlier
incident is recorded in memory as `gotcha_entra_need_admin_approval_easyauth`.

## Definition of done

One real non-admin login succeeded on the chosen environment, with the date, the URL, the
observed department list and the cold-start time recorded.

---

## AMENDMENT 2026-09-06 — downgraded from blocker to confirmation

D1 chose production. Production's Entra app registration is `61d5d556-…` with
`isAutoProvisioned: true`, unlike staging's `7035aa47-…` (`isAutoProvisioned: false`), so the
"Need admin approval" failure this ticket exists to catch is far less likely there.

It is still worth doing once, because nothing in the record actually proves Pornthip has signed
in to the **production** URL with her own account — the SIT workbook's Info sheet names the
staging URL while `plan/sit/sit-test-plan.md:150` records the click-through as production, and
that contradiction was never resolved. One five-minute login settles it.

Steps 3 (the `DEV_AUTH_EMAIL` distinction) and 4 (the cold-start delay) are staging-only and no
longer apply.
