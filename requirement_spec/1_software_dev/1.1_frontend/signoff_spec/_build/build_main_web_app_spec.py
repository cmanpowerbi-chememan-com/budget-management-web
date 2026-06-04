# -*- coding: utf-8 -*-
"""
Generator — Main Budget Web App page · User Sign-off Specification (.docx).

ส่วน A · Module 01 — หน้าหลักของระบบงบประมาณ (OPEX Data Management).
ตารางงบประมาณรายเดือน: ส่วน SAP (Actuals) + ส่วน Pending (รออนุมัติ กรอกมือ)
พร้อม toolbar Export / Import approved budget (admins only).

DRAFT (ฉบับร่าง) — "ร่างตามนี้ก่อน" รายละเอียดเพิ่มเติมจะตามมา.

Reuses the OOXML + Pillow + Playwright pattern from build_special_gl_subform_spec.py
VERBATIM (OOXML helpers copied, capture()/annotate()/build_body()/main() shape kept).
New here: capture step targets the MAIN table page (not the modal) and computes gold
marker coordinates from live DOM getBoundingClientRect — no hand-tuned pixels.

HARD CONSTRAINTS:
  - NO package installation. stdlib + Pillow + Playwright (all installed).
  - .docx built by hand as WordprocessingML. Thai uses Leelawadee UI, szCs==sz.
  - Mockup source: design/mockups/0002claude design/0002budget-export.html
Re-runnable: overwrites screenshots (bin/, prefix main_), assets, and the .docx each run.
"""

import os, io, sys, zipfile, html, pathlib
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

# Console may be cp1252 on Windows; PROOF lines print ①②③ — force UTF-8 stdout.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT_ROOT = r"c:\04.budget_management_web"
SIGNOFF_DIR = os.path.join(PROJECT_ROOT, "requirement_spec", "1_software_dev", "1.1_frontend", "signoff_spec")
ASSETS_DIR = os.path.join(SIGNOFF_DIR, "assets")
BIN_DIR = os.path.join(PROJECT_ROOT, "bin")
DOCX_PATH = os.path.join(SIGNOFF_DIR, "01_main_web_app_spec.docx")
MOCKUP = pathlib.Path(PROJECT_ROOT, "design", "mockups", "0002claude design", "0002budget-export.html")
os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(BIN_DIR, exist_ok=True)

GOLD = (201, 150, 61); GOLD_DARK = (140, 100, 35); WHITE = (255, 255, 255)
# Per-marker accent colors (FIX A — SAP markers only; everything else stays GOLD).
RED = (211, 47, 47); RED_DARK = (142, 27, 27)        # SAP status badge   (marker ①)
GREEN = (46, 125, 50); GREEN_DARK = (27, 94, 32)     # SAP green value     (marker ②)
NUM_FONT_PATH = r"C:\Windows\Fonts\arialbd.ttf"
THAI_FONT = "Leelawadee UI"
SCALE = 2  # device_scale_factor


# --------------------------------------------------------------------------- #
# CAPTURE — screenshot the main page + read element rects for gold markers.
# Returns {key: (img_path, markers)} where markers are in image-pixel space.
# --------------------------------------------------------------------------- #
def _markers_from_rects(points, rects, base_box, colors=None):
    """Convert page rects -> image-pixel markers relative to a screenshotted box.

    colors (optional): list parallel to `points`; each item is a (fill, outline)
    tuple OR None. None / missing -> default GOLD (so every other illustration is
    unchanged). FIX A passes RED for the SAP status marker and GREEN for the SAP
    value marker only. Each marker also records the rect box it anchors to
    (ex/ey/ew/eh) so the proof step can assert the leader endpoint lands inside it.
    """
    markers = []
    for i, ((label, _), r) in enumerate(zip(points, rects)):
        if not r:
            continue
        ex = (r["x"] - base_box["x"]) * SCALE; ey = (r["y"] - base_box["y"]) * SCALE
        ew = r["w"] * SCALE; eh = r["h"] * SCALE
        if ex > 70:  # place circle to the LEFT of the element
            cx, cy, tx, ty = ex - 30, ey + eh / 2, ex, ey + eh / 2
        elif ey > 70:  # place ABOVE
            cx, cy, tx, ty = ex + ew / 2, ey - 28, ex + ew / 2, ey
        else:  # too close to both edges -> place BELOW
            cx, cy, tx, ty = ex + ew / 2, ey + eh + 28, ex + ew / 2, ey + eh
        # Pull the leader endpoint a few px INSIDE the element box (clamped) so the
        # dot visibly touches the cell and the proof's inside-box check is exact.
        ins = 4
        tx = min(max(tx, ex + ins), ex + ew - ins)
        ty = min(max(ty, ey + ins), ey + eh - ins)
        col = (colors[i] if colors and i < len(colors) and colors[i] else (GOLD, GOLD_DARK))
        markers.append({"label": label, "cx": cx, "cy": cy, "tx": tx, "ty": ty,
                        "fill": col[0], "dark": col[1],
                        "ex": ex, "ey": ey, "ew": ew, "eh": eh})
    return markers


RECT_JS = """(sels)=>sels.map(s=>{const e=document.querySelector(s);
    if(!e)return null;const r=e.getBoundingClientRect();return {x:r.left,y:r.top,w:r.width,h:r.height};})"""


def capture():
    out = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1700, "height": 1180}, device_scale_factor=SCALE)
        pg.goto(MOCKUP.as_uri()); pg.wait_for_selector(".data-table tbody tr")
        pg.wait_for_timeout(300)

        # ── 0) LOGIN BAR — two role views (NEW 2026-06-05) ──
        #     The new mockup adds <section id="userBar"> showing WHO is logged in and
        #     WHAT scope (avatar, name, ADMIN/USER badge, email-or-scope subline,
        #     department-name chips, and a demo "เข้าสู่ระบบเป็น" switcher). We capture
        #     it twice: admin (sees ALL CC) + a normal user (paiboon, scoped to own CC).
        #     No markers (annotate handles []). Then switch BACK to admin so all later
        #     captures (overview/sap/approved/pending/detail) stay in admin scope.
        # LOGIN BAR — admin (sees all CC)
        pg.evaluate("switchUser('admin')"); pg.wait_for_timeout(150)
        ub = pg.locator("#userBar").first
        la_path = os.path.join(BIN_DIR, "main_login_admin.png")
        ub.screenshot(path=la_path)
        out["login_admin"] = (la_path, [])
        # LOGIN BAR — normal user (paiboon, scoped to own CC)
        pg.evaluate("switchUser('paiboon')"); pg.wait_for_timeout(150)
        ub2 = pg.locator("#userBar").first
        lu_path = os.path.join(BIN_DIR, "main_login_user.png")
        ub2.screenshot(path=lu_path)
        out["login_user"] = (lu_path, [])
        # back to admin for remaining captures
        pg.evaluate("switchUser('admin')"); pg.wait_for_timeout(150)

        # ── 1) OVERVIEW — whole table panel (SAP + Approved + Pending rows) ──
        #     EDIT (2026-06-04): removed the SAP-STATUS marker. It duplicated the
        #     SAP green-VALUE marker (both said "this row is SAP Actuals"), so the
        #     status badge ('.status-cell.sap') was dropped and the remaining 4
        #     markers renumbered 1–4 (no gap). All markers still belong to ONE row
        #     group via data-txn-id="4" (the Entertainment / MKT001 / 6211900030 row),
        #     except marker 4 which points at the FIRST Pending month-value cell
        #     (ม.ค./Jan) of txn-id 3 (KKAW01, normal GL) where the user drew the red
        #     dot. (Re-anchored 2026-06-04 from the txn-3 PENDING status bar onto
        #     this Pending input cell.)
        #     Labels travel WITH the selector via zip() in _markers_from_rects, so no
        #     positional auto-renumbering happens: marker "N" == the Nth selector.
        #
        #     New top-to-bottom order:
        #       1 = SAP green value      (.month-value.sap, txn 4) — Actuals read-only
        #       2 = APPROVED blue input  (.month-value.approved-input, txn 4) — Admin import/type
        #       3 = PENDING input cell   (.month-value.pending-readonly, txn 4) — special GL, read-only sum from subform
        #       4 = PENDING input cell   (.month-value.pending-input, txn 3 Jan) — normal GL, user types Pending directly
        #
        #     NB: Entertainment IS a Special GL group, so its Pending sub-row renders
        #     .month-value.pending-readonly (the grey box) — NOT .pending-input — which
        #     is why marker 3 uses the -readonly selector pinned to txn-id 4.
        panel = pg.locator(".table-panel").first
        pbox = panel.bounding_box()
        ov_points = [
            ("1", 'tr[data-status="sap"][data-txn-id="4"] .month-value.sap'),
            ("2", 'tr[data-status="approved"][data-txn-id="4"] .month-value.approved-input'),
            ("3", 'tr[data-status="pending"][data-txn-id="4"] .month-value.pending-readonly'),
            # marker 4 (re-anchored 2026-06-04): moved RIGHT off the txn-3 PENDING
            # status bar onto the FIRST month-value cell (ม.ค./Jan) of that SAME
            # txn-3 PENDING row where the user drew the red dot. txn-3 = KKAW01,
            # GL 5200016355 (group 'ค่าบำรุงรักษา') is a NORMAL GL → its pending
            # cells are editable .month-value.pending-input (not -readonly). The
            # pending <tr> direct children are: [status td] then 12 month <td>s, so
            # querySelector('.month-value.pending-input') (document order) returns
            # the leftmost = Jan column (data-i="0") deterministically.
            ("4", 'tr[data-status="pending"][data-txn-id="3"] .month-value.pending-input'),
        ]
        ov_rects = pg.evaluate(RECT_JS, [s for _, s in ov_points])
        ov_path = os.path.join(BIN_DIR, "main_overview.png")
        panel.screenshot(path=ov_path)
        out["overview"] = (ov_path, _markers_from_rects(ov_points, ov_rects, pbox))

        # ── 2) TOOLBAR — Export / Import / Add buttons ──
        tb = pg.locator(".toolbar").first
        tbox = tb.bounding_box()
        tb_points = [("1", ".btn-export"), ("2", ".btn-import"), ("3", "#yearFilter")]
        tb_rects = pg.evaluate(RECT_JS, [s for _, s in tb_points])
        tb_path = os.path.join(BIN_DIR, "main_toolbar.png")
        tb.screenshot(path=tb_path)
        out["toolbar"] = (tb_path, _markers_from_rects(tb_points, tb_rects, tbox))

        # ── 3) SAP COLUMNS (Actuals) — FIX A (2026-06-04) ──
        #     Problem: the 2 SAP markers read poorly on the full wide panel — they were
        #     tiny because the panel is ~1700px wide.
        #     Fix: TIGHT crop. base_box = union of the SAP status badge + the SAP first
        #     month value cell, padded, and only ONE row tall (the txn-1 SAP row). The
        #     status badge sits in the far-left STATUS column and the green value is the
        #     first month column — the crop spans status→Jan but is vertically tight, so
        #     ①② render large and clear. Coords stay DOM-rect based relative to clip box.
        #       ① = SAP status badge (.status-cell.sap, txn 1) → RED   (status colour)
        #       ② = SAP green value  (.month-value.sap,  txn 1) → GREEN (value colour)
        sap_points = [
            ("1", 'tr[data-status="sap"][data-txn-id="1"] .status-cell.sap'),
            ("2", 'tr[data-status="sap"][data-txn-id="1"] .month-value.sap'),
        ]
        sap_rects = pg.evaluate(RECT_JS, [s for _, s in sap_points])
        rs, rv = sap_rects[0], sap_rects[1]   # status rect, value rect
        # Union box of the two anchors + padding; clamp height to a single SAP row.
        pad = 26
        clip_x = min(rs["x"], rv["x"]) - pad
        clip_y = min(rs["y"], rv["y"]) - pad
        clip_r = max(rs["x"] + rs["w"], rv["x"] + rv["w"]) + pad
        clip_b = max(rs["y"] + rs["h"], rv["y"] + rv["h"]) + pad
        sap_box = {"x": clip_x, "y": clip_y, "w": clip_r - clip_x, "h": clip_b - clip_y}
        sap_path = os.path.join(BIN_DIR, "main_sap_columns.png")
        pg.screenshot(path=sap_path, clip={"x": sap_box["x"], "y": sap_box["y"],
                                           "width": sap_box["w"], "height": sap_box["h"]})
        out["sap"] = (sap_path, _markers_from_rects(
            sap_points, sap_rects, sap_box, colors=[(RED, RED_DARK), (GREEN, GREEN_DARK)]))

        # ── 3b) APPROVED · งบ (สีฟ้า) + Submit button — FIX B (2026-06-04, NEW) ──
        #     Shows the blue Approved input cell AND the Submit button that writes
        #     Approved data straight to DB (NO approval loop). The mockup has ONE shared
        #     .btn-submit (#submitBtn "Submit to Database") used by both Approved and
        #     Pending — there is no Approved-only submit button — so we reuse it and the
        #     caption makes clear that for the Approved part this submit writes directly
        #     to DB without the approval loop. Markers default GOLD.
        #       ① = APPROVED blue input (.month-value.approved-input, txn 1, Jan)
        #       ② = Submit button (.btn-submit)
        appr_points = [
            ("1", 'tr[data-status="approved"][data-txn-id="1"] .month-value.approved-input'),
            ("2", ".btn-submit"),
        ]
        appr_rects = pg.evaluate(RECT_JS, [s for _, s in appr_points])
        appr_main = pg.locator("main.wrap").first
        ambox = appr_main.bounding_box()
        appr_path = os.path.join(BIN_DIR, "main_approved_submit.png")
        appr_main.screenshot(path=appr_path)
        out["approved"] = (appr_path, _markers_from_rects(appr_points, appr_rects, ambox))

        # ── 4) PENDING input cells + Submit button ──
        #     Pending row of a NORMAL GL (txn id 1) has editable .pending-input fields.
        pend_points = [
            ("1", 'tr[data-status="pending"] .status-cell.pending'),
            ("2", 'tr[data-status="pending"] .month-value.pending-input'),
            ("3", ".btn-submit"),
        ]
        pend_rects = pg.evaluate(RECT_JS, [s for _, s in pend_points])
        # screenshot the <main> region so both pending row and submit button fit
        main_el = pg.locator("main.wrap").first
        mbox = main_el.bounding_box()
        pend_path = os.path.join(BIN_DIR, "main_pending_submit.png")
        main_el.screenshot(path=pend_path)
        out["pending"] = (pend_path, _markers_from_rects(pend_points, pend_rects, mbox))

        # ── 5) SPECIAL GL — "+ ใส่รายละเอียดงบทำการ" detail entry button (ref to doc 02) ──
        #     EDIT (2026-06-04): re-anchor BOTH detail markers to the SAME special-GL
        #     row = Lease & Rental (txn-id 5 · 10PB030000 / GL 6211200060 / group
        #     'Lease & Rental' — verified in the mockup txn data). It is a Special GL
        #     group, so its Pending <tr> renders the .btn-detail button THEN twelve
        #     grey .month-value.pending-readonly cells (isSpec branch). Pinning both
        #     markers to data-txn-id="5" makes the illustration coherent (one row).
        #       ① = .btn-detail ("+ ใส่รายละเอียดงบทำการ") → RED   (opens subform — doc 02)
        #       ② = leftmost .month-value.pending-readonly cell (the grey "–" box right
        #           of the button = ม.ค./Jan, document order) → GREEN (read-only sum back).
        #     querySelector on the row returns the FIRST pending-readonly cell = Jan
        #     deterministically (the 12 cells follow the button td in document order).
        det_points = [
            ("1", 'tr[data-status="pending"].special[data-txn-id="5"] .btn-detail'),
            ("2", 'tr[data-status="pending"].special[data-txn-id="5"] .month-value.pending-readonly'),
        ]
        det_rects = pg.evaluate(RECT_JS, [s for _, s in det_points])
        det_path = os.path.join(BIN_DIR, "main_special_detail.png")
        panel.screenshot(path=det_path)
        out["detail"] = (det_path, _markers_from_rects(
            det_points, det_rects, pbox, colors=[(RED, RED_DARK), (GREEN, GREEN_DARK)]))

        b.close()
    return out


# ---------------- Pillow annotation (verbatim from reference) ---------------- #
def _num_font(s):
    try: return ImageFont.truetype(NUM_FONT_PATH, s)
    except Exception: return ImageFont.load_default()

def _leader(draw, cx, cy, tx, ty, radius, fill=GOLD, dark=GOLD_DARK):
    import math
    dx, dy = tx-cx, ty-cy; dist = math.hypot(dx, dy)
    if dist < 1: return
    ux, uy = dx/dist, dy/dist; sx, sy = cx+ux*(radius+1), cy+uy*(radius+1)
    draw.line([(sx+1, sy+1), (tx+1, ty+1)], fill=dark, width=2)
    draw.line([(sx, sy), (tx, ty)], fill=fill, width=2)
    draw.ellipse([tx-3, ty-3, tx+3, ty+3], fill=fill, outline=dark)

def _circle(draw, label, cx, cy, tx, ty, radius=18, fill=GOLD, dark=GOLD_DARK):
    _leader(draw, cx, cy, tx, ty, radius, fill=fill, dark=dark)
    draw.ellipse([cx-radius+2, cy-radius+2, cx+radius+2, cy+radius+2], fill=(0, 0, 0, 60))
    draw.ellipse([cx-radius, cy-radius, cx+radius, cy+radius], fill=fill, outline=dark, width=2)
    f = _num_font(radius+4); bb = draw.textbbox((0, 0), label, font=f)
    tw, th = bb[2]-bb[0], bb[3]-bb[1]
    draw.text((cx-tw/2-bb[0], cy-th/2-bb[1]), label, fill=WHITE, font=f)

def annotate(src_path, out_name, markers):
    im = Image.open(src_path).convert("RGBA")
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0)); dr = ImageDraw.Draw(ov)
    for m in markers:
        _circle(dr, m["label"], m["cx"], m["cy"], m["tx"], m["ty"],
                fill=m.get("fill", GOLD), dark=m.get("dark", GOLD_DARK))
    out = Image.alpha_composite(im, ov).convert("RGB")
    op = os.path.join(ASSETS_DIR, out_name); out.save(op, "PNG")
    return op, out.size


# ---------------- OOXML helpers (verbatim from reference) ---------------- #
EMU_PER_IN = 914400; TARGET_WIDTH_IN = 6.3
def esc(t): return html.escape(str(t), quote=True)
def run_props(sz, bold=False, color=None, italic=False):
    p = ['<w:rPr>', f'<w:rFonts w:ascii="{THAI_FONT}" w:hAnsi="{THAI_FONT}" w:cs="{THAI_FONT}"/>']
    if bold: p.append('<w:b/><w:bCs/>')
    if italic: p.append('<w:i/><w:iCs/>')
    if color: p.append(f'<w:color w:val="{color}"/>')
    p.append(f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/></w:rPr>'); return "".join(p)
def run(t, sz=22, bold=False, color=None, italic=False):
    return f'<w:r>{run_props(sz, bold, color, italic)}<w:t xml:space="preserve">{esc(t)}</w:t></w:r>'
def para(rx, align=None, space_before=0, space_after=120, shading=None, keep_next=False):
    pp = ['<w:pPr>', f'<w:rFonts w:ascii="{THAI_FONT}" w:hAnsi="{THAI_FONT}" w:cs="{THAI_FONT}"/>',
          f'<w:spacing w:before="{space_before}" w:after="{space_after}"/>']
    if align: pp.append(f'<w:jc w:val="{align}"/>')
    if shading: pp.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{shading}"/>')
    if keep_next: pp.append('<w:keepNext/>')
    pp.append('</w:pPr>'); return f'<w:p>{"".join(pp)}{rx}</w:p>'
def heading(t, sz=30, color="2F6B3F", space_before=240, space_after=120):
    return para(run(t, sz=sz, bold=True, color=color), space_before=space_before, space_after=space_after, keep_next=True)
def body_para(t, sz=22, space_after=120): return para(run(t, sz=sz), space_after=space_after)
def bullet(t, sz=22): return para(run("•  "+t, sz=sz), space_after=60)
def image_para(rid, px_w, px_h, doc_pr_id, name, width_in=None):
    cx = int((width_in or TARGET_WIDTH_IN)*EMU_PER_IN); cy = int(cx*(px_h/px_w))
    d = f'''<w:r><w:rPr><w:rFonts w:ascii="{THAI_FONT}" w:hAnsi="{THAI_FONT}" w:cs="{THAI_FONT}"/></w:rPr><w:drawing>
<wp:inline distT="0" distB="0" distL="0" distR="0" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">
<wp:extent cx="{cx}" cy="{cy}"/><wp:effectExtent l="0" t="0" r="0" b="0"/><wp:docPr id="{doc_pr_id}" name="{esc(name)}"/>
<wp:cNvGraphicFramePr><a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/></wp:cNvGraphicFramePr>
<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:nvPicPr><pic:cNvPr id="{doc_pr_id}" name="{esc(name)}"/><pic:cNvPicPr/></pic:nvPicPr>
<pic:blipFill><a:blip r:embed="{rid}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>
</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>'''
    pp = (f'<w:pPr><w:rFonts w:ascii="{THAI_FONT}" w:hAnsi="{THAI_FONT}" w:cs="{THAI_FONT}"/>'
          f'<w:spacing w:before="80" w:after="80"/><w:jc w:val="center"/><w:keepNext/></w:pPr>')
    return f'<w:p>{pp}{d}</w:p>'
def tcell(cx, width_dxa=None, fill=None):
    t = ['<w:tcPr>']
    t.append(f'<w:tcW w:w="{width_dxa}" w:type="dxa"/>' if width_dxa else '<w:tcW w:w="0" w:type="auto"/>')
    if fill: t.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>')
    t.append('<w:tcMar><w:top w:w="40" w:type="dxa"/><w:bottom w:w="40" w:type="dxa"/><w:left w:w="80" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tcMar>')
    t.append('<w:vAlign w:val="center"/></w:tcPr>'); return f'<w:tc>{"".join(t)}{cx}</w:tc>'
def cell_para(t, bold=False, color=None, sz=18, align=None):
    return para(run(t, sz=sz, bold=bold, color=color), align=align, space_after=20, space_before=20)
def table(rows, widths, header_fill="E8F0E8"):
    t = ['<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/>',
         '<w:tblBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="9AB59A"/><w:left w:val="single" w:sz="4" w:space="0" w:color="9AB59A"/>'
         '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="9AB59A"/><w:right w:val="single" w:sz="4" w:space="0" w:color="9AB59A"/>'
         '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="C7D6C7"/><w:insideV w:val="single" w:sz="4" w:space="0" w:color="C7D6C7"/></w:tblBorders>',
         '<w:tblLayout w:type="fixed"/></w:tblPr><w:tblGrid>']
    for w in widths: t.append(f'<w:gridCol w:w="{w}"/>')
    t.append('</w:tblGrid>')
    for ri, row in enumerate(rows):
        hdr = ri == 0; tr = ['<w:tr>']
        if hdr: tr.append('<w:trPr><w:tblHeader/></w:trPr>')
        for ci, c in enumerate(row):
            tr.append(tcell(cell_para(c, bold=hdr, color=("1E3A24" if hdr else None), sz=(18 if hdr else 17)),
                            width_dxa=widths[ci], fill=(header_fill if hdr else None)))
        tr.append('</w:tr>'); t.append("".join(tr))
    t.append('</w:tbl>'); t.append(para(run("", sz=8), space_after=80)); return "".join(t)

DESC = [620, 1700, 2600, 4440]
SRC = [3200, 6160]
SIGN = [1900, 3000, 2460, 2000]
META = [2700, 6660]
CTRL = [2400, 6560]

def _sign_table(rows, widths):
    t = ['<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/>',
         '<w:tblBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="9AB59A"/><w:left w:val="single" w:sz="4" w:space="0" w:color="9AB59A"/>'
         '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="9AB59A"/><w:right w:val="single" w:sz="4" w:space="0" w:color="9AB59A"/>'
         '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="C7D6C7"/><w:insideV w:val="single" w:sz="4" w:space="0" w:color="C7D6C7"/></w:tblBorders><w:tblLayout w:type="fixed"/></w:tblPr><w:tblGrid>']
    for w in widths: t.append(f'<w:gridCol w:w="{w}"/>')
    t.append('</w:tblGrid>')
    for ri, row in enumerate(rows):
        hdr = ri == 0; tr = ['<w:tr><w:trPr>']
        tr.append('<w:tblHeader/>' if hdr else '<w:trHeight w:val="900" w:hRule="atLeast"/>')
        tr.append('</w:trPr>')
        for ci, c in enumerate(row):
            tr.append(tcell(cell_para(c, bold=hdr, color=("1E3A24" if hdr else None), sz=18),
                            width_dxa=widths[ci], fill=("E8F0E8" if hdr else None)))
        tr.append('</w:tr>'); t.append("".join(tr))
    t.append('</w:tbl>'); t.append(para(run("", sz=8), space_after=80)); return "".join(t)


# ---------------- Body ---------------- #
def build_body(meta, rids):
    P = []
    P.append(para(run("Chememan — ระบบบริหารงบประมาณ (Budget Management Web)", sz=18, color="6B7280"), space_after=40))
    P.append(para(run("เอกสารข้อกำหนดเพื่อขออนุมัติ (User Sign-off Specification)", sz=40, bold=True, color="2F6B3F"), space_after=40))
    P.append(para(run("ส่วน A — หน้าหลักของระบบ · Module 01: หน้าจัดการข้อมูลงบประมาณ (Main Budget Web App)",
                      sz=24, bold=True, color="1E3A24"), space_after=160))
    P.append(table([["รายการ", "รายละเอียด"], ["เวอร์ชัน", "v0.3 (ฉบับร่าง · Draft)"], ["วันที่", "5 มิถุนายน 2569 (2026-06-05)"],
                    ["ผู้จัดทำ", "ทีม Data Analytics"], ["สถานะ", "รออนุมัติจากผู้ใช้"]], META))

    # ── 0. Login & role-based visibility (Points 1 + 8) ──
    P.append(heading("0) การเข้าสู่ระบบ & สิทธิ์การเห็นข้อมูล (Login & Role)"))
    P.append(body_para(
        "ทั้งผู้ใช้ทั่วไป (User) และผู้ดูแลระบบ (Admin) เข้าสู่หน้าหลักนี้เหมือนกัน — ด้านบนของหน้ามี "
        "\"แถบผู้ใช้ (Login bar)\" บอกว่ากำลัง login เป็นใคร และเห็นข้อมูลในขอบเขตใด: รูปย่อ (avatar) "
        "+ ชื่อผู้ใช้ + ป้ายบทบาท ADMIN/USER + อีเมล/ขอบเขต + ป้ายชื่อฝ่าย (Department) ของ Cost Center ที่ตนดูแล"))
    P.append(bullet("User (ผู้ใช้ทั่วไป): เห็นเฉพาะ Cost Center ที่ผูกกับ orgcode ของตน (ตาม RLS chain — ดูเอกสาร 10)"))
    P.append(bullet("Admin: เห็นทุก Cost Center ทั้งบริษัท"))
    P.append(para(run("ภาพประกอบ: Admin — เห็นทุก Cost Center", sz=21, bold=True, color="1E3A24"),
                  space_before=80, space_after=40))
    P.append(image_para(rids["login_admin"], *meta["login_admin"][1], 106, "main_login_admin", width_in=5.6))
    P.append(para(run("ภาพประกอบ: User (ตัวอย่าง) — เห็นเฉพาะ Cost Center ของตน", sz=21, bold=True, color="1E3A24"),
                  space_before=40, space_after=40))
    P.append(image_para(rids["login_user"], *meta["login_user"][1], 107, "main_login_user", width_in=5.6))
    P.append(para(run("RLS chain — สายการ trace สิทธิ์ (รายละเอียดเต็มในเอกสาร 10):",
                      sz=21, bold=True, color="1E3A24"), space_before=60, space_after=40))
    P.append(table([
        ["ขั้น", "ตาราง / แหล่ง", "เชื่อมด้วย"],
        ["1", "login email → dbo.mas_employee_data (Fabric SQL DB)", "empcode ↔ orgcode"],
        ["2", "cfg_master.orgcode_costcenter_map (Fabric SQL DB)", "orgcode ↔ cost_center"],
        ["3", "ผลลัพธ์: cost_center ของผู้ใช้", "→ กำหนดสิทธิ์ เห็น / กรอก ข้อมูล"],
    ], [800, 5500, 2860]))

    # ── 0b. Point 8 — login "cc name" == department (ฝ่าย), NOT Description ──
    P.append(para(run("ชื่อที่แสดงคู่กับอีเมลคืออะไร? (ข้อ 8 — \"cc name\" = ชื่อฝ่าย/Department หรือไม่)",
                      sz=22, bold=True, color="1E3A24"), space_before=120, space_after=40))
    P.append(body_para(
        "ตรวจสอบจากไฟล์ master docs/02cost center & department (master)_disable.xlsx "
        "(sheet 'Cost center (Update 18 Mar 26)' · คอลัมน์: Cost Ctr | Description | C Level | สายงาน[Division] | ฝ่าย[Department]) "
        "ได้ข้อสรุปว่า: ชื่อที่แถบ login แสดง = คอลัมน์ ฝ่าย (Department) — ไม่ใช่ Description (ชื่อ CC จริง):", sz=21))
    P.append(table([
        ["Cost Ctr", "ชื่อที่ระบบแสดง (= ฝ่าย/Department)", "Description (ชื่อ CC จริง)", "สายงาน (Division)"],
        ["10MN014200", "Plant Maint. Planning & Store (PBB)", "Spare Parts & Equipment Store (PBB)", "Plant Maintenance (PBB)"],
        ["10PQ013100", "Warehouse (PBB)", "Quicklime Warehouse (PBB)", "PBB Factory"],
        ["10PQ011000", "Production (PBB)", "Quicklime Production Department (PBB)", "PBB Factory"],
    ], [1500, 3100, 3100, 1860]))
    P.append(bullet("สถิติจากไฟล์จริง: Description ตรงกับ ฝ่าย เพียง 37% ของ 210 แถว → Description โดยทั่วไป "
                    "ไม่ใช่ชื่อฝ่าย ระบบจึงเลือกใช้คอลัมน์ ฝ่าย เป็นป้ายชื่อที่อ่านง่ายแทน", sz=20))
    P.append(bullet("เหตุผล: 1 คนผูกได้หลาย Cost Center ที่รวมขึ้นเป็น 1 ฝ่าย (เช่น anuchitm: 2 CC → 1 ฝ่าย) "
                    "→ แสดงชื่อฝ่ายอ่านง่ายกว่า · รหัส CC แสดงเป็นข้อมูลละเอียดรอง", sz=20))
    P.append(para(run(
        "ข้อสรุป (ตัดสินแล้ว): แถบ login แสดง อีเมล + ชื่อฝ่าย (Department) เป็นขอบเขตที่อ่านง่าย · "
        "\"cc name ที่แสดง = ชื่อฝ่าย (Department) ไม่ใช่ Description ของ cost center\"",
        sz=21, bold=True, color="8C6423"), space_before=60, space_after=120))

    # ── 1. Overview ──
    P.append(heading("1) ภาพรวม (Overview)"))
    P.append(body_para(
        "หน้านี้คือหน้าหลัก (Main App Web) ของระบบบริหารงบประมาณ ทั้งผู้ใช้ทั่วไป (User) และผู้ดูแลระบบ (Admin) "
        "เข้ามาที่หน้านี้เพื่อดู (View) และกรอกข้อมูล (Fill data) งบประมาณรายเดือน ต่อ Cost Center / GL Code / ปีงบประมาณ"))
    P.append(body_para(
        "ตารางแสดงข้อมูล 3 ชั้นต่อรายการ (Transaction): SAP · ใช้จริง (Actuals), Approved · งบที่อนุมัติแล้ว, "
        "และ Pending · งบรออนุมัติ (กรอกมือ) — แต่ละชั้นมีแถบสีและสถานะกำกับชัดเจน", sz=21))
    P.append(para(run("เปลี่ยนแปลงจาก mockup (สรุปสั้น — รายละเอียด GL กลุ่มพิเศษอยู่ในเอกสาร 02):",
                      sz=21, bold=True, color="8C6423"), space_before=60, space_after=40))
    P.append(bullet("เพิ่มแถบ Login bar บอกผู้ใช้/บทบาท/ขอบเขต + ตัวสลับผู้ใช้ (เดโม่) · กรองตาราง/สรุป/export/submit ตามบทบาท", sz=20))
    P.append(bullet("ตัวกรองปี: เอาตัวเลือก \"ทุกปี (all)\" ออก — เหลือเฉพาะ FY2024 / FY2025 / FY2026 (ค่าเริ่มต้น 2025)", sz=20))
    P.append(bullet("Cost Center ใช้ข้อมูลโรงงาน PBB จริง · GL ใช้ GL กลุ่มพิเศษจริง (รวม Travelling Expense 8 GL) — "
                    "ดูฟอร์มย่อย/per-diem engine ในเอกสาร 02", sz=20))
    P.append(image_para(rids["overview"], *meta["overview"][1], 100, "main_overview", width_in=6.3))
    P.append(table([
        ["#", "จุด", "ความหมาย"],
        ["①", "ยอด Actuals จาก SAP (สีเขียว · read-only)", "ดึงจาก Lakehouse gold_sap_gl_trans · คอลัมน์ company_curr_amount (อธิบายข้อ 3)"],
        ["②", "APPROVED · งบ (ช่องกรอกสีฟ้า)", "Admin import .csv หรือกรอกมือที่ช่องนี้ → กด submit เข้า DB เลย (ไม่ผ่าน approval loop)"],
        ["③", "ยอด Pending (รวมจาก subform) — ผู้ใช้กรอกมือ", "ผู้ใช้กรอกที่ subform (ปุ่ม \"ใส่รายละเอียดงบทำการ\") → ระบบรวมยอดมาแสดงผลที่ part นี้อัตโนมัติ (read-only) · ใช้กับ GL กลุ่มพิเศษ"],
        ["④", "ช่อง Pending · รออนุมัติ (แถว GL ปกติ)", "ผู้ใช้กรอกยอด Pending มือโดยตรง (GL ปกติ) — ต่างจากข้อ 3 ที่เป็น read-only มาจาก subform ของ special GL"],
    ], [620, 3400, 5340]))

    # ── 2. RLS ──
    P.append(heading("2) การมองเห็นข้อมูล (RLS — Row Level Security ตาม Login)"))
    P.append(body_para(
        "ผู้ใช้แต่ละคนเห็นเฉพาะข้อมูลของตัวเอง โดยกำหนดจากสายการ login (login chain) ต่อไปนี้ — "
        "ตัวกำหนดสุดท้ายว่าใครเห็นข้อมูลอะไรได้บ้างคือ cost_center"))
    P.append(table([
        ["ขั้น", "ตาราง / แหล่ง", "เชื่อมด้วย"],
        ["1", "dbo.mas_employee_data (Fabric SQL DB)", "empcode ↔ orgcode"],
        ["2", "cfg_master.orgcode_costcenter_map (Fabric SQL DB)", "orgcode ↔ cost_center"],
        ["3", "ผลลัพธ์: cost_center ของผู้ใช้", "→ กำหนดสิทธิ์เห็น/กรอกข้อมูล"],
    ], [800, 5500, 2860]))
    P.append(para(run("สรุปกฎการเห็นข้อมูล:", sz=22, bold=True, color="1E3A24"), space_before=60, space_after=40))
    P.append(bullet("cost_center เป็นตัวกำหนดว่าใครเห็นข้อมูลอะไรได้บ้าง — trace จาก login → empcode → orgcode → cost_center"))
    P.append(bullet("User เห็นเฉพาะข้อมูลของตัวเอง (ตาม cost_center ที่ trace ได้)"))
    P.append(bullet("Admin มี 3 คน — เห็นและแก้ไขได้ทุกอย่าง (ทุก cost_center)"))
    P.append(bullet("ใครเข้าถึง (เห็น) อะไร → กรอก/แก้ได้แค่นั้น ทั้งหน้าหลักและการ \"ใส่รายละเอียดงบทำการ\" (subform ย่อย — ดูเอกสาร 02) · ยกเว้น Admin เห็นและแก้ทุกอย่าง"))
    P.append(para(run("จุดเข้าฟอร์มย่อย \"+ ใส่รายละเอียดงบทำการ\" (Special GL Group) — รายละเอียดเต็มอยู่ในเอกสาร 02:",
                      sz=21, bold=True, color="1E3A24"), space_before=80, space_after=40))
    P.append(image_para(rids["detail"], *meta["detail"][1], 104, "main_special_detail", width_in=6.3))
    P.append(table([
        ["#", "จุด", "ความหมาย"],
        ["①", "ปุ่ม \"+ ใส่รายละเอียดงบทำการ\" (Special GL)", "เปิดฟอร์มย่อย (subform) กรอกรายละเอียด — ดูเอกสาร 02"],
        ["②", "ช่อง Pending (read-only)", "ยอดรวมจาก subform แสดงกลับที่ช่องนี้ (กรอกตรงไม่ได้)"],
    ], [620, 3700, 5040]))

    # ── 3. Data sources in table ──
    P.append(heading("3) แหล่งข้อมูลในตาราง (3 ส่วน)"))
    P.append(body_para(
        "ข้อมูลในตารางมาจาก 3 ส่วน — แต่ละส่วนมีแถบสีกำกับตรงกับภาพประกอบ: "
        "SAP (เขียว) · Approved (ฟ้า) · Pending (ดำ)"))
    P.append(table([
        ["ส่วน (สี)", "แหล่งข้อมูล / ใครกรอก", "การทำงาน"],
        ["1. SAP · ใช้จริง (Actuals) — สีเขียว",
         "ดึงจาก Lakehouse gold_sap_gl_trans · คอลัมน์ company_curr_amount",
         "อ่านอย่างเดียว (read-only) · ดึงอัตโนมัติ"],
        ["2. Approved · งบ — สีฟ้า",
         "Admin กรอก — import .csv จากปุ่มด้านบนเป็นหลัก หรือแก้มือก็ได้",
         "หลังกรอก/แก้ กด submit → เข้า DB เลย ไม่ต้องผ่าน approval loop"],
        ["3. Pending · รออนุมัติ — สีดำ",
         "User (L3/L4) กรอกมือ (Admin แก้ส่วนนี้ด้วยมือได้)",
         "กด submit → เข้า approval loop: Submitter (L3/L4) → managerempcode → นิภาพร → วราพร "
         "(มี special case เช่น นิภาพร/วราพร กรอกเอง, C-Level — ดูรายละเอียดในเอกสาร approval workflow)"],
    ], [2600, 3300, 3000]))
    P.append(para(run("ภาพประกอบ: คอลัมน์ส่วน SAP (Actuals)", sz=22, bold=True, color="1E3A24"), space_before=80, space_after=40))
    P.append(image_para(rids["sap"], *meta["sap"][1], 101, "main_sap_columns", width_in=6.3))
    P.append(table([
        ["#", "จุด", "ความหมาย"],
        ["①", "สถานะแถว SAP · ใช้จริง (วงสีแดง)", "บอกว่าแถวนี้เป็นยอด Actuals จาก SAP"],
        ["②", "ยอดรายเดือน (SAP · สีเขียว)", "ค่าจาก gold_sap_gl_trans.company_curr_amount — read-only"],
    ], [620, 3400, 5340]))
    # ── 3 · Approved illustration (FIX B — between SAP and Pending) ──
    P.append(para(run("ภาพประกอบ: Approved · งบ (สีฟ้า) + ปุ่มส่ง (ไม่ผ่าน approval loop)",
                      sz=22, bold=True, color="1E3A24"), space_before=80, space_after=40))
    P.append(image_para(rids["approved"], *meta["approved"][1], 105, "main_approved_submit", width_in=6.3))
    P.append(table([
        ["#", "จุด", "ความหมาย"],
        ["①", "ช่องกรอก Approved · งบ (สีฟ้า)", "Admin import .csv หรือกรอกมือ"],
        ["②", "ปุ่มส่ง (Submit)", "ส่งเข้า DB เลย — ไม่ผ่าน approval loop"],
    ], [620, 3400, 5340]))
    P.append(para(run("ภาพประกอบ: ช่องกรอก Pending · รออนุมัติ + ปุ่มส่ง/อนุมัติ", sz=22, bold=True, color="1E3A24"),
                  space_before=80, space_after=40))
    P.append(image_para(rids["pending"], *meta["pending"][1], 102, "main_pending_submit", width_in=6.3))
    P.append(table([
        ["#", "จุด", "ความหมาย"],
        ["①", "สถานะแถว Pending · รออนุมัติ", "งบที่ผู้ใช้กรอกมือ รอเข้าอนุมัติ"],
        ["②", "ช่องกรอกยอดรายเดือน (Pending)", "ผู้ใช้กรอกมือ — กรอกได้เฉพาะ cost_center ที่ตัวเองเห็น"],
        ["③", "ปุ่มส่ง/อนุมัติ (Submit to Database)", "ยืนยันส่งข้อมูล Pending เข้ากระบวนการอนุมัติ"],
    ], [620, 3700, 5040]))

    # ── Data sources summary (3 sources — moved into section 3) ──
    P.append(heading("สรุปแหล่งข้อมูล (Data sources — 3 ส่วน)"))
    P.append(body_para("ข้อมูลในตารางมาจาก 3 ส่วน (SAP เขียว · Approved ฟ้า · Pending ดำ) + ตาราง RLS ที่ใช้กำหนดสิทธิ์การเห็น", sz=21))
    P.append(table([
        ["แหล่ง / ตาราง", "บทบาท"],
        ["1. gold_sap_gl_trans (Lakehouse) · company_curr_amount",
         "SAP · ใช้จริง (สีเขียว) — Actuals อ่านอย่างเดียว"],
        ["2. Approved · งบ (สีฟ้า) — Admin import .csv หรือแก้มือ",
         "งบที่อนุมัติแล้ว — submit เข้า DB เลย ไม่ผ่าน approval loop"],
        ["3. Pending · รออนุมัติ (สีดำ) — User กรอกมือ / Admin แก้ได้",
         "งบรออนุมัติ — submit เข้า approval loop (มี routing การส่งต่อ)"],
        ["dbo.mas_employee_data + cfg_master.orgcode_costcenter_map (Fabric SQL DB)",
         "RLS chain: empcode ↔ orgcode ↔ cost_center — กำหนดสิทธิ์เห็น/กรอกข้อมูล"],
    ], SRC))

    # ── 3c. See / Fill / Submit matrix per data part × role (Point 2 — centerpiece) ──
    P.append(heading("3.1) ใครเห็น / ใครกรอก / การ Submit (แยกตามส่วนข้อมูล × บทบาท)"))
    P.append(body_para(
        "ตารางสรุปสิทธิ์ต่อข้อมูล 3 ส่วน — User เห็น/กรอกได้เฉพาะ Cost Center ของตน (RLS) · "
        "Admin เห็นทุก CC และแก้ Pending ได้ทุก CC แต่ \"ปุ่มส่ง\" จำกัดเฉพาะ CC ของตัวเอง (ดูข้อ 6):", sz=21))
    P.append(table([
        ["ส่วนข้อมูล (สี)", "ใครเห็น", "ใครกรอก + วิธีกรอก", "การ Submit"],
        ["SAP · ใช้จริง (เขียว)",
         "ทุกคนตาม RLS scope (User = CC ตน · Admin = ทุก CC)",
         "ไม่มีใครกรอก — auto จาก Lakehouse gold_sap_gl_trans.company_curr_amount (read-only)",
         "ไม่มี"],
        ["Approved · งบ (ฟ้า)",
         "ตาม scope",
         "Admin เท่านั้น — import .csv (หลัก) หรือแก้มือช่องสีฟ้า",
         "กดส่ง → เข้า DB ตรง · ไม่ผ่าน approval loop"],
        ["Pending · รออนุมัติ (ดำ)",
         "ตาม scope",
         "User (L3/L4) กรอก CC ของตน (รายเดือน ม.ค.–ธ.ค. หรือผ่าน subform สำหรับ special GL) · Admin แก้ของ CC ใดก็ได้",
         "เข้า approval loop · Admin ส่งได้เฉพาะ CC ของตัวเอง"],
    ], [2100, 1900, 3300, 1600]))

    # Point 3 — Admin editing a normal user's Pending
    P.append(para(run("(ข้อ 3) สิทธิ์ Admin ในการแก้ Pending ของ User",
                      sz=22, bold=True, color="1E3A24"), space_before=80, space_after=40))
    P.append(bullet("Admin แก้ไขงบ Pending ของ Cost Center ใดก็ได้ (บันทึกเป็นฉบับร่างของเจ้าของ CC นั้น)"))
    P.append(bullet("ข้อจำกัด (เอกสาร 10 ข้อ 3): Admin กดส่ง (submit) ได้เฉพาะ CC ที่ผูกกับ orgcode ของตัวเอง — ส่งแทนเจ้าของไม่ได้"))
    P.append(bullet("กันยอดซ้ำ (ข้อ 4): คีย์ = (cost_center, fiscal_year, gl_account, month) ไม่มี empcode → 1 CC = ชุดงบเดียว · last-write-wins"))

    # Point 4 — How a normal user fills Pending
    P.append(para(run("(ข้อ 4) ขั้นตอน User กรอกงบ Pending",
                      sz=22, bold=True, color="1E3A24"), space_before=120, space_after=40))
    P.append(bullet("(1) เลือก Cost Center (ของตนเท่านั้น) → (2) เลือก GL Code → (3) กรอกยอด ม.ค.–ธ.ค."))
    P.append(bullet("ยอดรวมทั้งปี auto-sum · division / department / GL name / GL group auto-fill อัตโนมัติ"))
    P.append(bullet("GL กลุ่มพิเศษ → กดปุ่ม \"+ ใส่รายละเอียดงบทำการ\" เปิด subform (เอกสาร 02) แล้วยอดรวมเด้งกลับช่อง Pending (read-only)"))
    P.append(bullet("ปุ่ม Save = บันทึกฉบับร่าง (DRAFT) · ปุ่ม Submit = ส่งเข้า approval loop"))

    # ── 4. Export ──
    P.append(heading("4) ปุ่ม Export Approved Budget (เฉพาะ Admin)"))
    P.append(body_para(
        "ปุ่มนี้สำหรับ Admin เท่านั้น — ใช้ส่งออกข้อมูลงบที่อนุมัติแล้วเป็นไฟล์ ใครเห็นอะไร (ตาม RLS) "
        "จะ export ออกมาตามหน้านั้น แต่ปุ่ม Export จะแสดงเฉพาะ Admin"))
    P.append(table([
        ["#", "หัวข้อ", "รายละเอียด"],
        ["1", "สิทธิ์", "Admin เท่านั้น (3 คน)"],
        ["2", "ขอบเขตข้อมูล", "Export ตามที่ผู้ใช้นั้นเห็น (ตาม RLS / cost_center)"],
        ["3", "Filter", "กรองตามปีที่เลือก (2024 / 2025 / 2026) — ไม่มีตัวเลือก \"ทุกปี\" แล้ว"],
        ["4", "ชื่อไฟล์", "ปีกำหนดชื่อไฟล์ เช่น approved_budget_2025.csv (เปลี่ยนตามปีที่เลือก)"],
        ["5", "รูปแบบไฟล์", ".csv (UTF-8 มี BOM · คั่นด้วย ,)"],
        ["6", "ค่ายอดที่ export", "ยอดของ \"Approved · งบ\" (สีฟ้า) รายเดือน jan–dec"],
    ], [620, 2600, 6140]))
    P.append(para(run(
        "คอลัมน์ของไฟล์ .csv ที่ระบบ export ออกมาจริง (จากฟังก์ชัน exportApprovedCSV ใน mockup) "
        "เรียงตามลำดับ 21 คอลัมน์ดังนี้:", sz=21, bold=True, color="1E3A24"),
        space_before=80, space_after=40))
    P.append(table([
        ["#", "ชื่อคอลัมน์", "ความหมาย"],
        ["1", "cost_center", "รหัส Cost Center"],
        ["2", "gl_code", "รหัส GL"],
        ["3", "gl_name", "ชื่อ GL (auto จาก master)"],
        ["4", "gl_group", "กลุ่ม GL (auto จาก master)"],
        ["5", "remark", "หมายเหตุ (แก้ไขได้)"],
        ["6", "c_level", "ระดับผู้บริหาร (auto จาก cost center)"],
        ["7", "division", "สายงาน (auto จาก cost center)"],
        ["8", "department", "หน่วยงาน (auto จาก cost center)"],
        ["9–20", "jan, feb, mar, apr, may, jun, jul, aug, sep, oct, nov, dec",
         "ยอดงบ Approved รายเดือน 12 คอลัมน์ (ยอดของแถวสีฟ้า)"],
        ["21", "year", "ปีงบประมาณของรายการ"],
    ], [620, 3400, 5340]))
    P.append(para(run("หมายเหตุสำคัญ — เรื่องชื่อไฟล์ vs ชื่อคอลัมน์:", sz=21, bold=True, color="8C6423"),
                  space_before=80, space_after=40))
    P.append(bullet("ชื่อไฟล์ที่ export = approved_budget_<ปี>.csv (เช่น approved_budget_2025.csv) — <ปี> เปลี่ยนตามปีที่เลือก", sz=20))
    P.append(bullet("ยอดงบที่อนุมัติแล้ว → เก็บอยู่ใน 12 คอลัมน์รายเดือน jan–dec", sz=20))

    # ── 5. Import ──
    P.append(heading("5) ปุ่ม Import Approved Budget (เฉพาะ Admin)"))
    P.append(body_para(
        "นำไฟล์ที่ได้จากข้อ 4 (Export) มาแก้ไขข้อมูล แล้วใส่กลับเข้าระบบผ่านปุ่ม Import นี้ "
        "ข้อมูลที่ใส่เข้ามาจะวิ่งไปเก็บหลังบ้าน และเพิ่ม control column ตอนเก็บ ด้วย streaming mode batch"))
    P.append(body_para("ภาพประกอบ: toolbar ปุ่ม Export / Import Approved Budget", sz=21))
    P.append(image_para(rids["toolbar"], *meta["toolbar"][1], 103, "main_toolbar", width_in=6.3))
    P.append(table([
        ["#", "จุด", "ความหมาย"],
        ["①", "ปุ่ม Export Approved Budget", "ส่งออกงบอนุมัติเป็น .csv (Admin) — ข้อ 4"],
        ["②", "ปุ่ม Import Approved Budget", "นำไฟล์ที่แก้แล้วกลับเข้าระบบ (Admin) — ข้อ 5"],
        ["③", "ตัวกรองปี (Year filter)", "กำหนดปีของข้อมูลที่ export / import"],
    ], [620, 3700, 5040]))

    # ── 6. Control columns ──
    P.append(heading("6) Control Columns (เพิ่มตอน Import เก็บหลังบ้าน)"))
    P.append(body_para("เมื่อ Import ระบบจะเพิ่มคอลัมน์ควบคุม (control column) เก็บไว้หลังบ้านอัตโนมัติ ด้วย streaming mode batch:"))
    P.append(table([
        ["Column", "ค่า"],
        ["_load_dt", "current_date() → 2026-05-04"],
        ["_load_dttm", "current_timestamp()"],
        ["_user", "ex. jakkaritw@chememan.com (ผู้ upload หรือ fill data)"],
    ], CTRL))
    P.append(bullet("ไม่เก็บ control column ที่เกี่ยวกับไฟล์ (_file_name / _file_path / _file_size / _file_mod) "
                    "เพราะ import เป็นแบบ direct-to-table (overwrite) — ไม่ได้เก็บไฟล์ไว้", sz=20))

    # ── 7. Confirmed design decisions ──
    P.append(heading("7) ข้อสรุปการออกแบบ"))

    P.append(para(run("(1) วิธีเก็บข้อมูลหลัง import .csv → เขียนลง table ตรงๆ (direct-to-table)",
                      sz=22, bold=True, color="1E3A24"), space_before=40, space_after=40))
    P.append(bullet("parse .csv แล้ว insert ลง table เลย — ไม่เก็บไฟล์ลง landing / Volume"))
    P.append(bullet("control columns ที่เก็บ = เฉพาะ _load_dt, _load_dttm, _user เท่านั้น"))
    P.append(bullet("control columns ที่เกี่ยวกับไฟล์ (_file_name / _file_path / _file_size / _file_mod) "
                    "ไม่เก็บ — เพราะ import เป็นแบบ direct-to-table (overwrite) ไม่ได้เก็บไฟล์ไว้"))

    P.append(para(run("(2) อัปโหลดซ้ำปีเดิม → Replace by Year",
                      sz=22, bold=True, color="1E3A24"), space_before=120, space_after=40))
    P.append(bullet("DELETE WHERE year = X (เช่น 2025) แล้ว INSERT ข้อมูลใหม่ทั้งก้อนของปีนั้น"))
    P.append(bullet("จับปีจาก ชื่อไฟล์ และ คอลัมน์ year — สองค่านี้ต้องตรงกัน "
                    "(validate ก่อน import; ถ้าไม่ตรง → reject)"))
    P.append(bullet("ขอบเขตการทับ = ทั้งปี (เฉพาะ part Approved งบ) · row ในไฟล์ระบุตัวด้วย cost_center + gl_code + ปี (year)"))

    # ── 8. Submit loop + admin special condition (Point 6) ──
    P.append(heading("8) การส่งข้อมูล (Submit)"))
    P.append(body_para("การ \"ส่ง\" มี 2 เส้นทางต่างกันชัดเจนตามส่วนข้อมูล:", sz=21))
    P.append(table([
        ["ส่วน", "เส้นทางหลังกดส่ง"],
        ["Pending · รออนุมัติ (User กรอก)",
         "เข้า approval chain: ผู้กรอก (L3/L4) → managerempcode → นิภาพร ทองกิ่ง → วราพร ติรสิทธิ์ "
         "(มี special case: นิภาพร/วราพร กรอกเอง, C-Level — ดูเอกสาร 10 + เอกสาร approval workflow)"],
        ["Approved · งบ (Admin)",
         "เข้า DB ตรง — ไม่ผ่าน approval loop"],
    ], [3000, 6200]))
    P.append(para(run("Special condition (สำคัญ) — ขอบเขตปุ่มส่งของ Admin:",
                      sz=22, bold=True, color="8C6423"), space_before=80, space_after=40))
    P.append(bullet("Admin เห็นทุก CC และแก้ Pending ได้ทุก CC — แต่ \"ปุ่มส่ง\" จำกัดเฉพาะ CC ของตัวเอง "
                    "(กันการกดส่งแทนทั้งบริษัทเข้า loop โดยไม่ตั้งใจ)"))
    P.append(bullet("หมายเหตุ: ตัว mockup เดโม่ปัจจุบันกดส่งตามที่เห็นทั้งหมด — เป็นการ simplify ของเดโม่ · "
                    "กฎที่ยึด = ส่งเฉพาะ CC ตัวเอง (ตามเอกสาร 10 ข้อ 3)"))

    # ── 9. Other suggestions (Point 7) ──
    P.append(heading("9) ข้อเสนอแนะเพิ่มเติม / ประเด็นควรตัดสิน"))
    P.append(bullet("Concurrency: หลายคนใน dept เดียวกันกรอก CC คนละตัว — last-write-wins ตามคีย์ "
                    "(cost_center, year, gl, month) · ควรมีตัวบ่งชี้/ล็อกเบาๆ กันเขียนทับโดยไม่รู้ตัว"))
    P.append(bullet("Deadline lock: ถึงวันปิดรับ form ปิดอัตโนมัติ (GET /api/deadline)"))
    P.append(bullet("Validation ก่อน submit แบบ lean — เตือน (warn) ไม่บล็อก"))
    P.append(bullet("Audit ผ่าน control column _user / _updated_at — ไม่ต้องมี audit table แยก"))
    P.append(bullet("Admin act-as: มีตัวระบุ \"CC ที่กำลังแก้แทน\" ให้ชัดว่ากำลังแก้ของใคร"))

    # ── 10. Performance when Admin sees all CC (Point 9) ──
    P.append(heading("10) ประสิทธิภาพเมื่อ Admin เห็นทุก CC (~1000+ รายการ)"))
    P.append(body_para(
        "ตอบตรงประเด็น: เว็บ \"ไม่ error\" — ทำงานได้ปกติ แต่ถ้า render ทุกแถวฝั่ง client พร้อมกันที่ "
        "~1000+ แถวจะเริ่มหน่วง (mockup ปัจจุบัน render ทั้งหมดฝั่ง client). คำแนะนำ (lean · คงประสิทธิภาพระดับมาตรฐาน):", sz=21))
    P.append(bullet("Server-side pagination + filter — กรองตาม Cost Center / Division / ปี ก่อนดึง · "
                    "Admin เปิดมาให้เลือก scope ก่อน ไม่ดึงทั้งหมดทันที"))
    P.append(bullet("Virtualized table — render เฉพาะแถวที่มองเห็นบนจอ"))
    P.append(bullet("SAP actuals มาจาก Lakehouse gold (datawarehouse endpoint · อ่านอย่างเดียว · aggregate มาแล้ว) · "
                    "Pending/Approved จาก Fabric SQL DB — ใส่ index (cost_center, fiscal_year, gl_account)"))
    P.append(bullet("สรุป: ทำงานได้ปกติถ้าใช้ pagination / virtualization + server filter — ไม่ใช่ปัญหา error "
                    "แต่เป็นเรื่อง UX/ความเร็วที่แก้ด้วยการแบ่งหน้า"))

    # ── Closing note ──
    P.append(heading("หมายเหตุท้ายเอกสาร"))
    P.append(para(run(
        "เอกสารฉบับร่าง (Draft · v0.3) — ข้อสรุปการออกแบบทั้งหมดดูได้ในข้อ 7 · "
        "ภาพประกอบ render จากแบบ (mockup) ตัวเลข/ชื่อเป็นข้อมูลตัวอย่าง · "
        "วงกลมสีทองคือจุดอ้างอิงในตารางคำอธิบายของแต่ละหัวข้อ",
        sz=20, italic=True, color="8C6423"), space_before=40, space_after=120))

    P.append(heading("ช่องลงนามอนุมัติ (Sign-off)"))
    P.append(_sign_table([["บทบาท", "ชื่อ-นามสกุล", "ลายเซ็น", "วันที่"], ["ผู้จัดทำ", "", "", ""],
                          ["ผู้ตรวจสอบ", "", "", ""], ["ผู้อนุมัติ", "", "", ""]], SIGN))
    return "".join(P)


def content_types_xml():
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Default Extension="png" ContentType="image/png"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
def root_rels_xml():
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
def document_rels_xml(image_rels):
    r = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    for rid, fn in image_rels:
        r.append(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{fn}"/>')
    r.append('</Relationships>'); return "".join(r)
def document_xml(body):
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><w:body>'
            f'{body}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="708" w:footer="708" w:gutter="0"/>'
            '</w:sectPr></w:body></w:document>')


def main():
    print("[1/4] Capturing main-page screenshots + DOM rects (Playwright) ...")
    shots = capture()
    print("[2/4] Annotating with gold markers (Pillow) ...")
    meta = {}
    # FIX B: "approved" added between "sap" and "pending" (matches section-3 order).
    # 2026-06-05: login_admin/login_user prepended (login-bar section near top). They
    # carry NO markers, so the PROOF loops below (sap/approved/pending/toolbar/detail)
    # are unaffected — they never reference the login keys.
    order = ["login_admin", "login_user", "overview", "sap", "approved", "pending", "toolbar", "detail"]
    for k in order:
        src, markers = shots[k]
        meta[k] = annotate(src, os.path.basename(src), markers)
        print(f"      {k}: {meta[k][0]}  {meta[k][1]}  markers={len(markers)}")

    # ---- PROOF (computed only — no PNG viewing) ---------------------------- #
    def _inside(m):
        return (m["ex"] <= m["tx"] <= m["ex"] + m["ew"]
                and m["ey"] <= m["ty"] <= m["ey"] + m["eh"])
    print("[PROOF] per-image marker counts:",
          {k: len(shots[k][1]) for k in ("sap", "approved", "pending")})
    sap_m = shots["sap"][1]
    print(f"[PROOF] SAP ①: leader=({sap_m[0]['tx']:.0f},{sap_m[0]['ty']:.0f}) "
          f"in status box[{sap_m[0]['ex']:.0f},{sap_m[0]['ey']:.0f},"
          f"{sap_m[0]['ew']:.0f},{sap_m[0]['eh']:.0f}] inside={_inside(sap_m[0])} "
          f"fill={sap_m[0]['fill']} (RED={sap_m[0]['fill']==RED})")
    print(f"[PROOF] SAP ②: leader=({sap_m[1]['tx']:.0f},{sap_m[1]['ty']:.0f}) "
          f"in value  box[{sap_m[1]['ex']:.0f},{sap_m[1]['ey']:.0f},"
          f"{sap_m[1]['ew']:.0f},{sap_m[1]['eh']:.0f}] inside={_inside(sap_m[1])} "
          f"fill={sap_m[1]['fill']} (GREEN={sap_m[1]['fill']==GREEN})")
    ap_m = shots["approved"][1]
    print(f"[PROOF] APPROVED ①: leader=({ap_m[0]['tx']:.0f},{ap_m[0]['ty']:.0f}) "
          f"in input box[{ap_m[0]['ex']:.0f},{ap_m[0]['ey']:.0f},"
          f"{ap_m[0]['ew']:.0f},{ap_m[0]['eh']:.0f}] inside={_inside(ap_m[0])} "
          f"fill={ap_m[0]['fill']} (GOLD={ap_m[0]['fill']==GOLD})")
    print(f"[PROOF] APPROVED ②: leader=({ap_m[1]['tx']:.0f},{ap_m[1]['ty']:.0f}) "
          f"in submit box[{ap_m[1]['ex']:.0f},{ap_m[1]['ey']:.0f},"
          f"{ap_m[1]['ew']:.0f},{ap_m[1]['eh']:.0f}] inside={_inside(ap_m[1])} "
          f"fill={ap_m[1]['fill']} (GOLD={ap_m[1]['fill']==GOLD})")
    # DETAIL image (EDIT 2026-06-04): both markers on the SAME Lease & Rental row
    # (data-txn-id=5). ① = .btn-detail → RED · ② = leftmost pending-readonly → GREEN.
    det_m = shots["detail"][1]
    det_txn = "5"  # the data-txn-id both detail selectors are pinned to
    print(f"[PROOF] DETAIL anchored to data-txn-id={det_txn} (both markers, Lease & Rental)")
    print(f"[PROOF] DETAIL ① (btn-detail): leader=({det_m[0]['tx']:.0f},{det_m[0]['ty']:.0f}) "
          f"in button box[{det_m[0]['ex']:.0f},{det_m[0]['ey']:.0f},"
          f"{det_m[0]['ew']:.0f},{det_m[0]['eh']:.0f}] inside={_inside(det_m[0])} "
          f"fill={det_m[0]['fill']} (RED={det_m[0]['fill']==RED})")
    print(f"[PROOF] DETAIL ② (pending-readonly): leader=({det_m[1]['tx']:.0f},{det_m[1]['ty']:.0f}) "
          f"in cell  box[{det_m[1]['ex']:.0f},{det_m[1]['ey']:.0f},"
          f"{det_m[1]['ew']:.0f},{det_m[1]['eh']:.0f}] inside={_inside(det_m[1])} "
          f"fill={det_m[1]['fill']} (GREEN={det_m[1]['fill']==GREEN})")
    for k in ("overview", "toolbar", "pending"):
        allgold = all(m["fill"] == GOLD for m in shots[k][1])
        print(f"[PROOF] {k}: markers default GOLD = {allgold}")
    # ----------------------------------------------------------------------- #

    media = {k: f"image{i+1}.png" for i, k in enumerate(order)}
    rids = {k: f"rId{i+10}" for i, k in enumerate(order)}
    image_rels = [(rids[k], media[k]) for k in order]
    print("[3/4] Building OOXML ...")
    doc = document_xml(build_body(meta, rids))
    print("[4/4] Writing .docx ...")
    if os.path.exists(DOCX_PATH): os.remove(DOCX_PATH)
    with zipfile.ZipFile(DOCX_PATH, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types_xml())
        z.writestr("_rels/.rels", root_rels_xml())
        z.writestr("word/document.xml", doc.encode("utf-8"))
        z.writestr("word/_rels/document.xml.rels", document_rels_xml(image_rels))
        for k in order:
            with open(meta[k][0], "rb") as f:
                z.writestr(f"word/media/{media[k]}", f.read())
    print(f"DONE: {DOCX_PATH}  ({os.path.getsize(DOCX_PATH)} bytes)")


if __name__ == "__main__":
    main()
