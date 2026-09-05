# T04 — Production deploy  [CLOSED 2026-09-06]

Type: `wayfinder:task` (HITL — jakkaritw approves, never-cut)

## Question
Ship to production before the next master sync lands, and prove it landed.

## Notes
Deadline is the daily ~06:31 sync. Rollback = redeploy the previous revision; note that the
master flip is NOT rolled back by a code rollback, so a rollback re-opens the broken window —
if the code must be rolled back, the Excel has to be reverted too.

## Hold (2026-09-05, jakkaritw)
Deferred so the production deploy can carry a parallel session's wording edits ("แก้ไขคำ") in
the same release rather than deploying twice.

Consequences:
- `budget-web:bab089b` is no longer the image to ship. Rebuild from a commit that contains BOTH
  bab089b and the wording session's commit, then deploy that.
- Overlap warning for the wording session: bab089b already rewrote user-facing Thai copy in
  `frontend/src/subform/TripManager.tsx` ("4 ประเภทค่าใช้จ่าย" → "3", the legend line dropped
  "/อื่น", the section label 4 → 3). Those counts are now FACTUALLY correct — the trip form has
  3 rows. Restoring "4" would be wrong and would fail `TripManager.test.tsx`.
- The risk of waiting is unchanged and stated in D8: prd runs old code against a flipped master,
  so the silent-zeroing window is open. Measured exposure on 2026-09-05 is 0 rows (no trip exists
  in 10IT011300 FY2027), but it grows as Fillers type into the newly-opened cells.

## Resolution
jakkaritw reviewed staging, approved, and asked to promote the staging image as-is. No rebuild:
`budget-web:72affd9` (the image staging was already serving) was pointed at production.

`cman-budget-web-prd--0000033` — active True, RunningAtMaxScale, Healthy, trafficWeight 100,
image tag verified `72affd9`. Previous revision `--0000032` (`55e0753`) dropped to 0% traffic.
Anonymous probe on the container FQDN returns 401 = Easy Auth on = expected.

The release carries 4 commits, not 1: bab089b (this effort) plus ad12d4a / 230ffa7 / 72affd9,
a parallel session's Thai→English copy pass over the approval flow.

**The silent-zeroing window is now closed.** From 2026-09-05 06:31 (master sync) until this
deploy, production ran code that still owned these GLs as trip-driven. Measured exposure during
that window was 0 rows at risk.

Incidental finding, pre-existing and unrelated: no custom domain is bound to the prd container
app and `budget.chememan.com` does not resolve — production is reachable only on
`cman-budget-web-prd.kindstone-f34836dd.southeastasia.azurecontainerapps.io`.
