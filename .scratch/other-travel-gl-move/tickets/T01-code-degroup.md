# T01 — Remove the other-travel pair from the trip subform  [CLOSED 2026-09-04 · awaiting gate verdict]

Type: `wayfinder:task` (AFK) · blocks T02, T03

## Question
What code must change so Trip Manager stops rendering/saving `5210400999`/`6210400999`, and
so a plain `PUT /budget/rows` edit on them is accepted once the master flips?

## Status
Dispatched to 05-software-developer 2026-09-04. Scope: `write_model.TRAVEL_GL_BY_TYPE_SIDE`
and every consumer; `glDropdownConstants.TRAVEL_GL_BY_TYPE_SIDE` / `MANUAL_TRAVEL_TYPES` /
`TRAVEL_TYPE_LABEL_TH` and every consumer; tests updated not weakened; `docs/reference/
gl-master.md`; `.claude/plan.md`. Out: `SPECIAL_GL_GROUPS`, the .docx sign-off specs, deploy.
Verification required: backend pytest, frontend vitest, and `npx next build` (vitest does not
type-check — that combination has shipped red CI here before).

## Resolution
Done, uncommitted. Two latent defects closed along the way — see D8 (silent zeroing) and the
fail-open on the COST/SGA side check (`_TRAVEL_GL_SIDE.get()` returned `None`, so the check
skipped rather than rejected; now any GL not in `_TRAVEL_GL_SIDE` is rejected inside the
`Travelling Expense` branch). A third source of truth turned up beyond the original brief:
`docs/reference/special-gl-dropdown-fixture.json`, which both sides' parity tests assert
against.

Verified: backend 1114 passed / 48 deselected; frontend 792 passed; `npx next build` clean;
`checks.sh` secret scan passed. Also corrected a wrong claim written into `.claude/plan.md`:
`not_special_gl` maps to HTTP **400**, not 403 (`write_model.py:255`).
