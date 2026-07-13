# -*- coding: utf-8 -*-
"""
Generator — Spec A (V2.0) · หน้าหลักและสิทธิ์การเข้าถึง (Main Budget Web App).

User Sign-off Specification (.docx). This REVISES Spec A V1.0 into a 3-PART
structure AND reconciles the V1.0 text against the ADRs changed the week of
2026-07-11/12:
  - RLS (See/Fill) now derives from the Cost Center↔Filler map `cc dept.xlsx`
    (ADR-0019) — the old orgcode-chain / department-union model is gone.
  - Approved budget arrives as a yearly Excel file on SharePoint
    (`approved_budget_<year>.xlsx`, ADR-0021) — the in-app CSV import/export
    buttons are removed; Approved is read-only on the web.
  - Approval unit = (ฝ่าย, ปี) (ADR-0008); approve inline on the main page
    (ADR-0016); editing never changes status (ADR-0013); admin-mode is an opt-in
    toggle (ADR-0014); admin submit post-deadline → APPROVED directly (ADR-0012);
    Master FX is read-only here, recompute-on-read (ADR-0015).

Machinery: OOXML cover / header / footer / sign-off / company-logo forked from
build_spec_c_master_tables.py (blue laddawan family theme); Pillow gold-marker
annotation + PNG embedding forked from build_main_web_app_spec.py. Crops + marker
coords come from _capture_spec_a_main_v2.py (bin/speca2_coords.json).

HARD CONSTRAINTS: stdlib + Pillow only. .docx built by hand as WordprocessingML.
Thai = Leelawadee UI on ascii/hAnsi/cs, szCs==sz. document.xml UTF-8.
Re-runnable: run the capture script first, then this; overwrites assets + .docx.
Does NOT touch the V1.0 .docx.
"""

import os
import io
import json
import html
import zipfile
from PIL import Image, ImageDraw, ImageFont

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
PROJECT_ROOT = r"c:\04.budget_management_web"
SIGNOFF_DIR = os.path.join(
    PROJECT_ROOT, "requirement_spec", "1_software_dev", "1.1_frontend", "signoff_spec")
ASSETS_DIR = os.path.join(SIGNOFF_DIR, "assets")
LADDAWAN_DIR = os.path.join(SIGNOFF_DIR, "laddawan")
BIN_DIR = os.path.join(PROJECT_ROOT, "bin")
LOGO_SRC = os.path.join(os.path.dirname(__file__), "assets", "spec_c_logo.jpeg")
COORDS_PATH = os.path.join(BIN_DIR, "speca2_coords.json")
OUT_DOCX = os.path.join(LADDAWAN_DIR, "Spec A หน้าหลักและสิทธิ์การเข้าถึง_V2.0.docx")

os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(LADDAWAN_DIR, exist_ok=True)

THAI_FONT = "Leelawadee UI"

# Palette (blue laddawan family — matches Spec C)
HEAD_BLUE = "0F4761"
SUB_BLUE = "1F3864"
ACCENT_BROWN = "8C6423"   # "decided / important" callouts
BLACK = "000000"
GREY = "6B7280"
TH_FILL = "D6E4F0"
TH_TEXT = "0F4761"

# Gold markers (Pillow)
GOLD = (201, 150, 61)
GOLD_DARK = (140, 100, 35)
WHITE = (255, 255, 255)
NUM_FONT_PATH = r"C:\Windows\Fonts\arialbd.ttf"

EMU_PER_PX = 9525
EMU_PER_IN = 914400
TARGET_WIDTH_IN = 6.3

with open(COORDS_PATH, encoding="utf-8") as _f:
    COORDS = json.load(_f)


# --------------------------------------------------------------------------- #
# Pillow annotation (forked from build_main_web_app_spec.py)
# --------------------------------------------------------------------------- #
def _num_font(size):
    try:
        return ImageFont.truetype(NUM_FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


def _leader(draw, cx, cy, tx, ty, radius):
    import math
    dx, dy = tx - cx, ty - cy
    dist = math.hypot(dx, dy)
    if dist < 1:
        return
    ux, uy = dx / dist, dy / dist
    sx, sy = cx + ux * (radius + 1), cy + uy * (radius + 1)
    draw.line([(sx + 1, sy + 1), (tx + 1, ty + 1)], fill=GOLD_DARK, width=2)
    draw.line([(sx, sy), (tx, ty)], fill=GOLD, width=2)
    draw.ellipse([tx - 3, ty - 3, tx + 3, ty + 3], fill=GOLD, outline=GOLD_DARK)


def _circle(draw, label, cx, cy, tx, ty, radius=18):
    _leader(draw, cx, cy, tx, ty, radius)
    draw.ellipse([cx - radius + 2, cy - radius + 2, cx + radius + 2, cy + radius + 2],
                 fill=(0, 0, 0, 60))
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                 fill=GOLD, outline=GOLD_DARK, width=2)
    f = _num_font(radius + 4)
    bb = draw.textbbox((0, 0), label, font=f)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    draw.text((cx - tw / 2 - bb[0], cy - th / 2 - bb[1]), label, fill=WHITE, font=f)


def annotate(key):
    """Draw gold numbered markers on bin/speca2_<key>.png -> assets/, return (path,(w,h))."""
    blk = COORDS[key]
    src = os.path.join(BIN_DIR, blk["png"])
    im = Image.open(src).convert("RGBA")
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(ov)
    for m in blk["markers"]:
        _circle(dr, m["label"], m["cx"], m["cy"], m["tx"], m["ty"])
    out = Image.alpha_composite(im, ov).convert("RGB")
    op = os.path.join(ASSETS_DIR, blk["png"])
    out.save(op, "PNG")
    return op, out.size


# --------------------------------------------------------------------------- #
# OOXML low-level helpers (forked from build_spec_c_master_tables.py)
# --------------------------------------------------------------------------- #
def esc(text):
    return html.escape(str(text), quote=True)


def run_props(sz, bold=False, color=None, italic=False):
    p = ['<w:rPr>',
         f'<w:rFonts w:ascii="{THAI_FONT}" w:hAnsi="{THAI_FONT}" w:cs="{THAI_FONT}"/>']
    if bold:
        p.append('<w:b/><w:bCs/>')
    if italic:
        p.append('<w:i/><w:iCs/>')
    if color:
        p.append(f'<w:color w:val="{color}"/>')
    p.append(f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/></w:rPr>')
    return "".join(p)


def run(text, sz=24, bold=False, color=None, italic=False):
    return f'<w:r>{run_props(sz, bold, color, italic)}<w:t xml:space="preserve">{esc(text)}</w:t></w:r>'


def para(runs_xml, align=None, space_before=0, space_after=120, shading=None,
         keep_next=False, page_break_before=False):
    ppr = ['<w:pPr>']
    if page_break_before:
        ppr.append('<w:pageBreakBefore/>')
    ppr.append(f'<w:rFonts w:ascii="{THAI_FONT}" w:hAnsi="{THAI_FONT}" w:cs="{THAI_FONT}"/>')
    ppr.append(f'<w:spacing w:before="{space_before}" w:after="{space_after}"/>')
    if align:
        ppr.append(f'<w:jc w:val="{align}"/>')
    if shading:
        ppr.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{shading}"/>')
    if keep_next:
        ppr.append('<w:keepNext/>')
    ppr.append('</w:pPr>')
    return f'<w:p>{"".join(ppr)}{runs_xml}</w:p>'


def section_heading(text, page_break_before=False):
    return para(run(text, sz=32, bold=True, color=HEAD_BLUE),
                space_before=(0 if page_break_before else 320), space_after=120,
                keep_next=True, page_break_before=page_break_before)


def subheading(text):
    return para(run(text, sz=26, bold=True, color=SUB_BLUE),
                space_before=160, space_after=60, keep_next=True)


def label_para(text, color=BLACK):
    return para(run(text, sz=24, bold=True, color=color), space_before=100, space_after=40)


def body_para(text, sz=24, space_after=120, color=None):
    return para(run(text, sz=sz, color=color), space_after=space_after)


def bullet(text, sz=24):
    return para(run("•  " + text, sz=sz), space_after=50)


def note_para(text, sz=22):
    """A brown 'important / decided' callout (bold)."""
    return para(run(text, sz=sz, bold=True, color=ACCENT_BROWN),
                space_before=60, space_after=100)


def caption(text):
    return para(run(text, sz=21, bold=True, color=SUB_BLUE), space_before=80, space_after=40)


# ------- tables ------------------------------------------------------------ #
def tcell(content_xml, width_dxa=None, fill=None):
    tc = ['<w:tcPr>']
    tc.append(f'<w:tcW w:w="{width_dxa}" w:type="dxa"/>' if width_dxa else '<w:tcW w:w="0" w:type="auto"/>')
    if fill:
        tc.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>')
    tc.append('<w:tcMar><w:top w:w="40" w:type="dxa"/><w:bottom w:w="40" w:type="dxa"/>'
              '<w:left w:w="90" w:type="dxa"/><w:right w:w="90" w:type="dxa"/></w:tcMar>')
    tc.append('<w:vAlign w:val="center"/></w:tcPr>')
    return f'<w:tc>{"".join(tc)}{content_xml}</w:tc>'


def cell_para(text, bold=False, color=None, sz=20, align=None):
    return para(run(text, sz=sz, bold=bold, color=color), align=align,
                space_after=20, space_before=20)


def table(rows, col_widths_dxa):
    tbl = ['<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/>',
           '<w:tblBorders>'
           '<w:top w:val="single" w:sz="4" w:space="0" w:color="9DB7D5"/>'
           '<w:left w:val="single" w:sz="4" w:space="0" w:color="9DB7D5"/>'
           '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="9DB7D5"/>'
           '<w:right w:val="single" w:sz="4" w:space="0" w:color="9DB7D5"/>'
           '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="C7D6EA"/>'
           '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="C7D6EA"/>'
           '</w:tblBorders><w:tblLayout w:type="fixed"/></w:tblPr><w:tblGrid>']
    for w in col_widths_dxa:
        tbl.append(f'<w:gridCol w:w="{w}"/>')
    tbl.append('</w:tblGrid>')
    for ri, row in enumerate(rows):
        hdr = ri == 0
        tr = ['<w:tr>']
        if hdr:
            tr.append('<w:trPr><w:tblHeader/></w:trPr>')
        for ci, cell in enumerate(row):
            content = cell_para(cell, bold=hdr, color=(TH_TEXT if hdr else None), sz=20)
            tr.append(tcell(content, width_dxa=col_widths_dxa[ci],
                            fill=(TH_FILL if hdr else None)))
        tr.append('</w:tr>')
        tbl.append("".join(tr))
    tbl.append('</w:tbl>')
    tbl.append(para(run("", sz=8), space_after=80))
    return "".join(tbl)


def sign_table(rows, col_widths_dxa):
    tbl = ['<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/>',
           '<w:tblBorders>'
           '<w:top w:val="single" w:sz="4" w:space="0" w:color="9DB7D5"/>'
           '<w:left w:val="single" w:sz="4" w:space="0" w:color="9DB7D5"/>'
           '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="9DB7D5"/>'
           '<w:right w:val="single" w:sz="4" w:space="0" w:color="9DB7D5"/>'
           '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="C7D6EA"/>'
           '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="C7D6EA"/>'
           '</w:tblBorders><w:tblLayout w:type="fixed"/></w:tblPr><w:tblGrid>']
    for w in col_widths_dxa:
        tbl.append(f'<w:gridCol w:w="{w}"/>')
    tbl.append('</w:tblGrid>')
    for ri, row in enumerate(rows):
        hdr = ri == 0
        tr = ['<w:tr><w:trPr>']
        tr.append('<w:tblHeader/>' if hdr else '<w:trHeight w:val="1000" w:hRule="atLeast"/>')
        tr.append('</w:trPr>')
        for ci, cell in enumerate(row):
            content = cell_para(cell, bold=hdr, color=(TH_TEXT if hdr else None), sz=20)
            tr.append(tcell(content, width_dxa=col_widths_dxa[ci],
                            fill=(TH_FILL if hdr else None)))
        tr.append('</w:tr>')
        tbl.append("".join(tr))
    tbl.append('</w:tbl>')
    tbl.append(para(run("", sz=8), space_after=80))
    return "".join(tbl)


# ------- images ------------------------------------------------------------ #
def _pic_xml(rid, cx, cy, doc_pr_id, name):
    return (
        f'<w:r><w:rPr><w:rFonts w:ascii="{THAI_FONT}" w:hAnsi="{THAI_FONT}" '
        f'w:cs="{THAI_FONT}"/></w:rPr><w:drawing>'
        '<wp:inline distT="0" distB="0" distL="0" distR="0" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
        f'<wp:extent cx="{cx}" cy="{cy}"/><wp:effectExtent l="0" t="0" r="0" b="0"/>'
        f'<wp:docPr id="{doc_pr_id}" name="{esc(name)}"/>'
        '<wp:cNvGraphicFramePr><a:graphicFrameLocks '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'noChangeAspect="1"/></wp:cNvGraphicFramePr>'
        '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        f'<pic:nvPicPr><pic:cNvPr id="{doc_pr_id}" name="{esc(name)}"/><pic:cNvPicPr/></pic:nvPicPr>'
        f'<pic:blipFill><a:blip r:embed="{rid}" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
        '<a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
        f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
        '</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>')


def image_para(rid, px_w, px_h, doc_pr_id, name, width_in=None):
    cx = int((width_in or TARGET_WIDTH_IN) * EMU_PER_IN)
    cy = int(cx * (px_h / px_w))
    ppr = (f'<w:pPr><w:rFonts w:ascii="{THAI_FONT}" w:hAnsi="{THAI_FONT}" w:cs="{THAI_FONT}"/>'
           f'<w:spacing w:before="80" w:after="80"/><w:jc w:val="center"/><w:keepNext/></w:pPr>')
    return f'<w:p>{ppr}{_pic_xml(rid, cx, cy, doc_pr_id, name)}</w:p>'


def cover_logo_para(rid, px_w, px_h, target_px_w=170):
    cx = int(target_px_w * EMU_PER_PX)
    cy = int(cx * (px_h / px_w))
    ppr = (f'<w:pPr><w:rFonts w:ascii="{THAI_FONT}" w:hAnsi="{THAI_FONT}" w:cs="{THAI_FONT}"/>'
           f'<w:spacing w:before="480" w:after="240"/><w:jc w:val="center"/></w:pPr>')
    pic = _pic_xml(rid, cx, cy, 500, "cover_logo")
    return f'<w:p>{ppr}{pic}</w:p>'


# Column-width presets (content width ~9600 dxa for A4 @ 1134 margins)
LEG3 = [640, 3200, 5760]          # เลข | จุด/หน้าที่ | ความหมาย
SRC3 = [2600, 3300, 3700]         # แหล่ง | รายละเอียด | การทำงาน
SIGN_WIDTHS = [1500, 2700, 2900, 1300, 1200]


# --------------------------------------------------------------------------- #
# Document body
# --------------------------------------------------------------------------- #
def build_body(logo_rid, logo_size, meta, rids):
    p = []

    # ---- COVER ----------------------------------------------------------- #
    p.append(cover_logo_para(logo_rid, logo_size[0], logo_size[1]))
    cover_lines = [
        "บริษัท เคมีแมน จำกัด (มหาชน)",
        "เอกสารยืนยันข้อกำหนด เพื่อลงนามอนุมัติ",
        "(User Sign-off Specification)",
        "Spec A หน้าหลักและสิทธิ์การเข้าถึง",
        "Data Warehouse and BI Dashboard Budgeting and Management",
    ]
    for i, line in enumerate(cover_lines):
        p.append(para(run(line, sz=28, bold=True, color=BLACK),
                      align="center", space_before=(40 if i else 120), space_after=40))
    p.append(para(run(
        "เอกสารฉบับนี้ (ฉบับปรับปรุง V2.0) อธิบายหน้าหลักของระบบบริหารงบประมาณ (Main Budget "
        "Web App) — หน้าจอเดียวที่ทุกบทบาทเข้าใช้งาน — โดยแบ่งเนื้อหาเป็น 3 ส่วน และปรับข้อความ "
        "ให้ตรงกับข้อตัดสินใจ (ADR) ล่าสุดเรื่องสิทธิ์การเข้าถึงและที่มาของงบอนุมัติ",
        sz=22, color=GREY), align="center", space_before=240, space_after=40))

    # ---- INTRO ----------------------------------------------------------- #
    p.append(section_heading("บทนำ — หน้าหลักคืออะไร และแบ่งเป็น 3 ส่วนอย่างไร",
                             page_break_before=True))
    p.append(body_para(
        "\"หน้าหลัก\" (Main Budget Web App) เป็นหน้าจอเดียวที่ทุกบทบาทเข้าใช้งานร่วมกัน ทั้งผู้กรอกงบ "
        "(User) ผู้อนุมัติ (Approver) และผู้ดูแลระบบ (Admin) เมื่อ login เข้ามา ระบบจะแสดงข้อมูลตามสิทธิ์ "
        "ของผู้ใช้คนนั้นทันที หน้านี้ทำได้ทั้ง ดูข้อมูลจริงจาก SAP เทียบกับงบที่อนุมัติแล้ว "
        "และ กรอกงบของปีถัดไปเพื่อส่งเข้าสู่การอนุมัติ"))
    p.append(body_para("เพื่อให้อ่านง่าย เอกสารนี้แบ่งหน้าหลักออกเป็น 3 ส่วน:", space_after=60))
    p.append(bullet("ส่วนที่ 1 — แถบข้อมูลผู้ใช้ (หลัง login) และสิทธิ์การเข้าถึง (ใครเห็น/กรอกอะไรได้)"))
    p.append(bullet("ส่วนที่ 2 — แถบตัวกรอง (ปี / ฝ่าย) และปุ่มเครื่องมือของหน้า"))
    p.append(bullet("ส่วนที่ 3 — ตารางกรอกข้อมูลงบประมาณ และปุ่ม Submit to Database (การส่ง/อนุมัติ)"))

    # ==================================================================== #
    # PART 1 — user bar + access rights
    # ==================================================================== #
    p.append(section_heading("ส่วนที่ 1 — แถบข้อมูลผู้ใช้ (หลัง login) และสิทธิ์การเข้าถึง",
                             page_break_before=True))
    p.append(body_para(
        "หลัง login ด้านบนของหน้าจะมี \"แถบข้อมูลผู้ใช้\" (user bar) บอกว่ากำลังใช้งานเป็นใคร และเห็นข้อมูล "
        "ในขอบเขตใด โดยเรียงเป็นลำดับชั้นอ่านจากซ้ายไปขวา: รูปย่อ (avatar) + ชื่อ/อีเมล และป้ายบทบาท "
        "USER/ADMIN  ›  สายงาน (Division)  ›  ฝ่าย (Department) พร้อมจำนวนฝ่าย  ›  จำนวน Cost Center และ "
        "จำนวน GL Codes ที่อยู่ในขอบเขต"))
    p.append(caption("ภาพที่ 1 — แถบข้อมูลผู้ใช้ (ตัวอย่าง: ผู้กรอกงบ) พร้อมสวิตช์โหมด Admin"))
    p.append(image_para(rids["page_head"], *meta["page_head"][1], 10, "speca2_page_head", width_in=6.3))
    p.append(table([
        ["เลข", "จุดบนภาพ", "หน้าที่ / ความหมาย"],
        ["①", "รูปย่อ (avatar) + ชื่อผู้ใช้", "แสดงว่ากำลัง login เป็นใคร (ตัวย่อชื่อ/อีเมล + ชื่อเต็ม + อีเมล)"],
        ["②", "ป้ายบทบาท (USER / ADMIN)", "บอกบทบาทของผู้ใช้: USER = ผู้กรอก/ผู้อนุมัติ · ADMIN = ผู้ดูแลระบบ"],
        ["③", "สายงาน (Division)", "สายงานของผู้ใช้ — ดึงจากคอลัมน์ สายงาน ในไฟล์ master ของ Cost Center"],
        ["④", "ฝ่าย (Department) + จำนวน", "ฝ่ายที่ผู้ใช้ดูแล พร้อมตัวเลขจำนวนฝ่าย (วางไว้ติดกับคำว่า ฝ่าย)"],
        ["⑤", "จำนวน Cost Center + GL Codes", "จำนวน Cost Center และ GL ที่อยู่ในขอบเขตการเห็นของผู้ใช้"],
        ["⑥", "🛡️ สวิตช์โหมด Admin", "ปุ่มสลับหมวก base ↔ admin (แสดงเฉพาะคนที่มี 2 บทบาท · ADR-0014)"],
    ], LEG3))

    p.append(subheading("แถบข้อมูลผู้ใช้แสดงอะไร"))
    p.append(bullet(
        "ลำดับชั้น สายงาน › ฝ่าย (จำนวน) › Cost Center (จำนวน) + GL Codes โดยวางตัวเลขจำนวนไว้ติดกับ "
        "สิ่งที่นับ เพื่อให้เห็นขอบเขตชัดในบรรทัดเดียว"))
    p.append(bullet(
        "ชื่อสายงาน/ฝ่าย ดึงจากคอลัมน์ สายงาน และ ฝ่าย ในไฟล์ master ไม่ใช้คอลัมน์ Description (ชื่อ Cost "
        "Center จริง) เพราะจากข้อมูลจริง Description ตรงกับชื่อฝ่ายเพียง 37% จึงเลือกชื่อฝ่ายที่อ่านง่ายกว่า"))

    p.append(subheading("บทบาทและโหมด Admin"))
    p.append(bullet("บทบาทหลักมี 2 แบบ: USER (ผู้กรอก/ผู้อนุมัติ) และ ADMIN (ผู้ดูแลระบบ)"))
    p.append(bullet(
        "ผู้ดูแลระบบมี 4 คน — เห็นและแก้ไขงบ Pending ได้ทุก Cost Center ทั้งบริษัท"))
    p.append(bullet(
        "คนที่มี 2 บทบาท (เช่น เป็นทั้งผู้อนุมัติและผู้ดูแลระบบ) จะมีปุ่ม \"🛡️ โหมด Admin\" ไว้สลับหมวก "
        "ระหว่างบทบาทฐาน (base) กับบทบาท admin ตามต้องการ (ADR-0014) — กันเผลอใช้อำนาจ admin ตอนทำงานปกติ"))
    p.append(bullet(
        "ผู้ดูแลหลัก (jakkaritw) เป็น admin ถาวร จึงไม่มีปุ่มสลับ"))
    p.append(note_para(
        "หมายเหตุเรื่องภาพ: สวิตช์สลับผู้ใช้และปุ่มโหมด Admin ในภาพเป็นเพียงตัวช่วยสาธิต (demo) ในแบบจำลอง "
        "เท่านั้น — ระบบจริงไม่มีปุ่มสลับผู้ใช้ (login แล้วเห็นข้อมูลของตัวเองทันที)"))

    p.append(subheading("สิทธิ์การเข้าถึง (RLS) — ใครเห็น / ใครกรอก (ตาม ADR-0019)"))
    p.append(body_para(
        "สิทธิ์การเห็น (See) และสิทธิ์การกรอก (Fill) ของระบบงบประมาณ อ้างอิงจากไฟล์เดียว คือ Cost Center ↔ "
        "ผู้กรอก (ไฟล์ cc dept.xlsx บน SharePoint) ซึ่งระบุต่อ Cost Center ว่ามีใครเป็น \"ผู้กรอก\" (Filler) "
        "บ้าง (ดูรายละเอียดไฟล์ในเอกสาร Spec C):"))
    p.append(bullet(
        "สิทธิ์กรอก (Fill-scope) = ทุก Cost Center ที่อีเมลของผู้ใช้ปรากฏในคอลัมน์ Filler ของ Cost Center "
        "นั้นในไฟล์ cc dept.xlsx — ถูกระบุคือได้สิทธิ์กรอกทันที ไม่มีการตรวจระดับตำแหน่งหรือ role เพิ่มเติม"))
    p.append(bullet(
        "สิทธิ์การเห็น (See-scope) = ผู้กรอก (Filler) ของ Cost Center นั้น รวมกับ หัวหน้าโดยตรง (direct "
        "manager) ของผู้กรอกแต่ละคน โดยหัวหน้าเห็นข้อมูลได้แต่กรอกไม่ได้ เว้นแต่ถูกระบุเป็นผู้กรอกด้วย"))
    p.append(bullet(
        "สิทธิ์กรอกอยู่ภายใต้สิทธิ์การเห็นเสมอ (Fill ⊆ See) — กรอกได้เฉพาะที่ตัวเองเห็น"))
    p.append(bullet(
        "กรอกแทนหัวหน้า: ทำได้โดยเพิ่มอีเมลของผู้กรอกแทนลงในช่อง Filler ของ Cost Center นั้น — ไม่ใช่กลไก "
        "แยกต่างหาก แค่เพิ่มชื่อในไฟล์เดียวกัน"))
    p.append(note_para(
        "Cost Center ที่ไม่มีผู้กรอก (ช่อง Filler ว่าง) = ยังไม่มีเจ้าของ จนกว่า admin จะเติมอีเมลผู้กรอก"
        "ในไฟล์ cc dept.xlsx (ADR-0019)"))
    p.append(bullet(
        "การกำหนดสายอนุมัติ (approval routing) หลังกดส่ง เป็นคนละเรื่องกับสิทธิ์การเห็น — อธิบายในส่วนที่ 3"))

    # ==================================================================== #
    # PART 2 — filters + tools
    # ==================================================================== #
    p.append(section_heading("ส่วนที่ 2 — แถบตัวกรอง (ปี / ฝ่าย) และปุ่มเครื่องมือ",
                             page_break_before=True))
    p.append(body_para(
        "ใต้แถบผู้ใช้คือ \"แถบเครื่องมือ\" (toolbar) รวมตัวกรองและปุ่มที่ใช้บ่อยของหน้า: ตัวกรองปี ตัวกรองฝ่าย "
        "คำอธิบายสีสถานะ (legend) ปุ่มรีเซ็ตความกว้างคอลัมน์ ปุ่มเพิ่มรายการ และปุ่มแนบไฟล์"))
    p.append(caption("ภาพที่ 2 — แถบตัวกรองและปุ่มเครื่องมือ"))
    p.append(image_para(rids["toolbar"], *meta["toolbar"][1], 11, "speca2_toolbar", width_in=6.3))
    p.append(table([
        ["เลข", "จุดบนภาพ", "หน้าที่ / ความหมาย"],
        ["①", "ตัวกรองปีงบประมาณ", "เลือกปี FY2024 / 2025 / 2026 (ค่าเริ่มต้น = ปีปัจจุบัน) — ไม่มีตัวเลือก \"ทุกปี\""],
        ["②", "ตัวกรองฝ่าย (ฝ่าย-picker)", "เลือก 1 ฝ่าย → ล็อกหน้าให้เหลือ 1 หน่วยอนุมัติ = (ฝ่าย, ปี)"],
        ["③", "คำอธิบายสีสถานะ (legend)", "SAP (เขียว) · Approved งบอนุมัติ (ฟ้า) · Pending งบรออนุมัติ"],
        ["④", "ปุ่ม Reset columns", "รีเซ็ตความกว้างคอลัมน์ของตารางกลับค่าเริ่มต้น"],
        ["⑤", "ปุ่ม + เพิ่ม Transaction", "เพิ่มแถวรายการใหม่ (Cost Center × GL) เลือกจาก master"],
        ["⑥", "ปุ่ม แนบไฟล์", "เก็บเอกสารประกอบ (PDF/Excel/รูป) เข้า SharePoint ตามฝ่าย + ปี"],
    ], LEG3))

    p.append(subheading("ตัวกรองปีงบประมาณ"))
    p.append(bullet("มี FY2024 / FY2025 / FY2026 · ค่าเริ่มต้น = ปีปัจจุบัน"))
    p.append(bullet(
        "ป้ายปีในวงเล็บที่แต่ละแถว/legend เลื่อนตามตัวกรองปี: ยืนปี Y → SAP (Y) · Approved (Y) · Pending "
        "(Y+1) — คือกรอกงบปีหน้า เทียบกับ actual และงบอนุมัติของปีนี้"))

    p.append(subheading("ตัวกรองฝ่าย = หน่วยอนุมัติ (ADR-0008)"))
    p.append(bullet("1 หน่วยอนุมัติ = (ฝ่าย, ปี) — เลือกฝ่ายแล้วหน้าจะล็อกให้เหลือฝ่ายนั้นทั้งฝ่าย"))
    p.append(bullet("รายการฝ่ายในตัวเลือกจัดกลุ่มตามสายงาน (Division) เพื่อให้หาง่าย"))
    p.append(bullet("ผู้กรอกถูกล็อกที่ฝ่ายของตนอัตโนมัติ (กรอกได้เฉพาะฝ่ายที่ตนเป็นผู้กรอก)"))
    p.append(bullet(
        "ผู้อนุมัติเห็นป้ายสถานะ รออนุมัติ / อนุมัติแล้ว ต่อฝ่าย และมีสวิตช์ \"เฉพาะที่รออนุมัติ\" เพื่อกรอง "
        "เหลือเฉพาะคิวของตน"))

    p.append(subheading("ปุ่มเครื่องมือ"))
    p.append(bullet(
        "ปุ่ม + เพิ่ม Transaction: เพิ่มแถวรายการ (Cost Center × GL) โดยเลือกจาก master · รายการ Cost "
        "Center จำกัดเฉพาะฝ่ายที่ผู้ใช้กรอกได้ (fill-scope)"))
    p.append(bullet(
        "ปุ่ม แนบไฟล์: เก็บเอกสารประกอบ (PDF/Excel/รูป) เข้า SharePoint โดยจัดโฟลเดอร์ตามฝ่าย + ปี ของหน้าที่กำลังดู"))
    p.append(bullet("ปุ่ม Reset columns และคำอธิบายสีสถานะ (legend) ช่วยเรื่องการอ่านตารางเท่านั้น"))

    # ==================================================================== #
    # PART 3 — table + Submit
    # ==================================================================== #
    p.append(section_heading("ส่วนที่ 3 — ตารางกรอกข้อมูล และปุ่ม Submit to Database",
                             page_break_before=True))
    p.append(body_para(
        "ส่วนหลักของหน้าคือตารางงบประมาณรายเดือน (ม.ค.–ธ.ค.) ต่อ Cost Center / GL Code / ปี แต่ละรายการ "
        "แสดง 3 ชั้นข้อมูลซ้อนกัน (SAP / Approved / Pending) และมีปุ่ม Submit to Database อยู่ด้านล่างสำหรับ "
        "ส่งงบเข้าสู่การอนุมัติ"))
    p.append(caption("ภาพที่ 3.1 — ตารางกรอกข้อมูล (3 ชั้น + GL กลุ่มพิเศษ)"))
    p.append(image_para(rids["table"], *meta["table"][1], 12, "speca2_table", width_in=6.3))
    p.append(caption("ภาพที่ 3.2 — แถบด้านล่าง: ปุ่ม Submit to Database"))
    p.append(image_para(rids["submit"], *meta["submit"][1], 13, "speca2_submit", width_in=6.3))
    p.append(table([
        ["เลข", "จุดบนภาพ", "หน้าที่ / ความหมาย"],
        ["①", "คอลัมน์ Cost Center / GL Code / GL Group / Remark", "คอลัมน์ระบุรายการ (GL Group / ชื่อ auto-fill จาก master · Remark แก้ได้)"],
        ["②", "คอลัมน์ Status + 3 ชั้น", "SAP (เขียว·อ่านอย่างเดียว) / Approved (ฟ้า·อ่านอย่างเดียว) / Pending (กรอกมือ)"],
        ["③", "ช่องกรอกรายเดือน (Pending)", "ผู้กรอกพิมพ์ยอดรายเดือน — แก้ได้เฉพาะสถานะ DRAFT / REJECTED"],
        ["④", "ป้าย GL กลุ่มพิเศษ + ปุ่ม \"ใส่รายละเอียดงบทำการ\"", "GL กลุ่มพิเศษมีป้ายสีเฉพาะ · กรอกผ่าน subform (รายละเอียดใน Spec B)"],
        ["⑤", "ปุ่ม Submit to Database (ภาพ 3.2)", "ส่งงบทั้งฝ่ายเป็นแพ็กเกจเข้าสู่การอนุมัติ"],
    ], LEG3))

    p.append(subheading("3 แหล่งข้อมูลในตาราง"))
    p.append(table([
        ["ชั้นข้อมูล (สี)", "แหล่งที่มา / ใครกรอก", "การทำงาน"],
        ["SAP · ใช้จริง (เขียว)",
         "ดึงจาก Lakehouse gold_sap_gl_trans · คอลัมน์ company_curr_amount",
         "อ่านอย่างเดียว · ดึงอัตโนมัติ (แก้ในตารางไม่ได้)"],
        ["Approved · งบอนุมัติ (ฟ้า)",
         "ไฟล์ Excel รายปีบน SharePoint (ADR-0021)",
         "อ่านอย่างเดียวบนเว็บ · นำเข้าแบบ Replace-by-Year"],
        ["Pending · รออนุมัติ (กรอกมือ)",
         "ผู้กรอก (Filler) พิมพ์ยอดรายเดือน · admin แก้ได้ทุก CC",
         "กด Submit to Database → เข้าสู่สายการอนุมัติ"],
    ], SRC3))

    p.append(subheading("งบอนุมัติ (Approved) มาจากไฟล์ Excel บน SharePoint (ADR-0021)"))
    p.append(bullet(
        "เจ้าหน้าที่งบประมาณวางไฟล์ Excel ทั้งปีไว้บน SharePoint (site CMANDWPRD › library "
        "\"Budgeting and Management\" › folder \"approved budget\")"))
    p.append(bullet(
        "ชื่อไฟล์ต้องเป็น approved_budget_<ปี>.xlsx (เช่น approved_budget_2026.xlsx) — ระบบอ่านคอลัมน์ "
        "A–N และดึงปีจากชื่อไฟล์เท่านั้น จึงต้องตั้งชื่อไฟล์ให้ถูกปี"))
    p.append(bullet("นำเข้าแบบ Replace-by-Year (แทนที่ทั้งปีของปีนั้น) เข้าสู่ Fabric SQL Database"))
    p.append(note_para(
        "บนเว็บ Approved เป็น อ่านอย่างเดียว — ไม่มีปุ่มนำเข้าหรือส่งออกในแอปอีกต่อไป (ยกเลิกแล้ว) การอัปเดต "
        "งบอนุมัติทำผ่านการวางไฟล์บน SharePoint เท่านั้น"))

    p.append(subheading("การล็อกการแก้ไข (edit-lock · ADR-0013)"))
    p.append(bullet("แก้ยอด Pending ได้เฉพาะสถานะ DRAFT หรือ REJECTED เท่านั้น"))
    p.append(bullet("ชั้น SAP และ Approved แก้ในตารางไม่ได้ (อ่านอย่างเดียว)"))
    p.append(bullet("การแก้ตัวเลขไม่เปลี่ยนสถานะ — สถานะเลื่อนได้ทางปุ่ม Submit / Approve / Reject เท่านั้น"))

    p.append(subheading("GL กลุ่มพิเศษ และ Master FX"))
    p.append(bullet(
        "GL กลุ่มพิเศษ (เช่น ค่าเดินทาง / ค่าที่ปรึกษา) มีป้ายสีเฉพาะกลุ่ม และกรอกผ่านฟอร์มย่อย (subform) "
        "ด้วยปุ่ม \"ใส่รายละเอียดงบทำการ\" — รายละเอียดฟอร์มย่อยอยู่ในเอกสาร Spec B"))
    p.append(bullet(
        "อัตราแลกเปลี่ยน (Master FX) แสดงบนหน้านี้แบบ อ่านอย่างเดียว และคำนวณเบี้ยเลี้ยงต่างประเทศแบบสด "
        "ทุกครั้งที่อ่าน (recompute-on-read · ADR-0015) — แก้อัตราได้ที่หน้า Master Currency เท่านั้น"))

    p.append(subheading("การส่ง (Submit) และการอนุมัติ (Approval)"))
    p.append(bullet(
        "ปุ่ม Submit to Database ส่งงบ ทั้งฝ่าย เป็นแพ็กเกจเข้าสู่การอนุมัติ (หน่วยส่ง/อนุมัติ = (ฝ่าย, ปี) · ADR-0008)"))
    p.append(bullet(
        "สายอนุมัติ = ผู้จัดการโดยตรงของผู้ส่ง (managerempcode) → นิภาพร → วราพร (มีกรณีพิเศษ: นิภาพร / "
        "วราพร / ผู้บริหาร C-Level กรอกและอนุมัติเอง · ADR-0006)"))
    p.append(bullet(
        "อนุมัติได้บนหน้าหลักเลย — ไม่มีหน้ากล่องงาน (inbox) แยก (ADR-0016) · ปุ่มอนุมัติ/ตีกลับจะโผล่เมื่อฝ่าย "
        "ที่เลือกอยู่ที่ขั้นอนุมัติของผู้ใช้พอดี"))
    p.append(bullet(
        "การตีกลับ (Reject) เด้งทั้งฝ่ายกลับเป็น DRAFT พร้อมแจ้งผู้ส่งล่าสุด · มีการแจ้งเตือนทางอีเมล "
        "(Microsoft Graph)"))
    p.append(bullet(
        "ผู้ดูแลระบบหลังวันปิดรับ (deadline) สามารถส่งงบฝ่ายใดก็ได้ โดยเข้าสถานะ APPROVED โดยตรง "
        "(ADMIN_OVERRIDE · ADR-0012) ไม่ผ่านสายอนุมัติ"))

    # ==================================================================== #
    # Sign-off
    # ==================================================================== #
    p.append(section_heading("ช่องลงนามอนุมัติ", page_break_before=True))
    sign_rows = [
        ["บทบาท", "ชื่อ-นามสกุล", "ตำแหน่ง", "ลายเซ็น", "วันที่"],
        ["ผู้จัดทำ", "Jakkarit Wanichkamonnull",
         "Senior STEM - Data & Analytics", "", ""],
        ["ผู้ตรวจสอบ", "Laddawan Kearnoi",
         "Assistant Department Head - Data & Analytic", "", ""],
        ["ผู้ตรวจสอบ", "Nipaporn Tongking",
         "Senior Associate - Budgeting and Management Accounting", "", ""],
        ["ผู้อนุมัติ", "Waraporn Tirasit",
         "Assistant Department Head - Budgeting and Management Accounting", "", ""],
    ]
    p.append(sign_table(sign_rows, SIGN_WIDTHS))

    return "".join(p)


# --------------------------------------------------------------------------- #
# Header / Footer (forked from build_spec_c_master_tables.py)
# --------------------------------------------------------------------------- #
def header_xml(logo_rid, logo_size, target_px_w=90):
    cx = int(target_px_w * EMU_PER_PX)
    cy = int(cx * (logo_size[1] / logo_size[0]))
    logo_run = (
        f'<w:r><w:rPr><w:rFonts w:ascii="{THAI_FONT}" w:hAnsi="{THAI_FONT}" '
        f'w:cs="{THAI_FONT}"/></w:rPr><w:drawing>'
        '<wp:inline distT="0" distB="0" distL="0" distR="0" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
        f'<wp:extent cx="{cx}" cy="{cy}"/><wp:effectExtent l="0" t="0" r="0" b="0"/>'
        '<wp:docPr id="600" name="header_logo"/>'
        '<wp:cNvGraphicFramePr><a:graphicFrameLocks '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'noChangeAspect="1"/></wp:cNvGraphicFramePr>'
        '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:nvPicPr><pic:cNvPr id="600" name="header_logo"/><pic:cNvPicPr/></pic:nvPicPr>'
        f'<pic:blipFill><a:blip r:embed="{logo_rid}" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
        '<a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
        f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
        '</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>')
    logo_p = (f'<w:p><w:pPr><w:rFonts w:ascii="{THAI_FONT}" w:hAnsi="{THAI_FONT}" '
              f'w:cs="{THAI_FONT}"/><w:spacing w:after="0"/></w:pPr>{logo_run}</w:p>')
    lines = [
        "เอกสารยืนยันข้อกำหนด เพื่อลงนามอนุมัติ",
        "Data Warehouse and BI Dashboard Budgeting and Management",
        "Spec A หน้าหลักและสิทธิ์การเข้าถึง (V2.0)",
    ]
    line_ps = "".join(
        para(run(t, sz=16, color=GREY), align="right", space_after=0) for t in lines)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        f'{logo_p}{line_ps}</w:hdr>')


def footer_xml():
    left = run("Data Warehouse and BI Dashboard Budgeting and Management", sz=18, color=GREY)
    page_field = (
        f'<w:r><w:rPr><w:rFonts w:ascii="{THAI_FONT}" w:hAnsi="{THAI_FONT}" '
        f'w:cs="{THAI_FONT}"/><w:sz w:val="18"/><w:szCs w:val="18"/>'
        f'<w:color w:val="{GREY}"/></w:rPr><w:t xml:space="preserve">หน้าที่ </w:t></w:r>'
        f'<w:r><w:rPr><w:sz w:val="18"/><w:szCs w:val="18"/><w:color w:val="{GREY}"/></w:rPr>'
        '<w:fldChar w:fldCharType="begin"/></w:r>'
        f'<w:r><w:rPr><w:sz w:val="18"/><w:szCs w:val="18"/><w:color w:val="{GREY}"/></w:rPr>'
        '<w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
        f'<w:r><w:rPr><w:sz w:val="18"/><w:szCs w:val="18"/><w:color w:val="{GREY}"/></w:rPr>'
        '<w:fldChar w:fldCharType="separate"/></w:r>'
        f'<w:r><w:rPr><w:sz w:val="18"/><w:szCs w:val="18"/><w:color w:val="{GREY}"/></w:rPr>'
        '<w:t>1</w:t></w:r>'
        f'<w:r><w:rPr><w:sz w:val="18"/><w:szCs w:val="18"/><w:color w:val="{GREY}"/></w:rPr>'
        '<w:fldChar w:fldCharType="end"/></w:r>')
    tbl = (
        '<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/>'
        '<w:tblBorders>'
        '<w:top w:val="single" w:sz="4" w:space="0" w:color="C7D6EA"/>'
        '<w:left w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
        '<w:bottom w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
        '<w:right w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
        '<w:insideH w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
        '<w:insideV w:val="none" w:sz="0" w:space="0" w:color="auto"/>'
        '</w:tblBorders><w:tblLayout w:type="fixed"/></w:tblPr>'
        '<w:tblGrid><w:gridCol w:w="7600"/><w:gridCol w:w="2000"/></w:tblGrid>'
        '<w:tr>'
        f'<w:tc><w:tcPr><w:tcW w:w="7600" w:type="dxa"/></w:tcPr>'
        f'<w:p><w:pPr><w:spacing w:after="0"/></w:pPr>{left}</w:p></w:tc>'
        f'<w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/></w:tcPr>'
        f'<w:p><w:pPr><w:spacing w:after="0"/><w:jc w:val="right"/></w:pPr>{page_field}</w:p></w:tc>'
        '</w:tr></w:tbl>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'{tbl}</w:ftr>')


# --------------------------------------------------------------------------- #
# Static OOXML parts
# --------------------------------------------------------------------------- #
def content_types_xml():
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Default Extension="jpeg" ContentType="image/jpeg"/>'
        '<Default Extension="png" ContentType="image/png"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/header1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>'
        '<Override PartName="/word/footer1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
        '</Types>')


def root_rels_xml():
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>')


def document_rels_xml(image_rels):
    r = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
         '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    r.append('<Relationship Id="rIdImg" '
             'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
             'Target="media/image1.jpeg"/>')
    r.append('<Relationship Id="rIdHdr" '
             'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" '
             'Target="header1.xml"/>')
    r.append('<Relationship Id="rIdFtr" '
             'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" '
             'Target="footer1.xml"/>')
    for rid, fn in image_rels:
        r.append(f'<Relationship Id="{rid}" '
                 'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                 f'Target="media/{fn}"/>')
    r.append('</Relationships>')
    return "".join(r)


def header_rels_xml():
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rIdHdrLogo" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
        'Target="media/image1.jpeg"/></Relationships>')


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
        '<w:headerReference w:type="default" r:id="rIdHdr"/>'
        '<w:footerReference w:type="default" r:id="rIdFtr"/>'
        '<w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1134" w:bottom="1134" w:left="1134" '
        'w:header="708" w:footer="708" w:gutter="0"/>'
        '</w:sectPr></w:body></w:document>')


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
# order → media/image{N+2}.png (image1 = logo jpeg)
IMG_ORDER = ["page_head", "toolbar", "table", "submit"]


def main():
    print("[1/4] Annotating crops with gold markers (Pillow) ...")
    meta = {}
    for k in IMG_ORDER:
        meta[k] = annotate(k)
        print(f"      {k}: {meta[k][0]}  size={meta[k][1]}  markers={len(COORDS[k]['markers'])}")

    print("[2/4] Loading company logo ...")
    with open(LOGO_SRC, "rb") as f:
        logo_bytes = f.read()
    logo_size = Image.open(io.BytesIO(logo_bytes)).size
    print(f"      logo {logo_size}")

    # media + rel wiring
    media = {k: f"image{i + 2}.png" for i, k in enumerate(IMG_ORDER)}   # image2..image5
    rids = {k: f"rId{i + 10}" for i, k in enumerate(IMG_ORDER)}          # rId10..rId13
    image_rels = [(rids[k], media[k]) for k in IMG_ORDER]

    print("[3/4] Building OOXML ...")
    body = build_body("rIdImg", logo_size, meta, rids)
    doc_xml = document_xml(body)
    hdr_xml = header_xml("rIdHdrLogo", logo_size)
    ftr_xml = footer_xml()

    print("[4/4] Writing .docx ...")
    if os.path.exists(OUT_DOCX):
        os.remove(OUT_DOCX)
    with zipfile.ZipFile(OUT_DOCX, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types_xml())
        z.writestr("_rels/.rels", root_rels_xml())
        z.writestr("word/document.xml", doc_xml.encode("utf-8"))
        z.writestr("word/_rels/document.xml.rels", document_rels_xml(image_rels))
        z.writestr("word/header1.xml", hdr_xml.encode("utf-8"))
        z.writestr("word/_rels/header1.xml.rels", header_rels_xml())
        z.writestr("word/footer1.xml", ftr_xml.encode("utf-8"))
        z.writestr("word/media/image1.jpeg", logo_bytes)
        for k in IMG_ORDER:
            with open(meta[k][0], "rb") as f:
                z.writestr(f"word/media/{media[k]}", f.read())

    print(f"DONE: {OUT_DOCX}  ({os.path.getsize(OUT_DOCX)} bytes)")


if __name__ == "__main__":
    main()
