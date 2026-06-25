# TASK-001 repo cleanup — Cursor report

Completed: 2026-06-26

## Bucket A — temp junk (plain delete)

- `tasks/_tmp_img/` (whole dir)
- `tasks/_tmp_jung_all.txt`
- `tasks/_tmp_jung_left.txt`
- `tasks/_tmp_jung_result.txt`

## Bucket B — superseded one-off scripts (plain delete)

- `tasks/signoff-spec-v2/_tools/apply_specb_clarity.py`
- `tasks/signoff-spec-v2/_tools/apply_specb_eng.py`
- `tasks/signoff-spec-v2/_tools/patch_ent_ext_options.py`
- `tasks/signoff-spec-v2/_tools/patch_jung_arrows.py`
- `tasks/signoff-spec-v2/_tools/rebuild_specb.py`
- `tasks/signoff-spec-v2/_tools/scan_specb_thai.py`
- `tasks/signoff-spec-v2/_tools/__pycache__/` (whole dir)

## Bucket C — bin/ throwaway (plain delete)

- `bin/temp-verify/` (whole dir)
- `bin/verify_0008/` (whole dir)
- `bin/verify_01_load.png`
- `bin/verify_02_cc_open.png`
- `bin/verify_03_cc_selected.png`
- `bin/verify_04_org_selected.png`
- `bin/verify_05_by_org.png`
- `bin/verify_06_save.png`
- `bin/verify_07_duplicate.png`
- `bin/verify_screenshot.png`
- `bin/verify_special_entertainment.png`
- `bin/verify_special_lease_building.png`
- `bin/verify_special_training.png`
- `bin/verify_special_width.png`

## Bucket D — git rm (tracked one-off tools)

- `tasks/signoff-spec-v2/_tools/apply_task2.py`
- `tasks/signoff-spec-v2/_tools/patch_task2.py`
- `tasks/signoff-spec-v2/_tools/find_fragments.py`
- `tasks/signoff-spec-v2/_tools/probe_xml.py`
- `tasks/signoff-spec-v2/edits_specA.json`

## Bucket E — committed (git add)

- `tasks/signoff-specB-clarity/CURSOR_PROMPT.md`

## Bucket F — git rm (version2 docx, already deleted from working tree)

- `requirement_spec/1_software_dev/1.1_frontend/signoff_spec/version2/SpecA_หน้าหลัก_สิทธิ์_v3.docx`
- `requirement_spec/1_software_dev/1.1_frontend/signoff_spec/version2/SpecB_GL_Subform_v3.docx`
- `requirement_spec/1_software_dev/1.1_frontend/signoff_spec/version2/SpecC_Master_Tables_v3.docx`

## Keepers confirmed present

**9 reusable `_tools/*.py`:**

- `docx_text.py`, `docx_edit.py`, `extract_runs.py`, `apply_runs.py`, `check_preservation.py`
- `build_clarity_edits.py`, `extract_paras.py`, `apply_paras.py`, `check_paras.py`

**Kept task files:**

- `tasks/signoff-spec-v2/TODO.md`, `CURSOR_PROMPT.md`, `CURSOR_REPORT.md`, `edits_specC_clarity.json`
- `tasks/signoff-specB-clarity/` (directory intact)

**bin/ keepers untouched:** `azure-sql-legacy/`, `old-mockups/`, `streamlit-scaffold/`, `style_reference/`, `diagnostic-scripts/`, capture PNGs (`bcd_*`, `mc_*`, `main_*`, `sub_*`, `wa_*`, `0011_*`, `bcd_coords.json`).

## Pre-commit checks

| Check | Result |
|-------|--------|
| A/B/C paths gone from disk | PASS |
| D paths not in `git ls-files` | PASS (0 hits) |
| E in `git ls-files` | PASS |
| F docx not in `git ls-files` | PASS (0 hits) |
| 9 keeper tools + kept task files | PASS |
| Unrelated pre-existing changes untouched | PASS (see status below) |

## Commit contents (staged only)

- Bucket D: 5 deletions (4 `_tools/*.py` + `edits_specA.json`)
- Bucket E: 1 addition (`CURSOR_PROMPT.md`)
- Bucket F: 3 docx deletions

## `git status --short` (unrelated changes still present, not staged)

```
 M .claude/project-context.md
 M 03-edit-master-table/master-tables/01frontend/hide-document.html
 D 03-edit-master-table/master-tables/01frontend/index.html
 M 03-edit-master-table/master-tables/01frontend/shared/gl-group.js
 M 03-edit-master-table/master-tables/01frontend/shared/orgcode-cc.js
 M "design/mockups/0002claude design/0002.1budget-export.html"
 M graphify-out/GRAPH_REPORT.md
 M graphify-out/graph.html
 M requirement_spec/1_software_dev/1.1_frontend/signoff_spec/_build/build_special_gl_subform_spec.py
D  requirement_spec/.../version2/SpecA_*.docx  (staged — bucket F)
D  requirement_spec/.../version2/SpecB_GL_Subform_v3.docx  (staged — bucket F)
D  requirement_spec/.../version2/SpecC_Master_Tables_v3.docx  (staged — bucket F)
D  tasks/signoff-spec-v2/_tools/apply_task2.py  (staged — bucket D)
D  tasks/signoff-spec-v2/_tools/find_fragments.py  (staged — bucket D)
D  tasks/signoff-spec-v2/_tools/patch_task2.py  (staged — bucket D)
D  tasks/signoff-spec-v2/_tools/probe_xml.py  (staged — bucket D)
D  tasks/signoff-spec-v2/edits_specA.json  (staged — bucket D)
A  tasks/signoff-specB-clarity/CURSOR_PROMPT.md  (staged — bucket E)
 M tasks/signoff-specB-clarity/TODO.md
?? tasks/repo-cleanup/
```

Dashboard step skipped — no `tasks/sync_summary.ps1` in this repo.
