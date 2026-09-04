# D7 — The deadline is 2026-09-05 ~06:31  [CLOSED 2026-09-04]

## Question
When exactly does the master flip reach the app?

## Resolution
The next daily sync. `dbo.submission_deadline._load_dttm` = 2026-09-04 06:31:55 shows today's
run finished BEFORE jakkaritw edited the Excel, and `dbo.gl_group` still reads
`Travelling Expense` for both GLs — so nothing has flipped yet and the next run owns it.

The window is controllable: the sync can be triggered on demand, scoped to this one master
(`only_spec=Budget_Masters_gl_group`, ~1.5 min), so the dead-row window after deploy can be
minutes instead of a day.
