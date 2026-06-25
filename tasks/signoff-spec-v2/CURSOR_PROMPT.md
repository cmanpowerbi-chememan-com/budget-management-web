Implement tasks/signoff-spec-v2/TODO.md.

Context: You are revising 3 Thai-language sign-off summary `.docx` (SpecA/B/C) that a manager
(Laddawan) made by consolidating the team's 8 detailed module specs. CC has already done the
review. The authoritative spec with every exact edit + evidence is:
  requirement_spec/1_software_dev/1.1_frontend/signoff_spec/manager_review/REVIEW_FINDINGS.md
READ IT FIRST, then TODO.md.

Key facts to respect:
- Stdlib Python ONLY. NEVER `pip install` (python-docx etc.) — the dev machine blocks all installs.
  Edit `word/document.xml` inside the .docx zip with literal string replace (target strings are
  contiguous — verified). Use the provided tools: tasks/signoff-spec-v2/_tools/docx_edit.py (apply
  edits + the " จึง "→" → " arrow rule) and _tools/docx_text.py (extract text + --metrics to verify).
- Output goes to a NEW folder requirement_spec/1_software_dev/1.1_frontend/signoff_spec/version2/
  (same base filenames). The user uploads to SharePoint; you have no SharePoint access.
- Do NOT change numbers/facts (18 groups/137 accounts, per-diem table, 8 GL, FX years/range) — verified correct.
- Do NOT touch the `เพิ่ม Transaction` button (different, correct button).

For each task item in TODO.md:
1. Complete all work in "Files" and "Spec". TASK-001 is tool-driven (mechanical); TASK-002 is judgment
   (read the matching source spec in manager_review/_extracted/sources/ before editing).
2. Run every command in "Pre-commit (cs):" — verify each version2 docx OPENS and the docx_text --metrics
   acceptance numbers are met. Do NOT commit if a docx fails to open or a metric is wrong.
3. Write tasks/signoff-spec-v2/CURSOR_REPORT.md: list every change, docx_text metrics before/after per
   doc, your decision on each residual `จึง`, and clearly surface the TWO items that need the MANAGER:
   (a) comment #4 — which `③` the comment is anchored to; (b) comment #10 — the exact title/number of
   the standalone approval document (you leave "(Approval Workflow)" as a placeholder).
4. Change `- Status: [ ]` → `- Status: [x]` for each completed task.
5. Commit: `[cursor-done] TASK-001 ...` and `[cursor-done] TASK-002 ...` (one per task, or combined).
   Commit the version2/ docx, edits json, _tools, and CURSOR_REPORT.md. Do NOT delete manager_review/ inputs.
6. Touch only: version2/*, tasks/signoff-spec-v2/* (TODO.md, edits_specA.json, _tools/*, CURSOR_REPORT.md).
   This repo has NO tasks/sync_summary.ps1 — skip the dashboard step.

Important: if docx_edit.py reports `!! NOT FOUND` or a count mismatch for any literal edit, the string is
run-split or uses curly quotes (“ ” / NBSP) — inspect with docx_text.py, correct the find-string, re-run.
Verify, don't assume.
