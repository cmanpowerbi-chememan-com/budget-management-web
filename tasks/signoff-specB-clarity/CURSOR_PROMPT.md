Implement tasks/signoff-specB-clarity/TODO.md.

Context: revise the Thai sign-off doc `requirement_spec/1_software_dev/1.1_frontend/signoff_spec/version2/SpecB_GL_Subform_v3.docx`
for readability/concision — SAME concept as the SpecC polish CC just shipped (commit e3a5e39), but SpecB is
run-fragmented so you edit by **paragraph** (collapse) not run-id. CC has pre-built + PROVED 3 stdlib tools in
`tasks/signoff-spec-v2/_tools/` (extract_paras.py, apply_paras.py, check_paras.py) — USE them, do not reinvent
OOXML editing. The TODO has the full house-style, the facts you must NOT drop, the version/changelog targets
(para 28 → v0.4.1; para 36 changelog), and the exact command sequence.

Hard rules:
- Stdlib Python ONLY — NEVER `pip install` (dev machine blocks installs). Run all python with `PYTHONUTF8=1`.
- Wording only. Do NOT change any number/fact/table-id/`/api` path/ADR/marker ①–⑤/section number/quoted UI
  string/`เพิ่ม Transaction` button. Copy facts verbatim from the OLD paragraph text into your rewrite.
- Do NOT touch paragraphs flagged `skip:true` by extract_paras (images/hyperlinks/mixed-bold/empty).
- `check_paras.py` MUST print `PASS` before you apply. A DROP flag = you lost a fact; an OVERLAP flag = your
  edit hit the WRONG paragraph index (the bug class that bit CC on SpecC). Fix and re-run — never apply on a non-PASS.
- apply_paras writes in place and validates XML; if it raises, do not commit.

For TASK-001:
1. Do all work in "Process" + "Files" + "Spec".
2. Run every "Pre-commit (cs)" check — do NOT commit if any fails.
3. Write tasks/signoff-specB-clarity/CURSOR_REPORT.md (paragraphs rewritten w/ a few before/after, check_paras
   PASS output, version/changelog change, confirm skip-paras + `เพิ่ม Transaction` untouched).
4. Change `- Status: [ ]` → `- Status: [x]`.
5. Commit: `[cursor-done] TASK-001 SpecB clarity polish` (one commit). Include: the edited docx,
   edits_specB_clarity.json, parasB.json, the 3 `_tools/*paras*.py`, CURSOR_REPORT.md, TODO.md.
6. Touch ONLY files listed in the item's "Files" (+ TODO.md, CURSOR_REPORT.md, CURSOR_PROMPT.md).
   This repo has NO tasks/sync_summary.ps1 — SKIP the dashboard step.

Verify, don't assume: if check_paras flags anything, inspect that paragraph's OLD vs NEW and correct the edit
before applying. The manager signs this doc — fidelity first, brevity second.
