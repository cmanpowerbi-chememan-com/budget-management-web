# T03 — Ship to staging and verify  [PARTIALLY CLOSED 2026-09-04 · UI check needs a human]

Type: `wayfinder:task` · blocks T04

## Question
Does the trip form render exactly 3 rows and do the 2 GLs behave as ordinary editable grid
cells, on staging, against the real DB?

## Notes
Staging still reads the same `dbo.gl_group`, which has NOT flipped yet — so staging will show
the OLD grouping until the sync runs. Decide before testing whether to trigger the DW sync
notebook on demand (Fabric REST `jobs/instances`, `only_spec=Budget_Masters_gl_group`, ~1.5
min) or wait for ~06:31. Verification is headless-Playwright + `page.evaluate()` assertions,
screenshots saved to disk and NOT read into context (project rule).

## Resolution (server side, done)
Image `budget-web:bab089b` built in ACR (run `cm1v`, Succeeded) from a clean detached worktree
at commit bab089b. Deployed to `cman-budget-web-stg`, revision **cman-budget-web-stg--0000066**:
active True, runningState Running, healthState Healthy, trafficWeight 100, image tag confirmed
`bab089b`. Anonymous probe returns 401 = Easy Auth on = expected.

Extra evidence the removal is real in what actually ships: `grep -rl "6210400999\|5210400999"
frontend/out` returns **0 files**, while `6210400030` (accommodation) still matches 1 — so the
control works and the moved GLs are genuinely absent from the built bundle.

## Still open — needs jakkaritw
Staging enforces Easy Auth (401 to every unauthenticated request), so the UI cannot be driven
headlessly from here. A human must open Trip Manager on staging and confirm it renders 3
expense rows, not 4.

Expected on staging right now: the 2 moved GLs still appear as LOCKED special cells with a
dead subform button, because `dbo.gl_group` has not flipped yet. That is the intended safe
state (D4), not a defect.
