# -*- coding: utf-8 -*-
"""Standalone validator for the Master Currency (doc 09) sign-off .docx.

Same pattern as signoff_spec/_build/_validate_docx.py (doc 03), pointed at
09_master_currency_spec.docx. Checks (stdlib only):
  1. Required zip parts present.
  2. Every .xml / .rels part parses as well-formed XML.
  3. Every r:embed resolves to a relationship -> media file present in the zip.
  4. document.xml contains the current UI strings that prove the doc matches the
     NEW module page (2026-06-11 changes): the UPDATE success title and the
     NEW/UPDATE badge variants + the corrected "Travelling" spelling.
"""
import sys
import zipfile
import xml.etree.ElementTree as ET

# Thai output on Windows console (cp1252) would crash print(); force UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DOCX = (
    r"c:\04.budget_management_web\requirement_spec\1_software_dev"
    r"\1.1_frontend\signoff_spec\09_master_currency_spec.docx"
)

REQUIRED_PARTS = [
    "[Content_Types].xml",
    "_rels/.rels",
    "word/document.xml",
    "word/_rels/document.xml.rels",
]

# Strings that must be present (prove the doc reflects the final demo page)
REQUIRED_STRINGS = [
    "อัปเดตสำเร็จ",          # UPDATE modal title variant (item 4)
    "เพิ่มใหม่ · NEW",        # NEW badge variant (item 5)
    "แก้ไข · UPDATE",         # UPDATE badge variant (item 5)
    "Travelling Expenses",   # corrected spelling (item 7)
    "DEMO",                  # demo notice (item 6)
    "32.45",                 # rate example aligned to UI (item 1)
    "first year",            # delta "first year" / hidden vs-label (item 3)
]
# Strings that must NOT be present (stale wording removed)
FORBIDDEN_STRINGS = [
    "Traveling Expenses",    # single-L typo removed (item 7)
    "v0.1 (ฉบับร่าง)",        # superseded version (item 8)
]

R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def main():
    ok = True
    with zipfile.ZipFile(DOCX) as z:
        names = set(z.namelist())

        print("[1] Required parts:")
        for p in REQUIRED_PARTS:
            present = p in names
            ok &= present
            print(f"    {'OK ' if present else 'MISSING'}  {p}")

        print("[2] XML well-formedness:")
        xml_parts = [n for n in names if n.endswith(".xml") or n.endswith(".rels")]
        for n in sorted(xml_parts):
            try:
                ET.fromstring(z.read(n))
                print(f"    OK    {n}")
            except ET.ParseError as e:
                ok = False
                print(f"    FAIL  {n}  -> {e}")

        print("[3] r:embed -> relationship -> media target:")
        doc = z.read("word/document.xml")
        doc_root = ET.fromstring(doc)
        embeds = set()
        for el in doc_root.iter():
            val = el.get(f"{{{R_NS}}}embed")
            if val:
                embeds.add(val)
        rels_root = ET.fromstring(z.read("word/_rels/document.xml.rels"))
        rel_targets = {r.get("Id"): r.get("Target")
                       for r in rels_root.findall(f"{{{PKG_REL_NS}}}Relationship")}
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

        text = doc.decode("utf-8")
        print("[4] Required current strings in document.xml:")
        for s in REQUIRED_STRINGS:
            found = s in text
            ok &= found
            print(f"    {'OK ' if found else 'FAIL'}  '{s}' "
                  f"{'found' if found else 'NOT found'} (count={text.count(s)})")

        print("[5] Forbidden stale strings absent:")
        for s in FORBIDDEN_STRINGS:
            absent = s not in text
            ok &= absent
            print(f"    {'OK ' if absent else 'FAIL'}  '{s}' "
                  f"{'absent' if absent else 'STILL PRESENT'} (count={text.count(s)})")

    print("\nRESULT:", "ALL CHECKS PASSED" if ok else "VALIDATION FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
