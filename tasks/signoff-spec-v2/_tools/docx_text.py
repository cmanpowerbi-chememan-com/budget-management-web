#!/usr/bin/env python
"""Extract readable text + acceptance metrics from a .docx (stdlib only).

Used to VERIFY the version2 docx after editing:
  python docx_text.py FILE.docx            # print body text
  python docx_text.py FILE.docx --metrics  # print acceptance counts only

Metrics: จึง count, arrow count, and presence of key strings.
"""
import sys, zipfile, re
import xml.etree.ElementTree as ET

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
def q(t): return f"{{{W}}}{t}"

def body_text(path):
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    body = root.find(q("body"))
    out = []
    def rec(el):
        tag = el.tag
        if tag == q("p"):
            for c in el: rec(c)
            out.append("\n"); return
        if tag == q("tr"):
            for c in el: rec(c)
            out.append("\n"); return
        if tag == q("tc"):
            out.append(" | ")
            for c in el: rec(c)
            return
        if tag == q("t"): out.append(el.text or ""); return
        if tag in (q("tab"),): out.append("\t"); return
        if tag in (q("br"), q("cr")): out.append("\n"); return
        for c in el: rec(c)
    rec(body)
    t = "".join(out)
    while "\n\n\n" in t: t = t.replace("\n\n\n", "\n\n")
    return t

def metrics(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    txt = body_text(path)
    print(f"=== {path} ===")
    print(f"  จึง total: {xml.count('จึง')}   ' จึง '(spaced): {len(re.findall(r' จึง ', xml))}   → : {xml.count('→')}")
    print(f"  'Azure AD' : {xml.count('Azure AD')}   'Entra ID' : {xml.count('Entra ID')}   'ADR-' : {xml.count('ADR-')}")
    print(f"  '+ ใส่รายละเอียดงบทำการ' : {xml.count('+ ใส่รายละเอียดงบทำการ')} (target 0)   'ใส่รายละเอียดงบทำการ' : {xml.count('ใส่รายละเอียดงบทำการ')}")
    print(f"  'เอกสาร 02' : {xml.count('เอกสาร 02')}   'เอกสาร approval' : {xml.count('เอกสาร approval')} (target 0)")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    if "--metrics" in sys.argv:
        metrics(sys.argv[1])
    else:
        print(body_text(sys.argv[1]))
