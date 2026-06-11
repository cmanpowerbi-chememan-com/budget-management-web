# -*- coding: utf-8 -*-
"""
Generator for the Edit GL Group User Sign-off Specification (.docx).

HARD CONSTRAINTS honoured:
  - NO package installation. Only Python standard library + Pillow (already installed).
  - The .docx is built BY HAND as Office Open XML (WordprocessingML) via zipfile + str XML.
  - Thai text uses Leelawadee UI on w:ascii / w:hAnsi / w:cs, with w:szCs == w:sz.
  - document.xml is UTF-8 encoded.

Two stages:
  1. Pillow: draw numbered gold markers + leader lines onto the 6 source screenshots.
  2. OOXML: assemble paragraphs, tables and inline images into a valid .docx zip.

Re-runnable: deletes/overwrites outputs each run.
"""

import os
import io
import zipfile
import html
from PIL import Image, ImageDraw, ImageFont

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
PROJECT_ROOT = r"c:\04.budget_management_web"
SIGNOFF_DIR = os.path.join(
    PROJECT_ROOT,
    "requirement_spec", "1_software_dev", "1.1_frontend", "signoff_spec",
)
ASSETS_DIR = os.path.join(SIGNOFF_DIR, "assets")
DOCX_PATH = os.path.join(SIGNOFF_DIR, "03_edit_gl_group_spec.docx")

os.makedirs(ASSETS_DIR, exist_ok=True)

# Brand gold
GOLD = (201, 150, 61)          # #C9963D
GOLD_DARK = (140, 100, 35)     # darker outline for legibility
WHITE = (255, 255, 255)

NUM_FONT_PATH = r"C:\Windows\Fonts\arialbd.ttf"

THAI_FONT = "Leelawadee UI"    # ships with Windows, Thai-capable

# --------------------------------------------------------------------------- #
# Pillow annotation helpers
# --------------------------------------------------------------------------- #


def _load_num_font(size):
    try:
        return ImageFont.truetype(NUM_FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


def _draw_leader(draw, cx, cy, tx, ty, radius):
    """Thin gold leader line from circle edge toward target (tx,ty)."""
    import math
    dx, dy = tx - cx, ty - cy
    dist = math.hypot(dx, dy)
    if dist < 1:
        return
    ux, uy = dx / dist, dy / dist
    # start just outside the circle edge
    sx, sy = cx + ux * (radius + 1), cy + uy * (radius + 1)
    # subtle dark shadow under the line for legibility on light bg
    draw.line([(sx + 1, sy + 1), (tx + 1, ty + 1)], fill=GOLD_DARK, width=2)
    draw.line([(sx, sy), (tx, ty)], fill=GOLD, width=2)
    # small arrowhead dot at target
    draw.ellipse([tx - 3, ty - 3, tx + 3, ty + 3], fill=GOLD, outline=GOLD_DARK)


def _draw_circle_marker(draw, label, cx, cy, tx, ty, radius=16):
    """Filled gold circle with white bold centered number, dark outline, leader."""
    _draw_leader(draw, cx, cy, tx, ty, radius)
    # drop shadow
    draw.ellipse(
        [cx - radius + 2, cy - radius + 2, cx + radius + 2, cy + radius + 2],
        fill=(0, 0, 0, 60),
    )
    # main circle with dark outline
    draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        fill=GOLD, outline=GOLD_DARK, width=2,
    )
    fsize = radius + 4
    font = _load_num_font(fsize)
    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(
        (cx - tw / 2 - bbox[0], cy - th / 2 - bbox[1]),
        label, fill=WHITE, font=font,
    )


def _draw_pill_marker(draw, label, cx, cy, tx, ty, height=30):
    """Rounded pill for two-part labels like '1.1' so text fits; gold + white."""
    fsize = 15
    font = _load_num_font(fsize)
    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad_x = 10
    w = tw + pad_x * 2
    h = height
    left = cx - w / 2
    top = cy - h / 2
    right = cx + w / 2
    bottom = cy + h / 2
    r = h / 2
    # leader from pill edge to target (approx from center, clipped to radius)
    _draw_leader(draw, cx, cy, tx, ty, int(w / 2))
    # drop shadow
    draw.rounded_rectangle(
        [left + 2, top + 2, right + 2, bottom + 2], radius=r, fill=(0, 0, 0, 60)
    )
    draw.rounded_rectangle(
        [left, top, right, bottom], radius=r, fill=GOLD, outline=GOLD_DARK, width=2
    )
    draw.text(
        (cx - tw / 2 - bbox[0], cy - th / 2 - bbox[1]),
        label, fill=WHITE, font=font,
    )


def annotate(src_name, out_name, markers):
    """markers: list of dicts {label, cx, cy, tx, ty, shape}."""
    src = os.path.join(PROJECT_ROOT, "bin", src_name)
    im = Image.open(src).convert("RGBA")
    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for m in markers:
        if m.get("shape") == "pill":
            _draw_pill_marker(draw, m["label"], m["cx"], m["cy"], m["tx"], m["ty"])
        else:
            _draw_circle_marker(draw, m["label"], m["cx"], m["cy"], m["tx"], m["ty"])
    out = Image.alpha_composite(im, overlay).convert("RGB")
    out_path = os.path.join(ASSETS_DIR, out_name)
    out.save(out_path, "PNG")
    return out_path, out.size


def build_annotated_images():
    results = {}

    # 01 overview — circled numbers
    # Coords recomputed 2026-06-11 from live getBoundingClientRect (1280x720, DPR1).
    results["01"] = annotate(
        "verify_0003_01_load.png", "01_overview.png",
        [
            {"label": "1", "cx": 25, "cy": 32, "tx": 130, "ty": 32},     # .nav (y0-65)
            {"label": "2", "cx": 25, "cy": 106, "tx": 55, "ty": 106},    # breadcrumb y~106
            {"label": "3", "cx": 735, "cy": 276, "tx": 768, "ty": 276},  # #summaryStrip x765
            {"label": "4", "cx": 25, "cy": 352, "tx": 70, "ty": 352},    # editor panel head
            {"label": "5", "cx": 25, "cy": 569, "tx": 70, "ty": 569},    # table panel (y538+)
        ],
    )

    # 02 GL code dropdown — pill labels
    results["02"] = annotate(
        "verify_0003_02_dropdown.png", "02_glcode.png",
        [
            {"label": "1.1", "cx": 300, "cy": 320, "tx": 233, "ty": 353, "shape": "pill"},  # #modeBadge cx232 cy353
            {"label": "1.2", "cx": 45, "cy": 449, "tx": 75, "ty": 449, "shape": "pill"},    # #glCodeInput y449
        ],
    )

    # 03 GL group dropdown + Save button — pill labels
    results["03"] = annotate(
        "verify_0003_03_group.png", "03_glgroup.png",
        [
            {"label": "1.3", "cx": 572, "cy": 449, "tx": 592, "ty": 449, "shape": "pill"},  # #glGroupInput x588 cy449
            {"label": "1.4", "cx": 1157, "cy": 408, "tx": 1157, "ty": 448, "shape": "pill"},  # .btn-save top447
        ],
    )

    # 04 search — pill labels (toolbar scrolled to top: toolbar y~75-106)
    results["04"] = annotate(
        "verify_0003_05_search.png", "04_search.png",
        [
            {"label": "2.1", "cx": 45, "cy": 97, "tx": 75, "ty": 97, "shape": "pill"},     # .search-box cy97
            {"label": "2.2", "cx": 620, "cy": 150, "tx": 560, "ty": 99, "shape": "pill"},  # legend cx515 + count pill cx1033
            {"label": "2.3", "cx": 1062, "cy": 90, "tx": 1097, "ty": 90, "shape": "pill"}, # #exportCsvBtn x1099 cy90
        ],
    )

    # 05 edit row — pill label (first-row edit action at y~189 in this scroll)
    results["05"] = annotate(
        "verify_0003_edit.png", "05_edit.png",
        [
            {"label": "2.4", "cx": 1062, "cy": 189, "tx": 1140, "ty": 189, "shape": "pill"},  # .action-btn.edit cx1158
        ],
    )

    # 06 delete modal — pill label (confirm button cx773 cy486)
    results["06"] = annotate(
        "verify_0003_delete_modal.png", "06_delete.png",
        [
            {"label": "2.4a", "cx": 905, "cy": 486, "tx": 833, "ty": 486, "shape": "pill"},  # #confirmBtn right831
        ],
    )

    return results


# --------------------------------------------------------------------------- #
# OOXML (WordprocessingML) builders
# --------------------------------------------------------------------------- #
EMU_PER_PX = 9525
TARGET_WIDTH_IN = 6.3
EMU_PER_IN = 914400
TARGET_WIDTH_EMU = int(TARGET_WIDTH_IN * EMU_PER_IN)  # 5760720

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def esc(text):
    return html.escape(str(text), quote=True)


def run_props(size_half_pt, bold=False, color=None, italic=False):
    """Run properties with Leelawadee UI on ascii/hAnsi/cs and szCs == sz."""
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


def image_para(rid, px_w, px_h, doc_pr_id, name):
    """Inline image drawing scaled to TARGET_WIDTH_IN keeping aspect."""
    cx = TARGET_WIDTH_EMU
    cy = int(cx * (px_h / px_w))
    drawing = f'''<w:r><w:rPr><w:rFonts w:ascii="{THAI_FONT}" w:hAnsi="{THAI_FONT}" w:cs="{THAI_FONT}"/></w:rPr><w:drawing>
<wp:inline distT="0" distB="0" distL="0" distR="0" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">
<wp:extent cx="{cx}" cy="{cy}"/>
<wp:effectExtent l="0" t="0" r="0" b="0"/>
<wp:docPr id="{doc_pr_id}" name="{esc(name)}"/>
<wp:cNvGraphicFramePr><a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/></wp:cNvGraphicFramePr>
<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
<pic:nvPicPr><pic:cNvPr id="{doc_pr_id}" name="{esc(name)}"/><pic:cNvPicPr/></pic:nvPicPr>
<pic:blipFill><a:blip r:embed="{rid}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>
</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>'''
    ppr = (
        f'<w:pPr><w:rFonts w:ascii="{THAI_FONT}" w:hAnsi="{THAI_FONT}" '
        f'w:cs="{THAI_FONT}"/><w:spacing w:before="80" w:after="80"/>'
        f'<w:jc w:val="center"/><w:keepNext/></w:pPr>'
    )
    return f'<w:p>{ppr}{drawing}</w:p>'


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
    """rows: list of list[str]. First row is header.
    col_widths_dxa: list of column widths in twentieths of a point (total ~9360 for full)."""
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
    # grid
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
    # spacer paragraph after table (Word requires a p after a tbl)
    tbl.append(para(run("", size_half_pt=8), space_after=80))
    return "".join(tbl)


# --------------------------------------------------------------------------- #
# Document body assembly
# --------------------------------------------------------------------------- #
# Column-width presets (full content area ~ 9360 dxa for 6.5in)
DESC_WIDTHS = [620, 1500, 2300, 2740, 2200]   # # | ชื่อจุด | จุดประสงค์ | การทำงาน | ตาราง
SRC_WIDTHS = [3200, 3560, 2600]               # ตาราง | คำอธิบาย | บทบาท
SIGN_WIDTHS = [1900, 3000, 2460, 2000]        # บทบาท | ชื่อ | ลายเซ็น | วันที่
META_WIDTHS = [2700, 6660]


def build_body(img_meta, rids):
    """img_meta: {key: (path,(w,h))}; rids: {key: rId}."""
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
        run("ส่วน C — การแก้ไขข้อมูลตารางหลัก (Master Tables) · หน้า: Edit GL Group",
            size_half_pt=24, bold=True, color="1E3A24"),
        space_after=160,
    ))

    # Meta table (2 cols)
    meta_rows = [
        ["รายการ", "รายละเอียด"],
        ["เวอร์ชัน", "v0.2 (ฉบับร่าง)"],
        ["วันที่", "11 มิถุนายน 2569 (2026-06-11)"],
        ["ผู้จัดทำ", "ทีม Data Analytics"],
        ["สถานะ", "รออนุมัติจากผู้ใช้"],
    ]
    parts.append(table(meta_rows, META_WIDTHS))

    # Changelog — keep a short history of doc revisions
    parts.append(para(
        run("ประวัติการแก้ไขเอกสาร (Changelog)", size_half_pt=22, bold=True,
            color="1E3A24"),
        space_before=120, space_after=60,
    ))
    changelog_rows = [
        ["เวอร์ชัน", "วันที่", "รายละเอียดการแก้ไข"],
        ["v0.1", "2026-06-02", "ฉบับร่างแรก"],
        ["v0.2", "2026-06-11",
         "ปรับให้ตรงกับหน้าจอจริงหลังเชื่อมต่อ Backend: เพิ่มคำอธิบายการ "
         "\"รวมแถว (Merge)\" ของ GL Group ที่ซ้ำกัน · แก้รูปแบบตัวนับเป็น "
         "\"x / y records\" · เพิ่มเงื่อนไขการสลับโหมดแก้ไขเมื่อเลือก GL Code "
         "ที่จับคู่แล้ว · เพิ่มหน้าต่างแจ้งผล \"บันทึก/อัปเดตสำเร็จ\" · "
         "ถ่ายภาพหน้าจอใหม่ทั้งหมด (รวมปุ่ม Export CSV)"],
    ]
    parts.append(table(changelog_rows, [1400, 2000, 5960]))

    # ---- Context ---------------------------------------------------------
    parts.append(heading("บริบทและขอบเขต (Context)"))
    parts.append(body_para(
        "หน้า Edit GL Group เป็นหน้าสำหรับผู้ดูแลระบบ (Master Table Admins) เท่านั้น "
        "ใช้จับคู่รหัสบัญชี GL Code (อ้างอิงจาก SAP) เข้ากับ GL Group "
        "เพื่อใช้จัดหมวดหมู่ในรายงานงบประมาณ ระบบควบคุมสิทธิ์ด้วย Azure Entra ID group "
        "`master-table-admins` ฐานข้อมูลใช้ Microsoft Fabric SQL Database (schema `cfg_master`)."
    ))
    parts.append(para(
        run("ผู้ดูแลระบบที่ได้รับสิทธิ์ (3 คน)", size_half_pt=22, bold=True,
            color="1E3A24"),
        space_before=80, space_after=60,
    ))
    parts.append(bullet("nipapornt@chememan.com"))
    parts.append(bullet("warapornt@chememan.com"))
    parts.append(bullet("jakkaritw@chememan.com"))

    # ---- Overview --------------------------------------------------------
    parts.append(heading("ภาพรวมหน้าจอ"))
    parts.append(image_para(rids["01"], *img_meta["01"][1], 101, "01_overview"))
    overview_rows = [
        ["#", "ชื่อจุด", "จุดประสงค์", "การทำงาน", "ตารางต้นทาง / ปลายทาง"],
        ["①", "แถบเมนูหลัก (Navigation)",
         "สลับไปหน้า Master อื่น + กลับหน้าแรก + สลับธีม",
         "ลิงก์ไปหน้า Master อื่นๆ ตามแถบเมนูด้านบนของภาพ · ปุ่มกลับหน้าแรก (Home) · ปุ่มสลับธีม (สว่าง/มืด)",
         "—"],
        ["②", "ส่วนหัวหน้า (Breadcrumb + ชื่อหน้า)",
         "บอกตำแหน่งและชื่อโมดูล",
         "แสดง \"Module 03 · Master Data\" และคำอธิบายหน้า",
         "—"],
        ["③", "แถบสรุปตัวเลข (Summary chips)",
         "สรุปสถานะการจับคู่แบบเรียลไทม์",
         "GL Codes (จับคู่แล้ว) · GL Groups (กลุ่มที่ใช้) · Unmapped (ยังไม่จับคู่) · SAP Total",
         "อ่านจาก `cfg_master.sap_gl_code_ref` + `cfg_master.gl_group_mapping`"],
        ["④", "ส่วนที่ 1 — กล่อง Mapping editor",
         "ฟอร์มเพิ่ม/แก้ไขการจับคู่",
         "ดูรายละเอียดข้อ 1.1–1.4",
         "—"],
        ["⑤", "ส่วนที่ 2 — กล่อง Mapping records",
         "ตารางรายการที่จับคู่แล้ว",
         "ดูรายละเอียดข้อ 2.1–2.4",
         "`cfg_master.gl_group_mapping` ⨝ `cfg_master.gl_group_dim`"],
    ]
    parts.append(table(overview_rows, DESC_WIDTHS))

    # ---- Section 1: Mapping editor --------------------------------------
    parts.append(heading("ส่วนที่ 1 — Mapping editor (กล่องเพิ่ม/แก้ไขการจับคู่)"))
    parts.append(image_para(rids["02"], *img_meta["02"][1], 102, "02_glcode"))
    parts.append(image_para(rids["03"], *img_meta["03"][1], 103, "03_glgroup"))
    editor_rows = [
        ["#", "ชื่อจุด", "จุดประสงค์", "การทำงาน", "ตารางต้นทาง / ปลายทาง"],
        ["1.1", "ป้ายโหมด (Mode badge)",
         "บอกว่ากำลัง \"เพิ่มใหม่ · NEW\" หรือ \"แก้ไข · UPDATE\"",
         "เปลี่ยนเป็น \"แก้ไข · UPDATE\" อัตโนมัติใน 2 กรณี: (ก) กดปุ่ม Edit ในตาราง "
         "หรือ (ข) เลือก GL Code ที่จับคู่ไว้แล้วจาก dropdown (ระบบจะเติม GL Group เดิมให้) "
         "· ปุ่มบันทึกจะเปลี่ยนข้อความเป็น \"อัปเดต\"; หากเลือก GL Code ที่ยังไม่จับคู่ จะกลับเป็น \"เพิ่มใหม่ · NEW\"",
         "—"],
        ["1.2", "ช่องเลือก GL Code · จาก SAP",
         "เลือกรหัสบัญชี SAP ที่จะจับคู่",
         "พิมพ์ค้นหาด้วยรหัสหรือชื่อบัญชี และเลือกได้เฉพาะจากรายการ SAP เท่านั้น",
         "ต้นทาง: `cfg_master.sap_gl_code_ref` (อ่านอย่างเดียว, sync จาก SAP รายคืน)"],
        ["1.3", "ช่องเลือก GL Group · เลือกหรือสร้างใหม่",
         "เลือกกลุ่มเดิม หรือพิมพ์สร้างกลุ่มใหม่ได้ทันที",
         "ถ้าพิมพ์ชื่อที่ยังไม่มีในระบบ จะมีตัวเลือก \"สร้างกลุ่มใหม่: …\" (inline create)",
         "ต้นทาง: `cfg_master.gl_group_dim` · ปลายทาง (กรณีสร้างใหม่): เพิ่มแถวใน `gl_group_dim`"],
        ["1.4", "ปุ่ม บันทึก / อัปเดต",
         "บันทึกการจับคู่ + แจ้งผล",
         "เพิ่มใหม่ (กันข้อมูลซ้ำแบบ Fail-Fast) หรืออัปเดต ผ่าน `POST /api/master/gl-group/save` · "
         "เมื่อสำเร็จจะแสดงหน้าต่างแจ้งผล \"บันทึกสำเร็จ\" หรือ \"อัปเดตสำเร็จ\" "
         "พร้อมสรุปรายการ และแถวที่บันทึกจะถูกไฮไลต์/ย้ายขึ้นบนสุดของตาราง",
         "ปลายทาง: `cfg_master.gl_group_mapping`"],
    ]
    parts.append(table(editor_rows, DESC_WIDTHS))

    # ---- Section 2: Mapping records -------------------------------------
    parts.append(heading("ส่วนที่ 2 — Mapping records (ตารางรายการ)"))
    parts.append(image_para(rids["04"], *img_meta["04"][1], 104, "04_search"))
    parts.append(image_para(rids["05"], *img_meta["05"][1], 105, "05_edit"))
    records_rows = [
        ["#", "ชื่อจุด", "จุดประสงค์", "การทำงาน", "ตารางต้นทาง / ปลายทาง"],
        ["2.1", "ช่องค้นหา (Search)",
         "กรองตารางตาม GL Code หรือ GL Group",
         "กรองทันทีขณะพิมพ์ ผลการกรองสะท้อนที่ตัวนับ (ดูข้อ 2.2)",
         "กรองข้อมูลฝั่งหน้าเว็บ"],
        ["2.2", "คำอธิบายสี + ตัวนับ (Legend + count pill)",
         "บอกสีประจำ GL Code / GL Group และจำนวนแถว",
         "ป้ายตัวนับแสดงเป็น \"x / y records\" (x = จำนวนแถวที่กรองได้, y = จำนวนแถวทั้งหมด)",
         "—"],
        ["2.3", "ปุ่ม Export CSV",
         "ดาวน์โหลดรายการที่กรองอยู่เป็นไฟล์ CSV",
         "ส่งออกเฉพาะแถวที่แสดงอยู่ (รองรับภาษาไทย, UTF-8 BOM)",
         "จาก `cfg_master.gl_group_mapping` ⨝ `gl_group_dim`"],
        ["2.4", "ตารางข้อมูล (เรียงลำดับได้ + รวมแถว + ปุ่ม Edit/Delete)",
         "แสดง / แก้ไข / ลบการจับคู่",
         "คลิกหัวคอลัมน์เพื่อเรียงลำดับ · แถวที่อยู่ติดกันและมี GL Group เดียวกันจะถูก "
         "\"รวมแถว (Merge)\" ในคอลัมน์ GL Group (ดูคำอธิบายด้านล่าง) · ปุ่ม Edit ดึงค่าขึ้นฟอร์มด้านบน "
         "· ปุ่ม Delete เปิดหน้าต่างยืนยัน",
         "ต้นทาง: `cfg_master.gl_group_mapping` ⨝ `gl_group_dim` ผ่าน `GET /api/master/gl-group/list`"],
    ]
    parts.append(table(records_rows, DESC_WIDTHS))

    parts.append(para(
        run("การรวมแถว GL Group ที่ซ้ำกัน (Merged rows)", size_half_pt=22, bold=True,
            color="1E3A24"),
        space_before=80, space_after=60,
    ))
    parts.append(body_para(
        "เมื่อมี GL Code หลายรหัสที่ถูกจับคู่กับ GL Group เดียวกัน และอยู่ติดกันในตาราง "
        "ระบบจะ \"รวมแถว\" ของคอลัมน์ GL Group ให้เป็นช่องเดียว (rowspan) เพื่อให้เห็นชัดว่า "
        "รหัสเหล่านั้นอยู่กลุ่มเดียวกัน ในช่องที่รวมแล้วจะมีป้ายกำกับจำนวน เช่น \"3× MERGED\" "
        "(แสดงจำนวนรหัสในกลุ่มนั้น) ป้ายนี้มีเอฟเฟกต์เคลื่อนไหว (liquid) เพื่อสื่อว่าเป็นกลุ่มที่รวมกัน "
        "— เป็นเพียงการจัดรูปแบบการแสดงผลเท่านั้น ไม่กระทบข้อมูลที่บันทึก (แต่ละ GL Code ยังคงเป็น 1 แถวข้อมูล)"
    ))

    # ---- Delete ----------------------------------------------------------
    parts.append(heading("การลบรายการ"))
    parts.append(image_para(rids["06"], *img_meta["06"][1], 106, "06_delete"))
    delete_rows = [
        ["#", "ชื่อจุด", "จุดประสงค์", "การทำงาน", "ตารางต้นทาง / ปลายทาง"],
        ["2.4a", "หน้าต่างยืนยัน \"ยืนยันลบ\"",
         "ป้องกันการลบผิดพลาด (ลบถาวร ย้อนกลับไม่ได้ผ่าน UI)",
         "กดปุ่ม \"ลบรายการ\" เพื่อยืนยัน ผ่าน `DELETE /api/master/gl-group/delete`",
         "ปลายทาง: ลบแถวใน `cfg_master.gl_group_mapping`"],
    ]
    parts.append(table(delete_rows, DESC_WIDTHS))

    # ---- Data sources ----------------------------------------------------
    parts.append(heading("สรุปแหล่งข้อมูล (Data sources)"))
    src_rows = [
        ["ตาราง", "คำอธิบาย", "บทบาทในหน้านี้"],
        ["`cfg_master.sap_gl_code_ref` (code, name)",
         "รายการ GL Code อ้างอิงจาก SAP (อ่านอย่างเดียว, sync รายคืน; "
         "ปัจจุบัน seed 137 แถว, ระบบจริงสูงสุด ~430)",
         "ต้นทางของ dropdown GL Code (ข้อ 1.2)"],
        ["`cfg_master.gl_group_dim` (group_id, group_name)",
         "รายชื่อ GL Group (18 กลุ่ม) แยกเป็น dimension เพื่อเปลี่ยนชื่อกลุ่มได้โดยแก้แถวเดียว",
         "ต้นทางของ dropdown GL Group (1.3) และปลายทางเมื่อสร้างกลุ่มใหม่"],
        ["`cfg_master.gl_group_mapping` (gl_code PK, group_id FK)",
         "การจับคู่ GL Code → GL Group (1 รหัสต่อ 1 กลุ่ม)",
         "ปลายทางของ บันทึก/ลบ และต้นทางของตารางรายการ (ข้อ 2.4)"],
    ]
    parts.append(table(src_rows, SRC_WIDTHS))

    # ---- Sign-off --------------------------------------------------------
    parts.append(heading("ช่องลงนามอนุมัติ (Sign-off)"))
    sign_rows = [
        ["บทบาท", "ชื่อ-นามสกุล", "ลายเซ็น", "วันที่"],
        ["ผู้จัดทำ", "", "", ""],
        ["ผู้ตรวจสอบ", "", "", ""],
        ["ผู้อนุมัติ", "", "", ""],
    ]
    # make sign-off rows taller for handwriting
    parts.append(_sign_table(sign_rows, SIGN_WIDTHS))

    return "".join(parts)


def _sign_table(rows, col_widths_dxa):
    """Like table() but data rows have a tall fixed height for signing."""
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
                size_half_pt=(18 if is_header else 18),
            )
            tr.append(tcell(content, width_dxa=col_widths_dxa[ci], fill=fill))
        tr.append('</w:tr>')
        tbl.append("".join(tr))
    tbl.append('</w:tbl>')
    tbl.append(para(run("", size_half_pt=8), space_after=80))
    return "".join(tbl)


# --------------------------------------------------------------------------- #
# Static OOXML parts
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
    """image_rels: list of (rId, mediaFileName)."""
    rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    for rid, fname in image_rels:
        rels.append(
            f'<Relationship Id="{rid}" '
            f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
            f'Target="media/{fname}"/>'
        )
    rels.append('</Relationships>')
    return "".join(rels)


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
    print("[1/3] Annotating screenshots with Pillow ...")
    img_meta = build_annotated_images()
    for k, (p, size) in img_meta.items():
        print(f"      {k}: {p}  {size}")

    # Assign relationship + media names per image, ordered.
    order = ["01", "02", "03", "04", "05", "06"]
    media_names = {
        "01": "image1.png", "02": "image2.png", "03": "image3.png",
        "04": "image4.png", "05": "image5.png", "06": "image6.png",
    }
    rids = {k: f"rId{i+10}" for i, k in enumerate(order)}  # rId10..rId15
    image_rels = [(rids[k], media_names[k]) for k in order]

    print("[2/3] Building OOXML document.xml ...")
    body = build_body(img_meta, rids)
    doc_xml = document_xml(body)

    print("[3/3] Writing .docx zip ...")
    if os.path.exists(DOCX_PATH):
        os.remove(DOCX_PATH)
    with zipfile.ZipFile(DOCX_PATH, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types_xml())
        z.writestr("_rels/.rels", root_rels_xml())
        z.writestr("word/document.xml", doc_xml.encode("utf-8"))
        z.writestr("word/_rels/document.xml.rels", document_rels_xml(image_rels))
        for k in order:
            with open(img_meta[k][0], "rb") as f:
                z.writestr(f"word/media/{media_names[k]}", f.read())

    print(f"DONE: {DOCX_PATH}  ({os.path.getsize(DOCX_PATH)} bytes)")


if __name__ == "__main__":
    main()
