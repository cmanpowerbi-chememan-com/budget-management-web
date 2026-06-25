# Feature: signoff-spec-v2 — revise manager sign-off summary docs (SpecA/B/C)

Revise the manager's 3 sign-off summary docs per the reviewed findings, producing a **version2/** set
of `.docx`. CC reviewed the manager's 11 comments (SpecA) + verified SpecB/C against the repo source specs.

**Authoritative spec (READ FIRST):**
`requirement_spec/1_software_dev/1.1_frontend/signoff_spec/manager_review/REVIEW_FINDINGS.md`
— every edit, with exact strings, evidence, and the owner's 3 decisions. This TODO is the execution plan; REVIEW_FINDINGS is the source of truth.

**Inputs** (in `requirement_spec/1_software_dev/1.1_frontend/signoff_spec/`):
- `manager_review/SpecA_หน้าหลัก_สิทธิ์_v3.docx`, `manager_review/SpecB_GL_Subform_v3.docx`, `manager_review/SpecC_Master_Tables_v3.docx`
- `manager_review/_extracted/*.txt` (extracted text of manager docs + comments JSON) and `manager_review/_extracted/sources/*.txt` (the repo's 8 source specs = "ต้นฉบับ").
- Helper tools (stdlib only — **DO NOT pip install anything**, dev machine forbids it): `tasks/signoff-spec-v2/_tools/docx_edit.py`, `_tools/docx_text.py`.

**Output:** `requirement_spec/1_software_dev/1.1_frontend/signoff_spec/version2/` containing the 3 revised docx (keep the same base filenames). The user uploads them to the SharePoint version2 folder (Cursor has no SharePoint access).

**Constraints:**
- Stdlib Python only. Edit `word/document.xml` inside the zip (target strings are contiguous — verified). Other zip members copied unchanged → valid docx.
- Do NOT change any numbers/facts (18 groups/137 accounts, per-diem table, 8 GL, FX years/range) — they were verified correct. Only fix what's listed.
- Do NOT touch the `เพิ่ม Transaction` button (it's a different, correct button).

---

## TASK-001 — Mechanical fixes (tool-driven) — Status: [x]

**Files:** `version2/SpecA_หน้าหลัก_สิทธิ์_v3.docx`, `version2/SpecB_GL_Subform_v3.docx`, `version2/SpecC_Master_Tables_v3.docx` (new), `tasks/signoff-spec-v2/edits_specA.json`

**Spec:**
1. Apply the global arrow-restore rule **`" จึง " → " → "`** to all 3 docs (the consolidation mangled flow arrows `→` into the word `จึง`; ~149 of 159 are clean space-delimited). Use `--arrows`.
2. Apply the SpecA literal edits in `edits_specA.json` (#8 button label, #2/6/7/9 `เอกสาร 02`→SpecB name, #1 Primary/Acting note, #10 approval-doc ref, #0 union clarity).

**Commands (cs):**
```powershell
$S = "requirement_spec\1_software_dev\1.1_frontend\signoff_spec"
New-Item -ItemType Directory -Force "$S\version2" | Out-Null
# SpecA: literal edits + arrows
python tasks\signoff-spec-v2\_tools\docx_edit.py --in "$S\manager_review\SpecA_หน้าหลัก_สิทธิ์_v3.docx" --out "$S\version2\SpecA_หน้าหลัก_สิทธิ์_v3.docx" --edits tasks\signoff-spec-v2\edits_specA.json --arrows
# SpecB / SpecC: arrows only here (content edits in TASK-002)
python tasks\signoff-spec-v2\_tools\docx_edit.py --in "$S\manager_review\SpecB_GL_Subform_v3.docx" --out "$S\version2\SpecB_GL_Subform_v3.docx" --arrows
python tasks\signoff-spec-v2\_tools\docx_edit.py --in "$S\manager_review\SpecC_Master_Tables_v3.docx" --out "$S\version2\SpecC_Master_Tables_v3.docx" --arrows
```

**Pre-commit (cs):**
- Read the docx_edit.py output. If any edit reports `!! NOT FOUND` or a count mismatch, the string is run-split or uses curly quotes — open the docx text (`docx_text.py`) and fix the string in edits_specA.json (or note it for TASK-002), re-run.
- `python tasks\signoff-spec-v2\_tools\docx_text.py "$S\version2\SpecA_หน้าหลัก_สิทธิ์_v3.docx" --metrics` (and B, C).
- Confirm each version2 docx still OPENS (load with `docx_text.py` without error = zip/xml intact).

**Acceptance:**
- [ ] `version2/` has all 3 docx, openable.
- [ ] metrics: `'+ ใส่รายละเอียดงบทำการ'` = **0**; `'ใส่รายละเอียดงบทำการ'` ≥ 3; `'เอกสาร approval'` = **0** (became Approval Workflow); spaced `จึง` ≈ 0.
- [ ] Numbers unchanged (spot-check per-diem table + 18/137 still present via docx_text).

---

## TASK-002 — Judgment fixes (per doc, read source + apply) — Status: [x]

**Files:** the 3 `version2/*.docx` (continue editing the TASK-001 output).

Apply by reading each doc's text + its source spec (`_extracted/sources/`) and REVIEW_FINDINGS.md §SpecB/§SpecC. Some are insertions, not replaces — locate the right sentence. For run-split strings that TASK-001 couldn't match, edit the paragraph directly.

**SpecA residuals:**
- **#1 (Primary vs Acting) — INSERT** (anchor `(ทั้งตำแหน่ง Primary และ Acting)` is run-split, so edit the paragraph directly). Add near the RLS step-1 table: `— ทั้งสองดึงจากตารางพนักงานเดียวกัน (mas_employee_data) แยกด้วยคอลัมน์ posstatus ไม่มี master แยก; ผู้รักษาการ (Acting) เห็น Cost center ของ orgcode ที่รักษาการนั้นด้วย`. (Answers manager's "ต่างกันยังไง เรามี master แยกไหม".)
- **#0 (optional)** — `(orgcode และฝ่าย)` is run-split; if easy, change to `(รวมจาก orgcode ∪ ฝ่าย)` so it reads as a union not AND. Skippable.
- **#5 (optional)** — sharpen `Cost center ที่ผู้ดูแลระบบกำหนดเพิ่มเติม` → `Cost center เพิ่มเติมจากสิทธิ์ผู้ดูแลระบบ (admin-overlay)`. Skippable.
- Run-split copies of `เอกสาร 02` / `เอกสาร approval` (if metrics still show `เอกสาร 02` without the SpecB suffix, or `เอกสาร approval` > 0, or the L486 `ดูเอกสาร 10 + เอกสาร approval`): fix them the same way (→ SpecB name / → `เอกสารกระบวนการอนุมัติ (Approval Workflow)`).
- Embedded/edge `จึง` left after TASK-001 (docx_edit listed them as `REVIEW จึง: ...`): for each, check the matching source paragraph — if source had `→`, restore the arrow; if it's legit Thai prose ("...ระบบจึง..."), leave it.
- **#4 `③` — DO NOT guess.** Open SpecA.docx in Word, find which `③` the manager's comment is anchored to. If it's the legend table in หัวข้อ 1 (no image), add the note `หมายเหตุ: สัญลักษณ์ ①–④ อ้างถึงชั้นข้อมูลในตารางหลัก ไม่ใช่ตำแหน่งในภาพ`. If it's a figure-backed `③`, confirm the embedded screenshot still shows the `③` marker. **Flag this in CURSOR_REPORT for manager confirmation.**
- **#10 exact doc title — FLAG in CURSOR_REPORT:** the label `(Approval Workflow)` is a placeholder; the manager must confirm the real standalone approval document's title/number.
- #3 (optional, nice-to-have): add the example sentence after the "ผู้อนุมัติเห็นป้ายสถานะ..." line (see REVIEW_FINDINGS #3); embedding `main_fai_picker.png` is optional.

**SpecB:** (REVIEW_FINDINGS §SpecB)
- Re-add ADR refs dropped from source: `Recompute-on-read (ADR-0015)`, `Read-only lock (ADR-0013)`.
- Add per-diem month-split rounding sentence (ADR-0005): `การแบ่งลงเดือน: แต่ละเดือนปัดทศนิยม 2 ตำแหน่ง เดือนสุดท้ายที่เลือกรับเศษที่เหลือ เพื่อให้ผลรวมทั้งปีเท่ายอดเต็มพอดี (ADR-0005)`.
- Remove the duplicated `ส่วน B` header line (two consecutive section titles).
- Machinery list: text says `11 ชนิด` but lists 10 + "…" — verify vs `docs/13Template Special*` and fix count or complete the list.
- `Azure AD` → `Azure Entra ID` if present.

**SpecC:** (REVIEW_FINDINGS §SpecC)
- Re-add ALL ADR refs (SpecC currently has ZERO "ADR"; leaves dangling `(ตาม)`): closing-date `ADR-0012` (~5 spots), orgcode-cc `ADR-0007` (2 spots), hide-doc `ADR-0010` (2 spots), currency `ADR-0015` + superseded `ADR-0011`.
- `Azure AD` → `Azure Entra ID` (4 spots) — suggest form `Microsoft Entra ID (เดิม Azure AD)`.
- Restore `— first year` (currency 2.4, became `: first year`).
- Verify closing-date breadcrumb `Module 10 · Submission Deadline` vs the prototype (should it be 06?). Note in report; only change if confirmed wrong.
- Separator labels where `·` became `:` in UI labels (e.g. `Module 03 · Master Data`) — restore where it's clearly a label, not a list colon.

**Pre-commit (cs):**
- Re-run `docx_text.py --metrics` on all 3: `Azure AD` = 0 / `Entra ID` > 0 (SpecC); `ADR-` > 0 in B and C; `เอกสาร approval` = 0.
- Confirm all 3 still open.

**Acceptance:**
- [ ] All SpecA 11 comments resolved (see REVIEW_FINDINGS checklist); #4 + #10-title flagged for manager.
- [ ] SpecB: ADR-0013/0015 present, rounding rule added, dup header gone, machinery count reconciled.
- [ ] SpecC: ADR refs present (no dangling `(ตาม)`), `Azure AD`→`Entra ID`, `— first year` restored.
- [ ] No facts/numbers changed.

---

## Notes for cs
- One commit per task: `[cursor-done] TASK-001 mechanical fixes` then `[cursor-done] TASK-002 judgment fixes` (or combine if done together).
- Write `tasks/signoff-spec-v2/CURSOR_REPORT.md`: list every change, the docx_text metrics before/after, the residual `จึง` decisions, and the **2 manager-flags (#4 ③ anchor, #10 approval doc title)**.
- Commit the version2 docx + edits json + tools + report. Leave `manager_review/` inputs as-is (do not delete).
- This repo has no `tasks/sync_summary.ps1` (dashboard infra not set up) — skip that step.
