# D6 — What do UAT emails look like, and who may receive one?

Type: `wayfinder:grilling` · Status: OPEN · Blocked by: nothing

## Question

Every notification this round sends is real, unmarked, and indistinguishable from production
mail. Is that what UAT wants, and who is allowed to be on the receiving end?

## Ground truth

- `NOTIFICATIONS_DRY_RUN=false` on **both** containers. `NOTIFICATIONS_ENVIRONMENT_LABEL` and
  `NOTIFICATIONS_REDIRECT_ALL_TO` are **absent from both** — the Thai test label was deliberately
  removed after 2026-08-17 at jakkaritw's request, so staging mail is byte-identical to
  production mail.
- Mail is sent as `cmanpowerbi@chememan.com` (displays "CMAN_PowerBI") and every notification
  cc's that same mailbox as the audit trail.
- **The whole notification layer is still Thai** — `backend/app/notifications.py` was never
  touched by the 2026-09-05 Englishing, so the UI is English while every email is Thai.
- **A genuine collision sits inside any plausible window:** `dbo.submission_deadline.reminder_date
  = 2026-09-22`. The real deadline-reminder mail fires to **real fillers company-wide** on that
  date, unrelated to UAT.
- Nightly automations (`budget-automations.yml`, `fx-repersist.yml`) run at 03:00 BKK and are
  currently gated to zero writes and zero sends — but one manual `workflow_dispatch` with
  `execute=true` would mail production users.

## Who gets mail if the round runs as planned

With D3 option (a), the chain for both departments is Pornthip → Laddawan → Nipaporn → Waraporn,
i.e. **only attendees**. The exposure is:
- **Arthid** — if Laddawan (rather than Pornthip) ever submits Solution Delivery, or if anything
  routes to him by manager fallback.
- **Suchanya** — as Solution Delivery's real filler, she receives the reject and final-approve
  mails for her own department.

## Options

- **(a) Leave mail real and unlabelled.** Unmarked mail is what UAT is meant to accept; warn the
  two non-attendees in advance.
- **(b) Set `NOTIFICATIONS_ENVIRONMENT_LABEL` for the window** — red banner plus subject prefix.
  Safe, but then UAT never sees the mail a real user will see.
- **(c) Set `NOTIFICATIONS_REDIRECT_ALL_TO=<one catcher mailbox>`** — nobody outside the round is
  ever mailed, and the banner prints the real To/cc it would have used.
- **(d) `NOTIFICATIONS_DRY_RUN=true`.** Never — 16 of the 61 SIT cases are email cases.

## Recommendation

**(a)** if the round stays confined to attendees, with Suchanya and Arthid briefed first, and
with the round finishing before **2026-09-22** or every tester told that both mails are genuine.
Switch to **(c)** the moment any case can route to a non-attendee. Also bar manual dispatch of
both GitHub workflows for the duration.
