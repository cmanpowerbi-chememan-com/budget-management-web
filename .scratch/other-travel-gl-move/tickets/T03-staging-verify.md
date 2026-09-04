# T03 — Ship to staging and verify  [OPEN · blocked by T01]

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
