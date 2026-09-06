## 1. `requirement_spec\` full inventory (105 files tracked by git)

Top level has **four** numbered folders — `1_software_dev`, `3_approval_workflow`, `4_sit`, `5_uat`. **There is no `2_*` folder** (numbering gap, no trace of one in `git log --diff-filter=A`). No `README.md` at any level.

**`1_software_dev\1.1_frontend\signoff_spec\`** — the only deep tree, and the project's richest convention:
- `assets\` — 69 PNGs, prefix-namespaced per spec module: `main_*` (13), `sub_*` (12), `mc_*` (6), `occ_*` (7), `bcd_*` (6), `hd_*` (5), `speca2_*` (4), `wa_*` (5), `01_..07_*` (7), plus 6 `★`-prefixed files (`★entertainment_subform.png`, `★sub_prof_filled.png`, …) marking hand-picked hero shots.
- `jakkaritw\` — 8 working `.docx`, numbered by module: `01_main_web_app_spec.docx`, `01_special_gl_subform_spec.docx`, `03_edit_gl_group_spec.docx`, `06_budget_closing_date.docx`, `07_edit_orgcode_costcenter_spec.docx`, `08_hide_document_number_spec.docx`, `09_master_currency_spec.docx`, `10_web_access_submit_data_spec.docx`.
- `laddawan\` — 3 delivered `.pdf`, Thai-titled + versioned: `Spec A หน้าหลักและสิทธิ์การเข้าถึง_V2.0.pdf`, `Spec B ฟอร์มย่อยรายละเอียดงบประมาณ_V2.0.pdf`, `Spec C การจัดการตารางข้อมูลหลัก_V2.0.pdf`.
  → **Convention: per-owner delivery folders. `jakkaritw/` = editable source, `<business-owner>/` = the signed artifact that person receives** (commit `0b77eb7` "reorganize by owner").
- `_build\` — 9 `build_*.py` generators + 4 underscore helpers (`_capture_spec_a_main_v2.py`, `_validate_docx.py`, `_validate_main_docx.py`, `_validate_mc_docx.py`) + `_build/assets/spec_c_logo.jpeg`. Underscore prefix = tooling, sorts above content. **`build_main_web_app_spec.py` is referenced in commit `0b77eb7` but is absent from the tree today** — a generator was deleted without its `.docx` being deleted.

**`3_approval_workflow\`** — flat, 3 files: `approval_workflow_spec.md` (source) + `approval_workflow_spec.pdf` (delivered) + `generate_pdf.py` (generator co-located with output, not in a `_build/`). Different pattern from signoff_spec — the folder is small enough not to warrant `_build/`.

**`4_sit\`** — exactly **one** file: `Budget_SIT_Test_Cases_10.08.2026.xlsx`, 314,284 bytes, git-tracked. **No generator lives here** — all four editors live in `setup\` (see §2). `.gitignore:68` excludes `requirement_spec/4_sit/*_before_*.xlsx` (pre-edit snapshots); commit `62d42a7` (2026-09-06 03:20) removed the last tracked `*_before_*` snapshot.

**`5_uat\`** — empty, created 2026-09-06 03:23 (3 min after the 4_sit cleanup commit), **untracked** — git cannot track an empty directory, so it does not exist in any commit.

Workbook internals (verified by reading the file): 4 sheets — `1. Info & Instructions` (A1:B30), `2. Test Cases` (A1:P64), `3. Summary` (B2:E27), `Note` (A5:B33, 3 tester comments + 6 pasted pictures). Headers on **row 2**, example row `EX`/`TC-EX` on **row 3**, real cases rows **4–64 = 61 cases**. 16 columns: `No. | Test Case ID | Module | PIC | Test Scenario | Priority | Preconditions / เงื่อนไขก่อนทดสอบ | Test Steps | Test Data | Expected Result | Actual Result | Status | Severity | Tester | Test Date | Remarks / หมายเหตุ`. Status tally **59 Pass / 2 N/A** — N/A rows are **row 30 TC-027** (Reports/Export, out of scope this version) and **row 45 TC-042** (deadline reminder mail) — this confirms your brief exactly. PIC distribution: Pornthip 41, Jakkarit 7, Laddawan 9, "Pornthip / Laddawan" 2, blank 1. Modules (12): Email Alert/Notification 16, Budget Entry (Filler) 9, Special GL Subform 6, Approval (Approver1) 6, Login/Authentication 5, Approval (Approver 2/3) 4, Submission/Workflow 4, UI/UX 3, Security 3, Business Rules 2, Data Integrity 2, Reports/Export 1. Info sheet fields: Application / Environment (**stg URL**) / Test Phase / **Department under test = "Data Analytic"** / Role–Filler=Pornthip / Role–Approver 1=Laddawan / Role–Approver 2=Jakkarit / Test Lead="Data and Analytics team" / Test Cycle="Round 1" / Start Date=2026-08-17 / Target End Date=2026-08-21, then a 7-step "How to use this workbook" block and a Legend (yellow = tester-fills; Severity Critical/High/Medium/Low). Summary sheet = `COUNTA`/`COUNTIF`/`COUNTIFS` hard-bounded to `$4:$64` plus a per-module breakdown, one row per module.

## 2. How the SIT workbook was produced — 4 scripts, all in `setup\`, all Graph-uploading

| Script | Size | What it does |
|---|---|---|
| `setup\update_sit_test_cases.py` | 17,377 b | **The origin script.** Appends new cases. Owns the SharePoint layer: `SHARE_URL` const at lines 32-35, `_get_token()` (msal client-credentials, `ENTRA_*`, scope `https://graph.microsoft.com/.default`) :131, `_share_id()` base64-`u!` encoder :143, `resolve_item()` `GET /v1.0/shares/{id}/driveItem` :148, `download()` :165, `upload()` `PUT /drives/{driveId}/items/{id}/content` :174. Docstring flow: resolve → download → append (style copied from last row) → **extend autofilter + 3 dropdown validations + Summary formula ranges** → save local to `requirement_spec/4_sit` → `--upload` PUTs back, aborting if `lastModifiedDateTime` moved. |
| `setup\fill_sit_test_case_gaps.py` | 57,325 b | **The multi-pass editor.** 14 documented passes in the module docstring (pass 1 → pass 14), each pass = new data in `EDITS` / `NEW_CASES` / `RESULTS` / `IMAGE_RESULTS`, *same script, never forked* ("per the project's build-organized rule"). Grew 37 → 61 cases. Owns the label-preservation fix (lines 658-805, see §4) and `verify_binary_parts()`. |
| `setup\write_sit_actual_results.py` | 13,380 b | **The run-result writer.** Deliberately separate "per the harness spec §4.6" so the two safety models can't mask each other; it *imports* `HEADER_ROW, PURPLE_ARGB, _col, _find_row_by_no, _font_matches_except_color, _header_map, _purple_font` from `fill_sit_test_case_gaps` and `SHEET_CASES, _get_token, download, resolve_item, upload` from `update_sit_test_cases`. `PROTECTED_ROWS = frozenset({40, 41, 42})` (Laddawan's rows) refused in two independent places. |
| `setup\run_sit_ai.py` | 25,437 b | **AI SIT harness.** `ALLOWED_HOST` hard-coded to the stg FQDN, "no env var can override it"; phases 0/A..I; cookie-based persona switching; `BaselineManager` writes baseline to disk before the first write; evidence to `plan/sit/evidence`; unregistered cases return `NOT_RUN`, never a fabricated PASS. |
| `setup\tests\test_write_sit_actual_results.py` | — | unit tests for the writer (the only SIT script with tests). |

Every one of them uploads to SharePoint by Graph `PUT …/content`. Per memory `project_sit_workbook_editing_protocol`: **the subagent cannot run `--upload` (permission classifier blocks it); the main session runs it.**

## 3. Reusable "generate a Thai .docx / .pdf with nothing installed" pattern

From `_build\build_spec_a_main_spec_v2.py` docstring (lines 24-27), verbatim: *"HARD CONSTRAINTS: stdlib + Pillow only. .docx built by hand as WordprocessingML. Thai = Leelawadee UI on ascii/hAnsi/cs, szCs==sz. document.xml UTF-8. Re-runnable."*

Imports across all 9 generators: `os, io, json, html, zipfile` + `PIL.Image/ImageDraw/ImageFont` only (two also import `playwright.sync_api` for capture). **No python-docx, no Word, no COM.**

The reusable helper set (line refs in `build_spec_a_main_spec_v2.py`):
- Text: `esc` :130, `run_props(sz,bold,color,italic)` :134 (emits `<w:rFonts w:ascii/hAnsi/cs="Leelawadee UI">`), `run` :147, `para` :151, `section_heading` :168, `subheading` :174, `label_para` :179, `body_para` :183, `bullet` :187, `note_para` :191, `caption` :197.
- Tables: `tcell` :202, `cell_para` :213, `table(rows, col_widths_dxa)` :218, **`sign_table(rows, col_widths_dxa)` :247** — the ready-made signature block.
- Images: `_pic_xml` :277, `image_para` :300, `cover_logo_para` :308.
- Package: `header_xml` :567, `footer_xml` :609 (page-number field), `content_types_xml` :652, `root_rels_xml` :669, `document_rels_xml(image_rels)` :678, `header_rels_xml` :698 — then `zipfile` writes the .docx.
- Annotation: gold numbered callout circles drawn with Pillow — `_num_font` :80 (`NUM_FONT_PATH = r"C:\Windows\Fonts\arialbd.ttf"`), `_leader` :87, `_circle` :100, `annotate(key)` :112. Crop boxes + marker coordinates come from a separate Playwright capture pass (`_capture_spec_a_main_v2.py` → `bin/speca2_coords.json`).
- Theme constants: `THAI_FONT="Leelawadee UI"`, `HEAD_BLUE=0F4761`, `SUB_BLUE=1F3864`, `ACCENT_BROWN=8C6423`, `TH_FILL=D6E4F0`.
- **Every generator has a paired validator.** `_validate_docx.py:4-11` checks: required zip parts present; every `.xml`/`.rels` parses; every `r:embed` resolves to a rel whose media target exists in the zip; and a content assertion on a live UI string ("Export CSV").

PDF path is different and simpler: `requirement_spec\3_approval_workflow\generate_pdf.py` uses **fpdf** with `C:\Windows\Fonts\tahoma.ttf` / `tahomabd.ttf`, a subclassed `PDF(FPDF)` with `header()`/`footer()`. **The signoff docx→PDF V2.0 conversion (commit `0b77eb7`) was done by hand in Word — no conversion script exists in the repo.** XLSX generation uses openpyxl, and lives in `setup\`, not in any `_build\`.

## 4. SharePoint location, sync mechanism, and the label gotcha

- **Path** (from memory `project_sit_workbook_sharepoint`): site `CMANDigitalTechnology` → `General/05 Data Analytics/03 Project/6.Budgeting and Management/03_SIT`. Owner/editor **Laddawan Kearnoi**.
- **Share URL** hard-coded at `setup/update_sit_test_cases.py:32-35`: `https://chememan.sharepoint.com/:x:/t/CMANDigitalTechnology/IQC3yfoY_0ExQo_fB3eD6rOoAXlplryNhGHbEroD4MlDWXA`.
- **"Sync" is manual pull/push, not a job.** No workflow, no cron. Each script does download → edit in memory → save local snapshot into `requirement_spec/4_sit/` → `--upload` PUT, with a `lastModifiedDateTime` concurrency abort. **SharePoint is the live copy; the repo file is a snapshot** (commit `62d42a7` says so explicitly: *"The live workbook and its own version history are on SharePoint."*).
- **Gotcha — openpyxl strips the sensitivity label.** A *no-edit* openpyxl round-trip drops `docMetadata/LabelInfo.xml` (the Microsoft sensitivity label, `enabled="1" removed="0"`), `customXml/item{1,2,3}.xml` + itemProps + `_rels` (SharePoint content-type / managed-metadata plumbing), `xl/calcChain.xml`, `xl/printerSettings/*`. **Every AI upload from pass 1 to pass 12 stripped the label**; it only reappeared because a human re-saved in Excel.
- **Fix (2026-08-20, pass 13)** in `setup/fill_sit_test_case_gaps.py`: `_save_workbook()` is now the only save path — openpyxl save, then `_preserve_sharepoint_parts()` splices the original's `customXml/*` + `docMetadata/*` back into the zip and re-declares them in `[Content_Types].xml` Overrides, `_rels/.rels` (classificationlabels rel) and `xl/_rels/workbook.xml.rels`, re-stamping ids as `rIdSPpkg*` / `rIdSPcx*` so they cannot collide with openpyxl's `rId1..N`. Constants at :668 `_PRESERVED_PART_PREFIXES = ("customXml/", "docMetadata/")`; messages at :753 and :805. `verify_binary_parts()` fails the run on any lost part, any picture dropped (sha256 set comparison), a changed sheet list, or another sheet's picture count moving.
- **HTTP 423 `resourceLocked`** = someone has the file open in Excel; wait, do not loop.
- **Editing conventions locked by jakkaritw:** purple font `7030A0` on every AI-written cell (change color only, preserve name/size/bold/italic); Test Steps use `1. `/`2. ` prefixes one per line; Expected Result states observable outcome only; backend-verification SQL goes inside Expected as "ตรวจ backend (ทีมพัฒนารัน query แนบผลเป็นหลักฐาน): …"; TC-040/041/042 are Laddawan's and are never touched.
- **NOT VERIFIABLE:** whether a UAT sibling folder already exists next to `03_SIT`. The M365 SharePoint connector does not index that site path — `sharepoint_folder_search("SIT")` and `("Budgeting and Management")` returned **zero hits from CMANDigitalTechnology**. What the connector *did* surface is a **company-wide UAT folder convention from another CMAN project** (`teams/exportshipmentDB` › `Shared Documents/General/`): `35 System Integration Test (SIT)/` → `10 SIT Script Template`, `20 SIT Result`; and `40 User Acceptant Test (UAT)/` → `10 UAT Script Template`, `20 UAT Result`, `30 UAT Signed Off`. That is the closest thing to a house standard for UAT deliverables.

## 5. Every UAT hit in the repo (`grep -rn "UAT"`, excluding `.git`, `node_modules`, `venv`)

**There is no UAT plan, no UAT entry/exit criteria doc, and no go-live checklist file anywhere in the repo.** The two that once existed were **deleted and folded into the SIT plan** — `plan/sit/sit-test-plan.md:24-25` names them: `plan/post-deploy-smoke-uat-plan.md` (1052 lines, Phase 0 pre-flight / Phase 1 smoke / Phase 2 A–L / **Phase 3 UAT** / Appendix B tester traps / Appendix D evidence table / Appendix E 10 decisions) and `plan/uat-quick-guide.md` (48 lines, one-page filler + approver guide). The plan says explicitly: *"ถ้าเจอไฟล์เหล่านี้กลับมา ให้ถือว่าเป็นของเก่า ห้ามใช้"*.

Where the UAT substance now lives:

| Location | Content |
|---|---|
| `plan/sit/sit-test-plan.md:1011-1035` | **"ภาคผนวก — คู่มือผู้ใช้สำหรับ UAT (1 หน้า)"** — the surviving one-page Thai guide: prd URL, 6 filler steps, 4 approver steps, "อาการที่ควรรายงานทันที" (5 symptoms), 3 FAQs. Sender corrected to `cmanpowerbi@chememan.com`. |
| `plan/sit/sit-test-plan.md:1105-1151` | **"UAT — ฝ่ายนำร่องและช่วงวัน (ยืนยันโดย jakkaritw 2026-08-07)"** — pilot dept 1 = Solution Delivery (`10IT012000`), pilot dept 2 = Data & Analytic (`10IT011300` + `10IT0130000`, Digital Technology/CTO); testers laddawank + pornthipp; window Mon 17 – Fri 21 Aug 2026; a 3-row "สิ่งที่ต้องเตรียมให้เสร็จก่อน 17 ส.ค." owner table; 3 tester warnings (screen year Y = system year Y+1; concurrent-edit 409 is by design; email links are long Azure URLs until `budget.chememan.com`); and the permanent `cc dept.xlsx` filler change (rows 193/194, 4 → 2 rows in `dbo.cc_filler_map`, Laddawan fill → 0, still Approver 1). |
| `plan/sit/sit-test-plan.md:913-946` | **"เกณฑ์เข้า / ออก (entry / exit criteria)"** — the only entry/exit gate that exists in this project (written for SIT). |
| `plan/sit/sit-test-plan.md:817-835` | Part 20 — round-open / round-close gates `SIT-000`..`SIT-007` + evidence rules. |
| `plan/sit/sit-run-log.md:773+` §21 | Dry-run UAT of pilot dept 2, done by AI ahead of the real date; §21.1 = "🔴 สิ่งที่ต้องแก้ก่อน 17 ส.ค. ไม่งั้น UAT เดินไม่ได้". |
| `plan/sit/sit-run-log.md:877+` §23 | Pre-UAT test-data wipe — "ยอดคุมตั้งต้นของ UAT = 0 ทุกตาราง". |
| `plan/sit/sit-run-log.md:1039-1097` §27 | **"วิธีทดสอบอีเมล + การอนุมัติผ่านหน้าเว็บ (ใช้ตอน UAT)"** — the 3 env vars that make mail safe (`NOTIFICATIONS_DRY_RUN=false`, `NOTIFICATIONS_REDIRECT_ALL_TO`, `NOTIFICATIONS_ENVIRONMENT_LABEL`), the impersonation header, a 5-step full approval chain, what evidence to trust (`notification_warning` field ✅, mailbox ✅, `az containerapp logs show` ⚠️ unreliable), and **§27.5 "กฎเหล็กตอน UAT" — 4 hard rules**. |
| `docs/adr/0029-approver-see-overlay.md:19,25` | The **only ADR mentioning UAT**: the step-2/3 approvers' See-scope (7 CC, byte-identical, measured twice) contains neither `10IT011300` nor `10IT0130000`, so *"a defect that would otherwise block the 17–21 Aug UAT approval chain end to end."* |
| `monthly_update/project_status_report_2026-08.html:219,240,252,261,273,281` (+ its generator `_build_status_report.py:244,265,277,286,298,306`) | **Management-level UAT commitments already made:** pilot on production, 1–2 departments, 3–5 working days, at least one department reaching Approved with no developer help; a **one-page Thai approver guide to complement the filler guide**; **a single feedback channel**; **an observation sheet where every issue is numbered, ranked blocker/major/minor, and assigned an owner and a date**; **formal Go/No-Go criteria** (zero blockers, all emails delivered correctly, no data-visibility leak, response times within standard, department totals reconciled, written approval); then a staged rollout pilot → one wave of ~10–20 departments (one division) → all 114. |
| `backend/app/config.py:53` | `# SIT/UAT test aid` → `sit_impersonate`, guarded by `app.auth._sit_guard_ok` (three conditions: `app_env != "production"`, caller in `admin_emails_set`, caller equals the value's own `from_email`). |
| `tracker/pending.json:11` | Task **`wayfinder-uat-prep`, state `doing`** — scope: revise stg env for UAT (session expiry 1h), create `requirement_spec/5_uat` artifacts, settle role assignment (pornthipp + laddawank each cover Data Analytic + Solution Delivery; open Q whether laddawank displaces suchanya on Solution Delivery), revise the 61-case SIT workbook into a UAT pack. It claims a map at `.scratch/uat-prep/MAP.md` — **that file and directory do not exist**. |
| `.claude/plan.md:287` | Single occurrence (`grep -c UAT` = **1**), inside the ADR-0029 decision line. |
| `setup/phase2_harness_dkl.py:506` | Comment: `budget.* is GENUINELY EMPTY for all real years (pre-UAT)`. |

## 6. Where UAT sits in `.claude\plan.md`, and the go-live target

`.claude/plan.md` is 582 lines, header `# Current Phase (2026-09-04)`. **UAT is not a phase, not a section, and not a checklist item.** Its one mention (line 287) is a decision note under the ADR-0029 section, recording that the approver See-scope gap "blocked the full approve-through-the-UI flow needed for the 17–21 Aug UAT chain". The Current Phase is a stack of ~35 shipped feature sections (most tagged UNCOMMITTED); the forward `[ ]` items at the bottom are all master-tables→Excel/Fabric-sync work. **No go-live date appears in `plan.md`, `CONTEXT.md`, `README.md`, or any ADR** (`grep -i "go-live|go live|golive"` → 0 content hits in those files).

The only recorded target is memory `project_golive_target`, decided 2026-06-07: **Phase-1 go-live = end of Aug 2026**, scope = budget input form + approval workflow + email notifications + deploy; dashboard = Phase 2. **That date has passed** (today 2026-09-06) and nothing in the repo supersedes it. UAT was scheduled 17–21 Aug precisely to leave *"สัปดาห์สุดท้ายของเดือนไว้แก้ปัญหาที่ UAT เจอ ก่อน go-live ปลายสิงหาคม"* (`sit-test-plan.md:1113`) — so the whole UAT→go-live sequence is now running late and needs re-dating in whatever artifact you create.

### Environment facts verified live today (`az containerapp show`, read-only) — these belong in the UAT artifacts

| Key | stg | prd | |
|---|---|---|---|
| `FABRIC_SQL_SERVER` / `FABRIC_SQL_DATABASE` | md5 `882aeec5341a` / `f1ec4dedf135` | identical | **SAME — one DB, confirmed** |
| `GOLD_SQL_SERVER` / `GOLD_SQL_DATABASE` | `115efb72e429` / `a4b02c7435d9` | identical | SAME |
| `NOTIFICATIONS_DRY_RUN` | `false` | `false` | **real mail from BOTH** |
| `NOTIFICATIONS_REDIRECT_ALL_TO` | absent | absent | **no mail funnel anywhere** |
| `NOTIFICATIONS_ENVIRONMENT_LABEL` | absent | absent | **staging mail is unlabelled — indistinguishable from production** |
| `APP_ENV` | **`local`** | `production` | **changed since the 2026-08-07 run log, which recorded `production` on both** |
| `DEV_AUTH_EMAIL` | **`pornthipp@chememan.com`** | absent | with `app_env=local` this override is **honored** on stg (`config.py:49-50`, `auth.py:9-10`) |
| `SIT_IMPERSONATE` | `jakkaritw@chememan.com:pornthipp,laddawank,nipapornt,warapornt,arthids` (5 targets) | absent | |
| `ADMIN_EMAILS` | jakkaritw, nipapornt, warapornt (3) | identical | `piyadad` still absent |
| Easy Auth | enabled, `RedirectToLoginPage` | enabled, same | |
| `timeToExpiration` | **not set** (platform default) | `14:00:00` | the tracker task wants stg set to 1h — currently it is neither 1h nor 14h |

## 7. Proposed contents for `requirement_spec\5_uat\` (proposal only — nothing created)

Naming follows the observed rules: numbered/underscored folders, `_build/` for generators, `assets/` for screenshots, per-owner delivery folders, `Budget_<PHASE>_<Artifact>_<DD.MM.YYYY>.xlsx` for the workbook, Thai titles + `_V<n>.<n>` for business-facing documents.

```
requirement_spec/5_uat/
├── Budget_UAT_Test_Cases_<DD.MM.YYYY>.xlsx     ← the pack (committed snapshot; SharePoint is live)
├── UAT_Entry_Exit_Criteria.md                  ← Thai, the Go/No-Go gate
├── UAT_Defect_Log_<DD.MM.YYYY>.xlsx            ← OR a 5th sheet "4. Defects" in the pack (prefer the sheet)
├── assets/                                     ← Playwright-captured screenshots for the guides
├── jakkaritw/                                  ← editable sources
│   ├── UAT_คู่มือผู้กรอกงบ_1หน้า_V1.0.docx
│   ├── UAT_คู่มือผู้อนุมัติ_1หน้า_V1.0.docx
│   └── UAT_ใบรับรองผลการทดสอบ_V1.0.docx        ← acceptance sign-off sheet
├── <business-owner>/                           ← delivered PDFs (mirrors signoff_spec/laddawan/)
└── _build/
    ├── build_uat_test_cases.py                 ← workbook generator/editor
    ├── build_uat_user_guides.py                ← the two 1-page guides + sign-off sheet (.docx)
    ├── _capture_uat_screens.py                 ← Playwright capture → coords json
    └── _validate_uat_pack.py                   ← validator for both workbook and docx
```

What each is for, and the precedent it copies:

1. **`Budget_UAT_Test_Cases_<DD.MM.YYYY>.xlsx`** — same 4-sheet / 16-column / header-row-2 / data-from-row-4 shape as the SIT workbook so testers who did SIT need zero re-learning, and so `3. Summary`'s `COUNTIF` shape ports directly. Info sheet changes: `Environment` = **prd** URL, `Test Phase` = "User Acceptance Test (UAT)", **`Departments under test` = "Data Analytic + Solution Delivery"** (two rows, not one), and five role rows for Pornthip / Laddawan / Jakkarit / Nipaporn / Waraporn with each person's dept coverage spelled out (this is where the "each carries 2 departments" decision gets recorded). Add a `Department` column to `2. Test Cases` — the SIT sheet has no per-case department column and a two-department round needs one. Seed from the 61 SIT cases minus the 12 dev-only ones (Security, Data Integrity, backend-SQL Expected results) and minus TC-027 (out of scope) — UAT is business acceptance, not re-running SIT.
2. **`UAT_Entry_Exit_Criteria.md`** — Thai, ported from `sit-test-plan.md:913-946` and made concrete with the Go/No-Go bullet already promised to management (`project_status_report_2026-08.html:281`): zero blockers, all four mail types delivered to the right person, no cross-department visibility leak, department totals reconciled before/after, response time within standard, **written approval by jakkaritw**. Entry side must carry the pre-flight this round actually needs: `dbo.submission_deadline` row open for the FY under test, SharePoint attachment folders created for both departments, `cc_filler_map` reflecting the agreed 2-dept coverage, and the four environment decisions from the table in §6.
3. **`UAT_Defect_Log`** (sheet preferred over a separate file, per the "extend, don't create" rule) — the numbered / ranked blocker-major-minor / owner / date observation sheet promised at `project_status_report_2026-08.html:273`. The SIT workbook has `Severity` per case but **no defect register** — findings ended up in `sit-run-log.md` tables (D-01…D-16, PC-04…PC-20), which business users will never open.
4. **The two 1-page Thai guides** — the filler guide already exists as prose at `sit-test-plan.md:1011-1035` and needs only re-targeting; the **approver guide does not exist yet** and is explicitly promised. Build both with the WordprocessingML + Pillow pattern (§3), reusing `run_props`/`para`/`table`/`image_para` and the gold `annotate()` markers over fresh prd screenshots.
5. **`UAT_ใบรับรองผลการทดสอบ`** — the acceptance sign-off sheet; `sign_table()` at `build_spec_a_main_spec_v2.py:247` already renders exactly this block. Delivered as PDF into the owner folder, matching `signoff_spec/laddawan/`. This is the artifact the "written approval" exit criterion refers to, and it is what the company's other project files under `30 UAT Signed Off`.
6. **`_build/build_uat_test_cases.py`** — a **new script that imports the proven helpers rather than reimplementing them**, exactly as `write_sit_actual_results.py` imports from `update_sit_test_cases.py`: `_get_token / _share_id / resolve_item / download / upload` for SharePoint, and `_save_workbook / _preserve_sharepoint_parts / verify_binary_parts` for the label splice. It must carry its own `SHARE_URL` (a different file), extend autofilter + the three dropdown validations + Summary ranges to the new last row, mark AI-written cells purple `7030A0`, and keep `--upload` off by default. A new script is justified here under rule 3(a) — different deliverable, different SharePoint target, different protected-rows set — but the SharePoint/label layer must **not** be copy-pasted a third time; the cleanest form is to lift those helpers into `setup/sharepoint_xlsx.py` and have all three scripts import it.
7. **`_validate_uat_pack.py`** — mirrors `_validate_docx.py`: assert 4 (or 5) sheets present; 16+ headers on row 2; `3. Summary` ranges end exactly at the last data row; the three dropdown validations cover the full range; `customXml/*` + `docMetadata/LabelInfo.xml` survive the save; picture sha256 set unchanged; and a content assertion (e.g. the prd URL string appears in `1. Info & Instructions`, and the stg URL does **not**).

**Companion (not in `5_uat`, mirroring the existing `plan/sit/` split):** the project deliberately separates the business-facing pack (`requirement_spec/4_sit/`, 1 file) from the engineering plan (`plan/sit/`, 18 tracked files — `sit-test-plan.md` 1198 lines, `sit-run-log.md` 1097 lines, `evidence/<CASE-ID>/`, `restore_*.sql`, `revert_*.sql`). Reproduce that: `plan/uat/uat-run-plan.md` (waves, safety rules, the four §27.5 hard rules, and a **baseline/reconcile contract instead of a sentinel-year contract** — UAT writes real years on the shared prd DB, so the 2093/2097/2099 shield does not apply), `plan/uat/uat-run-log.md` (round header table with the §6 env values filled in, per-case result table, allowed verdicts `PASS/FAIL/BLOCKED/N/A/OBSERVE`, evidence-path column, "ห้ามเว้นช่องผลว่าง"), `plan/uat/evidence/<CASE-ID>/`, and `plan/uat/restore_<dept>_<fy>_baseline.sql`.

**Two things the artifacts must state that no current document does:** (a) `APP_ENV=local` + `DEV_AUTH_EMAIL=pornthipp@chememan.com` is live on staging right now, so an unauthenticated staging browser *is* Pornthip; (b) with `NOTIFICATIONS_DRY_RUN=false` and no label/redirect on either environment, **a UAT click on staging writes production data and mails real colleagues with no visible marker** — the single highest-risk fact for this round.