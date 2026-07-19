# -*- coding: utf-8 -*-
"""
Generator — Special GL Group "Subform" User Sign-off Specification (.docx).

Module 10 — budget submission form, the "+ ใส่รายละเอียดงบทำการ" detail Subform
that 6 special GL groups open instead of typing monthly amounts directly.

FIFTH doc in the series. Reuses the OOXML + Pillow helpers from
build_master_currency_spec.py VERBATIM. New here: capture step uses Playwright to
screenshot each modal state AND read element bounding boxes, so gold marker
coordinates are computed from the live DOM (no hand-tuned pixels).

HARD CONSTRAINTS:
  - NO package installation. stdlib + Pillow + Playwright (all installed).
  - .docx built by hand as WordprocessingML. Thai uses Leelawadee UI, szCs==sz.
  - Mockup source: design/mockups/0002claude design/0002budget-export.html
Re-runnable: overwrites screenshots (bin/), assets, and the .docx each run.
"""

import os, io, zipfile, html, pathlib
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

PROJECT_ROOT = r"c:\04.budget_management_web"
SIGNOFF_DIR = os.path.join(PROJECT_ROOT, "requirement_spec", "1_software_dev", "1.1_frontend", "signoff_spec")
ASSETS_DIR = os.path.join(SIGNOFF_DIR, "assets")
BIN_DIR = os.path.join(PROJECT_ROOT, "bin")
DOCX_PATH = os.path.join(SIGNOFF_DIR, "01_special_gl_subform_spec.docx")
MOCKUP = pathlib.Path(PROJECT_ROOT, "design", "mockups", "0002claude design", "0002.1budget-export.html")
os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(BIN_DIR, exist_ok=True)

GOLD = (201, 150, 61); GOLD_DARK = (140, 100, 35); WHITE = (255, 255, 255)
NUM_FONT_PATH = r"C:\Windows\Fonts\arialbd.ttf"
THAI_FONT = "Leelawadee UI"
SCALE = 2  # device_scale_factor

# --------------------------------------------------------------------------- #
# STATES — what to capture. points: (label, selector). placement auto from rect.
#
# Capture against the CURRENT wired mockup (0002.1budget-export.html):
#   - Personas via switchUser(): suchanya (L3 submitter, Solution Delivery, default),
#     jakkaritw (admin/super-test → canEditPending() true, sees ALL CCs). We capture the
#     EDITABLE subforms as jakkaritw (so inputs are enabled regardless of ฝ่าย status),
#     and the LOCKED states as suchanya after flipping DEPT_STATUS (ADR-0013).
#   - The page locks to ONE ฝ่าย via the custom #faiPicker → pickDept('<ฝ่าย>').
#   - GL code is FIXED per transaction (read-only dropdown). detailColumns() keys off the
#     txn's own glCode, so to show a Lease/Public-Relation variant that has no seeded txn we
#     temporarily override an existing special txn's glCode just before opening the modal.
#   - Special-GL txns: id 5 = Professional & Legal Fee (6210700030, CC 10IT012000),
#     id 6 = Training & Seminar (6210100150, CC 10IT012000), id 8 = Entertainment external
#     (6211900030, CC 10AC020000). Travelling Trip Manager = ids 10–13 (CC 10IT012000).
#   - Normal subform: openDetailModal(id) → #detailModal / #detailModalBody, footer
#     #detailAddBtn/#detailSaveBtn/#detailCloseBtn. Trip Manager: openTripModal(cc, year)
#     → #tripModal / #tripModalBody, footer #tripAddBtn/#tripSaveBtn/#tripCloseBtn.
# --------------------------------------------------------------------------- #
SC = ".modal .detail-table"
def cell(n): return f"{SC} tbody tr:first-child td.special-col-cell:nth-child({1+n})"  # n=1..k special cell
# Non-travel special groups — dropdown / grey ขึ้นกับ GL (ตามไฟล์ docs/13Template Special).
MIN = ".modal .detail-table tbody tr:first-child td.month-cell input"
def grey(n): return f"{SC} tbody tr:first-child td.special-col-cell:nth-child({1+n}) .cell-disabled"

# A detail STATE may carry: user (switchUser key) · dept (pickDept ฝ่าย) · txn (id to open) ·
# gl (override that txn's glCode before opening) · seed (JS to seed a first pendingDetails row) ·
# deptStatus ((dept,status) to flip before open → drives the ADR-0013 read-only lock) · trip (bool).
STATES = [
    # Entertainment — ประเภทการรับรอง = dropdown ขึ้นกับ GL (ภายนอก 900030 / ภายใน 900031)
    # txn 8 = Entertainment external (6211900030) in ฝ่าย Budgeting. admin (jakkaritw) → editable.
    {"key":"ent_ext", "user":"jakkaritw", "dept":"Budgeting and Management Accounting",
     "txn":8, "gl":"6211900030", "img":"sub_ent_ext.png", "seedEnt":True,
     "points":[("1", cell(1)), ("2", cell(2)), ("3", MIN)]},
    {"key":"ent_int", "user":"jakkaritw", "dept":"Budgeting and Management Accounting",
     "txn":8, "gl":"6211900031", "img":"sub_ent_int.png", "seedEnt":True,
     "points":[("1", cell(1))]},
    # Lease & Rental — dropdown + พื้นที่เทา ขึ้นกับ sub-category (060 รถ / 030 เครื่องจักร / อื่น เทา).
    # No Lease txn is seeded → temporarily repoint txn 8's glCode to each Lease variant.
    {"key":"lease_veh", "user":"jakkaritw", "dept":"Budgeting and Management Accounting",
     "txn":8, "gl":"6211200060", "img":"sub_lease_vehicle.png", "seedBlank":True,
     "points":[("1", cell(1)), ("2", cell(2)), ("3", cell(3)), ("4", cell(4))]},
    {"key":"lease_mac", "user":"jakkaritw", "dept":"Budgeting and Management Accounting",
     "txn":8, "gl":"6211200030", "img":"sub_lease_machinery.png", "seedBlank":True,
     "points":[("1", cell(1)), ("2", grey(2)), ("3", cell(3))]},
    {"key":"lease_bld", "user":"jakkaritw", "dept":"Budgeting and Management Accounting",
     "txn":8, "gl":"6211200020", "img":"sub_lease_building.png", "seedBlank":True,
     "points":[("1", grey(1)), ("2", grey(2)), ("3", cell(3))]},
    # Professional / Public Relation — text ล้วน · Training — Method dropdown.
    # txn 5 = Professional (6210700030, Solution Delivery); txn 6 = Training (6210100150).
    {"key":"prof", "user":"jakkaritw", "dept":"Solution Delivery",
     "txn":5, "gl":None, "img":"sub_prof.png", "seedBlank":True,
     "points":[("1", cell(1)), ("2", cell(2))]},
    # Public Relation has no seeded txn → repoint txn 5's glCode to the PR&Donation GL.
    {"key":"pubrel", "user":"jakkaritw", "dept":"Solution Delivery",
     "txn":5, "gl":"6211700030", "img":"sub_pubrel.png", "seedBlank":True,
     "points":[("1", cell(1)), ("2", MIN)]},
    {"key":"training", "user":"jakkaritw", "dept":"Solution Delivery",
     "txn":6, "gl":None, "img":"sub_training.png", "seedBlank":True,
     "points":[("1", cell(1)), ("2", cell(2))]},
    # NEW (ADR-0013) — read-only lock of the normal Special-GL subform. suchanya (submitter)
    # opens Professional after the ฝ่าย flips to PENDING_APPROVER1 → all inputs disabled,
    # เพิ่มรายการ/บันทึก hidden, title shows 🔒. Capture the locked modal head + footer.
    {"key":"prof_locked", "user":"suchanya", "dept":"Solution Delivery",
     "txn":5, "gl":None, "img":"sub_prof_locked.png", "seedBlank":True,
     "deptStatus":("Solution Delivery", "PENDING_APPROVER1"),
     "points":[("1", "#detailModalTitle"),
               ("2", f"{SC} tbody tr:first-child td.special-col-cell:nth-child(2) .detail-input"),
               ("3", "#detailCloseBtn")]},
    # Travelling Expense — Trip Manager (#tripModal), shared across all 8 GLs of CC+year.
    #   1 trip = entered ONCE (traveler / destination / days / side / months) → posts to up to
    #   8 GLs automatically (4 expense types × 2 accounting sides 5/6). เบี้ยเลี้ยง = AUTO
    #   (per-diem, recompute-on-read from Master FX, ADR-0015); the other 3 types are typed as a
    #   per-trip total and split across the selected months. Open via openTripModal(cc, year).
    # IMAGE 1 — trip header (Section A, entered once) + per-diem AUTO row (Section B)
    {"key":"travel", "user":"jakkaritw", "dept":"Solution Delivery", "trip":True,
     "tripCC":"10IT012000", "tripYear":2025, "img":"sub_travel.png", "seedTrip":True,
     "points":[("1", "#tripModal .trip-manager-note"),
               ("2", "#tripModal .trip-card .trip-field-grid .tf:nth-child(1) select"),
               ("3", "#tripModal .trip-card .trip-field-grid .tf:nth-child(2) .tf-readonly"),
               ("4", "#tripModal .trip-card .side-toggle-wrap"),
               ("5", "#tripModal .trip-card .trip-months-grid .tm-toggle.on"),
               ("6", "#tripModal .trip-card .trip-exp-table tbody tr:first-child .exp-gl-chip"),
               ("7", "#tripModal .trip-card .trip-exp-table .exp-total-input.auto-calc")]},
    # IMAGE 2 — MANUAL types (พาหนะ/ที่พัก/อื่น): type per-trip total → split into selected months
    {"key":"travel_manual", "user":"jakkaritw", "dept":"Solution Delivery", "trip":True,
     "tripCC":"10IT012000", "tripYear":2025, "img":"sub_travel_manual.png", "seedTrip":True,
     "points":[("1", "#tripModal .trip-card .trip-exp-table .exp-total-input:not(.auto-calc)"),
               ("2", "#tripModal .trip-card .trip-exp-table .trip-month-val-input"),
               ("3", "#tripModal .trip-card .trip-exp-table .trip-month-val-locked"),
               ("4", "#tripModalFootInfo .trip-post-chip")]},
    # NEW (ADR-0013) — read-only lock of the Trip Manager. suchanya opens the same trip after the
    # ฝ่าย flips to PENDING_APPROVER1 → the whole body is wrapped in <fieldset disabled> (every
    # input/select/button disabled), เพิ่มทริป/บันทึก hidden, subtitle shows 🔒.
    {"key":"travel_locked", "user":"suchanya", "dept":"Solution Delivery", "trip":True,
     "tripCC":"10IT012000", "tripYear":2025, "img":"sub_travel_locked.png", "seedTrip":True,
     "deptStatus":("Solution Delivery", "PENDING_APPROVER1"),
     "points":[("1", "#tripModalSubtitle"),
               ("2", "#tripModal fieldset[disabled] .trip-field-grid .tf:nth-child(1) select"),
               ("3", "#tripCloseBtn")]},
]


def capture():
    """Open each modal, screenshot to bin/, return {key: (img_path, markers_imgpx)}."""
    out = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1700, "height": 1100}, device_scale_factor=SCALE)
        pg.goto(MOCKUP.as_uri()); pg.wait_for_selector(".data-table tbody tr")
        # ---- overview: main table entry point (admin sees all; hide month cols so chip + button fit) ----
        pg.evaluate("switchUser('jakkaritw')")
        pg.evaluate("pickDept('Solution Delivery')")
        pg.wait_for_timeout(150)
        pg.evaluate("var s=document.createElement('style');s.id='ovh';"
                    "s.textContent='.data-table{min-width:0 !important}.month-col,.month-cell{display:none !important}';"
                    "document.head.appendChild(s);")
        pg.wait_for_timeout(200)
        ovp = pg.locator(".table-panel").first; omb = ovp.bounding_box()
        orects = pg.evaluate("""(sels)=>sels.map(s=>{const e=document.querySelector(s);
            if(!e)return null;const r=e.getBoundingClientRect();return {x:r.left,y:r.top,w:r.width,h:r.height};})""",
            [".special-gl-group", ".btn-detail"])
        ov_path = os.path.join(BIN_DIR, "sub_overview.png")
        ovp.screenshot(path=ov_path)
        omk = []
        for label, r in zip(["1", "2"], orects):
            if not r: continue
            ex = (r["x"]-omb["x"])*SCALE; ey = (r["y"]-omb["y"])*SCALE; ew = r["w"]*SCALE; eh = r["h"]*SCALE
            if ey > 70: cx, cy, tx, ty = ex+ew/2, ey-28, ex+ew/2, ey
            else: cx, cy, tx, ty = ex-30, ey+eh/2, ex, ey+eh/2
            omk.append({"label": label, "cx": cx, "cy": cy, "tx": tx, "ty": ty})
        pg.evaluate("var e=document.getElementById('ovh'); if(e) e.remove();")
        out["overview"] = (ov_path, omk)
        for st in STATES:
            # persona + ฝ่าย-lock (switchUser resets adminMode/postDeadline + re-renders)
            pg.evaluate(f"switchUser('{st.get('user','jakkaritw')}')")
            # optional status flip BEFORE pickDept so the lock is in effect when the modal opens (ADR-0013)
            if st.get("deptStatus"):
                d, s = st["deptStatus"]
                pg.evaluate(f"DEPT_STATUS['{d}']='{s}'")
            else:
                # keep DRAFT for editable captures (undo any prior lock flip)
                pg.evaluate("DEPT_STATUS['Solution Delivery']='DRAFT';"
                            "DEPT_STATUS['Budgeting and Management Accounting']='DRAFT'")
            pg.evaluate(f"pickDept('{st['dept']}')")
            pg.wait_for_timeout(120)
            is_trip = st.get("trip", False)
            modal_sel = "#tripModal" if is_trip else "#detailModal"
            if is_trip:
                cc, yr = st["tripCC"], st["tripYear"]
                if st.get("seedTrip"):
                    pg.evaluate(f"tripStore[tripStoreKey('{cc}',{yr})]=[]; seedDemoTrip();")
                pg.evaluate(f"openTripModal('{cc}',{yr})")
            else:
                if st.get("gl"):
                    pg.evaluate("(a) => { transactions.find(t => t.id === a.id).glCode = a.code; }",
                                {"id": st["txn"], "code": st["gl"]})
                # seed a first pendingDetails row so column cells exist for the markers
                if st.get("seedEnt"):
                    pg.evaluate(
                        "(id) => { const t = transactions.find(t => t.id === id); "
                        "t.pendingDetails = [{ id:9991, 'ประเภทการรับรอง':'Customer', "
                        "'รายละเอียด':'รับรองลูกค้า VIP กลุ่ม A', months:new Array(12).fill(0) }]; }",
                        st["txn"])
                elif st.get("seedBlank"):
                    pg.evaluate(
                        "(id) => { const t = transactions.find(t => t.id === id); "
                        "const gl = glCodes.find(g => g.code === t.glCode); "
                        "const cols = detailColumns(gl.group, gl.code); "
                        "const row = { id:9992, months:new Array(12).fill(0) }; "
                        "cols.forEach(c => row[c.key] = ''); t.pendingDetails = [row]; }",
                        st["txn"])
                pg.evaluate("(id) => openDetailModal(id)", st["txn"])
            pg.wait_for_selector(st["points"][0][1])  # wait for first labelled element to render
            # expand modal body so full content shows in the element screenshot
            pg.evaluate("document.querySelectorAll('.modal-body').forEach(e=>{e.style.maxHeight='none';e.style.overflow='visible'});")
            pg.wait_for_timeout(300)
            modal = pg.locator(f"{modal_sel} .modal").first
            mb = modal.bounding_box()
            rects = pg.evaluate("""(sels)=>sels.map(s=>{const e=document.querySelector(s);
                if(!e)return null;const r=e.getBoundingClientRect();return {x:r.left,y:r.top,w:r.width,h:r.height};})""",
                [s for _, s in st["points"]])
            miss = [s for (_, s), r in zip(st["points"], rects) if not r]
            if miss: print("      WARN missing:", miss)
            img_path = os.path.join(BIN_DIR, st["img"])
            modal.screenshot(path=img_path)
            markers = []
            for (label, _), r in zip(st["points"], rects):
                if not r:
                    continue
                ex = (r["x"] - mb["x"]) * SCALE; ey = (r["y"] - mb["y"]) * SCALE
                ew = r["w"] * SCALE; eh = r["h"] * SCALE
                if ex > 60:  # place circle left of element
                    cx, cy, tx, ty = ex - 30, ey + eh/2, ex, ey + eh/2
                else:        # place above
                    cx, cy, tx, ty = ex + ew/2, ey - 28, ex + ew/2, ey
                markers.append({"label": label, "cx": cx, "cy": cy, "tx": tx, "ty": ty})
            pg.evaluate("closeTripModal()" if is_trip else "closeDetailModal()"); pg.wait_for_timeout(120)
            out[st["key"]] = (img_path, markers)
        b.close()
    return out


# ---------------- Pillow annotation (verbatim) ---------------- #
def _num_font(s):
    try: return ImageFont.truetype(NUM_FONT_PATH, s)
    except Exception: return ImageFont.load_default()

def _leader(draw, cx, cy, tx, ty, radius):
    import math
    dx, dy = tx-cx, ty-cy; dist = math.hypot(dx, dy)
    if dist < 1: return
    ux, uy = dx/dist, dy/dist; sx, sy = cx+ux*(radius+1), cy+uy*(radius+1)
    draw.line([(sx+1, sy+1), (tx+1, ty+1)], fill=GOLD_DARK, width=2)
    draw.line([(sx, sy), (tx, ty)], fill=GOLD, width=2)
    draw.ellipse([tx-3, ty-3, tx+3, ty+3], fill=GOLD, outline=GOLD_DARK)

def _circle(draw, label, cx, cy, tx, ty, radius=18):
    _leader(draw, cx, cy, tx, ty, radius)
    draw.ellipse([cx-radius+2, cy-radius+2, cx+radius+2, cy+radius+2], fill=(0, 0, 0, 60))
    draw.ellipse([cx-radius, cy-radius, cx+radius, cy+radius], fill=GOLD, outline=GOLD_DARK, width=2)
    f = _num_font(radius+4); bb = draw.textbbox((0, 0), label, font=f)
    tw, th = bb[2]-bb[0], bb[3]-bb[1]
    draw.text((cx-tw/2-bb[0], cy-th/2-bb[1]), label, fill=WHITE, font=f)

def annotate(src_path, out_name, markers):
    im = Image.open(src_path).convert("RGBA")
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0)); dr = ImageDraw.Draw(ov)
    for m in markers:
        _circle(dr, m["label"], m["cx"], m["cy"], m["tx"], m["ty"])
    out = Image.alpha_composite(im, ov).convert("RGB")
    op = os.path.join(ASSETS_DIR, out_name); out.save(op, "PNG")
    return op, out.size


# ---------------- OOXML helpers (verbatim) ---------------- #
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

DESC = [620, 1700, 2600, 4440]          # # | คอลัม/จุด | ชนิด/ตัวเลือก | การทำงาน/เงื่อนไข
SRC = [3200, 6160]
SIGN = [1900, 3000, 2460, 2000]
META = [2700, 6660]

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
    P.append(para(run("ส่วน B — หน้ากรอกงบประมาณ · Module 02: ฟอร์มย่อยใส่รายละเอียด (Special GL Group Subform)", sz=24, bold=True, color="1E3A24"), space_after=160))
    P.append(table([["รายการ", "รายละเอียด"], ["เวอร์ชัน", "v0.4 (ฉบับร่าง)"], ["วันที่", "14 มิถุนายน 2569 (2026-06-14)"],
                    ["ผู้จัดทำ", "ทีม Data Analytics"], ["สถานะ", "รออนุมัติจากผู้ใช้"]], META))
    P.append(para(run("ประวัติการแก้ไข: v0.4 — แก้ตัวอย่างอัตราแลกเปลี่ยน (FX) ในสูตรเบี้ยเลี้ยงให้ตรงกับภาพตัวอย่าง "
                      "(ภาพใช้ปี 2025 = 35.00 ตาม Master FX ของแบบ ไม่ใช่ FY2026 = 34.20 เดิม) · v0.3 — เพิ่มโหมดอ่านอย่างเดียว (ADR-0013)",
                      sz=18, italic=True, color="6B7280"), space_after=120))

    P.append(heading("บริบทและขอบเขต (Context)"))
    P.append(body_para(
        "ในหน้ากรอกงบประมาณ GL บางกลุ่ม (Special GL Group) ไม่ได้กรอกยอดรายเดือนตรงๆ แต่ต้องกด "
        "\"+ ใส่รายละเอียดงบทำการ\" เพื่อเปิดฟอร์มย่อย (Subform) กรอกรายละเอียดก่อน แล้วระบบรวมยอดกลับไปที่แถวงบรออนุมัติ "
        "เอกสารนี้ครอบคลุม 6 กลุ่ม โดยอ้างอิงคอลัมและตัวเลือก dropdown จากไฟล์ master จริงใน docs/13Template Special"))
    P.append(para(run("ผู้ใช้หน้านี้: ผู้กรอกงบประมาณ — ระดับ L3 + L4 (Department Head, Asst Dept Head, Supervisor ทุก tier) "
                      "ไม่ใช่ Master Table Admin · เปิดฟอร์มย่อยด้วยปุ่ม \"+ ใส่รายละเอียดงบทำการ\" ที่แถวของ GL กลุ่มพิเศษ (chip สีเฉพาะกลุ่ม)",
                      sz=22, bold=True, color="1E3A24"), space_before=40, space_after=60))
    P.append(para(run("หมายเหตุ: ภาพประกอบ render จากแบบ (mockup) ตัวเลข/ชื่อเป็นข้อมูลตัวอย่าง · "
                      "วงกลมสีทองคือจุดอ้างอิงในตารางคำอธิบายของแต่ละกลุ่ม", sz=20, italic=True, color="8C6423"),
                  space_before=40, space_after=80))
    P.append(table([
        ["กลุ่ม GL", "คอลัมรายละเอียด", "ชนิดการกรอก"],
        ["Entertainment", "ประเภทการรับรอง, รายละเอียด", "ประเภทการรับรอง = dropdown (ตัวเลือกต่างกันตาม GL ภายนอก/ภายใน)"],
        ["Lease & Rental", "ประเภทรถ, ทะเบียนรถ, สถานที่ใช้งาน, กิจกรรม", "dropdown + พื้นที่เทาตามชนิด GL (รถ/เครื่องจักร/อื่น)"],
        ["Professional & Legal Fee", "Project, รายละเอียด", "กรอกอิสระ (text) — ไม่มี dropdown"],
        ["Public Relation & Donation", "รายละเอียด", "กรอกอิสระ (text) — คอลัมเดียว"],
        ["Training & Seminar", "หลักสูตรอบรม, Method", "Method = dropdown (Inhouse/Public)"],
        ["Travelling Expense", "Trip Manager (ทริป → 4 ประเภท × 2 ฝั่ง = 8 GL)", "กรอกทริปครั้งเดียว · เบี้ยเลี้ยง = อัตโนมัติ · อีก 3 ประเภทกรอกยอดรวม (ดูส่วนท้าย)"],
    ], [2400, 3500, 3460]))

    # ---- Overview: entry point ----
    P.append(heading("ภาพรวม — จุดเข้าฟอร์มย่อย (จากตารางหลัก)"))
    P.append(body_para(
        "ในตารางหลักของหน้ากรอกงบ GL กลุ่มพิเศษจะมีป้ายกลุ่มเป็น chip สีเฉพาะกลุ่ม (Entertainment เหลือง · "
        "Lease ชมพู · Professional ม่วง · Public Relation ส้ม · Training ฟ้า · Travelling เขียว) และแทนที่จะกรอก "
        "ยอดรายเดือนตรงๆ จะมีปุ่ม \"+ ใส่รายละเอียดงบทำการ\" ให้กดเพื่อเปิดฟอร์มย่อย — ยอดรวมจากฟอร์มย่อยจะถูก "
        "นำกลับมาแสดงที่แถว \"งบรออนุมัติ (Pending)\" โดยอัตโนมัติ", sz=21))
    P.append(image_para(rids["overview"], *meta["overview"][1], 100, "sub_overview", width_in=6.3))
    P.append(table([
        ["#", "จุด", "ความหมาย"],
        ["①", "ป้ายกลุ่ม GL (chip สีเฉพาะกลุ่ม)", "บอกว่า GL นี้เป็นกลุ่มพิเศษ ต้องกรอกผ่านฟอร์มย่อย"],
        ["②", "ปุ่ม + ใส่รายละเอียดงบทำการ", "กดเพื่อเปิดฟอร์มย่อยของกลุ่มนั้น (เนื้อหาตามหัวข้อ 1–6)"],
    ], [620, 3200, 5540]))
    P.append(para(run("GL กลุ่มพิเศษแสดงในตารางหน้าเวปหลักได้ 2 ทาง — ทั้งคู่เข้าฟอร์มย่อยอัตโนมัติ:",
                      sz=22, bold=True, color="1E3A24"), space_before=60, space_after=40))
    P.append(bullet("(ก) มีอยู่แล้วในตาราง — GL ที่มี SAP actual/งบ ปีนั้น (ดูกฎการแสดงแถว เอกสาร 01 ข้อ 11.1)", sz=20))
    P.append(bullet("(ข) ผู้ใช้เพิ่มเอง — GL ที่ \"ไม่เคยมี actual จริงใน SAP\" แต่จะใช้ปีนี้ กดปุ่ม \"+ เพิ่ม Transaction\" "
                    "ที่หน้าหลัก เลือก CC + GL จาก master · ถ้า GL ที่เลือกเป็นกลุ่มพิเศษ → แถวนั้นเข้าโหมดฟอร์มย่อย "
                    "\"โดยอัตโนมัติ\" เหมือนแถวพิเศษทั่วไป (Travelling → เปิด Trip Manager) — ระบบดูจากกลุ่มของ GL "
                    "ไม่สนว่าแถวมาจากทางไหน", sz=20))
    P.append(bullet("กรอกฟอร์มย่อยเสร็จ → ยอดรวมเด้งกลับแถว Pending ของ GL นั้นในตารางหลักเหมือน GL พิเศษอื่น "
                    "(Travelling: ลงครบทั้ง 8 GL ตามฝั่งบัญชี)", sz=20))

    P.append(para(run("หมายเหตุการกรอก: คอลัมรายละเอียดบางช่องเป็น dropdown (ตัวเลือกตายตัว) บางช่องกรอกอิสระ (text) — "
                      "ตัวเลือก dropdown + เงื่อนไขพื้นที่เทา อ้างอิงไฟล์ต้นฉบับใน docs/13Template Special · "
                      "Entertainment กับ Lease & Rental ตัวเลือก/พื้นที่เทา เปลี่ยนตามรหัส GL ที่เลือก", sz=20, italic=True, color="8C6423"),
                  space_before=40, space_after=80))

    # ---- Read-only lock (ADR-0013) ----
    P.append(heading("โหมดอ่านอย่างเดียวของฟอร์มย่อย (Read-only lock · ADR-0013)"))
    P.append(body_para(
        "ฟอร์มย่อยจะเปิดในโหมด \"อ่านอย่างเดียว\" เมื่อฝ่ายนั้นแก้ไขไม่ได้สำหรับผู้ใช้ปัจจุบัน — เกิดใน 3 กรณี: "
        "(1) ส่งเข้าอนุมัติแล้ว (สถานะ PENDING_*) · (2) อนุมัติแล้ว (APPROVED) · (3) ผู้ใช้เป็นผู้อนุมัติ (เปิดเพื่อตรวจ) "
        "เงื่อนไขนี้มาจากฟังก์ชัน canEditPending() → ตั้งค่า detailReadonly (ฟอร์มปกติ) / tripReadonly (Trip Manager)", sz=21))
    P.append(para(run("เมื่อ \"แก้ไม่ได้\" ฟอร์มย่อยปกติจะเปลี่ยนเป็น:", sz=22, bold=True, color="1E3A24"),
                  space_before=40, space_after=40))
    P.append(bullet("ทุกช่องกรอก (input) และ dropdown ถูก disabled — กดไม่ได้ พิมพ์ไม่ได้", sz=20))
    P.append(bullet("ปุ่ม \"เพิ่มรายการ\" และ \"บันทึก\" ถูกซ่อน · ปุ่ม \"ยกเลิก\" เปลี่ยนข้อความเป็น \"ปิด\"", sz=20))
    P.append(bullet("หัวฟอร์มมี 🔒 ต่อท้ายชื่อ และคำว่า \"อ่านอย่างเดียว (แก้ไม่ได้)\" · ปุ่มที่หน้าหลักเปลี่ยนเป็น \"🔒 ดูรายละเอียด\"", sz=20))
    P.append(body_para("ตัวอย่าง: ผู้กรอก (สุชัญญา) เปิดฟอร์ม Professional & Legal Fee หลังจากฝ่ายถูกส่งเข้าอนุมัติแล้ว (PENDING_APPROVER1)", sz=21))
    P.append(image_para(rids["prof_locked"], *meta["prof_locked"][1], 120, "sub_prof_locked", width_in=6.3))
    P.append(table([
        ["#", "จุด", "สถานะ", "การทำงาน / เงื่อนไข"],
        ["①", "หัวฟอร์ม + 🔒", "อ่านอย่างเดียว", "ชื่อกลุ่มมี 🔒 ต่อท้าย + ขึ้นข้อความ \"อ่านอย่างเดียว (แก้ไม่ได้)\""],
        ["②", "ช่องกรอกรายละเอียด", "disabled", "ทุก input / dropdown ถูกล็อก พิมพ์/เลือกไม่ได้"],
        ["③", "ปุ่มท้ายฟอร์ม", "ปิด", "ซ่อน \"เพิ่มรายการ\"/\"บันทึก\" · เหลือปุ่ม \"ปิด\""],
    ], DESC))

    # ---- 1 Entertainment ----
    P.append(heading("1) Entertainment — ประเภทการรับรอง (dropdown ขึ้นกับ GL)"))
    P.append(body_para("GL ภายนอก (รหัสลงท้าย 900030 เช่น 6211900030 ค่าเลี้ยงรับรองภายนอก): ตัวเลือก 4 แบบ — Customer · Business partner · หน่วยงานราชการ · อื่นๆ", sz=21))
    P.append(image_para(rids["ent_ext"], *meta["ent_ext"][1], 101, "sub_ent_ext", width_in=6.3))
    P.append(table([
        ["#", "คอลัม", "ชนิด / ตัวเลือก", "การทำงาน / เงื่อนไข"],
        ["①", "ประเภทการรับรอง", "dropdown", "GL ภายนอก (…900030) → Customer · Business partner · หน่วยงานราชการ · อื่นๆ"],
        ["②", "รายละเอียด", "กรอกอิสระ (text)", "อธิบายรายการรับรอง เช่น รับรองลูกค้า VIP กลุ่ม A"],
        ["③", "ยอดรายเดือน ม.ค.–ธ.ค.", "ตัวเลข", "กรอกจำนวนเงินแต่ละเดือน · รวมอัตโนมัติคอลัมขวาสุด"],
    ], DESC))
    P.append(body_para("GL ภายใน (รหัส 6211900031 ค่าเลี้ยงรับรองภายใน): ตัวเลือก \"ประเภทการรับรอง\" เปลี่ยนเป็น พนักงานบริษัท · กรรมการบริษัท", sz=21))
    P.append(image_para(rids["ent_int"], *meta["ent_int"][1], 102, "sub_ent_int", width_in=6.3))
    P.append(para(run("⚠️ ตัวเลือก \"ประเภทการรับรอง\" ต่างกันตามรหัส GL — ต้องสลับชุดตัวเลือกอัตโนมัติ:",
                      sz=21, bold=True, color="1E3A24"), space_before=60, space_after=40))
    P.append(table([
        ["รหัส GL", "ประเภท", "ตัวเลือก dropdown \"ประเภทการรับรอง\""],
        ["5211900030 · 6211900030", "ค่าเลี้ยงรับรองภายนอก (External)", "Customer · Business partner · หน่วยงานราชการ · อื่นๆ  (4 ตัวเลือก)"],
        ["6211900031", "ค่าเลี้ยงรับรองภายใน (Internal)", "พนักงานบริษัท · กรรมการบริษัท  (2 ตัวเลือก)"],
    ], [2600, 3200, 3560]))

    # ---- 2 Lease & Rental ----
    P.append(heading("2) Lease & Rental — dropdown + พื้นที่เทาตามชนิด GL"))
    P.append(body_para("GL ยานพาหนะ (รหัสลงท้าย 060 เช่น 6211200060): กรอกได้ครบทุกคอลัม — ประเภทรถ + ทะเบียนรถ เป็น dropdown", sz=21))
    P.append(image_para(rids["lease_veh"], *meta["lease_veh"][1], 103, "sub_lease_vehicle", width_in=6.3))
    P.append(table([
        ["#", "คอลัม", "ชนิด / ตัวเลือก", "การทำงาน / เงื่อนไข"],
        ["①", "ประเภทรถ", "dropdown", "GL ยานพาหนะ (…060) → Car · Van · Trucks"],
        ["②", "ทะเบียนรถ", "dropdown", "ป้ายทะเบียน 8 ตัวเลือก (6ขผ-3918, 1นจ-3508, …, ไม่ระบุ) — เฉพาะ GL ยานพาหนะ"],
        ["③", "สถานที่ใช้งาน", "dropdown", "BK · TK · KK · PB · RY — ใช้ได้ทุกชนิด GL ในกลุ่มนี้"],
        ["④", "กิจกรรม", "กรอกอิสระ (text)", "ระบุการใช้งาน เช่น รับ-ส่งผู้บริหาร"],
    ], DESC))
    P.append(body_para("GL เครื่องจักร (รหัสลงท้าย 030 เช่น 6211200030): ประเภทรถ เป็น dropdown เครื่องจักร 11 ชนิด · ทะเบียนรถ = พื้นที่เทา (—) กรอกไม่ได้", sz=21))
    P.append(image_para(rids["lease_mac"], *meta["lease_mac"][1], 110, "sub_lease_machinery", width_in=6.3))
    P.append(table([
        ["#", "คอลัม", "ชนิด / สถานะ", "การทำงาน / เงื่อนไข"],
        ["①", "ประเภทรถ", "dropdown", "GL เครื่องจักร (…030) → Mobile Scalper · Dumper · Tractors · Backhoe · Forklift · Excavator · Loader · Crane · Water Truck · Road Sweeper Truck …"],
        ["②", "ทะเบียนรถ", "เทา / กรอกไม่ได้", "GL ไม่ใช่ยานพาหนะ"],
        ["③", "สถานที่ใช้งาน", "dropdown", "BK · TK · KK · PB · RY"],
    ], DESC))
    P.append(body_para("GL อื่น (Land 010 · Building 020 · Office Eq. 040 · Computer 050 · Other 999): ทั้ง ประเภทรถ + ทะเบียนรถ = พื้นที่เทา เหลือเฉพาะ สถานที่ใช้งาน (dropdown) + กิจกรรม", sz=21))
    P.append(image_para(rids["lease_bld"], *meta["lease_bld"][1], 104, "sub_lease_building", width_in=6.3))
    P.append(table([
        ["#", "คอลัม", "สถานะ", "เงื่อนไข"],
        ["①", "ประเภทรถ", "เทา / กรอกไม่ได้", "GL ไม่ใช่ยานพาหนะหรือเครื่องจักร"],
        ["②", "ทะเบียนรถ", "เทา / กรอกไม่ได้", "GL ไม่ใช่ยานพาหนะ"],
        ["③", "สถานที่ใช้งาน", "dropdown (ใช้ได้)", "BK · TK · KK · PB · RY"],
    ], DESC))

    # ---- 3 Professional ----
    P.append(heading("3) Professional & Legal Fee — กรอกอิสระ (ไม่มี dropdown)"))
    P.append(image_para(rids["prof"], *meta["prof"][1], 105, "sub_prof", width_in=6.3))
    P.append(table([
        ["#", "คอลัม", "ชนิด", "การทำงาน"],
        ["①", "Project", "กรอกอิสระ (text)", "ชื่อโครงการ/งานที่จ้าง"],
        ["②", "รายละเอียด", "กรอกอิสระ (text)", "รายละเอียดงานที่ปรึกษา — ไฟล์ยืนยันไม่มี dropdown"],
    ], DESC))

    # ---- 4 Public Relation ----
    P.append(heading("4) Public Relation & Donation — คอลัมเดียว (ไม่มี dropdown)"))
    P.append(image_para(rids["pubrel"], *meta["pubrel"][1], 106, "sub_pubrel", width_in=6.3))
    P.append(table([
        ["#", "คอลัม", "ชนิด", "การทำงาน"],
        ["①", "รายละเอียด", "กรอกอิสระ (text)", "รายละเอียดกิจกรรม/การบริจาค — คอลัมเดียว ไม่มี dropdown"],
        ["②", "ยอดรายเดือน ม.ค.–ธ.ค.", "ตัวเลข", "กรอกจำนวนเงินแต่ละเดือน · รวมอัตโนมัติ"],
    ], DESC))

    # ---- 5 Training ----
    P.append(heading("5) Training & Seminar — Method dropdown"))
    P.append(image_para(rids["training"], *meta["training"][1], 107, "sub_training", width_in=6.3))
    P.append(table([
        ["#", "คอลัม", "ชนิด / ตัวเลือก", "การทำงาน"],
        ["①", "หลักสูตรอบรม", "กรอกอิสระ (text)", "ชื่อหลักสูตร/หัวข้อการอบรม"],
        ["②", "Method", "dropdown", "Inhouse · Public"],
    ], DESC))

    # ---- 6 Travelling Expense (REDESIGNED 2026 → Trip Manager) ----
    P.append(heading("6) Travelling Expense — Trip Manager: 1 ทริปกรอกครั้งเดียว → ลง 8 GL อัตโนมัติ"))
    P.append(body_para(
        "Travelling Expense ออกแบบใหม่เป็น \"Trip Manager\" — ผู้ใช้กดจาก GL Travelling แถวใดก็ได้ในตารางหลัก "
        "(กด \"+ ใส่รายละเอียดงบทำการ\") ระบบเปิด Trip Manager ที่ \"ใช้ร่วมกันทั้ง 8 GL ของ Cost Center + ปี เดียวกัน\" "
        "ไม่ใช่ฟอร์มแยกราย GL อีกต่อไป", sz=21))
    P.append(body_para(
        "แนวคิดหลัก: กรอก \"ข้อมูลทริปครั้งเดียว\" (ผู้เดินทาง · ปลายทาง · จำนวนวัน · ฝั่งบัญชี · เดือนที่เดินทาง) "
        "แล้วระบบลงบัญชีให้อัตโนมัติทั้ง 4 ประเภทค่าใช้จ่าย — เลิกการกรอกผู้เดินทาง/เดือนซ้ำทีละ GL แบบเดิม "
        "(1 ทริปเคยต้องเปิด 4–5 ฟอร์ม กรอกเดือนซ้ำ ๆ ทุกครั้ง)", sz=21))
    P.append(para(run("โครงสร้าง Trip Manager (ต่อ 1 ทริป):", sz=22, bold=True, color="1E3A24"), space_before=60, space_after=40))
    P.append(bullet("ส่วน A — ข้อมูลทริป (กรอกครั้งเดียว): Traveler → Position(อัตโนมัติ) → Destination → Project/Purpose → "
                    "Total Days → ฝั่งบัญชี (toggle 5 ผลิต / 6 SG&A) · เลือกเดือนที่เดินทาง 1 ชุด (ทุกประเภทใช้เดือนชุดเดียวกัน)", sz=20))
    P.append(bullet("ส่วน B — ค่าใช้จ่าย 4 ประเภทในการ์ดเดียว: เบี้ยเลี้ยง (คำนวณอัตโนมัติ) · ค่าพาหนะ / ค่าที่พัก / "
                    "ค่าใช้จ่ายอื่น (กรอกยอดรวม/ทริป → ระบบแบ่งเท่ากันลงเดือนที่เลือก)", sz=20))
    P.append(bullet("ฝั่งบัญชี (toggle 5/6) เป็นตัวเลือกว่าค่าใช้จ่ายทั้ง 4 ประเภทลงฝั่งผลิต(5) หรือ SG&A(6) — กำหนด GL ปลายทาง", sz=20))
    P.append(bullet("กด \"บันทึก & ลงบัญชี\" → ระบบรวมยอดทุกทริปแยกตามประเภท×ฝั่ง แล้วเขียนกลับแถว Pending ของ GL ที่ตรงกัน "
                    "(ดูแถบสรุปการลงบัญชีท้ายหน้าต่าง)", sz=20))
    P.append(para(run("4 ประเภทค่าใช้จ่าย × 2 ฝั่งบัญชี = 8 GL (จากชีต GL ของไฟล์ Traveling expenses.xlsx)",
                      sz=22, bold=True, color="1E3A24"), space_before=80, space_after=60))
    P.append(table([
        ["ประเภท (ชื่อไทย)", "GL ฝั่งผลิต/ต้นทุน (5)", "GL ฝั่ง SG&A (6)", "วิธีกรอก"],
        ["เบี้ยเลี้ยง · Per Diem", "5210400010", "6210400010", "คำนวณอัตโนมัติ (per-diem engine)"],
        ["ค่าพาหนะเดินทาง · Transportation", "5210400020", "6210400020", "กรอกเอง รายเดือน"],
        ["ค่าที่พัก · Accommodation", "5210400030", "6210400030", "กรอกเอง รายเดือน"],
        ["ค่าใช้จ่ายเดินทางอื่น · Other Travel", "5210400999", "6210400999", "กรอกเอง รายเดือน"],
    ], [2960, 2100, 2100, 2200]))

    # 6a — Trip header (Section A, entered once) + per-diem AUTO (Section B)
    P.append(para(run("6.1) ส่วน A — ข้อมูลทริป (กรอกครั้งเดียว) + เบี้ยเลี้ยงคำนวณอัตโนมัติ",
                      sz=24, bold=True, color="2F6B3F"), space_before=160, space_after=80, keep_next=True))
    P.append(body_para(
        "กรอกข้อมูลทริปครั้งเดียว (ส่วน A) — เบี้ยเลี้ยง (ส่วน B แถวแรก) ระบบคิดยอดให้อัตโนมัติจาก [ตำแหน่ง × กลุ่มประเทศ] "
        "แล้วเฉลี่ยลงเดือนที่เลือก แก้ตัวเลขรายเดือนไม่ได้", sz=21))
    P.append(image_para(rids["travel"], *meta["travel"][1], 108, "sub_travel", width_in=6.3))
    P.append(table([
        ["#", "คอลัม / จุด", "ชนิด", "การทำงาน / เงื่อนไข"],
        ["①", "ขั้นตอน A→B→C (หัวฟอร์ม)", "คำอธิบาย", "ย้ำ \"1 ทริป = กรอกครั้งเดียว\" ระบบลง GL ให้ทั้ง 4 ประเภทอัตโนมัติ"],
        ["②", "ผู้เดินทาง (Traveler)", "dropdown", "เลือกจาก mas_employee_data.fullnameth (กรอกครั้งเดียว/ทริป)"],
        ["③", "ตำแหน่ง (Position)", "อัตโนมัติ", "ดึงจากผู้เดินทาง — แก้ไม่ได้ · ใช้คิดอัตราเบี้ยเลี้ยง"],
        ["④", "ฝั่งบัญชี (toggle)", "เลือก 5 / 6", "เลือกฝั่งผลิต(5) หรือ SG&A(6) — กำหนดว่าทั้ง 4 ประเภทลง GL กลุ่มไหน"],
        ["⑤", "เลือกเดือนเดินทาง", "คลิก toggle", "เลือกครั้งเดียว/ทริป ใช้ร่วมทุกประเภท · เดือนไม่เลือก = ล็อก"],
        ["⑥", "GL ของเบี้ยเลี้ยง", "อัตโนมัติ", "ชิปบอก GL ปลายทางของแถวเบี้ยเลี้ยง (5210400010 หรือ 6210400010 ตามฝั่ง)"],
        ["⑦", "ยอดเบี้ยเลี้ยง/ทริป", "คำนวณอัตโนมัติ (read-only)", "วัน × อัตรา × (FX ถ้าต่างประเทศ) — แล้วแบ่งเท่ากันลงเดือนที่เลือก"],
    ], DESC))
    P.append(para(run(
        "สูตรเบี้ยเลี้ยง: ในประเทศ(ไทย) = วัน × อัตรา ฿ (ไม่คูณ FX) · ต่างประเทศ = วัน × อัตรา $ × อัตราแลกเปลี่ยน "
        "(Master FX ของปีงบประมาณนั้น เช่น ภาพตัวอย่างปี 2025 = 35.00) · อัตราตาม [ตำแหน่ง × กลุ่มประเทศ] จากชีต เบี้ยเลี้ยง "
        "(ตำแหน่งระดับบริหารในประเทศ = ไม่มีอัตรา/—)", sz=20, color="3F4D45")))
    # ADR-0015 — per-diem is recompute-on-read, NOT a stored snapshot, NO fx_rate_used.
    P.append(para(run("เบี้ยเลี้ยงคำนวณใหม่ทุกครั้งที่อ่าน (Recompute-on-read · ADR-0015):",
                      sz=21, bold=True, color="1E3A24"), space_before=80, space_after=40))
    P.append(bullet("ยอดเบี้ยเลี้ยงต่างประเทศ = วัน × อัตรา(ตำแหน่ง × กลุ่มประเทศ) × Master FX \"ของปีนั้น\" — "
                    "ระบบคำนวณใหม่ทุกครั้งที่เปิด/อ่าน \"ไม่ได้\" เก็บค่าแช่แข็ง (snapshot) และ \"ไม่มี\" คอลัม fx_rate_used", sz=20))
    P.append(bullet("Master FX มี 1 อัตราต่อปีงบประมาณ · แก้ไขได้ที่หน้า Master Currency (Module 09) เท่านั้น — "
                    "หน้ากรอกงบ \"อ่านอย่างเดียว\" ไม่แก้ FX ที่นี่", sz=20))
    P.append(bullet("เมื่อแก้ Master FX ของปีใด → เบี้ยเลี้ยงต่างประเทศ \"ทุกทริปของปีนั้น\" คิดราคาใหม่ทันที "
                    "รวมทั้งฝ่ายที่อนุมัติแล้ว (APPROVED) ด้วย", sz=20))
    P.append(bullet("ค่าใช้จ่ายเดินทางอีก 3 ประเภท (พาหนะ / ที่พัก / อื่น) เป็นยอด ฿ ที่กรอกเอง — "
                    "\"ไม่\" เปลี่ยนตาม FX", sz=20))

    P.append(para(run("ตารางอัตราเบี้ยเลี้ยง (ตำแหน่ง × กลุ่มประเทศ) — จากชีต เบี้ยเลี้ยง", sz=22, bold=True, color="1E3A24"),
                  space_before=80, space_after=60))
    P.append(table([
        ["ตำแหน่ง", "ในประเทศ ฿/วัน", "กลุ่ม 2 Asian $/วัน", "กลุ่ม 3 Other $/วัน"],
        ["CEO / Chief Officer / Advisor", "— (ไม่มีอัตรา)", "110", "120"],
        ["Vice President / Assistant VP", "— (ไม่มีอัตรา)", "100", "110"],
        ["Department Head / Asst Dept Head", "300", "80", "90"],
        ["Senior Supervisor / Supervisor", "250", "70", "80"],
        ["Operator", "200", "70", "80"],
        ["Company Driver / Logistics Driver", "200", "60", "70"],
    ], [3760, 1800, 1900, 1900]))
    P.append(para(run("กลุ่มประเทศ (กำหนดอัตราต่างกัน):", sz=21, bold=True, color="1E3A24"), space_before=40, space_after=40))
    P.append(bullet("กลุ่ม 1 — ไทย (ในประเทศ): ใช้ ฿ ตรงๆ ไม่คูณอัตราแลกเปลี่ยน", sz=20))
    P.append(bullet("กลุ่ม 2 — Asian ($): Papua New Guinea, China, Laos, Philippines, India, Vietnam, Myanmar, Indonesia, Bangladesh, South Africa, Cambodia, Malaysia", sz=20))
    P.append(bullet("กลุ่ม 3 — Other ($): USA, UK, Australia, New Zealand, Switzerland, Japan, Korea, Taiwan, Germany, Oman, Singapore, Argentina, Italy, Dubai, Saudi Arabia, Norway", sz=20))

    # 6b — MANUAL types (พาหนะ/ที่พัก/อื่น) in the SAME trip card
    P.append(para(run("6.2) ส่วน B — ค่าพาหนะ / ที่พัก / ค่าใช้จ่ายอื่น (กรอกยอดรวม → แบ่งลงเดือน) + การลงบัญชี",
                      sz=24, bold=True, color="2F6B3F"), space_before=200, space_after=80, keep_next=True))
    P.append(body_para(
        "อีก 3 ประเภทอยู่ในการ์ดทริปเดียวกัน (ไม่ต้องเปิดฟอร์มใหม่) — กรอก \"ยอดรวม/ทริป\" 1 ช่อง ระบบแบ่งเท่ากัน "
        "ลงเฉพาะเดือนที่เลือก (เดือนที่ไม่เลือก = ล็อกเทา) · แต่ละประเภทลง GL ของตัวเองตามฝั่งบัญชีที่เลือกในส่วน A", sz=21))
    P.append(image_para(rids["travel_manual"], *meta["travel_manual"][1], 109, "sub_travel_manual", width_in=6.3))
    P.append(table([
        ["#", "คอลัม / จุด", "ชนิด", "การทำงาน / เงื่อนไข"],
        ["①", "ยอดรวม/ทริป (ประเภท manual)", "กรอกเอง (ตัวเลข)", "พิมพ์ยอดรวมทั้งทริป 1 ช่อง — ระบบแบ่งเท่ากันลงเดือนที่เลือก"],
        ["②", "ยอดรายเดือน (เดือนที่เลือก)", "แก้ได้รายช่อง", "ค่าจากการแบ่งอัตโนมัติ ปรับรายเดือนเพิ่มได้"],
        ["③", "เดือนที่ไม่เลือก", "ล็อก / เทา (—)", "อยู่นอกชุดเดือนของทริป → กรอกไม่ได้"],
        ["④", "แถบสรุปการลงบัญชี (ท้ายหน้าต่าง)", "อัตโนมัติ", "ชิปบอกแต่ละ GL ปลายทาง + ยอด เช่น \"6210400020 ฿…\" — รวมทุกประเภท×ฝั่งของทุกทริป"],
    ], DESC))

    # 6.3 — Trip Manager read-only lock (ADR-0013)
    P.append(para(run("6.3) โหมดอ่านอย่างเดียวของ Trip Manager (Read-only lock · ADR-0013)",
                      sz=24, bold=True, color="2F6B3F"), space_before=200, space_after=80, keep_next=True))
    P.append(body_para(
        "Trip Manager ใช้กฎล็อกเดียวกับฟอร์มย่อยอื่น (canEditPending → tripReadonly): เมื่อฝ่ายแก้ไม่ได้ "
        "(PENDING_* / APPROVED / ผู้ใช้เป็นผู้อนุมัติ) ระบบครอบเนื้อหาทั้งหมดด้วย <fieldset disabled> "
        "ทำให้ทุก input / select / ปุ่มภายในถูก disabled พร้อมกัน · ซ่อนปุ่ม \"เพิ่มทริป\" และ \"บันทึก & ลงบัญชี\" · "
        "ปุ่ม \"ยกเลิก\" เปลี่ยนเป็น \"ปิด\" และหัวเรื่องขึ้น 🔒 \"อ่านอย่างเดียว (แก้ไม่ได้)\"", sz=21))
    P.append(body_para("ตัวอย่าง: ผู้กรอก (สุชัญญา) เปิด Trip Manager หลังจากฝ่ายถูกส่งเข้าอนุมัติแล้ว (PENDING_APPROVER1)", sz=21))
    P.append(image_para(rids["travel_locked"], *meta["travel_locked"][1], 121, "sub_travel_locked", width_in=6.3))
    P.append(table([
        ["#", "จุด", "สถานะ", "การทำงาน / เงื่อนไข"],
        ["①", "หัวเรื่อง + 🔒", "อ่านอย่างเดียว", "ขึ้น \"🔒 อ่านอย่างเดียว (แก้ไม่ได้)\" ต่อท้าย CC · FY"],
        ["②", "ช่องในการ์ดทริป", "disabled (fieldset)", "ทั้งการ์ดถูกครอบด้วย fieldset disabled → ทุก input/select/ปุ่ม กดไม่ได้"],
        ["③", "ปุ่มท้ายหน้าต่าง", "ปิด", "ซ่อน \"เพิ่มทริป\"/\"บันทึก & ลงบัญชี\" · เหลือปุ่ม \"ปิด\""],
    ], DESC))

    # ---- Save behaviour ----
    P.append(heading("การบันทึกฟอร์มย่อย"))
    P.append(bullet("กลุ่มพิเศษ 5 กลุ่ม (Entertainment / Lease / Professional / Public Relation / Training): กด บันทึก → "
                    "รวมยอดทุกบรรทัด กลับไปแสดงที่แถว \"งบรออนุมัติ (Pending)\" ของ GL นั้นในตารางหลัก (read-only)"))
    P.append(bullet("Travelling (Trip Manager): กด \"บันทึก & ลงบัญชี\" → ระบบรวมยอดทุกทริป แยกตาม [ประเภท × ฝั่ง] "
                    "แล้วเขียนกลับแถว Pending ของ GL ที่ตรงกัน \"พร้อมกันได้ถึง 8 GL\" จากทริปชุดเดียว (ไม่ใช่ 1 ฟอร์ม = 1 GL อีกต่อไป)"))
    P.append(bullet("Trip Manager ใช้ร่วมกันทั้ง 8 GL ของ Cost Center + ปี เดียวกัน — เปิดจาก GL Travelling แถวใดก็เห็นทริปชุดเดียวกัน"))
    P.append(bullet("กด ยกเลิก/ปิด → ฟอร์มย่อยเป็นส่วนหนึ่งของหน้ากรอกงบ ยังไม่ส่งเข้าฐานข้อมูลจนกว่าจะกด Submit ที่หน้าหลัก"))
    P.append(bullet("กด เพิ่มทริป → เพิ่มอีก 1 ทริปในการ์ดถัดไป (ผู้เดินทาง/ปลายทางคนละชุด)"))

    # ---- Data sources ----
    P.append(heading("สรุปแหล่งข้อมูล (Data sources)"))
    P.append(table([
        ["แหล่ง / ไฟล์", "บทบาท"],
        ["docs/13Template Special/*.xlsx (6 ไฟล์)", "นิยามคอลัม + ตัวเลือก dropdown ของแต่ละกลุ่ม (sheet หลัก + sheet GL)"],
        ["docs/13Template Special/Traveling expenses.xlsx (sheet GL)", "mapping 8 GL → 4 ประเภท × 2 ฝั่ง (5 ผลิต / 6 SG&A) — กำหนดว่า GL ไหนคือประเภทใด"],
        ["docs/13Template Special/Traveling expenses.xlsx (sheet เบี้ยเลี้ยง)", "ตารางอัตราเบี้ยเลี้ยง [ตำแหน่ง × กลุ่มประเทศ] + รายชื่อประเทศแต่ละกลุ่ม"],
        ["cfg_master.master_currency_rate (Module 09)", "Master FX USD→THB 1 อัตรา/ปี — เจ้าของ/แก้ไขที่หน้า Master Currency เท่านั้น · หน้ากรอกงบอ่านอย่างเดียวแล้วคิดเบี้ยเลี้ยงใหม่ทุกครั้ง (recompute-on-read · ADR-0015)"],
        ["dbo.mas_employee_data", "dropdown ผู้เดินทาง (fullnameth) → ตำแหน่ง (joblevel)"],
    ], SRC))

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
    print("[1/4] Capturing modal screenshots + DOM rects (Playwright) ...")
    shots = capture()
    print("[2/4] Annotating with gold markers (Pillow) ...")
    meta = {}
    order = ["overview"] + [s["key"] for s in STATES]
    for k in order:
        src, markers = shots[k]
        meta[k] = annotate(src, os.path.basename(src), markers)
        print(f"      {k}: {meta[k][0]}  {meta[k][1]}  markers={len(markers)}")
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
