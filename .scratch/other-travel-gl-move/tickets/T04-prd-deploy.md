# T04 — Production deploy  [OPEN · blocked by T03]

Type: `wayfinder:task` (HITL — jakkaritw approves, never-cut)

## Question
Ship to production before the next master sync lands, and prove it landed.

## Notes
Deadline is the daily ~06:31 sync. Rollback = redeploy the previous revision; note that the
master flip is NOT rolled back by a code rollback, so a rollback re-opens the broken window —
if the code must be rolled back, the Excel has to be reverted too.
