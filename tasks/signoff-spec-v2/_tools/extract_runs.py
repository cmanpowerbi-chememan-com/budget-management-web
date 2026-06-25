#!/usr/bin/env python
"""Extract every <w:t> run from a .docx with a stable sequential id (stdlib only).

Each paragraph/table-cell in the SpecC docs is a SINGLE contiguous run, so one
run id == one editable unit of text. Editing by run id (not find/replace text) is
exact + unique, so repeated boilerplate can be edited consistently and there is no
risk of a find-string matching the wrong place.

  python extract_runs.py FILE.docx            # print id<TAB>text (one per line)
  python extract_runs.py FILE.docx --json OUT  # dump [{id,text}] + module segments

Module segmentation: a run whose text starts with the section-title prefix
'ส่วน C' marks the start of a module page. We tag each run with its module index.
"""
import sys, re, json, zipfile

DOC = "word/document.xml"
RUN_RE = re.compile(r"<w:t\b[^>]*>(.*?)</w:t>", re.S)

def unescape(s):
    return (s.replace("&lt;", "<").replace("&gt;", ">")
             .replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&"))

def runs(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read(DOC).decode("utf-8")
    out = []
    for i, m in enumerate(RUN_RE.finditer(xml)):
        out.append({"id": i, "text": unescape(m.group(1))})
    return out

def segment(rs):
    """Assign each run a module index by watching for 'ส่วน C ... หน้า:' title runs."""
    mod = -1
    titles = []
    for r in rs:
        t = r["text"]
        if t.startswith("ส่วน C") and "หน้า:" in t:
            mod += 1
            titles.append({"module": mod, "start_id": r["id"], "title": t})
        r["module"] = mod
    return titles

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    rs = runs(sys.argv[1])
    titles = segment(rs)
    if "--json" in sys.argv:
        out = sys.argv[sys.argv.index("--json") + 1]
        json.dump({"runs": rs, "modules": titles}, open(out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(f"runs={len(rs)} modules={len(titles)} -> {out}")
        for t in titles:
            print(f"  module {t['module']} starts id={t['start_id']}: {t['title'][:70]}")
    else:
        for r in rs:
            print(f"{r['id']}\t[m{r['module']}]\t{r['text']}")
