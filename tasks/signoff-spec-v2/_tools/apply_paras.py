#!/usr/bin/env python
"""Apply paragraph-index COLLAPSE rewrites to a .docx (stdlib only).

For each edited paragraph i: keep its <w:pPr> (alignment/list/spacing) and replace
ALL its runs with ONE new run that uses the rPr (font/size/colour/bold) of the
paragraph's longest existing text run — so Thai+Latin fonts (ascii + cs) survive.
Use the sentinel [[BR]] for line breaks and "• " at line starts for bullets.

SAFETY: refuses to edit a paragraph containing an image/hyperlink/field unless the
rPr template is found and no <w:drawing> present (those should be marked skip in
extract_paras.py and never sent here).

edits.json = {"paras": [{"i": <int>, "new": "<text with [[BR]]>"}, ...]}

  python apply_paras.py --in IN.docx --out OUT.docx --edits edits.json
  python apply_paras.py --in IN.docx --selftest
"""
import argparse, json, re, shutil, sys, zipfile
import xml.etree.ElementTree as ET

DOC = "word/document.xml"
P_RE = re.compile(r"(<w:p\b[^>]*>)(.*?)(</w:p>)", re.S)
PPR_RE = re.compile(r"<w:pPr\b.*?</w:pPr>", re.S)
R_RE = re.compile(r"<w:r\b.*?</w:r>", re.S)
RPR_RE = re.compile(r"<w:rPr\b.*?</w:rPr>", re.S)
T_RE = re.compile(r"<w:t\b[^>]*>(.*?)</w:t>", re.S)
BR = "</w:t><w:br/><w:t xml:space=\"preserve\">"

def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def expand(new):
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

def rpr_template(inner):
    """rPr of the text run with the most characters (dominant style)."""
    best, best_len = "", -1
    for r in R_RE.findall(inner):
        if "<w:t" not in r:
            continue
        txt = "".join(T_RE.findall(r))
        if len(txt) > best_len:
            best_len = len(txt)
            m = RPR_RE.search(r)
            best = m.group(0) if m else ""
    return best

def rebuild_para(open_tag, inner, new_text):
    if "<w:drawing" in inner or "<w:pict" in inner or "<w:object" in inner:
        raise ValueError("refuse: paragraph contains an image/object (mark skip)")
    ppr_m = PPR_RE.search(inner)
    ppr = ppr_m.group(0) if ppr_m else ""
    rpr = rpr_template(inner)
    run = f"<w:r>{rpr}<w:t xml:space=\"preserve\">{expand(new_text)}</w:t></w:r>"
    return open_tag + ppr + run + "</w:p>"

def apply_edits(xml, edits):
    by_i = {e["i"]: e["new"] for e in edits}
    done, missing = set(), set(by_i)
    counter = {"i": -1}
    def repl(m):
        counter["i"] += 1
        i = counter["i"]
        if i in by_i:
            done.add(i); missing.discard(i)
            return rebuild_para(m.group(1), m.group(2), by_i[i])
        return m.group(0)
    out = P_RE.sub(repl, xml)
    return out, sorted(done), sorted(missing)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out")
    ap.add_argument("--edits")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    xml = load(a.inp)
    if a.selftest:
        out, done, missing = apply_edits(xml, [])
        assert out == xml, "no-op pass changed the xml!"
        ET.fromstring(out)
        print(f"SELFTEST OK: no-op identical, well-formed, paragraphs={len(P_RE.findall(xml))}")
        return

    edits = json.load(open(a.edits, encoding="utf-8")).get("paras", [])
    xml, done, missing = apply_edits(xml, edits)
    ET.fromstring(xml)  # fail loudly on malformed xml
    write_docx(a.inp, a.out, xml)
    print(f"WROTE {a.out}")
    print(f"  paragraphs rewritten: {len(done)}")
    if missing:
        print(f"  !! indices NOT applied (out of range?): {missing}")

if __name__ == "__main__":
    main()
