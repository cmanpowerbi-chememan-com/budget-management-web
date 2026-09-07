# T5 — Build the UAT pack in `requirement_spec/5_uat/`

Type: `wayfinder:task` (AFK) · Status: **SPLIT — part A in progress, part B still blocked**
Claimed by: session 2026-09-07 (`uat-test-script-doc` in the ledger)
Blocked by: ~~D1~~ closed · ~~D3~~ closed · ~~D4~~ closed · **D7 (part B only)**

## Split, 2026-09-07

jakkaritw asked for "the UAT script doc, referencing the SIT workbook, adjusted for UAT scope,
easy to test and comprehend, placed at `requirement_spec/5_uat`". That is part A of this ticket,
and every decision it depends on (D1 environment, D3 roles, D4 pack scope) is already closed —
only the entry/exit criteria file waits on D7. So T5 splits:

**Part A — the test script (IN PROGRESS, this session).** **54 cases** across 8 waves and 8
modules: the business-acceptance subset of the SIT 61 that D4 chose, the ~25 new-behaviour cases
from `research/post-sit-changes.md` §7, and 13 more that `research/sit-coverage-gaps.md` §3 marks
"UAT: IN SCOPE" but D4's resolution text did not enumerate — the whole Attachments feature (5),
per-diem arithmetic the business can hand-check (2), the Approved and SAP layers (2), the admin
mode toggle, the year lock, the grid ergonomics block, and deleting a hand-added row. Delivers:
the workbook, a Thai companion `UAT_Test_Script.md`, a generator and a validator under `_build/`.
Brief: `.scratch/uat-prep/_T5_brief.md` (REVISION 2).

**De-duplication pass, approved by jakkaritw 2026-09-07: 68 → 54.** The first draft gave every
assertion its own row. jakkaritw asked which were duplicated or unimportant, and approved the
cut. Thirteen cases were **merged** into a neighbour they already shared a screen and a
click-path with — the `+N` chip overflow into the login case; the six money-input values
(146 / 30 / 999999999 / 33333.33 / letters / negatives) into one `Test Data` table; Public
Relation & Donation into Entertainment; destination search and the trip remark into the
create-trip case; open-detail and the step-2/3 title chips into the Reject/Approve case; the
step-2 and approved mails into one chain case; the step-override mail into the step-override
screen case; and the Thai-truncation checks into the CI-palette sweep. One case was **cut
outright**: SIT `TC-034` concurrent edit in two windows, which jakkaritw already judged Pass on
2026-08-20 while waiving 3 of its 4 sub-cases because the numbers refresh immediately.

**Coverage was not reduced** — a merged case is one row carrying several checks, and the
validator's check 9 asserts that every absorbed SIT id and all of U-01…U-25 still appear in the
traceability table. Nothing on the never-cut list moved: the money rules, the submitted-total
reconcile, the per-diem arithmetic, the silent-money-loss case, the seminar-GL regression, the
irreversible attachment delete and `Approved`, and the whole two-department premise all keep
their own rows.

**Part B — the gate artifacts (STILL BLOCKED by D7).** `UAT_Entry_Exit_Criteria.md`, the two
1-page Thai guides, the acceptance sign-off sheet, `assets/` screenshots, and any SharePoint
upload. None of these can be written before the window and the pass/fail rule exist.

## Question

Produce the business-facing pack, following this project's own conventions rather than inventing
new ones.

## Proposed contents

```
requirement_spec/5_uat/
├── Budget_UAT_Test_Cases_<DD.MM.YYYY>.xlsx     the pack (committed snapshot; SharePoint is live)
├── UAT_Entry_Exit_Criteria.md                  Thai, the Go/No-Go gate (from D7)
├── assets/                                     Playwright-captured screenshots for the guides
├── jakkaritw/
│   ├── UAT_คู่มือผู้กรอกงบ_1หน้า_V1.0.docx
│   ├── UAT_คู่มือผู้อนุมัติ_1หน้า_V1.0.docx
│   └── UAT_ใบรับรองผลการทดสอบ_V1.0.docx        acceptance sign-off sheet
└── _build/
    ├── build_uat_test_cases.py
    ├── build_uat_user_guides.py
    ├── _capture_uat_screens.py
    └── _validate_uat_pack.py
```

## Work

1. **The workbook** — same 4-sheet / 16-column / header-row-2 / data-from-row-4 shape as the SIT
   workbook so returning testers need zero re-learning. Changes: `Environment` = the D1 URL ·
   `Test Phase` = "User Acceptance Test (UAT)" · **`Departments under test` = both** · five role
   rows spelling out each attendee's department coverage (this is where D3 gets recorded) · a new
   **`Department` column** on `2. Test Cases` · a **`4. Defects` sheet** (prefer a sheet over a
   separate file, per the extend-don't-create rule) carrying the numbered / blocker-major-minor /
   owner / date register that the SIT workbook never had.
2. **Fix the three inherited workbook defects**: add the missing `Special GL Subform` row to the
   Summary breakdown; add the promised Defect ID column; extend the hard-coded `$4:$64` ranges,
   the autofilter and the three dropdown validations to the real last row.
3. **The two 1-page Thai guides** — the filler guide already exists as prose at
   `plan/sit/sit-test-plan.md:1011-1035` and needs re-targeting; **the approver guide does not
   exist yet**. Build both with the existing no-install WordprocessingML + Pillow pattern.
4. **The sign-off sheet** — `sign_table()` in the signoff_spec build scripts already renders
   exactly this block.
5. **Reuse, do not re-implement.** `setup/update_sit_test_cases.py` and
   `setup/fill_sit_test_case_gaps.py` already own the SharePoint `_get_token / _share_id /
   resolve_item / download / upload` helpers and the `_save_workbook / _preserve_sharepoint_parts
   / verify_binary_parts` label splice. Lift them into a shared `setup/sharepoint_xlsx.py` rather
   than copy-pasting a third time. Keep `--upload` off by default.
6. **Validate** — mirror `_validate_docx.py`: sheet count, headers on row 2, Summary ranges
   ending at the real last row, dropdown coverage, `customXml/*` + `docMetadata/LabelInfo.xml`
   surviving the save, and an assertion that the D1 URL appears and the other one does not.

## Constraints

- `openpyxl` saves strip the sensitivity label — every upload since pass 1 dropped it before the
  splice fix existed. The validator must prove the parts survived.
- Mark AI-written cells purple `7030A0`, per the SIT workbook editing protocol.
- Never read a screenshot into an agent's context. Save to disk, give the path, stop for
  jakkaritw to review.

## Definition of done

Every file above exists · the validator passes · jakkaritw has eyeballed the guides and the
workbook · nothing was uploaded to SharePoint without explicit approval.
