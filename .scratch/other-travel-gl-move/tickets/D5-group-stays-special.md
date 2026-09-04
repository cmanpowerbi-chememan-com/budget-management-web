# D5 — Travelling Expense stays a special group  [CLOSED 2026-09-04]

## Question
Does removing 2 of its 8 GLs change the group's own status?

## Resolution
No. `SPECIAL_GL_GROUPS` (`backend/app/special_gl.py:16`) keeps all 6 names; only membership
shrinks, 8 GLs → 6 (3 types x 2 sides). `test_special_gl_groups_constant_has_exactly_six_entries`
must still pass untouched.
