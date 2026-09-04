# T05 — Verify the master actually flipped  [OPEN]

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
