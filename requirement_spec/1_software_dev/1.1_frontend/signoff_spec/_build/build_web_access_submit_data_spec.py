# -*- coding: utf-8 -*-
"""
Generator for the Web Access & Submit Data User Sign-off Specification (.docx).

Module 10 — who can see / fill / submit budget, the submit→approval lifecycle
(6-state machine), the approval chain, C-Level system access, proxy fillers,
and admin override.

WHAT CHANGED (v0.3, 2026-06-14):
  - The design dropped the SEPARATE approver inbox. Approvers now review +
    approve on the SAME main page via the ฝ่าย-picker (#faiPicker) + bottom
    action bar (#approveBtn / #rejectBtn). The doc is re-pointed from the dead
    demo mockups 0013-approver-inbox-demo / 0012-main-table-demo / 0011-subform-demo
    to the canonical, wired source of truth:
        design/mockups/0002claude design/0002.1budget-export.html
  - "Approver Inbox (unit = ฝ่าย)" framing → "Approve on the main page".
  - Added the explicit Submit→approval lifecycle / 6-state machine, the
    edit-lock-after-submit rule (ADR-0006/0013), and admin-override-submit
    (ADR-0012).
  - NEW: this build now CAPTURES live screenshots from 0002.1 (Playwright) and
    annotates them with gold markers (Pillow), mirroring build_main_web_app_spec.py
    VERBATIM (capture/_markers_from_rects/annotate/image_para). Captures use the
    bin/ prefix `wa_` and embed into the .docx media folder.

HARD CONSTRAINTS honoured:
  - NO package installation. stdlib + Pillow + Playwright (all installed).
  - The .docx is built BY HAND as Office Open XML (WordprocessingML).
  - Thai text uses Leelawadee UI on w:ascii / w:hAnsi / w:cs, with w:szCs == w:sz.
  - document.xml is UTF-8 encoded.

Re-runnable: overwrites screenshots (bin/, prefix wa_), assets, and the .docx each run.
"""

import os, sys, zipfile, html, pathlib
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

# Console may be cp1252 on Windows; PROOF lines print ①②③ — force UTF-8 stdout.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
PROJECT_ROOT = r"c:\04.budget_management_web"
SIGNOFF_DIR = os.path.join(
    PROJECT_ROOT,
    "requirement_spec", "1_software_dev", "1.1_frontend", "signoff_spec",
)
ASSETS_DIR = os.path.join(SIGNOFF_DIR, "assets")
BIN_DIR = os.path.join(PROJECT_ROOT, "bin")
DOCX_PATH = os.path.join(SIGNOFF_DIR, "10_web_access_submit_data_spec.docx")
MOCKUP = pathlib.Path(PROJECT_ROOT, "design", "mockups", "0002claude design", "0002.1budget-export.html")
os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(BIN_DIR, exist_ok=True)

THAI_FONT = "Leelawadee UI"    # ships with Windows, Thai-capable
GOLD = (201, 150, 61); GOLD_DARK = (140, 100, 35); WHITE = (255, 255, 255)
RED = (211, 47, 47); RED_DARK = (142, 27, 27)        # action: submit / reject
GREEN = (46, 125, 50); GREEN_DARK = (27, 94, 32)     # action: approve
NUM_FONT_PATH = r"C:\Windows\Fonts\arialbd.ttf"
SCALE = 2  # device_scale_factor


# --------------------------------------------------------------------------- #
# CAPTURE — screenshot the main page approve/submit flow + read element rects.
# Returns {key: (img_path, markers)} where markers are in image-pixel space.
# Mirrors build_main_web_app_spec.py VERBATIM (only selectors / personas differ).
# --------------------------------------------------------------------------- #
def _markers_from_rects(points, rects, base_box, colors=None):
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
    """Capture the approve-ON-the-main-page flow from 0002.1 (no separate inbox).

    Personas via switchUser(); the page is locked to a ฝ่าย via pickDept(); the
    in-memory DEPT_STATUS map + submitToDB()/approverApprove()/approverReject()
    drive transitions. CCs: 10IT012000 (Solution Delivery), 10AC020000 (Budgeting).
    """
    out = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1700, "height": 1180}, device_scale_factor=SCALE)
        pg.goto(MOCKUP.as_uri()); pg.wait_for_selector(".data-table tbody tr")
        pg.wait_for_timeout(300)

        # ── 1) SUBMITTER on the main page — ฝ่าย-picker + Submit in the action bar ──
        #     สุชัญญา (L3 · Solution Delivery) = a submitter. Lock to her ฝ่าย; the
        #     bottom action bar shows the Submit button (DRAFT → can submit).
        #       ① #faipTrig (the ฝ่าย-picker — the approval unit, ADR-0008)
        #       ② #submitBtn (Submit → enters the chain)
        pg.evaluate("switchUser('suchanya')"); pg.wait_for_timeout(150)
        pg.evaluate("pickDept('Solution Delivery')"); pg.wait_for_timeout(200)
        sub_main = pg.locator("main.wrap").first
        smbox = sub_main.bounding_box()
        sub_points = [("1", "#faipTrig"), ("2", "#submitBtn")]
        sub_rects = pg.evaluate(RECT_JS, [s for _, s in sub_points])
        sub_path = os.path.join(BIN_DIR, "wa_submit_mainpage.png")
        sub_main.screenshot(path=sub_path)
        out["submit"] = (sub_path, _markers_from_rects(
            sub_points, sub_rects, smbox, colors=[(GOLD, GOLD_DARK), (RED, RED_DARK)]))

        # ── 2) LOCKED AFTER SUBMIT — ฝ่าย enters PENDING_APPROVER1, submitter read-only ──
        #     Drive the transition with submitToDB(), then re-render. The action-bar
        #     status note now reads "ส่งแล้ว · PENDING_APPROVER1 · แก้ไม่ได้".
        #       ① #faipTrig (still the unit) · ② #actStatus (locked note)
        pg.evaluate("DEPT_STATUS['Solution Delivery']='PENDING_APPROVER1'; renderTable();")
        pg.wait_for_timeout(200)
        lock_main = pg.locator("main.wrap").first
        lkbox = lock_main.bounding_box()
        lock_points = [("1", "#faipTrig"), ("2", "#actStatus")]
        lock_rects = pg.evaluate(RECT_JS, [s for _, s in lock_points])
        lock_path = os.path.join(BIN_DIR, "wa_locked_after_submit.png")
        lock_main.screenshot(path=lock_path)
        out["locked"] = (lock_path, _markers_from_rects(lock_points, lock_rects, lkbox))

        # ── 3) APPROVER on the main page — ฝ่าย-picker รออนุมัติ badge + Approve/Reject ──
        #     อาทิตย์ (L2/AVP · approver1 of Solution Delivery) logs in. The ฝ่าย is at
        #     PENDING_APPROVER1 = exactly his step → the picker shows the รออนุมัติ badge
        #     and the action bar shows Approve + Reject (NOT a separate inbox screen).
        #       ① #faipPP   (รออนุมัติ badge on the ฝ่าย-picker)
        #       ② #approveBtn (Approve) → GREEN
        #       ③ #rejectBtn  (Reject)  → RED
        pg.evaluate("switchUser('arthit')"); pg.wait_for_timeout(150)
        # arthit's status was reset by switchUser → re-seed PENDING_APPROVER1 + lock his ฝ่าย
        pg.evaluate("DEPT_STATUS['Solution Delivery']='PENDING_APPROVER1';")
        pg.evaluate("pickDept('Solution Delivery')"); pg.wait_for_timeout(200)
        apv_main = pg.locator("main.wrap").first
        apbox = apv_main.bounding_box()
        apv_points = [("1", "#faipPP"), ("2", "#approveBtn"), ("3", "#rejectBtn")]
        apv_rects = pg.evaluate(RECT_JS, [s for _, s in apv_points])
        apv_path = os.path.join(BIN_DIR, "wa_approve_mainpage.png")
        apv_main.screenshot(path=apv_path)
        out["approve"] = (apv_path, _markers_from_rects(
            apv_points, apv_rects, apbox, colors=[(GOLD, GOLD_DARK), (GREEN, GREEN_DARK), (RED, RED_DARK)]))

        # ── 4) ฝ่าย-PICKER panel open — รออนุมัติ badge per ฝ่าย + "เฉพาะที่รออนุมัติ" toggle ──
        #     Open the picker dropdown (approver view) to show the grouped-by-สายงาน list,
        #     the per-ฝ่าย รออนุมัติ/อนุมัติแล้ว badges, and the filter toggle.
        #       ① #faipToggleWrap ("เฉพาะที่รออนุมัติ" toggle) · ② #faipList (the ฝ่าย list)
        pg.evaluate("toggleFaiPanel()"); pg.wait_for_timeout(200)
        # The dropdown #faipPanel is position:absolute, so it overflows the #faiPicker
        # element box (~48px). Screenshot the PANEL itself — it contains both the toggle
        # (#faipToggleWrap) and the ฝ่าย list (#faipList), so both markers land inside it.
        pick = pg.locator("#faipPanel").first
        pkbox = pick.bounding_box()
        pick_points = [("1", "#faipToggleWrap"), ("2", "#faipList")]
        pick_rects = pg.evaluate(RECT_JS, [s for _, s in pick_points])
        pick_path = os.path.join(BIN_DIR, "wa_fai_picker.png")
        pick.screenshot(path=pick_path)
        out["picker"] = (pick_path, _markers_from_rects(pick_points, pick_rects, pkbox))
        pg.evaluate("toggleFaiPanel()"); pg.wait_for_timeout(120)  # close

        # ── 5) 🛡️ โหมด Admin toggle — dual-role admin hat (ADR-0014) ──
        #     นิภาพร (Budget Staff) is approver2 AND an overlay admin → the nav shows the
        #     "🛡️ โหมด Admin" toggle. Capture the nav region with the toggle visible.
        #       ① #adminModeWrap (the 🛡️ โหมด Admin toggle)
        pg.evaluate("switchUser('nipaporn')"); pg.wait_for_timeout(150)
        pg.evaluate("pickDept('Budgeting and Management Accounting')"); pg.wait_for_timeout(200)
        nav = pg.locator(".nav").first
        nvbox = nav.bounding_box()
        adm_points = [("1", "#adminModeWrap")]
        adm_rects = pg.evaluate(RECT_JS, [s for _, s in adm_points])
        adm_path = os.path.join(BIN_DIR, "wa_admin_toggle.png")
        nav.screenshot(path=adm_path)
        out["admin"] = (adm_path, _markers_from_rects(adm_points, adm_rects, nvbox))

        b.close()
    return out


# ---------------- Pillow annotation (verbatim from main spec) ---------------- #
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


# --------------------------------------------------------------------------- #
# OOXML (WordprocessingML) builders (VERBATIM from main / orgcode generators)
# --------------------------------------------------------------------------- #
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
EMU_PER_IN = 914400; TARGET_WIDTH_IN = 6.3


def esc(text):
    return html.escape(str(text), quote=True)


def run_props(size_half_pt, bold=False, color=None, italic=False):
    parts = ['<w:rPr>']
    parts.append(
        f'<w:rFonts w:ascii="{THAI_FONT}" w:hAnsi="{THAI_FONT}" w:cs="{THAI_FONT}"/>'
    )
    if bold:
        parts.append('<w:b/><w:bCs/>')
    if italic:
        parts.append('<w:i/><w:iCs/>')
    if color:
        parts.append(f'<w:color w:val="{color}"/>')
    parts.append(f'<w:sz w:val="{size_half_pt}"/>')
    parts.append(f'<w:szCs w:val="{size_half_pt}"/>')
    parts.append('</w:rPr>')
    return "".join(parts)


def run(text, size_half_pt=22, bold=False, color=None, italic=False):
    rpr = run_props(size_half_pt, bold=bold, color=color, italic=italic)
    return (
        f'<w:r>{rpr}<w:t xml:space="preserve">{esc(text)}</w:t></w:r>'
    )


def para(runs_xml, align=None, space_before=0, space_after=120, shading=None,
         keep_next=False):
    ppr = ['<w:pPr>']
    ppr.append(
        f'<w:rFonts w:ascii="{THAI_FONT}" w:hAnsi="{THAI_FONT}" w:cs="{THAI_FONT}"/>'
    )
    spacing = f'<w:spacing w:before="{space_before}" w:after="{space_after}"/>'
    ppr.append(spacing)
    if align:
        ppr.append(f'<w:jc w:val="{align}"/>')
    if shading:
        ppr.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{shading}"/>')
    if keep_next:
        ppr.append('<w:keepNext/>')
    ppr.append('</w:pPr>')
    return f'<w:p>{"".join(ppr)}{runs_xml}</w:p>'


def heading(text, size_half_pt=30, color="2F6B3F", space_before=240,
            space_after=120):
    return para(
        run(text, size_half_pt=size_half_pt, bold=True, color=color),
        space_before=space_before, space_after=space_after, keep_next=True,
    )


def body_para(text, size_half_pt=22, space_after=120):
    return para(run(text, size_half_pt=size_half_pt), space_after=space_after)


def bullet(text, size_half_pt=22):
    return para(
        run("•  " + text, size_half_pt=size_half_pt),
        space_after=60,
    )


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


def tcell(content_xml, width_dxa=None, fill=None):
    tc_pr = ['<w:tcPr>']
    if width_dxa:
        tc_pr.append(f'<w:tcW w:w="{width_dxa}" w:type="dxa"/>')
    else:
        tc_pr.append('<w:tcW w:w="0" w:type="auto"/>')
    if fill:
        tc_pr.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>')
    tc_pr.append('<w:tcMar><w:top w:w="40" w:type="dxa"/><w:bottom w:w="40" w:type="dxa"/>'
                 '<w:left w:w="80" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tcMar>')
    tc_pr.append('<w:vAlign w:val="center"/>')
    tc_pr.append('</w:tcPr>')
    return f'<w:tc>{"".join(tc_pr)}{content_xml}</w:tc>'


def cell_para(text, bold=False, color=None, size_half_pt=18, align=None):
    return para(
        run(text, size_half_pt=size_half_pt, bold=bold, color=color),
        align=align, space_after=20, space_before=20,
    )


def table(rows, col_widths_dxa, header_fill="E8F0E8"):
    tbl = ['<w:tbl>']
    tbl.append('<w:tblPr>')
    tbl.append('<w:tblW w:w="5000" w:type="pct"/>')
    tbl.append(
        '<w:tblBorders>'
        '<w:top w:val="single" w:sz="4" w:space="0" w:color="9AB59A"/>'
        '<w:left w:val="single" w:sz="4" w:space="0" w:color="9AB59A"/>'
        '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="9AB59A"/>'
        '<w:right w:val="single" w:sz="4" w:space="0" w:color="9AB59A"/>'
        '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="C7D6C7"/>'
        '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="C7D6C7"/>'
        '</w:tblBorders>'
    )
    tbl.append('<w:tblLayout w:type="fixed"/>')
    tbl.append('</w:tblPr>')
    tbl.append('<w:tblGrid>')
    for wdt in col_widths_dxa:
        tbl.append(f'<w:gridCol w:w="{wdt}"/>')
    tbl.append('</w:tblGrid>')

    for ri, row in enumerate(rows):
        is_header = ri == 0
        tr = ['<w:tr>']
        if is_header:
            tr.append('<w:trPr><w:tblHeader/></w:trPr>')
        for ci, cell in enumerate(row):
            fill = header_fill if is_header else None
            content = cell_para(
                cell, bold=is_header,
                color=("1E3A24" if is_header else None),
                size_half_pt=(18 if is_header else 17),
            )
            tr.append(tcell(content, width_dxa=col_widths_dxa[ci], fill=fill))
        tr.append('</w:tr>')
        tbl.append("".join(tr))
    tbl.append('</w:tbl>')
    tbl.append(para(run("", size_half_pt=8), space_after=80))
    return "".join(tbl)


def _sign_table(rows, col_widths_dxa):
    tbl = ['<w:tbl>']
    tbl.append('<w:tblPr><w:tblW w:w="5000" w:type="pct"/>')
    tbl.append(
        '<w:tblBorders>'
        '<w:top w:val="single" w:sz="4" w:space="0" w:color="9AB59A"/>'
        '<w:left w:val="single" w:sz="4" w:space="0" w:color="9AB59A"/>'
        '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="9AB59A"/>'
        '<w:right w:val="single" w:sz="4" w:space="0" w:color="9AB59A"/>'
        '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="C7D6C7"/>'
        '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="C7D6C7"/>'
        '</w:tblBorders><w:tblLayout w:type="fixed"/></w:tblPr>'
    )
    tbl.append('<w:tblGrid>')
    for wdt in col_widths_dxa:
        tbl.append(f'<w:gridCol w:w="{wdt}"/>')
    tbl.append('</w:tblGrid>')
    for ri, row in enumerate(rows):
        is_header = ri == 0
        tr = ['<w:tr>']
        trpr = ['<w:trPr>']
        if is_header:
            trpr.append('<w:tblHeader/>')
        else:
            trpr.append('<w:trHeight w:val="900" w:hRule="atLeast"/>')
        trpr.append('</w:trPr>')
        tr.append("".join(trpr))
        for ci, cell in enumerate(row):
            fill = "E8F0E8" if is_header else None
            content = cell_para(
                cell, bold=is_header,
                color=("1E3A24" if is_header else None),
                size_half_pt=18,
            )
            tr.append(tcell(content, width_dxa=col_widths_dxa[ci], fill=fill))
        tr.append('</w:tr>')
        tbl.append("".join(tr))
    tbl.append('</w:tbl>')
    tbl.append(para(run("", size_half_pt=8), space_after=80))
    return "".join(tbl)


# --------------------------------------------------------------------------- #
# Column widths (sum ~9360 dxa to match the established convention)
# --------------------------------------------------------------------------- #
META_WIDTHS = [2700, 6660]
RULE_WIDTHS = [520, 3200, 5640]            # # | กฎ | รายละเอียด
FLOW_WIDTHS = [520, 2400, 6440]            # # | ขั้น | สิ่งที่เกิดขึ้น
SCOPE_WIDTHS = [1700, 3000, 4660]          # ขอบเขต | นิยาม | ที่มาข้อมูล
STATE_WIDTHS = [2600, 2400, 4360]          # สถานะ | เกิดจาก | ความหมาย / ล็อก
ROLE_SUM_WIDTHS = [4960, 820, 820, 820, 820, 1120]   # role | L1 | L2 | L3 | L4 | รวม
CLEVEL_WIDTHS = [3000, 1360, 5000]         # C-Level | ใช้ระบบ | บทบาท
PROXY_WIDTHS = [2200, 3400, 1300, 2460]    # C-Level | ผู้กรอกแทน | empcode | managerempcode (=approver1)
APV_WIDTHS = [3300, 1380, 3300, 1380]      # Submitter | Level | approver1 | Level
EMAIL_WIDTHS = [4360, 5000]                # เหตุการณ์ | แจ้งใคร
MK_WIDTHS = [620, 3700, 5040]              # # | จุด | ความหมาย (marker tables)
SIGN_WIDTHS = [1900, 3000, 2460, 2000]     # บทบาท | ชื่อ | ลายเซ็น | วันที่


# --------------------------------------------------------------------------- #
# Document body assembly
# --------------------------------------------------------------------------- #
def build_body(meta, rids):
    parts = []

    # ---- Title block -----------------------------------------------------
    parts.append(para(
        run("Chememan — ระบบบริหารงบประมาณ (Budget Management Web)",
            size_half_pt=18, color="6B7280"),
        space_after=40,
    ))
    parts.append(para(
        run("เอกสารข้อกำหนดเพื่อขออนุมัติ (User Sign-off Specification)",
            size_half_pt=40, bold=True, color="2F6B3F"),
        space_after=40,
    ))
    parts.append(para(
        run("โมดูล 10 — สิทธิ์การเข้าถึงเว็บ & การส่ง-อนุมัติข้อมูลงบประมาณ "
            "(Web Access, Submit & Approve)",
            size_half_pt=24, bold=True, color="1E3A24"),
        space_after=160,
    ))

    meta_rows = [
        ["รายการ", "รายละเอียด"],
        ["เวอร์ชัน", "v0.3 (ฉบับร่าง — อนุมัติบนหน้าหลัก · ADR-0006/0008/0012/0013/0014/0015)"],
        ["วันที่", "14 มิถุนายน 2569 (2026-06-14)"],
        ["ผู้จัดทำ", "ทีม Data Analytics"],
        ["สถานะ", "รออนุมัติจากผู้ใช้"],
    ]
    parts.append(table(meta_rows, META_WIDTHS))

    parts.append(para(
        run("เปลี่ยนแปลงสำคัญจากร่างเดิม (v0.2 → v0.3): ไม่มี \"กล่องงานผู้อนุมัติ\" (approver inbox) "
            "แยกหน้าอีกต่อไป — ผู้อนุมัติ \"ตรวจและอนุมัติบนหน้าหลักหน้าเดียวกัน\" ผ่านตัวเลือกฝ่าย "
            "(ฝ่าย-picker) + แถบปุ่มด้านล่าง · ต้นแบบอ้างอิงเปลี่ยนเป็น 0002.1budget-export.html "
            "(แทน 0013/0012/0011 ที่ยกเลิกแล้ว)",
            size_half_pt=20, italic=True, color="8C6423"),
        space_before=40, space_after=120,
    ))

    # ---- Context ---------------------------------------------------------
    parts.append(heading("บริบทและขอบเขต (Context)"))
    parts.append(body_para(
        "เอกสารนี้อธิบาย “ระบบเดียวที่ต่อเนื่องกัน” ตั้งแต่ผู้ใช้เข้าเว็บ จนถึงการส่งและอนุมัติงบ "
        "เป็น 4 ขั้นที่ไหลต่อกัน: (1) เข้าเว็บ / ล็อกอิน → (2) มุมมองที่เห็นได้ (See view) → "
        "(3) มุมมองที่กรอกได้ (Fill view) → (4) การส่งและการอนุมัติ (Submit & Approve — บนหน้าหลัก). "
        "หลักสำคัญคือ “เห็น (See) ไม่เท่ากับ กรอกได้ (Fill)” และ “หน่วยอนุมัติคือฝ่าย (Department) ต่อปีงบ "
        "ไม่ใช่ Cost Center รายตัว” ทั้งหมดยึดข้อมูลจริงจากไฟล์ master ของบริษัท "
        "(การจับคู่ orgcode ↔ cost center = ไฟล์ 09, การจับคู่ ฝ่าย ↔ cost center = ไฟล์ 02, "
        "ตารางพนักงาน mas_employee_data, และตารางผู้กระทำการ docs/12budget_actors_full.csv)."
    ))
    parts.append(para(
        run("ภาพรวมการไหลของระบบ (one connected flow):",
            size_half_pt=21, bold=True, color="1E3A24"),
        space_before=40, space_after=40,
    ))
    parts.append(para(
        run("เข้าเว็บ/ล็อกอิน  →  See (เห็นอะไรบ้าง)  →  Fill (กรอกอะไรได้)  →  "
            "ส่ง + อนุมัติ บนหน้าหลัก (หน่วย = ฝ่าย)",
            size_half_pt=23, bold=True, color="1E3A24"),
        space_before=20, space_after=80, shading="F3F7F3",
    ))

    # ---- Section 1: Web access / login -----------------------------------
    parts.append(heading("ส่วนที่ 1 — การเข้าเว็บ & ล็อกอิน (Web Access / Login)"))
    parts.append(body_para(
        "ทุกพนักงาน (~275 คน) ล็อกอินผ่าน Azure Container Apps แบบ Built-in Auth (EasyAuth) "
        "ด้วยบัญชี Azure Entra ID ของบริษัท — “ผ่านการยืนยันตัวตน” ไม่ได้แปลว่า “เห็นทุกอย่าง” "
        "สิทธิ์การเห็น/กรอก/อนุมัติ ถูกกำหนดอีกชั้นหนึ่งหลังจากล็อกอิน (RLS layer).",
        size_half_pt=21,
    ))
    flow_rows = [
        ["#", "ขั้นตอน", "สิ่งที่เกิดขึ้น"],
        ["1", "ยืนยันตัวตน (Authentication)",
         "EasyAuth + Entra ID — พนักงานบริษัททุกคนที่ล็อกอินผ่าน “เข้าได้” "
         "ไม่ถูกกั้นด้วย ADMIN_EMAILS · ระบบอ่าน email จาก header ที่ EasyAuth ส่งมา"],
        ["2", "เช็ค Admin ก่อน (ลำดับสูงสุด)",
         "ถ้าอีเมล ∈ ADMIN_EMAILS (4 คน) → เป็น Admin เห็นทุก CC ทันที · "
         "“ไม่ต้องมีแถวใน mas และไม่โดน step 4 กั้น” — รองรับ admin ที่เป็นทีมภายนอก/outsource "
         "(เช่น jakkaritw — Data Analytics) ที่ไม่มีข้อมูลใน HR"],
        ["3", "เทียบอีเมลกับตารางพนักงาน (เฉพาะ non-admin)",
         "นำ email เทียบ mas_employee_data.email แบบ “ไม่สนตัวพิมพ์ใหญ่/เล็ก” (case-insensitive) · "
         "เทียบคอลัมน์อีเมลบริษัท (email) ไม่ใช่อีเมลส่วนตัว (pemail) · "
         "พบ → ผู้ใช้ทั่วไป จำกัด RLS ตาม CC ของตัวเอง"],
        ["4", "ไม่ใช่ admin และไม่พบใน mas → กั้น",
         "ล็อกอินได้แต่ไม่ใช่ admin และไม่มีแถวใน mas_employee_data (L5 / Gritsman / เวียดนาม ถูกตัดตั้งแต่ sync, "
         "พนักงานใหม่ที่ยังไม่ sync, service account) → “ถูกกั้น” พร้อมข้อความเป็นมิตร "
         "(“ไม่พบหน่วยงานของคุณในระบบ ติดต่อ budget dept”) · ไม่แสดงข้อมูลใด ๆ"],
    ]
    parts.append(table(flow_rows, FLOW_WIDTHS))
    parts.append(para(
        run("ผู้ดูแลระบบงบประมาณ (Admin) — 4 คน (ADMIN_EMAILS):",
            size_half_pt=21, bold=True, color="1E3A24"),
        space_before=80, space_after=60,
    ))
    parts.append(bullet("นิภาพร ทองกิ่ง (Budget Staff) — nipapornt@chememan.com"))
    parts.append(bullet("วราพร ติรสิทธิ์ (Budget Manager) — warapornt@chememan.com"))
    parts.append(bullet("ปิยะดา ดวงพลจันทร์ (AVP Budgeting) — piyadad@chememan.com"))
    parts.append(bullet("ทีม Data Analytics — jakkaritw@chememan.com (full admin · option A)"))
    parts.append(para(
        run("Admin — สิทธิ์กรอก/ส่ง (2 โหมด · ADR-0012):",
            size_half_pt=21, bold=True, color="1E3A24"),
        space_before=80, space_after=60,
    ))
    parts.append(bullet("เห็นทุก CC (oversight) · แก้ Pending ได้ทุก CC ทุกสถานะ (รวม Pending/APPROVED · แก้ฉุกเฉิน/แก้แทน)"))
    parts.append(bullet("โหมดปกติ (ช่วงเปิดรับ): submit ได้เฉพาะ CC ที่ผูก orgcode ตัวเอง "
                        "+ “ฝ่ายไม่มีผู้กรอก” (orphan ฝ่าย) ที่ admin กรอกแทน — ไม่ส่งแทนฝ่ายปกติอื่น"))
    parts.append(bullet("ฝ่ายไม่มีผู้กรอก (orphan) = ฝ่ายที่มี CC แต่ไม่มีใครใน user_fill_dept (8 ฝ่าย/10 CC: "
                        "CFO, COO, Company Secretary, General, KK/PBB Factory-node, Security KK/TK) "
                        "→ Admin กรอก+ส่งแทน → APPROVED ตรงๆ (ไม่ผ่าน chain) · budget dept ทยอย assign ผู้กรอกแทนจริงภายหลัง"))
    parts.append(bullet("โหมด override (หลังปิดรับ): override ล็อกเพื่อแก้ + “กดส่งแทนได้ทุกฝ่าย” "
                        "(หลังปิด user ล็อกหมด · admin = operator คนเดียว มิฉะนั้นงบค้าง DRAFT) → "
                        "“APPROVED ตรงๆ ไม่ผ่าน chain” · ทุก override log ADMIN_OVERRIDE"))
    parts.append(para(
        run("🛡️ โหมด Admin toggle (ADR-0014) — สำหรับ admin ที่มี 2 บทบาท:",
            size_half_pt=21, bold=True, color="1E3A24"),
        space_before=80, space_after=40,
    ))
    parts.append(body_para(
        "นิภาพร / วราพร / ปิยะดา เป็นทั้ง “ผู้อนุมัติ (หรือผู้กรอกงบตัวเอง)” และ “admin” พร้อมกัน — "
        "อำนาจ admin (เห็นทุก CC, แก้ทุก CC, override-submit) จึงถูกซ่อนไว้หลังสวิตช์ “🛡️ โหมด Admin” "
        "เพื่อกันสับสนบทบาท: ปิดสวิตช์ = ทำงานในบทบาทปกติ (กรอกงบ/อนุมัติ) · เปิดสวิตช์ = สวมหมวก admin. "
        "jakkaritw เป็น full admin (ไม่มีบทบาทอื่น) จึงเปิดอยู่เสมอ ไม่มีสวิตช์.",
        size_half_pt=20,
    ))
    parts.append(image_para(rids["admin"], *meta["admin"][1], 115, "wa_admin_toggle", width_in=6.3))
    parts.append(table([
        ["#", "จุด", "ความหมาย"],
        ["①", "สวิตช์ “🛡️ โหมด Admin” บนแถบ nav",
         "แสดงเฉพาะ admin ที่มีบทบาทอื่นด้วย (นิภาพร/วราพร/ปิยะดา) · เปิด = สวมหมวก admin (เห็น/แก้ทุก CC, override-submit) · ปิด = บทบาทปกติ"],
    ], MK_WIDTHS))

    # ---- Section 2: See view --------------------------------------------
    parts.append(heading("ส่วนที่ 2 — มุมมองที่เห็นได้ (See view / Visibility)"))
    parts.append(body_para(
        "“See-scope” = ชุด Cost Center ที่ผู้ใช้คนนี้มองเห็นได้บนหน้าจอ (เพื่อดู/เปรียบเทียบ/อนุมัติ) "
        "คำนวณจากการ “รวม (union)” 2 ทาง บวก role overlay ของ Admin:",
        size_half_pt=21,
    ))
    parts.append(para(
        run("SEE = (orgcode → ไฟล์ 09 → CC)  ∪  (ฝ่าย → ไฟล์ 02 → CC)  ∪  admin-overlay",
            size_half_pt=22, bold=True, color="1E3A24"),
        space_before=20, space_after=80, shading="F3F7F3",
    ))
    see_rows = [
        ["ส่วนประกอบ", "นิยาม", "ที่มาข้อมูล"],
        ["orgcode → CC",
         "CC ที่ orgcode ของผู้ใช้จับคู่ได้ (กว้าง · many-to-many · ครอบ CC ของลูกน้องด้วย)",
         "mas_employee_data.orgcode → ไฟล์ 09 (orgcode_costcenter_map) · "
         "ใช้ทั้ง Primary และ Acting posstatus (Acting ก็เห็น CC ของ orgcode นั้น)"],
        ["ฝ่าย → CC",
         "CC ทั้งหมดในฝ่าย (department) ของผู้ใช้ = Fill-scope ของเขาเอง",
         "ฝ่าย → ไฟล์ 02 (cost-center master) → CC"],
        ["admin-overlay",
         "Admin เห็นทุก CC ทั้งบริษัท (oversight) — เป็น role overlay นอกไฟล์ 09",
         "ฝ่าย Budget (เช่น orgcode 1142101) + รายชื่อใน ADMIN_EMAILS"],
    ]
    parts.append(table(see_rows, SCOPE_WIDTHS))
    parts.append(body_para(
        "ทำไมต้อง “รวม (union)”: ไฟล์ 09 (orgcode↔CC) กับ ไฟล์ 02 (ฝ่าย↔CC) เป็นการ map คนละแบบ "
        "ถ้าไม่รวมกัน จะมีผู้ใช้ ~29 คนที่ “กรอกได้แต่มองไม่เห็น” และ 1 คนที่ orgcode ไม่อยู่ในไฟล์ 09 "
        "จะ “มองไม่เห็นอะไรเลย ทั้งที่กรอกได้” · เมื่อรวมกันแล้ว รับประกันกฎสำคัญ FILL ⊆ SEE "
        "(สิ่งที่กรอกได้ ต้องมองเห็นได้เสมอ — พิสูจน์แล้ว 253/253 คน). "
        "การมองเห็น CC ร่วมกันหลายคนเป็นเรื่องปกติ (CC หนึ่งถูกเห็นจากหลาย orgcode/หลายหัวหน้า) "
        "— ไม่ทำให้ยอดงบชนกัน เพราะการกรอกถูกจำกัดด้วยฝ่าย และการอนุมัติเป็นหน่วยฝ่าย (ดูส่วนที่ 4).",
        size_half_pt=20,
    ))

    # ---- Section 3: Fill view -------------------------------------------
    parts.append(heading("ส่วนที่ 3 — มุมมองที่กรอกได้ (Fill view / ใครแก้-ส่งได้)"))
    parts.append(body_para(
        "“Fill-scope” = ชุด CC ที่ผู้ใช้แก้ไข (กรอกงบ Pending · รออนุมัติ) และส่งเข้าระบบอนุมัติได้ "
        "ถูกกั้นด้วย 2 เงื่อนไขพร้อมกัน — บทบาท (role) และ ฝ่าย (department):",
        size_half_pt=21,
    ))
    parts.append(para(
        run("เงื่อนไขที่ 1 — บทบาท (role gate):",
            size_half_pt=21, bold=True, color="1E3A24"),
        space_before=40, space_after=40,
    ))
    parts.append(bullet("เฉพาะ “ผู้กรอก (submitter set) = 254 คน” เท่านั้นที่ได้ฟอร์มที่แก้ได้ "
                        "= L3 + L4 + 3 L2 พิเศษ (ปรัชญา/ปิยะนุช/ธนกฤษณ์) + นิภาพร + วราพร "
                        "(อ้างอิง docs/12budget_actors_full.csv · role มีคำว่า \"submitter\")"))
    parts.append(bullet("ผู้ที่เป็น “approver1_only” (21 คน = L1×3 + L2×18) “เห็นได้เพื่ออนุมัติ "
                        "แต่ฟอร์มกรอกถูกล็อก” — ไม่เคยพิมพ์งบเอง"))
    parts.append(bullet("L5 (Operator/Driver/Maid) ไม่ใช้ระบบเลย"))
    parts.append(para(
        run("เงื่อนไขที่ 2 — ขอบเขตตามฝ่าย (department scope):",
            size_half_pt=21, bold=True, color="1E3A24"),
        space_before=40, space_after=40,
    ))
    parts.append(para(
        run("Fill-scope = CC ทุกตัวในฝ่ายของผู้ใช้  ←  ฝ่าย → ไฟล์ 02 → CC",
            size_half_pt=22, bold=True, color="1E3A24"),
        space_before=20, space_after=60, shading="F3F7F3",
    ))
    parts.append(bullet("ฝ่ายของผู้ใช้มาจากตารางที่คัดเลือกแล้ว cfg_master.user_fill_dept "
                        "(empcode → ฝ่าย) · จากนั้น ฝ่าย → ไฟล์ 02 → CC ในฝ่ายนั้น"))
    parts.append(bullet("ไฟล์คัดเลือกตั้งต้น: "
                        "docs/15.user_fill_dept_candidates.csv — 1 คนกรอกได้ 1 หรือหลายฝ่าย"))
    parts.append(bullet("การกระจายผู้กรอก (253 คนในไฟล์ 15) — กรอกกี่ฝ่าย: "
                        "1 ฝ่าย 75% (191 คน · เคสปกติ กรอกฝ่ายตัวเอง) · "
                        "2-3 ฝ่าย 15% (39 คน) · 4 ฝ่ายขึ้นไป 9% (23 คน) · รวมหลายฝ่าย 25% (62 คน)"))
    parts.append(bullet("กรอกหลายฝ่าย = ถูกต้องตามงานจริง (ไม่ใช่ error): "
                        "function ข้ามโรงงาน (เช่น Quality Management ครบทุกโรงงาน) · "
                        "หัวหน้าคุมหลาย sub-ฝ่าย (เช่น Production) · "
                        "ผู้กรอกแทน (proxy) = กรอกฝ่ายตัวเอง + ฝ่ายของผู้บริหารที่กรอกแทน · "
                        "ตาราง user_fill_dept คีย์ (empcode, ฝ่าย) รองรับหลายแถวต่อคน"))
    parts.append(bullet("ข้อควรระวัง: poscode ในไฟล์ CSV snapshot เพี้ยนเป็น scientific notation "
                        "(เช่น 1.17E+07) — ต้องดึงข้อมูลพนักงานต้นทางจาก Fabric SQL DB ไม่ใช่จาก CSV"))
    parts.append(para(
        run("Submit แสดงตาม fill-scope ไม่ใช่ตามบทบาท (สำคัญ):",
            size_half_pt=21, bold=True, color="1E3A24"),
        space_before=40, space_after=40,
    ))
    parts.append(bullet("ปุ่ม Submit “จะโผล่เฉพาะเมื่อฝ่ายที่เลือก ∈ fill-scope ของผู้ใช้ และสถานะเป็น DRAFT/REJECTED” "
                        "เท่านั้น · ถ้าผู้ใช้เป็นผู้อนุมัติของฝ่ายนั้น จะเห็นปุ่ม “อนุมัติ/ตีกลับ” แทน (ไม่เห็น Submit)"))
    parts.append(bullet("เมื่อถึงวันปิดรับ (deadline ของปีงบนั้น · เช่น 31 ต.ค. — admin ตั้งได้ต่อปี) → "
                        "ฟอร์ม Pending “ล็อกอัตโนมัติ” กรอก/ส่งไม่ได้ ดูได้อย่างเดียว · เฉพาะ Admin override ได้ "
                        "· (การ import board_budget ไม่ถูกล็อก — คนละ lifecycle)"))
    parts.append(bullet("ฝ่ายที่ยังเป็น DRAFT (กรอกค้าง ไม่ได้กดส่ง) ณ เวลาปิด → ระบบ “auto-submit” "
                        "เข้าสายอนุมัติให้อัตโนมัติทุกฝ่าย · approver1 = หัวหน้าของ “คนแก้ล่าสุด” "
                        "(invalid/ไม่มี → นิภาพร) · log AUTO_SUBMIT · ผู้อนุมัติตรวจ/ตีกลับได้ถ้าเลขไม่ครบ "
                        "· ฝ่ายที่ไม่มีข้อมูลเลย = ไม่มีอะไรส่ง"))
    parts.append(para(
        run("กฎคงที่ (invariant): FILL ⊆ SEE — สิ่งที่กรอกได้ต้องมองเห็นได้เสมอ "
            "(พิสูจน์แล้ว 253/253 คน). “เห็น” กว้างกว่า “กรอก” เสมอ.",
            size_half_pt=20, italic=True, color="8C6423"),
        space_before=40, space_after=80,
    ))

    # ---- Section 4: Approval unit + state machine ------------------------
    parts.append(heading("ส่วนที่ 4 — หน่วยอนุมัติ = (ฝ่าย, ปีงบ) + วงจรส่ง→อนุมัติ "
                         "(Approval Unit & Lifecycle)"))
    parts.append(body_para(
        "หน่วยการอนุมัติ “ไม่ใช่ Cost Center รายตัว” แต่เป็น “ฝ่าย (Department) ต่อปีงบ” (ADR-0008) "
        "ทำได้สะอาดเพราะ CC → ฝ่าย เป็น 1:1 (210/210 CC ตรงฝ่ายเดียวพอดี) → ฝ่ายแบ่ง CC "
        "ออกเป็นกลุ่มไม่ทับกัน · 1 ฝ่ายมี CC เฉลี่ย ~1.8 ตัว (สูงสุด 21).",
        size_half_pt=21,
    ))
    parts.append(bullet("ส่ง (Submit) = ส่งงบทั้งฝ่ายเป็น “แพ็กเกจเดียว” — ทุก CC ในฝ่ายเข้าระบบอนุมัติพร้อมกัน"))
    parts.append(bullet("1 แถวสถานะ (approval_status) ต่อ (ฝ่าย, ปีงบ) — ไม่ใช่ per row หรือ per CC"))
    parts.append(bullet("ผู้กรอกที่ถือหลายฝ่าย (25% · เช่น proxy, หัวหน้าข้ามโรงงาน) → ส่ง “แยกฝ่ายละแพ็กเกจ” "
                        "= N แถวสถานะ · CC แต่ละฝ่ายไม่ทับกัน (disjoint) → อนุมัติ/ตีกลับอิสระต่อฝ่าย"))
    parts.append(para(
        run("กลไกสถานะ 6 สถานะ (state machine — ADR-0006):",
            size_half_pt=21, bold=True, color="1E3A24"),
        space_before=40, space_after=40,
    ))
    parts.append(para(
        run("DRAFT  →(Submit)→  PENDING_APPROVER1  →(อนุมัติ)→  PENDING_APPROVER2  "
            "→  PENDING_APPROVER3  →  APPROVED",
            size_half_pt=22, bold=True, color="1E3A24"),
        space_before=20, space_after=40, shading="F3F7F3",
    ))
    parts.append(para(
        run("ผู้อนุมัติด่านใดกด ตีกลับ (Reject)  →  REJECTED (กลับมาแก้ได้)  →  แก้  →  Submit ใหม่ (เริ่มที่ approver1)",
            size_half_pt=21, bold=True, color="8C6423"),
        space_before=10, space_after=60, shading="FBF6E8",
    ))
    state_rows = [
        ["สถานะ", "เกิดจาก", "ความหมาย / การล็อก"],
        ["DRAFT", "เริ่มต้น / ถูกตีกลับ (REJECTED→แก้)",
         "ผู้กรอกแก้ได้ (auto-save) · เห็นปุ่ม Submit (ถ้าอยู่ใน fill-scope)"],
        ["PENDING_APPROVER1", "ผู้กรอกกด Submit",
         "ส่งถึง managerempcode (ของคนกดส่งล่าสุด) · “ฝ่ายถูกล็อก — แก้ไม่ได้ และเรียกคืน (recall) ไม่ได้”"],
        ["PENDING_APPROVER2", "approver1 อนุมัติ",
         "ส่งถึง นิภาพร (Budget Staff) · ยังล็อก"],
        ["PENDING_APPROVER3", "นิภาพร อนุมัติ",
         "ส่งถึง วราพร (Budget Manager) · ยังล็อก"],
        ["APPROVED", "วราพร อนุมัติ (ขั้นสุดท้าย)",
         "อนุมัติสมบูรณ์ · แก้ต่อได้เฉพาะ Admin (จะ re-snapshot กลับเข้าอนุมัติใหม่) · ไหลเข้า Gold (ADR-0011/0015)"],
        ["REJECTED", "ผู้อนุมัติด่านใดกด ตีกลับ",
         "กลับมาแก้ได้ (เหมือน DRAFT) · แจ้งคนกดส่งล่าสุด · Submit ใหม่ = วิ่งครบทุกด่านจาก approver1"],
    ]
    parts.append(table(state_rows, STATE_WIDTHS))
    parts.append(bullet("ล็อกหลัง Submit (ADR-0006/0013): เมื่อผู้กรอกกด Submit → ฝ่ายเข้าสู่ PENDING_* "
                        "“แก้ไม่ได้ ส่งไม่ได้ และเรียกคืนไม่ได้” จนกว่าจะถูกตีกลับ · subform ก็ถูกล็อกเป็น view-only ด้วย"))
    parts.append(bullet("Snapshot ตอนส่ง: ระบบ “แช่แข็ง” ตัว approver1/2/3 ไว้ในแถวสถานะ — "
                        "การปรับโครงสร้าง HR ภายหลังไม่กระทบงานที่อยู่ระหว่างอนุมัติ"))
    parts.append(bullet("approver1 ไม่ถูกต้อง (ไม่มี managerempcode / ชี้ไปคนที่ inactive/ถูกตัด) → "
                        "ตกไปที่ นิภาพร (approver2) โดยตรง · ไม่บล็อกการส่ง"))
    parts.append(bullet("ตีกลับ (Reject) = Reject (ทุก CC) ด้วยเหตุผลเดียว → REJECTED → แจ้งคนกดส่งล่าสุด · "
                        "ตีกลับ “หลังปิดรับ”: ฝ่ายกลับเป็น DRAFT แต่ผู้กรอกถูกล็อก → เฉพาะ Admin override แก้+ส่งใหม่"))

    # ---- Section 5: Approve on the main page (replaces inbox) ------------
    parts.append(heading("ส่วนที่ 5 — อนุมัติบนหน้าหลัก (Approve on the Main Page)"))
    parts.append(body_para(
        "ระบบ “ไม่มีกล่องงานผู้อนุมัติ (inbox) แยกหน้าอีกต่อไป” — ผู้อนุมัติทำงานบน “หน้าหลักหน้าเดียวกัน” "
        "กับผู้กรอก โดยใช้ 2 ส่วน: (ก) ตัวเลือกฝ่าย (ฝ่าย-picker) ที่มีป้าย “รออนุมัติ” + สวิตช์ "
        "“เฉพาะที่รออนุมัติ” เพื่อโฟกัสเฉพาะฝ่ายที่ค้างที่ขั้นของตน และ (ข) แถบปุ่มด้านล่าง "
        "(Approve / Reject) ที่โผล่เมื่อฝ่ายที่เลือกอยู่ที่ขั้นของผู้อนุมัติพอดี.",
        size_half_pt=21,
    ))
    parts.append(para(
        run("ภาพประกอบ 5.1 — ผู้กรอก (Submitter) บนหน้าหลัก: เลือกฝ่าย แล้วกด Submit",
            size_half_pt=21, bold=True, color="1E3A24"),
        space_before=60, space_after=40,
    ))
    parts.append(image_para(rids["submit"], *meta["submit"][1], 111, "wa_submit_mainpage", width_in=6.3))
    parts.append(table([
        ["#", "จุด", "ความหมาย"],
        ["①", "ตัวเลือกฝ่าย (ฝ่าย-picker)",
         "ล็อกหน้าหลักไว้ที่ 1 (ฝ่าย, ปี) = หน่วยอนุมัติ (ADR-0008) · ผู้กรอกถูกตั้งให้ฝ่ายตัวเองอัตโนมัติ"],
        ["②", "ปุ่ม Submit (สีแดง)",
         "ส่งงบทั้งฝ่าย → PENDING_APPROVER1 · โผล่เฉพาะเมื่อฝ่าย ∈ fill-scope และสถานะ DRAFT/REJECTED"],
    ], MK_WIDTHS))
    parts.append(para(
        run("ภาพประกอบ 5.2 — หลังกด Submit: ฝ่ายถูกล็อก (PENDING_APPROVER1) ผู้กรอกแก้ไม่ได้",
            size_half_pt=21, bold=True, color="1E3A24"),
        space_before=60, space_after=40,
    ))
    parts.append(image_para(rids["locked"], *meta["locked"][1], 112, "wa_locked_after_submit", width_in=6.3))
    parts.append(table([
        ["#", "จุด", "ความหมาย"],
        ["①", "ฝ่ายที่ส่งแล้ว (ฝ่าย-picker)", "ยังเป็นหน่วยเดียวกัน — สถานะเปลี่ยนเป็น PENDING_APPROVER1"],
        ["②", "แถบสถานะการกระทำ (action note)", "“ส่งแล้ว · PENDING_APPROVER1 · แก้ไม่ได้ (รออนุมัติ)” — ไม่มีปุ่ม Submit/Recall อีก"],
    ], MK_WIDTHS))
    parts.append(para(
        run("ภาพประกอบ 5.3 — ผู้อนุมัติ (approver1) บนหน้าหลัก: ป้าย “รออนุมัติ” + ปุ่มอนุมัติ/ตีกลับ",
            size_half_pt=21, bold=True, color="1E3A24"),
        space_before=60, space_after=40,
    ))
    parts.append(image_para(rids["approve"], *meta["approve"][1], 113, "wa_approve_mainpage", width_in=6.3))
    parts.append(table([
        ["#", "จุด", "ความหมาย"],
        ["①", "ป้าย “รออนุมัติ” บนฝ่าย-picker", "ฝ่ายนี้ค้างที่ขั้นของผู้อนุมัติพอดี (status = ขั้นของฉัน)"],
        ["②", "ปุ่ม “Approve” (สีเขียว)", "อนุมัติทุก CC ในฝ่าย → เลื่อนไปขั้นถัดไป (หรือ APPROVED ถ้าเป็นด่านสุดท้าย)"],
        ["③", "ปุ่ม “Reject” (สีแดง)", "ตีกลับทุก CC ด้วยเหตุผลเดียว → REJECTED · แจ้งคนกดส่งล่าสุด"],
    ], MK_WIDTHS))
    parts.append(para(
        run("ภาพประกอบ 5.4 — ฝ่าย-picker (เปิด): ป้ายรออนุมัติต่อฝ่าย + สวิตช์ “เฉพาะที่รออนุมัติ”",
            size_half_pt=21, bold=True, color="1E3A24"),
        space_before=60, space_after=40,
    ))
    parts.append(image_para(rids["picker"], *meta["picker"][1], 114, "wa_fai_picker", width_in=5.4))
    parts.append(table([
        ["#", "จุด", "ความหมาย"],
        ["①", "สวิตช์ “เฉพาะที่รออนุมัติ”", "กรองรายการให้เหลือเฉพาะฝ่ายที่ค้างที่ขั้นของผู้อนุมัติ (พร้อมจำนวน) — เปิดเป็นค่าเริ่มต้น"],
        ["②", "รายการฝ่าย (จัดกลุ่มตามสายงาน)", "แต่ละฝ่ายมีจำนวน CC + งบที่ขอ + ป้ายรออนุมัติ/อนุมัติแล้ว · คลิกเพื่อล็อกหน้าหลักไปฝ่ายนั้น"],
    ], MK_WIDTHS))
    parts.append(para(
        run("หมายเหตุการใช้งานผู้อนุมัติ (เหมือนกันทั้ง 3 ขั้น · ต่างที่ filter):",
            size_half_pt=21, bold=True, color="1E3A24"),
        space_before=60, space_after=40,
    ))
    parts.append(bullet("approver1 (หัวหน้าตรง) เห็นเฉพาะฝ่ายที่ตัวเองเป็นด่าน (PENDING_APPROVER1 · มัก 1-2 ฝ่าย) · "
                        "นิภาพร (approver2) / วราพร (approver3) เห็นทุกฝ่ายที่ค้างที่ขั้นของตน"))
    parts.append(bullet("เปรียบเทียบบนหน้าหลัก: ทุกแถวมี Pending (ปีหน้า) · Actual (ปีนี้ จาก SAP gold) · "
                        "Board (งบบอร์ดปีนี้) พร้อมบริบทปีในวงเล็บ — กันสับสนว่ากำลังดูปีไหน"))
    parts.append(bullet("ตีกลับ = ทั้งฝ่าย (ทุก CC) ด้วยเหตุผลเดียว → แจ้งคนกดส่งล่าสุดของฝ่ายนั้น · "
                        "เจาะดูรายละเอียด (drill-down) → CC ในฝ่าย → GL ในแต่ละ CC"))
    parts.append(para(
        run("อ้างอิงต้นแบบ (mockup): design/mockups/0002claude design/0002.1budget-export.html "
            "— ต้นแบบ wired ตัวจริง (ผู้กรอก/ผู้อนุมัติ/admin บนหน้าเดียว) · "
            "เลิกใช้ 0013-approver-inbox-demo / 0012-main-table-demo / 0011-subform-demo แล้ว.",
            size_half_pt=19, italic=True, color="6B7280"),
        space_before=40, space_after=80,
    ))

    # ---- Section 6: Role summary table ----------------------------------
    parts.append(heading("ส่วนที่ 6 — สรุปบทบาทผู้ใช้ทั้งหมด (User Roles — 275 คน)"))
    role_sum_rows = [
        ["บทบาท (role)", "L1", "L2", "L3", "L4", "รวม"],
        ["submitter — กรอกอย่างเดียว", "", "", "8", "170", "178"],
        ["submitter+approver1 — กรอก + approve ลูกน้อง", "", "3", "56", "15", "74"],
        ["approver1_only — approve เท่านั้น ไม่กรอก", "3", "18", "", "", "21"],
        ["submitter+approver2 — นิภาพร (loop จบที่ approver1)", "", "", "", "1", "1"],
        ["submitter+approver3 — วราพร (loop จบที่ approver1)", "", "", "1", "", "1"],
        ["รวม", "3", "21", "65", "186", "275"],
    ]
    parts.append(table(role_sum_rows, ROLE_SUM_WIDTHS))
    parts.append(body_para(
        "หมายเหตุ: ผู้กรอก (submitter) = 254 คน (178 + 74 + 1 + 1) · ผู้อนุมัติอย่างเดียว "
        "(approver1_only) = 21 คน · รวมทั้งสิ้น 275 คน (canonical = docs/12budget_actors_full.csv)",
        size_half_pt=19,
    ))

    # ---- Section 7: Approval chain --------------------------------------
    parts.append(heading("ส่วนที่ 7 — สายการอนุมัติ (Approval Chain)"))
    parts.append(para(
        run("ผู้กรอก (L3/L4)  →  managerempcode (ของคนกดส่งล่าสุด = approver1)  →  "
            "นิภาพร ทองกิ่ง (approver2)  →  วราพร ติรสิทธิ์ (approver3)  →  APPROVED",
            size_half_pt=22, bold=True, color="1E3A24"),
        space_before=40, space_after=100, shading="F3F7F3",
    ))
    parts.append(bullet("approver1 = managerempcode (หัวหน้าตรงของผู้กดส่งล่าสุด) — "
                        "ไม่ derive จาก level ใช้ตรงจากข้อมูลพนักงาน"))
    parts.append(bullet("approver2 = นิภาพร ทองกิ่ง (Budget Staff)"))
    parts.append(bullet("approver3 = วราพร ติรสิทธิ์ (Budget Manager — ผู้อนุมัติสุดท้าย)"))
    parts.append(para(
        run("กรณีพิเศษของสายอนุมัติ:",
            size_half_pt=21, bold=True, color="1E3A24"),
        space_before=40, space_after=40,
    ))
    parts.append(bullet("ผู้กรอก = นิภาพร เอง → Submit → วราพร → END (ข้ามตัวเองในฐานะ approver2)"))
    parts.append(bullet("ผู้กรอก = วราพร เอง → Submit → ปิยะดา ดวงพลจันทร์ → END (ปิยะดาเป็นผู้อนุมัติสุดท้ายเหนือวราพร)"))
    parts.append(bullet("approver1 ไม่ถูกต้อง (ไม่มี/ชี้คน inactive) → ตกไปที่ นิภาพร (approver2) โดยตรง · ไม่บล็อกการส่ง"))

    # ---- Section 8: C-Level system access -------------------------------
    parts.append(heading("ส่วนที่ 8 — ผู้บริหาร C-Level ที่ใช้ระบบ"))
    parts.append(body_para(
        "C-Level เข้าระบบเฉพาะคนที่มีลูกน้อง (submitter) report ตรงเท่านั้น "
        "เพื่อทำหน้าที่อนุมัติ (approver1) — คนที่ไม่มีลูกน้อง report ตรง ไม่ต้องเข้าระบบ",
        size_half_pt=21,
    ))
    clevel_rows = [
        ["C-Level", "ใช้ระบบ", "บทบาท"],
        ["อภิชัย สมบูรณ์ปกรณ์ (CTO)", "✅ ใช้", "อนุมัติ ฐานิยา"],
        ["เลิศศักดิ์ บุญส่งทรัพย์ (CSO)", "✅ ใช้", "อนุมัติ ปรัชญา + ปิยะนุช"],
        ["ปรีด์ สุวิมลธีระบุตร (CCO)", "✅ ใช้", "อนุมัติ ธนกฤษณ์ + Yuan-Ming"],
        ["อดิศักดิ์ เหล่าจันทร์ (CEO)", "❌ ไม่ใช้", "ไม่มี submitter report ตรง"],
        ["จันทรจุฑา จันทรทัต (CEO-Int)", "❌ ไม่ใช้", "ไม่มีใคร report ตรง"],
    ]
    parts.append(table(clevel_rows, CLEVEL_WIDTHS))

    # ---- Section 9: Proxy fillers ---------------------------------------
    parts.append(heading("ส่วนที่ 9 — ผู้กรอกแทนหัวหน้า (Proxy Fillers)"))
    parts.append(body_para(
        "ผู้บริหารที่ไม่กรอกงบเอง มอบหมายให้ลูกน้องกรอกแทน — งบยังผูกกับหน่วยงาน "
        "ของผู้บริหารตามไฟล์ master เสมอ ไม่เปลี่ยนการระบุสายงาน",
        size_half_pt=21,
    ))
    proxy_rows = [
        ["C-Level", "ผู้กรอกแทน", "empcode", "managerempcode ผู้กรอก (= approver1)"],
        ["อดิศักดิ์ + จันทรจุฑา (CEO)", "แพรวทิพย์ ลิ้มจิระวัฒนา", "101300", "100567 — สิเนห์นิษฐ์ ฆฤตเกียรติ"],
        ["อภิชัย (CTO)", "ฐานิยา วิจิตรพนมศิลป์", "101905", "101875 — อภิชัย สมบูรณ์ปกรณ์ (self-review)"],
        ["เลิศศักดิ์ (CSO)", "ปรัชญา เทพวรชัย + ปิยะนุช ปิยะนีรนาท", "100164 + 101801", "101632 — เลิศศักดิ์ บุญส่งทรัพย์ (ทั้งคู่)"],
        ["ปรีด์ (CCO)", "ธนกฤษณ์ ศรีอนุชาต", "101429", "101754 — ปรีด์ สุวิมลธีระบุตร"],
    ]
    parts.append(table(proxy_rows, PROXY_WIDTHS))
    parts.append(para(
        run("กรณีพิเศษเพิ่มเติม (ระดับต่ำกว่า C-Level):",
            size_half_pt=21, bold=True, color="1E3A24"),
        space_before=80, space_after=60,
    ))
    parts.append(bullet("ฝ่าย Budget — นิภาพร / วราพร กรอกแทน ปิยะดา ดวงพลจันทร์ "
                        "(AVP, หัวหน้าฝ่าย) สำหรับ Cost Center 10AC020000"))
    parts.append(bullet("เอเวอร์ จาซินธ์ โบโจส กรอกแทน Chief People Officer "
                        "(เลิศศักดิ์ รักษาการ) สำหรับ Cost Center สำนัก CPO"))

    # ---- Section 10: Special submitter -> approver1 ---------------------
    parts.append(heading("ส่วนที่ 10 — สายอนุมัติพิเศษ (Submitter → approver1 = C-Level)"))
    parts.append(body_para(
        "ผู้กรอกบางคน (L2/L3) มีหัวหน้าตรงเป็น C-Level (L1) — สายอนุมัติแรกจึงข้ามขึ้น "
        "ถึง C-Level โดยตรง",
        size_half_pt=21,
    ))
    apv_rows = [
        ["ผู้กรอก (Submitter)", "Level", "ผู้อนุมัติ (approver1)", "Level"],
        ["Yuan-Ming Huang", "L3", "ปรีด์ สุวิมลธีระบุตร", "L1"],
        ["ฐานิยา วิจิตรพนมศิลป์", "L3", "อภิชัย สมบูรณ์ปกรณ์", "L1"],
        ["ปรัชญา เทพวรชัย", "L2", "เลิศศักดิ์ บุญส่งทรัพย์", "L1"],
        ["ปิยะนุช ปิยะนีรนาท", "L2", "เลิศศักดิ์ บุญส่งทรัพย์", "L1"],
        ["ธนกฤษณ์ ศรีอนุชาต", "L2", "ปรีด์ สุวิมลธีระบุตร", "L1"],
    ]
    parts.append(table(apv_rows, APV_WIDTHS))

    # ---- Section 11: Email notification triggers ------------------------
    parts.append(heading("ส่วนที่ 11 — การแจ้งเตือนทางอีเมล (Email Notifications)"))
    parts.append(body_para(
        "ทุกขั้นของ workflow ส่งอีเมลแจ้งเตือนผ่าน Microsoft Graph sendMail (background task) "
        "— ส่งจาก cmanpowerbi@chememan.com · การอนุมัติ/ส่งคือ source of truth จะไม่ถูก rollback "
        "หากอีเมลล้มเหลว (retry ในเบื้องหลัง · การอนุมัติบนหน้าหลักเป็นช่องทางหลัก)",
        size_half_pt=20,
    ))
    email_rows = [
        ["เหตุการณ์", "แจ้งใคร"],
        ["ผู้กรอกกดส่ง (Submit)", "approver1 (managerempcode ของคนกดส่งล่าสุด)"],
        ["approver1 อนุมัติ", "นิภาพร (approver2)"],
        ["นิภาพร อนุมัติ", "วราพร (approver3)"],
        ["วราพร อนุมัติ (ขั้นสุดท้าย)", "ผู้กรอก (ยืนยันอนุมัติแล้ว)"],
        ["ตีกลับ (ทุกขั้น)", "ผู้กดส่งล่าสุด + ผู้อนุมัติก่อนหน้า (ตามสายอนุมัติ)"],
    ]
    parts.append(table(email_rows, EMAIL_WIDTHS))

    # ---- Closing note ----------------------------------------------------
    parts.append(heading("หมายเหตุท้ายเอกสาร"))
    parts.append(para(
        run("เอกสารฉบับร่าง (Draft · v0.3) — ภาพประกอบ render จากต้นแบบ "
            "0002.1budget-export.html ตัวเลข/ชื่อเป็นข้อมูลตัวอย่าง · "
            "วงกลมมีหมายเลขคือจุดอ้างอิงในตารางคำอธิบายของแต่ละหัวข้อ · "
            "การเปลี่ยนหลัก v0.2→v0.3 = ยกเลิกกล่องงานผู้อนุมัติแยกหน้า → อนุมัติบนหน้าหลัก.",
            size_half_pt=20, italic=True, color="8C6423"),
        space_before=40, space_after=120,
    ))

    # ---- Sign-off --------------------------------------------------------
    parts.append(heading("ช่องลงนามอนุมัติ (Sign-off)"))
    sign_rows = [
        ["บทบาท", "ชื่อ-นามสกุล", "ลายเซ็น", "วันที่"],
        ["ผู้จัดทำ", "", "", ""],
        ["ผู้ตรวจสอบ", "", "", ""],
        ["ผู้อนุมัติ", "", "", ""],
    ]
    parts.append(_sign_table(sign_rows, SIGN_WIDTHS))

    return "".join(parts)


# --------------------------------------------------------------------------- #
# Static OOXML parts (now with image content-type + image relationships)
# --------------------------------------------------------------------------- #
def content_types_xml():
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Default Extension="png" ContentType="image/png"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '</Types>'
    )


def root_rels_xml():
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        '</Relationships>'
    )


def document_rels_xml(image_rels):
    r = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
         '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    for rid, fn in image_rels:
        r.append(f'<Relationship Id="{rid}" '
                 f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                 f'Target="media/{fn}"/>')
    r.append('</Relationships>')
    return "".join(r)


def document_xml(body_xml):
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document '
        'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<w:body>'
        f'{body_xml}'
        '<w:sectPr>'
        '<w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" '
        'w:header="708" w:footer="708" w:gutter="0"/>'
        '</w:sectPr>'
        '</w:body></w:document>'
    )


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    print("[1/4] Capturing main-page approve/submit screenshots (Playwright) ...")
    shots = capture()

    print("[2/4] Annotating with gold/coloured markers (Pillow) ...")
    meta = {}
    order = ["submit", "locked", "approve", "picker", "admin"]
    for k in order:
        src, markers = shots[k]
        meta[k] = annotate(src, os.path.basename(src), markers)
        print(f"      {k}: {meta[k][0]}  {meta[k][1]}  markers={len(markers)}")

    # ---- PROOF (computed only — no PNG viewing) ---------------------------- #
    def _inside(m):
        return (m["ex"] <= m["tx"] <= m["ex"] + m["ew"]
                and m["ey"] <= m["ty"] <= m["ey"] + m["eh"])
    print("[PROOF] per-image marker counts:", {k: len(shots[k][1]) for k in order})
    sm = shots["submit"][1]
    print(f"[PROOF] SUBMIT ② (submitBtn): inside={_inside(sm[1])} fill={sm[1]['fill']} (RED={sm[1]['fill']==RED})")
    am = shots["approve"][1]
    print(f"[PROOF] APPROVE ② (approveBtn): inside={_inside(am[1])} fill={am[1]['fill']} (GREEN={am[1]['fill']==GREEN})")
    print(f"[PROOF] APPROVE ③ (rejectBtn): inside={_inside(am[2])} fill={am[2]['fill']} (RED={am[2]['fill']==RED})")
    for k in order:
        miss = [m["label"] for m in shots[k][1] if not _inside(m)]
        print(f"[PROOF] {k}: {len(shots[k][1])} markers · all-inside={not miss}" +
              (f" · MISSED={miss}" if miss else ""))
    # ----------------------------------------------------------------------- #

    media = {k: f"image{i+1}.png" for i, k in enumerate(order)}
    rids = {k: f"rId{i+10}" for i, k in enumerate(order)}
    image_rels = [(rids[k], media[k]) for k in order]

    print("[3/4] Building OOXML document.xml ...")
    body = build_body(meta, rids)
    doc_xml = document_xml(body)

    print("[4/4] Writing .docx zip ...")
    if os.path.exists(DOCX_PATH):
        os.remove(DOCX_PATH)
    with zipfile.ZipFile(DOCX_PATH, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types_xml())
        z.writestr("_rels/.rels", root_rels_xml())
        z.writestr("word/document.xml", doc_xml.encode("utf-8"))
        z.writestr("word/_rels/document.xml.rels", document_rels_xml(image_rels))
        for k in order:
            with open(meta[k][0], "rb") as f:
                z.writestr(f"word/media/{media[k]}", f.read())

    print(f"DONE: {DOCX_PATH}  ({os.path.getsize(DOCX_PATH)} bytes)")


if __name__ == "__main__":
    main()
