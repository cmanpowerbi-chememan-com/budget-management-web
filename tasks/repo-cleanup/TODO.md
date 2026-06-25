# Feature: repo-cleanup — delete unused files + tidy (user-approved buckets A/B/C/D + E + version2 git rm)

User approved an EXACT list (below). **Delete ONLY these paths. Do NOT hunt for more "unused" files,
do NOT touch anything not on this list.** The repo has many PRE-EXISTING uncommitted changes from
before this task — they are NOT yours to stage, modify, revert, or delete:
`.claude/project-context.md`, `03-edit-master-table/master-tables/01frontend/{hide-document.html,index.html,shared/gl-group.js,shared/orgcode-cc.js}`,
`design/mockups/0002claude design/0002.1budget-export.html`, `graphify-out/*`,
`requirement_spec/.../signoff_spec/_build/build_special_gl_subform_spec.py`, and the other `?? ` untracked items
not listed below. Leave all of those exactly as they are.

`PYTHONUTF8=1` for any python. Stdlib only, no installs.

---

## TASK-001 — Delete approved buckets + stage tracked changes — Status: [x]

### Bucket A — temp junk (untracked → plain delete, not git)
- `tasks/_tmp_img/`  (whole dir)
- `tasks/_tmp_jung_all.txt`
- `tasks/_tmp_jung_left.txt`
- `tasks/_tmp_jung_result.txt`

### Bucket B — superseded one-off scripts (untracked → plain delete)
- `tasks/signoff-spec-v2/_tools/apply_specb_clarity.py`
- `tasks/signoff-spec-v2/_tools/apply_specb_eng.py`
- `tasks/signoff-spec-v2/_tools/patch_ent_ext_options.py`
- `tasks/signoff-spec-v2/_tools/patch_jung_arrows.py`
- `tasks/signoff-spec-v2/_tools/rebuild_specb.py`
- `tasks/signoff-spec-v2/_tools/scan_specb_thai.py`
- `tasks/signoff-spec-v2/_tools/__pycache__/`  (whole dir — gitignored regenerable cache)

### Bucket C — bin/ throwaway (gitignored local → plain delete)
- `bin/temp-verify/`  (whole dir)
- `bin/verify_0008/`  (whole dir)
- `bin/verify_*.png`  (loose verify screenshots in bin root ONLY — e.g. verify_01_load.png … verify_07_duplicate.png, verify_screenshot.png, verify_special_*.png)
- **KEEP** everything else in bin/: `azure-sql-legacy/`, `old-mockups/`, `streamlit-scaffold/`, `style_reference/`, `diagnostic-scripts/`, and all capture PNGs (bcd_*, mc_*, main_*, sub_*, wa_*, 0011_*, bcd_coords.json).

### Bucket D — done one-off tools (TRACKED → `git rm`)
- `tasks/signoff-spec-v2/_tools/apply_task2.py`
- `tasks/signoff-spec-v2/_tools/patch_task2.py`
- `tasks/signoff-spec-v2/_tools/find_fragments.py`
- `tasks/signoff-spec-v2/_tools/probe_xml.py`
- `tasks/signoff-spec-v2/edits_specA.json`

### Bucket E — stray file to COMMIT (git add, do NOT delete)
- `tasks/signoff-specB-clarity/CURSOR_PROMPT.md`  → `git add`

### Bucket F — version2 docx (TRACKED, already deleted from working tree → stage the deletion with `git rm`)
- `requirement_spec/1_software_dev/1.1_frontend/signoff_spec/version2/SpecA_หน้าหลัก_สิทธิ์_v3.docx`
- `requirement_spec/1_software_dev/1.1_frontend/signoff_spec/version2/SpecB_GL_Subform_v3.docx`
- `requirement_spec/1_software_dev/1.1_frontend/signoff_spec/version2/SpecC_Master_Tables_v3.docx`
  (these live on SharePoint now; git history keeps them. If `git rm <path>` says the file is already gone,
   use `git rm -- <path>` or `git add -A -- <that version2 dir>` to stage the deletions.)

> DO NOT git rm `03-edit-master-table/.../01frontend/index.html` even though it shows deleted — NOT in scope, may be a deployed SWA file. Leave it.

### KEEPERS (must still exist after) — reusable tools, do NOT delete:
`_tools/`: docx_text.py, docx_edit.py, extract_runs.py, apply_runs.py, check_preservation.py, build_clarity_edits.py, extract_paras.py, apply_paras.py, check_paras.py.
Also keep: `tasks/signoff-spec-v2/{TODO.md,CURSOR_PROMPT.md,CURSOR_REPORT.md,edits_specC_clarity.json}`, all of `tasks/signoff-specB-clarity/`.

### Pre-commit (cs) — do NOT commit if any fails:
- A/B/C paths gone from disk (`ls` → not found).
- D paths no longer in `git ls-files` (git-removed).
- E: `git ls-files tasks/signoff-specB-clarity/CURSOR_PROMPT.md` now lists it.
- F: the 3 version2 docx no longer in `git ls-files`.
- KEEPERS still present (9 reusable `_tools/*.py` + the kept task files).
- **The pre-existing unrelated changes are UNTOUCHED**: `git status --short` still shows the same ` M`/` D` lines for project-context.md, the .html/.js files, graphify-out, _build script, index.html (you neither staged nor reverted them).

### Acceptance:
- [ ] Buckets A/B/C deleted from disk; D/F git-removed; E committed.
- [ ] All 9 keeper tools + kept task files still present.
- [ ] Only the cleanup paths are staged in the commit — no unrelated pre-existing changes swept in.
- [ ] Commit is `[cursor-done] TASK-001 repo cleanup`.

---

## Notes for cs
- Stdlib/CLI only, no installs. This repo has NO `tasks/sync_summary.ps1` — SKIP the dashboard step.
- ONE commit `[cursor-done] TASK-001 repo cleanup`. The commit will contain only: D (removed tools),
  E (added CURSOR_PROMPT.md), F (removed 3 version2 docx). A/B/C are untracked/gitignored so they
  won't appear in the commit — that's expected; still delete them from disk.
- `git add` ONLY the bucket D/E/F paths. Use explicit pathspecs — never `git add -A` / `git add .`
  (would sweep the pre-existing unrelated changes). 
- Write `tasks/repo-cleanup/CURSOR_REPORT.md`: list exactly what was deleted (A/B/C/D/F) + committed (E),
  confirm keepers present, and confirm `git status` unrelated changes untouched (paste the short status).
- Touch only: the listed paths + this TODO + CURSOR_REPORT.md.
