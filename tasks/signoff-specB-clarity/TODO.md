# Feature: signoff-specB-clarity — readability/concision polish of SpecB (GL Subform) sign-off doc

Same concept as the SpecC polish CC just shipped (commit e3a5e39): make the doc easier to read /
more concise / consistently formatted, **wording only — keep every fact, number, table identifier,
screenshot, marker and section number unchanged.** The manager signs this doc.

**Target file:** `requirement_spec/1_software_dev/1.1_frontend/signoff_spec/version2/SpecB_GL_Subform_v3.docx`
(currently on disk, differs from HEAD = recently re-saved; polish the **current on-disk** version so any pending edits in it are kept.)

## Why the method differs from SpecC (READ THIS)
SpecC had clean 1-run paragraphs → edited by run-id. **SpecB is run-fragmented** (manager Word saves split
every paragraph into many `<w:t>` runs at Thai/Latin/space boundaries — 0 clean single-run prose paragraphs,
1800 runs / 447 paragraphs). So the editable unit here is the **PARAGRAPH**, and we **collapse** a paragraph's
runs into one new run when rewriting it.

CC pre-built + PROVED the tooling (stdlib only, no install) — **USE these, do not reinvent OOXML surgery:**
- `tasks/signoff-spec-v2/_tools/extract_paras.py FILE.docx --json OUT` → `[{i,text,runs,mixed_bold,has_image,has_link,skip}]`
- `tasks/signoff-spec-v2/_tools/apply_paras.py --in --out --edits` → applies `{"paras":[{i,new}]}`; keeps `<w:pPr>`,
  rebuilds one run using the rPr of the paragraph's longest run (preserves font/size/colour → Thai `cs` + Latin
  `ascii` both survive, verified `Leelawadee UI`). `[[BR]]` = line break, `• ` = bullet. `--selftest` = no-op round-trip.
- `tasks/signoff-spec-v2/_tools/check_paras.py parasB.json edits.json` → preservation (no protected token dropped)
  + overlap (flags wrong-paragraph-index edits). **MUST print `PASS`.**

> GOTCHA (cost CC a corrupted cell on SpecC): a rewrite can get attached to the WRONG index → wrong paragraph
> overwritten. `check_paras.py` overlap-flag catches it. **Never apply if check_paras is not PASS.**

Run everything with `PYTHONUTF8=1` (Windows console is cp1252 — Thai will crash without it).

---

## TASK-001 — Polish SpecB paragraphs (collapse-rewrite) — Status: [x]

**Files:** `requirement_spec/1_software_dev/1.1_frontend/signoff_spec/version2/SpecB_GL_Subform_v3.docx`,
`tasks/signoff-specB-clarity/edits_specB_clarity.json` (you create), `tasks/signoff-spec-v2/_tools/*paras*.py` (commit the 3 CC-provided tools).

### House style (apply to the paragraphs you choose to rewrite)
เป้าหมาย: อ่านง่าย กระชับ เป็นระบบ — **ใจความ/ข้อเท็จจริงครบเหมือนเดิม**.
- ประโยคยาวที่คั่นด้วย `:` หลายท่อน (เดิมเป็น bullet ที่ถูกยุบ) → แตกเป็นรายการด้วย `[[BR]]` + `• ` เมื่อมี ≥2 ข้อ.
- ตัดคำฟุ่มเฟือย/ซ้ำ ("ระบบจะ", "ทำการ", "โดยที่", "สำหรับ...นั้น") ให้สั้นลง ความหมายเท่าเดิม.
- ใช้คำสม่ำเสมอ: "ผู้กรอกทั่วไป (L3/L4)", "อ่านอย่างเดียว", "งวด (ปีงบ + เดือน)", "ผู้ดูแลระบบ".
- ย่อหน้า Context / คำอธิบายยาว → ประโยคสั้น หรือ bullet; เก็บเงื่อนไข/ADR ครบ.
- ใส่ได้เฉพาะข้อความ + `[[BR]]` (ห้ามใส่แท็ก XML). อย่าวาง `[[BR]]` ซ้อนหรือท้ายสุด.

### Only rewrite paragraphs that benefit. DO NOT touch:
- any paragraph with `skip:true` from extract_paras (images / hyperlinks / mixed in-para bold / empty) — these are excluded for safety.
- short labels / table headers / already-clear lines (`#`, `รายการ`, `เวอร์ชัน`, `วันที่`, `ผู้จัดทำ`, role labels, single words).
- the **`เพิ่ม Transaction`** button text (it is a correct, different button — leave verbatim).

### NEVER change (facts — dropping any = fail):
ตัวเลข/ปี/ช่วง (FX years & range, per-diem numbers, machinery **11 ชนิด** count, L3/L4, **L2 3 คน**, Module 02),
the **8 GL** breakdown (4 type × 2 side), the per-diem table values, `backtick` table/column names, `/api/...` paths,
ADR refs (**ADR-0005 / ADR-0013 / ADR-0015** and any others present), screenshot markers `①②③④⑤`/circled numbers and
section numbers (1.1, 2.4a…), emails, `฿ THB USD %`, arrows `→ ▲ ▼`, quoted on-screen UI strings (keep verbatim),
`Microsoft Entra ID` / `Fabric SQL Database` / `Lakehouse` / `SAP` / `React`, `recompute-on-read`, `Oversea Trip`,
`per-diem`, `Travelling Expense`.

### Version + changelog (do these too)
- **para 28** `v0.4 (ฉบับร่าง)` → `v0.4.1 (ฉบับร่าง)`.
- **para 36** changelog (`ประวัติการแก้ไข: v0.4: <desc>`) → rewrite to add a NEW newest entry, KEEPING the existing v0.4 text verbatim:
  `ประวัติการแก้ไข[[BR]]• v0.4.1 (2026-06-26): ปรับถ้อยคำให้กระชับและอ่านง่ายขึ้น จัดบรรทัด/หัวข้อย่อยให้เป็นระบบ (คงตัวเลข โครงสร้าง และหมายเลขอ้างอิงภาพเดิมทั้งหมด)[[BR]]• v0.4: <existing desc verbatim>`

### Process
1. `PYTHONUTF8=1 python tasks/signoff-spec-v2/_tools/extract_paras.py "<SpecB>" --json tasks/signoff-specB-clarity/parasB.json`
2. Read parasB.json. For each rewritable paragraph you choose, add `{"i":<i>,"new":"<text with [[BR]]>"}` to
   `tasks/signoff-specB-clarity/edits_specB_clarity.json` (`{"paras":[ ... ]}`). Copy facts verbatim from the OLD text.
3. `PYTHONUTF8=1 python tasks/signoff-spec-v2/_tools/check_paras.py tasks/signoff-specB-clarity/parasB.json tasks/signoff-specB-clarity/edits_specB_clarity.json`
   → must print **PASS**. Any DROP/OVERLAP flag = fix that edit (you dropped a fact or hit the wrong index) and re-run.
4. `PYTHONUTF8=1 python tasks/signoff-spec-v2/_tools/apply_paras.py --in "<SpecB>" --out "<SpecB>" --edits tasks/signoff-specB-clarity/edits_specB_clarity.json`
   (writes in place; apply_paras validates XML and refuses image paragraphs).

### Pre-commit (cs) — do NOT commit if any fails:
- `apply_paras.py --selftest` on the ORIGINAL passes (well-formed baseline).
- `check_paras.py` prints **PASS** (0 preservation flags, 0 overlap flags).
- Result opens: `PYTHONUTF8=1 python tasks/signoff-spec-v2/_tools/extract_paras.py "<SpecB>"` runs without error.
- Spot-check facts still present in the result (grep the rendered text): `11 ชนิด`, the 8-GL wording, FX year/range,
  `ADR-0005`, `ADR-0013`, `ADR-0015`, `L2 3 คน`, `เพิ่ม Transaction`, markers `①`..`⑤`.
- `v0.4.1` present (version bump + changelog).

### Acceptance:
- [x] check_paras = PASS; result opens + XML well-formed.
- [x] No fact/number/identifier/marker/ADR dropped (deterministic check + spot-check).
- [x] skip:true paragraphs (images/links/bold) untouched; `เพิ่ม Transaction` untouched.
- [x] version → v0.4.1, changelog has the new v0.4.1 line + old v0.4 line intact.
- [x] readability improved (colon-chains → bullets, prose tightened) without changing meaning.

---

## Notes for cs
- Stdlib Python ONLY — **never pip install** (dev machine blocks it).
- This repo has **no** `tasks/sync_summary.ps1` (dashboard infra not set up) — **skip** the dashboard step.
- Commit: `[cursor-done] TASK-001 SpecB clarity polish` — include the edited docx, `edits_specB_clarity.json`,
  `parasB.json`, the 3 `_tools/*paras*.py`, and `CURSOR_REPORT.md`. Touch only these + this TODO.
- Write `tasks/signoff-specB-clarity/CURSOR_REPORT.md`: list paragraphs rewritten (count + a few before/after),
  the check_paras PASS output, version/changelog change, and confirm skip-paras + `เพิ่ม Transaction` untouched.
