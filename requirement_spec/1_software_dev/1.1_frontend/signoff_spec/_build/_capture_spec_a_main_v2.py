# -*- coding: utf-8 -*-
"""
Capture step for Spec A (V2.0) — หน้าหลักและสิทธิ์การเข้าถึง.

Renders the WIRED main-app mockup `design/mockups/0002claude design/0002.2budget-export.html`
to three cropped screenshots (one per document PART) and computes gold-marker
coordinates from live getBoundingClientRect — no hand-tuned pixels.

Two-file pattern (same as _capture_budget_closing_date.py + build_budget_closing_date_spec.py):
  this script   -> writes raw PNGs to bin/ (prefix speca2_) + bin/speca2_coords.json
  build script  -> Pillow-annotates those PNGs + assembles the .docx

Crops:
  speca2_page_head.png  — full .page-head (user bar + 🛡️ admin-mode toggle forced visible)   PART 1
  speca2_toolbar.png    — the .toolbar (year + ฝ่าย-picker + legend + reset + add + attach)   PART 2
  speca2_table.png      — the budget .table-panel (3-layer rows + special-GL detail button)    PART 3
  speca2_submit.png     — the #actionBar (Submit to Database button)                            PART 3

HARD CONSTRAINTS: stdlib + Playwright only (installed). Windows: run with `python -X utf8`.
Re-runnable: overwrites the PNGs + coords JSON each run.
"""

import os
import sys
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT_ROOT = r"c:\04.budget_management_web"
BIN_DIR = os.path.join(PROJECT_ROOT, "bin")
MOCKUP = Path(PROJECT_ROOT, "design", "mockups", "0002claude design",
              "0002.2budget-export.html")
COORDS_PATH = os.path.join(BIN_DIR, "speca2_coords.json")
os.makedirs(BIN_DIR, exist_ok=True)

SCALE = 2  # device_scale_factor — PNG is 2x the CSS pixels
RADIUS = 18  # gold-circle radius used by the builder (_circle default) — proof math matches it

RECT_JS = """(sels)=>sels.map(s=>{const e=document.querySelector(s);
    if(!e)return null;const r=e.getBoundingClientRect();
    return {x:r.left,y:r.top,w:r.width,h:r.height};})"""


def _markers_from_rects(points, rects, base_box):
    """Convert page rects -> image-pixel markers relative to a screenshotted box.

    Verbatim placement logic from build_main_web_app_spec.py: circle LEFT of the
    element when there is room, else ABOVE, else BELOW; leader endpoint pulled a few
    px inside the element box so the dot visibly touches it. All markers are GOLD
    (each PART has its own numbered legend table, so no per-marker accent needed).
    """
    markers = []
    for (label, _sel), r in zip(points, rects):
        if not r:
            markers.append(None)
            continue
        ex = (r["x"] - base_box["x"]) * SCALE
        ey = (r["y"] - base_box["y"]) * SCALE
        ew = r["w"] * SCALE
        eh = r["h"] * SCALE
        if ex > 70:                       # place circle to the LEFT
            cx, cy, tx, ty = ex - 30, ey + eh / 2, ex, ey + eh / 2
        elif ey > 70:                     # place ABOVE
            cx, cy, tx, ty = ex + ew / 2, ey - 28, ex + ew / 2, ey
        else:                             # place BELOW
            cx, cy, tx, ty = ex + ew / 2, ey + eh + 28, ex + ew / 2, ey + eh
        ins = 4
        tx = min(max(tx, ex + ins), ex + ew - ins)
        ty = min(max(ty, ey + ins), ey + eh - ins)
        markers.append({"label": label, "cx": cx, "cy": cy, "tx": tx, "ty": ty,
                        "ex": ex, "ey": ey, "ew": ew, "eh": eh})
    return markers


def _markers_above(points, rects, base_box, gap=6):
    """Place EACH circle centered ABOVE its element (leader points straight down).

    Toolbar-only. The default `_markers_from_rects` puts circles 30px to the LEFT,
    which in a dense horizontal .toolbar makes each number visually sit on the
    PREVIOUS element (bug from user visual review 2026-07-13). Above-markers avoid
    that: element centers-x are >150px apart, so stacked-above circles never collide.
    base_box is the padded CLIP region (headroom added above the toolbar) so the
    whole circle lands in that headroom — cy - RADIUS stays >= 0 with pad_top=34.
    Invariant: cy + RADIUS <= ey (entire circle above the element top).
    """
    markers = []
    for (label, _sel), r in zip(points, rects):
        if not r:
            markers.append(None)
            continue
        ex = (r["x"] - base_box["x"]) * SCALE
        ey = (r["y"] - base_box["y"]) * SCALE
        ew = r["w"] * SCALE
        eh = r["h"] * SCALE
        cx = ex + ew / 2                    # horizontally centered on the element
        cy = ey - (RADIUS + gap)           # whole circle above top: cy + RADIUS = ey - gap <= ey
        tx = cx                            # leader straight down
        ty = ey + min(eh / 2, 10)          # tip a few px inside the element top
        markers.append({"label": label, "cx": cx, "cy": cy, "tx": tx, "ty": ty,
                        "ex": ex, "ey": ey, "ew": ew, "eh": eh})
    return markers


def _grab_above(pg, key, base_selector, points, out, pad_top=34):
    """Toolbar variant: clip-screenshot with headroom ABOVE, place circles above."""
    base = pg.locator(base_selector).first
    bb = base.bounding_box()
    clip = {"x": bb["x"], "y": bb["y"] - pad_top, "width": bb["width"],
            "height": bb["height"] + pad_top}
    rects = pg.evaluate(RECT_JS, [s for _, s in points])
    png_name = f"speca2_{key}.png"
    png_path = os.path.join(BIN_DIR, png_name)
    pg.screenshot(path=png_path, clip=clip)
    base_box = {"x": clip["x"], "y": clip["y"]}
    markers = _markers_above(points, rects, base_box)
    missing = [points[i][0] for i, m in enumerate(markers) if m is None]
    out[key] = {"png": png_name, "markers": [m for m in markers if m]}
    print(f"  [{key}] {png_path}  markers={len(out[key]['markers'])}/{len(points)} (above+headroom)"
          + (f"  MISSING={missing}" if missing else ""))
    return missing


def _grab(pg, key, base_selector, points, out):
    """Measure child rects, screenshot the base element, store markers."""
    base = pg.locator(base_selector).first
    bbox = base.bounding_box()
    rects = pg.evaluate(RECT_JS, [s for _, s in points])
    png_name = f"speca2_{key}.png"
    png_path = os.path.join(BIN_DIR, png_name)
    base.screenshot(path=png_path)
    markers = _markers_from_rects(points, rects, bbox)
    missing = [points[i][0] for i, m in enumerate(markers) if m is None]
    out[key] = {"png": png_name, "markers": [m for m in markers if m]}
    print(f"  [{key}] {png_path}  markers={len(out[key]['markers'])}/{len(points)}"
          + (f"  MISSING={missing}" if missing else ""))
    return missing


def capture():
    out = {}
    all_missing = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1700, "height": 1180},
                        device_scale_factor=SCALE)
        pg.goto(MOCKUP.as_uri())
        pg.wait_for_selector(".data-table tbody tr")
        pg.wait_for_timeout(400)

        def use_user(key):
            pg.evaluate(f"switchUser('{key}')")
            pg.wait_for_timeout(160)

        def lock_dept(dept):
            pg.evaluate(f"pickDept({dept!r})")
            pg.wait_for_timeout(160)

        # The demo data is all seeded in FY2026 (the page default); no year pin needed.

        # ── PART 1 — .page-head (user bar + สิทธิ์การเข้าถึง) ──────────────────────
        #   suchanya = a normal submitter scoped to ONE division / ONE ฝ่าย / ONE CC
        #   → a clean hierarchy user-bar with a USER badge. The 🛡️ admin-mode toggle
        #   is display:none for a plain user, so we force it visible (it is a demo
        #   affordance — ADR-0014) so marker ⑥ has something to point at.
        use_user("suchanya")
        lock_dept("Solution Delivery")
        pg.evaluate(
            "var w=document.getElementById('adminModeWrap');"
            "if(w){w.style.display='';w.style.visibility='visible';}")
        pg.wait_for_timeout(120)
        ph_points = [
            ("1", "#userBar .user-avatar"),      # avatar + ชื่อผู้ใช้
            ("2", "#userBar .role-badge"),       # ป้ายบทบาท USER/ADMIN
            ("3", "#userBar .v3-division"),      # สายงาน (Division)
            ("4", "#userBar .v3-label-wrap"),    # ฝ่าย (Department) + จำนวน
            ("5", "#userBar .v3-metrics"),       # จำนวน Cost Center + GL Codes
            ("6", "#adminModeWrap"),             # 🛡️ สวิตช์โหมด Admin
        ]
        all_missing["page_head"] = _grab(pg, "page_head", ".page-head", ph_points, out)

        # ── PART 2 — .toolbar (ตัวกรอง + ปุ่มเครื่องมือ) ─────────────────────────
        #   Still suchanya · Solution Delivery. The legend year labels are populated
        #   by renderTable(), which switchUser/pickDept already ran.
        tb_points = [
            ("1", "#yearFilter"),               # ตัวกรองปีงบประมาณ
            ("2", "#faipTrig"),                 # ตัวกรองฝ่าย (ฝ่าย-picker trigger)
            ("3", ".toolbar .legend"),          # legend สถานะ (SAP/Approved/Pending)
            ("4", ".toolbar .btn-ghost"),       # Reset columns
            ("5", ".toolbar .btn-add"),         # + เพิ่ม Transaction
            ("6", ".toolbar .btn-attach"),      # แนบไฟล์
        ]
        #   Markers sit ABOVE each element (not left) on a clip with headroom — see
        #   _markers_above (fixes the "number labels the previous element" bug).
        all_missing["toolbar"] = _grab_above(pg, "toolbar", ".toolbar", tb_points, out)

        # ── PART 3a — .table-panel (ตารางกรอกข้อมูล · 3 ชั้น + special-GL) ────────
        #   suchanya + Solution Delivery + DRAFT → Pending cells editable, and the
        #   special-GL row (txn 5 = Professional & Legal Fee) shows the "ใส่รายละเอียด
        #   งบทำการ" detail button. txn 1 = a normal GL with SAP+Approved+Pending.
        use_user("suchanya")
        lock_dept("Solution Delivery")
        pg.wait_for_timeout(120)
        tbl_points = [
            ("1", "#cc_1 .dropdown-input"),                                             # คอลัมน์ Cost Center/GL/Group/Remark
            ("2", 'tr[data-status="sap"][data-txn-id="1"] .status-cell.sap'),           # STATUS + 3 ชั้น
            ("3", 'tr[data-status="pending"][data-txn-id="1"] .month-value.pending-input[data-i="0"]'),  # ช่องกรอกรายเดือน
            ("4", 'tr[data-status="pending"].special[data-txn-id="5"] .btn-detail'),    # ป้าย GL พิเศษ + subform
        ]
        all_missing["table"] = _grab(pg, "table", ".table-panel", tbl_points, out)

        # ── PART 3b — #actionBar (ปุ่ม Submit to Database) ───────────────────────
        #   submitBtn shows because Solution Delivery ∈ suchanya's fill-scope.
        sub_points = [("5", "#submitBtn")]
        all_missing["submit"] = _grab(pg, "submit", "#actionBar", sub_points, out)

        b.close()

    with open(COORDS_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\ncoords -> {COORDS_PATH}")

    # ---- self-check (computed only — never open a PNG) ----------------------- #
    def _inside(m):
        return (m["ex"] <= m["tx"] <= m["ex"] + m["ew"]
                and m["ey"] <= m["ty"] <= m["ey"] + m["eh"])
    ok = True
    for key, blk in out.items():
        insides = [_inside(m) for m in blk["markers"]]
        print(f"[PROOF] {key}: markers={len(blk['markers'])} "
              f"leaders-inside={sum(insides)}/{len(insides)}")

    # toolbar-specific proof: circle ABOVE element top + leader tip within element x-range
    print(f"[TOOLBAR-PROOF] RADIUS={RADIUS}; require cy+RADIUS<=ey (circle above) and ex<=tx<=ex+ew")
    for m in out.get("toolbar", {}).get("markers", []):
        above = (m["cy"] + RADIUS) <= m["ey"]
        tx_in = m["ex"] <= m["tx"] <= m["ex"] + m["ew"]
        print(f"  {m['label']}: cy={m['cy']:.0f} cy+r={m['cy']+RADIUS:.0f} ey(top)={m['ey']:.0f} "
              f"ABOVE={above} | tx={m['tx']:.0f} in [{m['ex']:.0f},{m['ex']+m['ew']:.0f}]={tx_in} "
              f"-> {'PASS' if above and tx_in else 'FAIL'}")
    for key, miss in all_missing.items():
        if miss:
            ok = False
            print(f"[WARN] {key} missing selectors: {miss}")
    print("CAPTURE_DONE" if ok else "CAPTURE_DONE_WITH_WARNINGS")
    return out


if __name__ == "__main__":
    capture()
