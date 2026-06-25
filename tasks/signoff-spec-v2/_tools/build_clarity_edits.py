#!/usr/bin/env python
"""Build the merged SpecC clarity-edit set from the workflow output (stdlib only).

Combines: all per-module agent edits + a few cross-module consistency tweaks +
per-module version bump + a changelog entry. Writes edits_specC_clarity.json
(schema consumed by apply_runs.py).

  python build_clarity_edits.py <workflow_output.json> <out_edits.json>
"""
import sys, json

POLISH = ("ปรับถ้อยคำให้กระชับและอ่านง่ายขึ้น จัดบรรทัด/หัวข้อย่อยให้เป็นระบบ "
          "(คงตัวเลข โครงสร้าง และหมายเลขอ้างอิงภาพเดิมทั้งหมด)")

def main():
    wf = json.load(open(sys.argv[1], encoding="utf-8"))
    mods = wf["result"]["modules"]
    text = {}            # id -> new
    for m in mods:
        for e in m["edits"]:
            text[e["id"]] = e["new"]

    # --- fix agent run-id mismatch: the "Downstream" first-half rewrite was
    #     tagged id 600 (the hard-delete cell) but belongs to id 624 (the
    #     Downstream paragraph). Move it; leave 600 untouched. ---
    assert 624 not in text, "id 624 unexpectedly already edited"
    text[624] = text.pop(600)

    # --- consistency tweaks (safe, clearly beneficial) ---
    # #2 add (L3/L4) where Closing id173 dropped it
    text[173] = text[173].replace("สำหรับผู้กรอกทั่วไป", "สำหรับผู้กรอกทั่วไป (L3/L4)", 1)
    # #7 / #8 align bullet style: these 2-line cells are statement+continuation -> no bullets
    for rid in (741, 762):
        text[rid] = text[rid].replace("• ", "")

    # --- version bump (value cell of each module's metadata table) ---
    text[16]  = "v0.2.2 (ฉบับร่าง)"   # M0 GL Group
    text[165] = "v0.2.1 (ฉบับร่าง)"   # M1 Closing Date
    text[317] = "v0.3.1 (ฉบับร่าง)"   # M2 Org & Cost center
    text[479] = "v0.3.1 (ฉบับร่าง)"   # M3 Hide Document Number
    text[639] = "v0.4.1 (ฉบับร่าง)"   # M4 Master Currency

    # --- M2 changelog lives in a big layout row -> append a line to the note (id324) ---
    text[324] = text[324] + "[[BR]]• v0.3.1 (2026-06-25): " + POLISH

    # --- changelog row inserts for modules with a real changelog table/row ---
    inserts = [
        {"anchor_id": 35,  "cells": ["v0.2.2", "2026-06-25", POLISH]},                 # M0 (3-col)
        {"anchor_id": 175, "cells": ["v0.2.1 (2026-06-25)", POLISH]},                  # M1 (2-col)
        {"anchor_id": 495, "cells": ["v0.3.1", "2026-06-25", POLISH]},                 # M3 (3-col)
        {"anchor_id": 647, "cells": ["การเปลี่ยนแปลง (v0.4.1)", POLISH]},              # M4 (2-col)
    ]

    out = {"text": [{"id": k, "new": v} for k, v in sorted(text.items())],
           "insert_row_after": inserts}
    json.dump(out, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"text edits: {len(out['text'])}   row inserts: {len(inserts)} -> {sys.argv[2]}")

if __name__ == "__main__":
    main()
