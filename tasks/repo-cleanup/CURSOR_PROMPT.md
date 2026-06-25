Implement tasks/repo-cleanup/TODO.md.

This is a DESTRUCTIVE cleanup with a USER-APPROVED EXACT LIST. Critical rules:

1. Delete ONLY the paths listed in buckets A/B/C/D/F. Do NOT search for additional "unused" files.
   Do NOT use judgment to delete extra things. The list is the whole job.
2. This repo has MANY pre-existing uncommitted changes from before this task (modified .html/.js,
   project-context.md, graphify-out/*, a modified _build script, a deleted index.html, etc.). These are
   NOT in scope. Do NOT stage them, modify them, revert them, or delete them. Leave them byte-for-byte.
3. NEVER use `git add -A` or `git add .` — that would sweep the unrelated pre-existing changes into your
   commit. Use explicit pathspecs for ONLY the bucket D/E/F paths.
4. Buckets A/B/C are untracked/gitignored → delete from disk with rm (they won't appear in the commit).
   Bucket D/F → `git rm` (tracked). Bucket E → `git add` the one file.
5. KEEP the 9 reusable `_tools/*.py` (docx_text, docx_edit, extract_runs, apply_runs, check_preservation,
   build_clarity_edits, extract_paras, apply_paras, check_paras) and the kept task files. Do NOT delete index.html.
6. `PYTHONUTF8=1` for any python. Stdlib only, no installs.

For TASK-001:
1. Do all bucket work exactly as listed.
2. Run every "Pre-commit (cs)" check. Do NOT commit if any fails — especially the check that the
   pre-existing unrelated changes are still shown in `git status --short` and were NOT staged.
3. Write tasks/repo-cleanup/CURSOR_REPORT.md (what was deleted per bucket, what was committed, keepers
   confirmed present, and paste `git status --short` proving unrelated changes untouched).
4. Set `- Status: [ ]` → `- Status: [x]`.
5. Commit: `[cursor-done] TASK-001 repo cleanup` — staging ONLY bucket D (git rm tools), E (CURSOR_PROMPT.md),
   F (git rm 3 version2 docx). Verify with `git status --short` before committing that nothing unrelated is staged.
6. This repo has NO tasks/sync_summary.ps1 — SKIP the dashboard step.

If `git rm` on a version2 docx errors because the file is already deleted from the working tree, use
`git rm -- "<path>"` (git still stages the index removal) — confirm with `git ls-files` afterward that the
3 docx are gone from the index.
