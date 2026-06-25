#!/usr/bin/env python
"""Verify a paragraph-collapse rewrite (stdlib only). Two hard checks per edit:

  1. PRESERVATION — every protected token in the OLD paragraph text still appears
     in the NEW text (numbers, `backtick`, ADR-, emails, /api, ①-⑳ markers,
     section nums, Module N, →▲▼). Order-independent multiset. Dropped = FLAG.
  2. OVERLAP — fraction of OLD word-tokens retained in NEW. <0.45 likely means the
     edit was attached to the WRONG paragraph index (the SpecC run-id mismatch class
     of bug). Low overlap = FLAG for a human look.

  python check_paras.py parasB.json edits.json
    parasB.json = output of extract_paras.py  [{i,text,...}]
    edits.json  = {"paras":[{i,new}, ...]}
"""
import sys, re, json
from collections import Counter

def prot(t):
    return {
        "backtick": re.findall(r"`[^`]+`", t),
        "adr": re.findall(r"ADR-\d+", t),
        "email": re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]+", t),
        "api": re.findall(r"/api[\w/.-]*", t),
        "marker": re.findall(r"[①-⑳]", t),
        "section": re.findall(r"\b\d+\.\d+[a-z]?\b", t),
        "module": re.findall(r"Module\s*\d+", t),
        "arrow": re.findall(r"[→▲▼]", t),
        "number": re.findall(r"\d+(?:\.\d+)?", t),
    }

def words(s):
    return set(re.findall(r"[A-Za-z0-9_.]+|[฀-๿]{2,}", s.replace("[[BR]]", " ")))

def main():
    paras = {p["i"]: p["text"] for p in json.load(open(sys.argv[1], encoding="utf-8"))}
    edits = json.load(open(sys.argv[2], encoding="utf-8")).get("paras", [])
    drop_flags = overlap_flags = 0
    for e in edits:
        i, new = e["i"], e["new"].replace("[[BR]]", "\n")
        old = paras.get(i, "")
        if not old.strip():
            print(f"  NOTE i={i}: original paragraph empty/not found"); continue
        po, pn = prot(old), prot(new)
        miss = []
        for k in po:
            oc, nc = Counter(po[k]), Counter(pn[k])
            for tok, c in oc.items():
                if nc[tok] < c:
                    miss.append(f"{k}:{tok}(x{c}->{nc[tok]})")
        if miss:
            drop_flags += 1
            print(f"  DROP  i={i}: {', '.join(miss)}")
        wo, wn = words(old), words(new)
        if wo:
            ov = len(wo & wn) / len(wo)
            if ov < 0.45:
                overlap_flags += 1
                print(f"  OVERLAP i={i} retain={ov:.2f}: OLD={old[:55]!r}  NEW={new[:55]!r}")
    print(f"\n=== {len(edits)} edits | preservation flags: {drop_flags} | overlap flags: {overlap_flags} ===")
    print("PASS" if drop_flags == 0 and overlap_flags == 0 else "REVIEW NEEDED")

if __name__ == "__main__":
    main()
