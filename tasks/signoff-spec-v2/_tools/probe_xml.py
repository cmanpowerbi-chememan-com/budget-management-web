#!/usr/bin/env python
"""Probe document.xml for string presence and comment anchors."""
import re, sys, zipfile

def strip_tags(s):
    return re.sub(r"<[^>]+>", "", s)

def probe(path, patterns):
    xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
    print(f"=== {path} ===")
    for pat in patterns:
        n = xml.count(pat)
        print(f"  {pat!r}: {n}")
        if n == 0:
            # fuzzy: strip tags and search
            plain = strip_tags(xml)
            if pat in plain:
                print(f"    (found in stripped text only — RUN-SPLIT)")
    print()

def comment_anchors(path):
    with zipfile.ZipFile(path) as z:
        if "word/comments.xml" not in z.namelist():
            print("no comments.xml"); return
        comments = z.read("word/comments.xml").decode("utf-8")
        doc = z.read("word/document.xml").decode("utf-8")
    print(f"=== comment anchors: {path} ===")
    for m in re.finditer(r'<w:commentRangeStart w:id="(\d+)"', doc):
        cid = m.group(1)
        s = m.start()
        ctx = strip_tags(doc[s:s+800])[:120]
        print(f"  id={cid}: {ctx!r}")
    print()

if __name__ == "__main__":
    p = sys.argv[1]
    if len(sys.argv) > 2:
        probe(p, sys.argv[2:])
    else:
        comment_anchors(p)
