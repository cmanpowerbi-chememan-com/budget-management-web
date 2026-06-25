#!/usr/bin/env python
"""Extract every <w:p> paragraph from a .docx with a stable index (stdlib only).

For docs whose paragraphs are fragmented into many <w:t> runs (Thai/Latin font
splits), the editable unit is the PARAGRAPH, not the run. Each paragraph gets:
  i           sequential index over <w:p> in document order
  text        concatenated visible text of all its <w:t> runs
  runs        number of text runs (fragmentation degree)
  mixed_bold  True if SOME text runs bold and some not (in-para emphasis)
  has_image   True if paragraph contains <w:drawing>/<w:pict> (a figure)
  has_link    True if paragraph contains <w:hyperlink>
  skip        True if it should NOT be collapse-rewritten (image/link/mixed_bold/empty)

  python extract_paras.py FILE.docx --json OUT
  python extract_paras.py FILE.docx            # print  i[skip?] <text>
"""
import sys, re, json, zipfile

DOC = "word/document.xml"
P_RE = re.compile(r"<w:p\b[^>]*>.*?</w:p>", re.S)
R_RE = re.compile(r"<w:r\b.*?</w:r>", re.S)
T_RE = re.compile(r"<w:t\b[^>]*>(.*?)</w:t>", re.S)

def unescape(s):
    return (s.replace("&lt;", "<").replace("&gt;", ">")
             .replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&"))

def paras(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read(DOC).decode("utf-8")
    out = []
    for i, m in enumerate(P_RE.finditer(xml)):
        p = m.group(0)
        runs = R_RE.findall(p)
        textruns = [r for r in runs if "<w:t" in r]
        text = unescape("".join("".join(T_RE.findall(r)) for r in textruns))
        bolds = [("<w:b/>" in r or "<w:b " in r) for r in textruns]
        mixed_bold = (any(bolds) and not all(bolds)) if textruns else False
        has_image = ("<w:drawing" in p) or ("<w:pict" in p) or ("<w:object" in p)
        has_link = "<w:hyperlink" in p
        empty = (len(text.strip()) == 0)
        out.append({
            "i": i, "text": text, "runs": len(textruns),
            "mixed_bold": mixed_bold, "has_image": has_image, "has_link": has_link,
            "skip": empty or has_image or has_link or mixed_bold,
        })
    return out

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    ps = paras(sys.argv[1])
    if "--json" in sys.argv:
        out = sys.argv[sys.argv.index("--json") + 1]
        json.dump(ps, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
        skip = sum(1 for p in ps if p["skip"])
        print(f"paragraphs={len(ps)}  rewritable={len(ps)-skip}  skip={skip} -> {out}")
    else:
        for p in ps:
            flag = "SKIP" if p["skip"] else f"r{p['runs']}"
            if p["text"].strip():
                print(f"{p['i']:4d} [{flag:>4}] {p['text'][:90]}")
