# T06 — Revise the human-signed spec documents  [CLOSED 2026-09-06 — deliberately not done]

Type: `wayfinder:task` (HITL)

## Question
Which signed-off `.docx` specs describe the trip form as 4 rows / 8 GLs, and how do they get
revised without breaking their SharePoint sensitivity label?

## Known starting points
`requirement_spec/1_software_dev/1.1_frontend/signoff_spec/_build/build_special_gl_subform_spec.py:538`
lists the 4 travel rows; `build_master_currency_spec.py` and `build_spec_c_master_tables.py`
both describe ค่าใช้จ่ายเดินทางอื่น as user-typed THB inside the trip form. Editing by run-id
without installing anything is a solved problem here (see the docx run-id memory); openpyxl/
OOXML saves strip the sensitivity label unless the docMetadata parts are spliced back.

## Resolution
jakkaritw decided NOT to revise the document. Chose not to do it, as opposed to not yet done.

What stays wrong, knowingly: `Spec B ฟอร์มย่อยรายละเอียดงบประมาณ_V2.0.pdf` (Laddawan's copy) and
`01_special_gl_subform_spec.docx` (jakkaritw's copy) both carry a 4-row table of trip expense
types whose 4th row is "ค่าใช้จ่ายเดินทางอื่น · Other Travel / 5210400999 / 6210400999". The
live Trip Manager has 3 rows. A reader of the document will expect a row the app no longer has.

No system impact — this is documentation drift only.

Also corrected here: an earlier claim in this session that the spec "must be re-signed" was
wrong. Nothing in the repo requires a re-signature on a content change. The generated .docx
ships with an EMPTY sign-off table (ผู้จัดทำ / ผู้ตรวจสอบ / ผู้อนุมัติ), so signing happens
outside the repo, and the documented convention for a content change is a version bump plus a
"ประวัติการแก้ไข" line (currently v0.4).

If this is ever revisited: `build_special_gl_subform_spec.py` cannot simply be re-run — it reads
`design/mockups/0002claude design/0002.1budget-export.html`, which no longer exists in the tree
(recoverable from commit d5484b1). Editing the .docx directly by run-id is the cheaper route.
