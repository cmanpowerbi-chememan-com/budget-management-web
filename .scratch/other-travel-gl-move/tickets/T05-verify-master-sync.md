# T05 — Verify the master actually flipped  [CLOSED 2026-09-05]

Type: `wayfinder:research` (AFK)

## Question
After the sync runs, does `dbo.gl_group` show BOTH GLs under exactly
`Other manpower exp (Per diem,Health check,Uniform…etc)` — and did the edit create a
near-duplicate group from a typo (extra space, ASCII "..." instead of U+2026)?

## How
`SELECT gl_code, gl_group FROM dbo.gl_group WHERE gl_code IN ('5210400999','6210400999')`
plus `SELECT gl_group, COUNT(*) FROM dbo.gl_group GROUP BY gl_group` — the group count must
stay at 19 distinct groups, with the target group going 10 → 12 GLs and Travelling Expense
8 → 6. A 20th group name appearing means a typo.

## Resolution
Sync landed 2026-09-05 06:31:36. Both GLs read exactly
`Other manpower exp (Per diem,Health check,Uniform…etc)`; `edit_by` still `user` on both (no
accidental admin flip, which would have hidden the rows AND moved them out of the department's
approval lane). Distinct group count still **19** — no typo created a 20th group. Membership
moved as predicted: target group 10 → 12, Travelling Expense 8 → 6.
