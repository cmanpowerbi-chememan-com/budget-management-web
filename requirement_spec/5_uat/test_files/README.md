# UAT test-input files

Mock files for the attachment cases (UAT-27 / UAT-28 / UAT-29 / UAT-30).

- **UAT-28-oversize-11MB.pdf** — a valid one-page PDF padded to ~11 MB, for UAT-28
  (upload a file over the 10 MB cap → the app must reject it with the Thai over-size
  message). NOT committed (keeps `.git` lean); regenerate any time with:

      python -X utf8 requirement_spec/5_uat/_build/gen_oversize_pdf.py

Other UAT-28 inputs (a `.docx` / `.zip` of a disallowed type) can be any small file
with that extension — the app rejects by extension before size.
