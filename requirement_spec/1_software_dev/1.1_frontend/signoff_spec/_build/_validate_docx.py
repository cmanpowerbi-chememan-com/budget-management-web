# -*- coding: utf-8 -*-
"""Standalone validator for the Edit GL Group sign-off .docx.

Checks (stdlib only):
  1. Required zip parts are present.
  2. Every .xml / .rels part parses as well-formed XML.
  3. Every r:embed in word/document.xml resolves to a relationship in
     word/_rels/document.xml.rels whose Target media file exists in the zip.
  4. word/document.xml contains the current UI button label "Export CSV"
     (the toolbar export button — re-added during the backend rewire 2026-06-11).
"""
import sys
import zipfile
import xml.etree.ElementTree as ET

DOCX = (
    r"c:\04.budget_management_web\requirement_spec\1_software_dev"
    r"\1.1_frontend\signoff_spec\03_edit_gl_group_spec.docx"
)

REQUIRED_PARTS = [
    "[Content_Types].xml",
    "_rels/.rels",
    "word/document.xml",
    "word/_rels/document.xml.rels",
]

R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def main():
    ok = True
    with zipfile.ZipFile(DOCX) as z:
        names = set(z.namelist())

        # 1. required parts present
        print("[1] Required parts:")
        for p in REQUIRED_PARTS:
            present = p in names
            ok &= present
            print(f"    {'OK ' if present else 'MISSING'}  {p}")

        # 2. every xml/rels part parses
        print("[2] XML well-formedness:")
        xml_parts = [n for n in names if n.endswith(".xml") or n.endswith(".rels")]
        for n in sorted(xml_parts):
            try:
                ET.fromstring(z.read(n))
                print(f"    OK    {n}")
            except ET.ParseError as e:
                ok = False
                print(f"    FAIL  {n}  -> {e}")

        # 3. r:embed ids resolve to relationships whose targets exist
        print("[3] r:embed -> relationship -> media target:")
        doc = z.read("word/document.xml")
        doc_root = ET.fromstring(doc)
        embeds = set()
        for el in doc_root.iter():
            val = el.get(f"{{{R_NS}}}embed")
            if val:
                embeds.add(val)

        rels_root = ET.fromstring(z.read("word/_rels/document.xml.rels"))
        rel_targets = {}
        for rel in rels_root.findall(f"{{{PKG_REL_NS}}}Relationship"):
            rel_targets[rel.get("Id")] = rel.get("Target")

        if not embeds:
            ok = False
            print("    FAIL  no r:embed found in document.xml")
        for rid in sorted(embeds):
            target = rel_targets.get(rid)
            if target is None:
                ok = False
                print(f"    FAIL  {rid} -> no relationship")
                continue
            media_path = "word/" + target.replace("\\", "/")
            exists = media_path in names
            ok &= exists
            print(f"    {'OK ' if exists else 'FAIL'}  {rid} -> {target} -> "
                  f"{'present' if exists else 'MISSING'}")

        # 4. current UI button label present
        print("[4] Current string in document.xml:")
        text = doc.decode("utf-8")
        found = "Export CSV" in text
        ok &= found
        print(f"    {'OK ' if found else 'FAIL'}  'Export CSV' "
              f"{'found' if found else 'NOT found'} "
              f"(count={text.count('Export CSV')})")

    print("\nRESULT:", "ALL CHECKS PASSED" if ok else "VALIDATION FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
