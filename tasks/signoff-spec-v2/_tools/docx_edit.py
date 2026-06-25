#!/usr/bin/env python
"""Apply literal find->replace edits + the arrow-restore rule to a .docx.

Stdlib only (no pip install — dev machine forbids it). Edits word/document.xml
inside the zip in place; all other members copied unchanged → valid .docx out.

Target strings in these docs are CONTIGUOUS in document.xml (verified), so literal
string replace works without run-merging.

Usage:
  python docx_edit.py --in IN.docx --out OUT.docx --edits edits.json [--arrows]

edits.json = [{"find": "...", "replace": "...", "expect": 1}, ...]
  expect (optional) = how many occurrences you expect; script warns if mismatch.
--arrows = also apply the global rule " จึง " -> " → " (restores flow arrows that the
           consolidation mangled). Reports any remaining non-space-delimited "จึง"
           for manual review against the source spec.
"""
import argparse, json, os, shutil, sys, zipfile, re

DOC = "word/document.xml"

def load_xml(path):
    with zipfile.ZipFile(path) as z:
        return z.read(DOC).decode("utf-8")

def write_docx(src, dst, new_xml):
    # copy every member except document.xml, then add the edited document.xml
    tmp = dst + ".tmp"
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename == DOC:
                continue
            zout.writestr(item, zin.read(item.filename))
        zout.writestr(DOC, new_xml.encode("utf-8"))
    shutil.move(tmp, dst)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", required=True)
    ap.add_argument("--edits", default=None)
    ap.add_argument("--arrows", action="store_true")
    a = ap.parse_args()

    xml = load_xml(a.inp)
    report = []

    if a.edits and os.path.exists(a.edits):
        edits = json.load(open(a.edits, encoding="utf-8"))
        for e in edits:
            find, repl = e["find"], e["replace"]
            n = xml.count(find)
            exp = e.get("expect")
            if n == 0:
                report.append(f"  !! NOT FOUND: {find!r}  (string not present — check quote chars / spacing in the real docx)")
                continue
            if exp is not None and n != exp:
                report.append(f"  ?? count {n} != expect {exp} for {find!r}")
            xml = xml.replace(find, repl)
            report.append(f"  ok x{n}: {find[:50]!r} -> {repl[:50]!r}")

    if a.arrows:
        before = xml.count("จึง")
        spaced = len(re.findall(r" จึง ", xml))
        xml = xml.replace(" จึง ", " → ")
        after = xml.count("จึง")
        report.append(f"  arrows: ' จึง '->' → ' applied x{spaced}; จึง {before} -> {after} (remaining are embedded/edge — review vs source)")
        # list remaining จึง with context for manual review
        for m in re.finditer(r"จึง", xml):
            s = max(0, m.start() - 30); e = min(len(xml), m.end() + 30)
            ctx = re.sub(r"<[^>]+>", "", xml[s:e])  # strip tags for readability
            report.append(f"     REVIEW จึง: ...{ctx}...")

    write_docx(a.inp, a.out, xml)
    print(f"WROTE {a.out}")
    print("\n".join(report))

if __name__ == "__main__":
    main()
