#!/usr/bin/env python
"""Find contiguous substrings in document.xml around a search term."""
import re, sys, zipfile

def strip(s):
    return re.sub(r"<[^>]+>", "", s)

def find_fragments(path, term, window=80):
    xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
    plain = strip(xml)
    idx = plain.find(term)
    print(f"term {term!r} in plain at {idx}")
    # find w:t runs containing parts
    runs = re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml)
    for i, r in enumerate(runs):
        if term[:3] in r or (len(term) > 3 and term in r):
            print(f"  run[{i}]: {r!r}")
            if i+1 < len(runs):
                print(f"  run[{i+1}]: {runs[i+1]!r}")
    # try contiguous pairs
    for i in range(len(runs)-1):
        pair = runs[i] + runs[i+1]
        if term in pair:
            print(f"  PAIR[{i}]+[{i+1}]: {pair!r}")

if __name__ == "__main__":
    find_fragments(sys.argv[1], sys.argv[2])
