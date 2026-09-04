# D8 — The dict edit is a money-loss fix  [CLOSED 2026-09-04]

## Question
Is removing `other` from `TRAVEL_GL_BY_TYPE_SIDE` cosmetic cleanup or a correctness fix?

## Resolution
A correctness fix, and the most load-bearing finding of the whole effort.

`TRAVEL_GL_BY_TYPE_SIDE` drives two trip-lifecycle loops — the side-flip re-home branch
(`write_model.py:~1564`) and `_delete_one_trip` (`~1797`). Both call `_recompute_parent_cell`
then `_delete_parent_if_orphaned` for every travel GL. Once the master flips, these 2 GLs are
plain monthly cells with no detail lines, so the recompute sets the cell to SUM(detail) = 0
and the orphan guard (remark IS NULL, total_year = 0, no detail lines) then deletes the row.

Concretely: a Filler types 500,000 THB into the new plain `6210400999` cell; an unrelated
colleague deletes any trip on the same cost_center + fiscal_year; the 500,000 is silently
zeroed and the row disappears. No error, no log, no email.

Latent until now only because the GLs were still trip-driven. Closed by construction (the
dict no longer contains them) and pinned by a regression test that was confirmed RED against
the pre-fix dict.
