#!/usr/bin/env python
"""Apply run-id based text edits (+ changelog row inserts) to a .docx. Stdlib only.

Editing by run id is exact: each <w:t> run keeps its position, so we never match the
wrong text and repeated boilerplate is edited deterministically.

edits.json schema:
{
  "text": [ {"id": <int>, "new": "<replacement text>"}, ... ],
  "insert_row_after": [ {"anchor_id": <int>, "cells": ["c1","c2","c3"]}, ... ]
}

Replacement text rules:
  - Plain Unicode text. &, <, > are auto-escaped. Do NOT write XML tags.
  - Use the sentinel  [[BR]]  to insert a line break inside the cell/paragraph
    (renders as a new line, same formatting). Use "• " at line starts for bullets.

insert_row_after clones the <w:tr> that contains anchor_id and overwrites its
<w:t> runs with `cells` (in order). Use it to add a new changelog row; provide
exactly as many cells as the anchor row has text runs (run id tool prints them).

Usage:
  python apply_runs.py --in IN.docx --out OUT.docx --edits edits.json
  python apply_runs.py --in IN.docx --selftest          # round-trip (no edits) check
"""
import argparse, json, re, shutil, sys, zipfile
import xml.etree.ElementTree as ET

DOC = "word/document.xml"
RUN_RE = re.compile(r"(<w:t\b[^>]*>)(.*?)(</w:t>)", re.S)
TR_OPEN_RE = re.compile(r"<w:tr(?:>|\s)")  # the ROW element, not <w:trPr> (row props)
TR_CLOSE = "</w:tr>"
BR = "</w:t><w:br/><w:t xml:space=\"preserve\">"

def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def expand(new):
    # escape literal text, then turn the [[BR]] sentinel into a real line break
    return esc(new).replace("[[BR]]", BR)

def load(path):
    with zipfile.ZipFile(path) as z:
        return z.read(DOC).decode("utf-8")

def write_docx(src, dst, xml):
    tmp = dst + ".tmp"
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for it in zin.infolist():
            if it.filename == DOC:
                continue
            zout.writestr(it, zin.read(it.filename))
        zout.writestr(DOC, xml.encode("utf-8"))
    shutil.move(tmp, dst)

def apply_text_edits(xml, text_edits):
    by_id = {e["id"]: e["new"] for e in text_edits}
    done, missing = set(), set(by_id)
    counter = {"i": -1}
    def repl(m):
        counter["i"] += 1
        i = counter["i"]
        if i in by_id:
            done.add(i); missing.discard(i)
            return m.group(1) + expand(by_id[i]) + m.group(3)
        return m.group(0)
    out = RUN_RE.sub(repl, xml)
    return out, sorted(done), sorted(missing)

def run_span(xml, run_id):
    for i, m in enumerate(RUN_RE.finditer(xml)):
        if i == run_id:
            return m.start(), m.end()
    return None

def insert_rows(xml, inserts):
    # process from the LAST anchor to the first so offsets stay valid
    inserts = sorted(inserts, key=lambda d: d["anchor_id"], reverse=True)
    n = 0
    for ins in inserts:
        span = run_span(xml, ins["anchor_id"])
        if not span:
            raise ValueError(f"anchor_id {ins['anchor_id']} not found")
        opens = [m.start() for m in TR_OPEN_RE.finditer(xml, 0, span[0])]
        rs = opens[-1] if opens else -1
        re_ = xml.find(TR_CLOSE, span[1]) + len(TR_CLOSE)
        # guard: anchor must actually be INSIDE this <w:tr> (a real table cell),
        # i.e. no </w:tr> may appear between the row open and the anchor.
        if rs < 0 or re_ <= len(TR_CLOSE) - 1 or TR_CLOSE in xml[rs:span[0]]:
            raise ValueError(f"anchor_id {ins['anchor_id']} is not inside a table row (<w:tr>)")
        row = xml[rs:re_]
        cells = ins["cells"]
        cell_iter = iter(cells)
        slot = {"k": 0}
        def repl(m):
            try:
                val = next(cell_iter)
            except StopIteration:
                return m.group(0)
            return m.group(1) + expand(val) + m.group(3)
        new_row = RUN_RE.sub(repl, row)
        nleft = len(cells) - sum(1 for _ in RUN_RE.finditer(row))
        if nleft > 0:
            raise ValueError(f"row at anchor {ins['anchor_id']} has fewer <w:t> runs than {len(cells)} cells")
        xml = xml[:re_] + new_row + xml[re_:]
        n += 1
    return xml, n

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out")
    ap.add_argument("--edits")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    xml = load(a.inp)
    if a.selftest:
        out, done, missing = apply_text_edits(xml, [])
        assert out == xml, "no-op text pass changed the xml!"
        ET.fromstring(out)  # parses == well formed
        print(f"SELFTEST OK: no-op pass identical, xml well-formed, runs={len(list(RUN_RE.finditer(xml)))}")
        return

    edits = json.load(open(a.edits, encoding="utf-8"))
    xml, done, missing = apply_text_edits(xml, edits.get("text", []))
    xml, nrows = insert_rows(xml, edits.get("insert_row_after", []))
    ET.fromstring(xml)  # fail loudly if we produced invalid xml
    write_docx(a.inp, a.out, xml)
    print(f"WROTE {a.out}")
    print(f"  text edits applied: {len(done)}   rows inserted: {nrows}")
    if missing:
        print(f"  !! run ids NOT applied (out of range?): {missing}")

if __name__ == "__main__":
    main()
