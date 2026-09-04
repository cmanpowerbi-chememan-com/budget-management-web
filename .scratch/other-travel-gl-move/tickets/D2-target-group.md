# D2 — Target group  [CLOSED 2026-09-04]

## Question
Which gl_group do the two GLs land in: `Other admin. Expenses`, a brand-new group, or stay in
`Travelling Expense` with a per-GL exception?

## Resolution
`Other manpower exp (Per diem,Health check,Uniform…etc)` — jakkaritw's own choice, and he had
already applied it to the SharePoint master (rows 132/133) before the question was settled.

Exact live string matters: U+2026 ellipsis, no space after the commas. A typo silently creates
a 20th group rather than failing.

Rejected: a brand-new group (group names must match SAP — they join to Accruals for dashboard
grouping); a per-GL exception in code (special-ness is decided at group grain in
`special_gl.classify_special_gl`, so an exception would break that contract everywhere).

Groups are not a table anywhere — they are distinct values of the `group` column in the
SharePoint master `gl group_gl th name.xlsx` (site CMANDWPRD, sourcedoc
43859ABF-0D0E-4CE1-B926-544F22F8A601), synced daily ~06:31 into `dbo.gl_group` by
`NB_budget_masters_sync` in workspace `cman-dw-ws`.
