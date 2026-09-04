# Runbook — from here to verified in production

Ordered. Each step names what must be true before the next one starts.

## 0. Gate verdict  (running)
Combined 06+07+08. A REQUEST CHANGES verdict stops everything below.

## 1. Wipe the leftover row   ← BLOCKED ON jakkaritw's APPROVAL
`python -X utf8 setup/wipe_other_travel_gl_rows.py` (dry run, already verified) then `--apply`.
Target: detail_id 248 (gl 6210400999, 0.00 THB) on trip 50 + its 0.00 parent row.
MUST survive: detail 245 per-diem 500.00, 246 transport 1,000.00, 247 accommodation 3,000.00,
and trip 50 itself.
Verify after: script re-surveys and must print `0 detail line(s), 0 parent row(s)`.
Do this while old code + old master are still coherent (D6).

## 2. Commit — this session's hunks ONLY
Stage exactly: `backend/app/write_model.py`, `backend/tests/test_write_model.py`,
`backend/tests/test_integration_live.py`, `docs/reference/special-gl-dropdown-fixture.json`,
`docs/reference/gl-master.md`, `frontend/src/subform/{glDropdownConstants.ts,model.ts,
model.test.ts,TripManager.tsx,TripManager.test.tsx}`, `.claude/plan.md`, `tracker/*.json`,
`setup/wipe_other_travel_gl_rows.py`, `.scratch/other-travel-gl-move/`.
NEVER stage: `setup/phase2_harness_dkl.py` (another session's auto-escalate removal) or
`frontend/next-env.d.ts` (build artifact).
Commit locally. Do NOT push unless jakkaritw asks (standing preference).

## 3. Build + staging deploy
Build from a CLEAN DETACHED WORKTREE — the main tree carries other sessions' leftovers:
`git worktree add --detach <scratch>/wt-<sha> <sha>`
`az acr build --registry cmanbudgetacr --image budget-web:<sha> --file backend/Dockerfile .`
`az containerapp update -n cman-budget-web-stg -g CMAN-BUDGET-MNGT-WEB-RG --image cmanbudgetacr.azurecr.io/budget-web:<sha>`
Traps: `az acr build` exits 1 here on a warn glyph even when it succeeded — judge by
`az acr task list-runs --registry cmanbudgetacr --top 2 -o tsv --query "[].{id:runId,status:status,img:outputImages[0].tag}"`.
Never use `--run-id ... --query "[0].status"` (returns empty, spins forever).

## 4. Verify on staging
Trip Manager shows 3 expense rows; the 2 GLs are absent from it. Master has NOT flipped yet,
so on staging the 2 GLs still render as locked special cells with a dead subform button —
that is EXPECTED and is exactly the safe state (D4). Headless Playwright + `page.evaluate()`
assertions; screenshots to disk, never read into context.

## 5. Production deploy   ← REQUIRES jakkaritw's APPROVAL (never-cut)
Same image, `cman-budget-web-prd`. Then verify the revision is Running/Healthy/100 and
confirm the deploy actually landed (never-cut: verify-deploy-landed).

## 6. Flip the master into the app
Either let the daily sync run (~06:31) or trigger it scoped:
Fabric REST `POST /v1/workspaces/{cman-dw-ws}/items/{NB_budget_masters_sync}/jobs/instances?jobType=RunNotebook`
with `only_spec = "Budget_Masters_gl_group"` (~1.5 min). No cache to purge; users just refresh.

## 7. Verify the flip  (ticket T05)
Both GLs under exactly `Other manpower exp (Per diem,Health check,Uniform…etc)`;
`edit_by` still `user` on both (an accidental `admin` would hide the rows AND move those
amounts out of the department's approval lane); distinct group count still 19 — a 20th group
name means a typo in the Excel; Travelling Expense 8 → 6, target group 10 → 12.

## Rollback
Redeploy the previous revision. NOTE: a code rollback does NOT roll back the master flip, so
it re-opens the broken window — if the code is rolled back, the Excel must be reverted too.
