#!/usr/bin/env python
"""Deterministic fact-preservation check for a run-text rewrite (stdlib only).

For every edited run, extract the "protected tokens" from the ORIGINAL text and
assert each still appears in the NEW text. Catches accidental drops of numbers,
code identifiers, markers, ADR refs, emails, API paths, arrows. Order-independent.
This is a hard, non-LLM guarantee; flagged items need a human look (not always wrong).

  python check_preservation.py runs.json edits.json
    runs.json  = {"runs":[{"id","text"},...]}  (original)
    edits.json = {"text":[{"id","new"},...], ...}
"""
import sys, re, json
from collections import Counter

def tokens(t):
    """Return dict of protected-token-kind -> list, extracted from text t."""
    return {
        "backtick": re.findall(r"`[^`]+`", t),
        "adr": re.findall(r"ADR-\d+", t),
        "email": re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]+", t),
        "api": re.findall(r"/api[\w/.-]*", t),
        "marker": re.findall(r"[①-⑳]", t),          # ①..⑳
        "section": re.findall(r"\b\d+\.\d+[a-z]?\b", t),       # 1.1, 2.4a
        "module": re.findall(r"Module\s*\d+", t),
        "arrow": re.findall(r"[→▲▼]", t),       # → ▲ ▼
        # all standalone integer/decimal runs (years, counts, ranges, rates, http codes)
        "number": re.findall(r"\d+(?:\.\d+)?", t),
    }

def main():
    runs = {r["id"]: r["text"] for r in json.load(open(sys.argv[1], encoding="utf-8"))["runs"]}
    edits = json.load(open(sys.argv[2], encoding="utf-8")).get("text", [])
    total_flags = 0
    for e in edits:
        rid, new = e["id"], e["new"].replace("[[BR]]", "\n")
        old = runs.get(rid, "")
        if not old:
            print(f"  !! id {rid}: original run not found"); total_flags += 1; continue
        ot, nt = tokens(old), tokens(new)
        miss = []
        for kind in ot:
            oc, nc = Counter(ot[kind]), Counter(nt[kind])
            for tok, cnt in oc.items():
                if nc[tok] < cnt:
                    miss.append(f"{kind}:{tok}(x{cnt}->{nc[tok]})")
        if miss:
            total_flags += 1
            print(f"  FLAG id {rid}: dropped {len(miss)} token(s): {', '.join(miss)}")
    print(f"\n=== {len(edits)} edits checked, {total_flags} flagged for review ===")
    if total_flags == 0:
        print("PASS: no protected tokens dropped.")

if __name__ == "__main__":
    main()
