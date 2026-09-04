# T06 — Revise the human-signed spec documents  [OPEN]

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
