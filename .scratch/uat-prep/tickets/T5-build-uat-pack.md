# T5 — Build the UAT pack in `requirement_spec/5_uat/`

Type: `wayfinder:task` (AFK) · Status: OPEN · Blocked by: **D1, D3, D4, D7**

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
