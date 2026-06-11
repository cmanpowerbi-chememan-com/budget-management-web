# -*- coding: utf-8 -*-
"""
Generator for the Hide Document Number User Sign-off Specification (.docx).

Module 08 — Part C, master-table editing (Hide SAP Document Number per period).

THIRD doc in the series. Reuses the proven OOXML + Pillow helpers from
build_edit_orgcode_costcenter_spec.py VERBATIM. Only content, image list,
marker coordinates and output filename differ.

HARD CONSTRAINTS honoured:
  - NO package installation. Only Python standard library + Pillow (installed).
  - The .docx is built BY HAND as Office Open XML (WordprocessingML).
  - Thai text uses Leelawadee UI on w:ascii / w:hAnsi / w:cs, with w:szCs == w:sz.
  - document.xml is UTF-8 encoded.

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
DOCX_PATH = os.path.join(SIGNOFF_DIR, "08_hide_document_number_spec.docx")
SRC_DIR = os.path.join(PROJECT_ROOT, "bin", "verify_0008")

os.makedirs(ASSETS_DIR, exist_ok=True)

# Brand gold
GOLD = (201, 150, 61)          # #C9963D
GOLD_DARK = (140, 100, 35)     # darker outline for legibility
WHITE = (255, 255, 255)

NUM_FONT_PATH = r"C:\Windows\Fonts\arialbd.ttf"

THAI_FONT = "Leelawadee UI"    # ships with Windows, Thai-capable

# Source images are calibrated for ~1456-wide canvas; actual files are 1440-wide.
# We scale incoming marker coords by (actual_width / CALIB_WIDTH) per-image.
CALIB_WIDTH = 1456.0

# --------------------------------------------------------------------------- #
# Pillow annotation helpers (VERBATIM from orgcode-costcenter generator)
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
    sx, sy = cx + ux * (radius + 1), cy + uy * (radius + 1)
    draw.line([(sx + 1, sy + 1), (tx + 1, ty + 1)], fill=GOLD_DARK, width=2)
    draw.line([(sx, sy), (tx, ty)], fill=GOLD, width=2)
    draw.ellipse([tx - 3, ty - 3, tx + 3, ty + 3], fill=GOLD, outline=GOLD_DARK)


def _draw_circle_marker(draw, label, cx, cy, tx, ty, radius=16):
    """Filled gold circle with white bold centered number, dark outline, leader."""
    _draw_leader(draw, cx, cy, tx, ty, radius)
    draw.ellipse(
        [cx - radius + 2, cy - radius + 2, cx + radius + 2, cy + radius + 2],
        fill=(0, 0, 0, 60),
    )
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
    _draw_leader(draw, cx, cy, tx, ty, int(w / 2))
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
    """markers: list of dicts {label, cx, cy, tx, ty, shape}.

    Marker coords are given on a CALIB_WIDTH (~1456) canvas; they are scaled to
    the actual image width before drawing.
    """
    src = os.path.join(SRC_DIR, src_name)
    im = Image.open(src).convert("RGBA")
    scale = im.size[0] / CALIB_WIDTH
    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for m in markers:
        cx, cy = m["cx"] * scale, m["cy"] * scale
        tx, ty = m["tx"] * scale, m["ty"] * scale
        if m.get("shape") == "pill":
            _draw_pill_marker(draw, m["label"], cx, cy, tx, ty)
        else:
            _draw_circle_marker(draw, m["label"], cx, cy, tx, ty)
    out = Image.alpha_composite(im, overlay).convert("RGB")
    out_path = os.path.join(ASSETS_DIR, out_name)
    out.save(out_path, "PNG")
    return out_path, out.size


def build_annotated_images():
    results = {}

    # 01 overview — circled numbers
    results["01"] = annotate(
        "01_load.png", "hd_01_overview.png",
        [
            {"label": "1", "cx": 28, "cy": 32, "tx": 135, "ty": 32},
            {"label": "2", "cx": 28, "cy": 143, "tx": 150, "ty": 143},
            {"label": "3", "cx": 825, "cy": 262, "tx": 858, "ty": 262},
            {"label": "4", "cx": 28, "cy": 338, "tx": 150, "ty": 338},
            {"label": "5", "cx": 28, "cy": 559, "tx": 150, "ty": 559},
        ],
    )

    # 02 editor (after paste, 4 chips) — pill labels
    results["02"] = annotate(
        "03_after_paste.png", "hd_02_editor.png",
        [
            {"label": "1.1", "cx": 365, "cy": 315, "tx": 380, "ty": 405, "shape": "pill"},
            {"label": "1.2", "cx": 40, "cy": 453, "tx": 165, "ty": 440, "shape": "pill"},
            {"label": "1.3", "cx": 783, "cy": 412, "tx": 783, "ty": 452, "shape": "pill"},
            {"label": "1.4", "cx": 1046, "cy": 412, "tx": 1046, "ty": 452, "shape": "pill"},
            {"label": "1.5", "cx": 1237, "cy": 535, "tx": 1237, "ty": 495, "shape": "pill"},
        ],
    )

    # 03 validation (format error) — pill label
    results["03"] = annotate(
        "04_format_error.png", "hd_03_validate.png",
        [
            {"label": "1.2a", "cx": 40, "cy": 530, "tx": 142, "ty": 512, "shape": "pill"},
        ],
    )

    # 04 records (grid after save) — pill labels
    results["04"] = annotate(
        "07_grid_after_save.png", "hd_04_records.png",
        [
            {"label": "2.1", "cx": 40, "cy": 603, "tx": 160, "ty": 603, "shape": "pill"},
            {"label": "2.2", "cx": 1140, "cy": 603, "tx": 1175, "ty": 603, "shape": "pill"},
            {"label": "2.3", "cx": 110, "cy": 712, "tx": 168, "ty": 735, "shape": "pill"},
            {"label": "2.3a", "cx": 457, "cy": 700, "tx": 457, "ty": 742, "shape": "pill"},
            {"label": "2.3b", "cx": 545, "cy": 700, "tx": 495, "ty": 742, "shape": "pill"},
        ],
    )

    # 05 save notice (modal capture, 1440x924) — pill label on modal title
    results["05"] = annotate(
        "06_save_notice.png", "hd_05_save.png",
        [
            {"label": "3.1", "cx": 620, "cy": 230, "tx": 620, "ty": 280, "shape": "pill"},
        ],
    )

    return results


# --------------------------------------------------------------------------- #
# OOXML (WordprocessingML) builders (VERBATIM from orgcode-costcenter generator)
# --------------------------------------------------------------------------- #
EMU_PER_PX = 9525
TARGET_WIDTH_IN = 6.3
EMU_PER_IN = 914400
TARGET_WIDTH_EMU = int(TARGET_WIDTH_IN * EMU_PER_IN)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


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
    """Inline image drawing scaled to width_in (default TARGET) keeping aspect."""
    cx = int((width_in or TARGET_WIDTH_IN) * EMU_PER_IN)
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


# --------------------------------------------------------------------------- #
# Document body assembly
# --------------------------------------------------------------------------- #
DESC_WIDTHS = [620, 1500, 2300, 2740, 2200]   # # | ชื่อจุด | จุดประสงค์ | การทำงาน | ตาราง
SRC_WIDTHS = [3200, 3560, 2600]               # ตาราง | คำอธิบาย | บทบาท
SIGN_WIDTHS = [1900, 3000, 2460, 2000]        # บทบาท | ชื่อ | ลายเซ็น | วันที่
META_WIDTHS = [2700, 6660]


def build_body(img_meta, rids):
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
        run("ส่วน C — การแก้ไขข้อมูลตารางหลัก (Master Tables) · หน้า: Hide Document Number",
            size_half_pt=24, bold=True, color="1E3A24"),
        space_after=160,
    ))

    meta_rows = [
        ["รายการ", "รายละเอียด"],
        ["เวอร์ชัน", "v0.2 (ฉบับร่าง)"],
        ["วันที่", "11 มิถุนายน 2569 (2026-06-11)"],
        ["ผู้จัดทำ", "ทีม Data Analytics"],
        ["สถานะ", "รออนุมัติจากผู้ใช้"],
    ]
    parts.append(table(meta_rows, META_WIDTHS))

    # ---- Context ---------------------------------------------------------
    parts.append(heading("บริบทและขอบเขต (Context)"))
    parts.append(body_para(
        "หน้า Hide Document Number เป็นหน้าสำหรับผู้ดูแลระบบ (Master Table Admins) เท่านั้น "
        "ใช้กำหนดกฎ ซ่อน เลขที่เอกสาร (SAP Document Number) ในงวดบัญชี (ปีงบ + เดือน) ที่กำหนด "
        "เพื่อไม่ให้เอกสารนั้นถูกนับและแสดงในรายงานงบประมาณและ dashboard — "
        "ใช้สำหรับการควบคุมงวดที่ปิดแล้ว (closed period), การตรวจสอบ (audit) และรายการปรับปรุง (adjustment) "
        "· 1 เอกสาร + 1 งวด = 1 แถว (ซ่อนหลายงวดต้องบันทึกหลายแถว) "
        "· ฐานข้อมูล Microsoft Fabric SQL Database `cfg_master.hide_document_number` "
        "(คีย์หลัก 3 คอลัมน์: doc_num, fiscal_year, fiscal_month)"
    ))
    parts.append(para(
        run("หมายเหตุ: หน้านี้แสดงรายการแบบจัดกลุ่มตามงวด (Period); "
            "ก่อนบันทึกระบบจะตรวจสอบว่าเลขเอกสารมีจริงใน SAP เสมอ (Fabric Lakehouse `gold_sap_gl_trans`)",
            size_half_pt=20, italic=True, color="8C6423"),
        space_before=40, space_after=80,
    ))
    parts.append(para(
        run("ผู้ดูแลระบบที่ได้รับสิทธิ์ (4 คน)", size_half_pt=22, bold=True,
            color="1E3A24"),
        space_before=80, space_after=60,
    ))
    parts.append(bullet("nipapornt@chememan.com"))
    parts.append(bullet("warapornt@chememan.com"))
    parts.append(bullet("jakkaritw@chememan.com"))
    parts.append(bullet("piyadad@chememan.com  (ปิยะดา ดวงพลจันทร์)"))

    # ---- Overview --------------------------------------------------------
    parts.append(heading("ภาพรวมหน้าจอ"))
    parts.append(image_para(rids["01"], *img_meta["01"][1], 101, "hd_01_overview"))
    overview_rows = [
        ["#", "ชื่อจุด", "จุดประสงค์", "การทำงาน", "ตารางต้นทาง / ปลายทาง"],
        ["①", "แถบเมนูหลัก (Navigation)",
         "สลับไปหน้า Master อื่น + กลับหน้าแรก + สลับธีม",
         "ลิงก์ไปหน้า Master อื่นๆ ตามแถบเมนูด้านบนของภาพ · ปุ่มกลับหน้าแรก (Home) · ปุ่มสลับธีม (สว่าง/มืด)",
         "—"],
        ["②", "ส่วนหัวหน้า (Breadcrumb + ชื่อหน้า)",
         "บอกตำแหน่งและชื่อโมดูล",
         "breadcrumb \"Hide Document Number\" + \"Module 08 · Document Hiding\"",
         "—"],
        ["③", "แถบสรุปตัวเลข (Summary chips)",
         "สรุปสถานะการซ่อนแบบเรียลไทม์",
         "Hidden Docs (เอกสารที่ซ่อน) · Periods (งวดที่มีการซ่อน) · "
         "Not hidden (เอกสารที่ยังไม่ถูกซ่อน) · SAP Total (เอกสารทั้งหมดจาก SAP) — "
         "หมายเหตุ: Not hidden / SAP Total ในหน้า demo (SWA) ยังไม่ดึงข้อมูลจาก SAP จึงแสดง 0 · "
         "จะเชื่อมต่อจริงในเวอร์ชัน React",
         "Hidden Docs / Periods: `cfg_master.hide_document_number` · "
         "Not hidden / SAP Total: `dbo.gold_sap_gl_trans` (เวอร์ชัน React)"],
        ["④", "ส่วนที่ 1 — กล่อง Mapping editor",
         "ฟอร์มเพิ่มกฎการซ่อน",
         "ดูรายละเอียดข้อ 1.1–1.5",
         "—"],
        ["⑤", "ส่วนที่ 2 — กล่อง Mapping records",
         "การ์ดแสดงกฎการซ่อน (จัดกลุ่มตามงวด)",
         "ดูรายละเอียดข้อ 2.1–2.3",
         "`cfg_master.hide_document_number`"],
    ]
    parts.append(table(overview_rows, DESC_WIDTHS))

    # ---- Section 1: Mapping editor --------------------------------------
    parts.append(heading("ส่วนที่ 1 — Mapping editor (กล่องเพิ่มกฎการซ่อน)"))
    parts.append(image_para(rids["02"], *img_meta["02"][1], 102, "hd_02_editor"))
    parts.append(image_para(rids["03"], *img_meta["03"][1], 103, "hd_03_validate"))
    editor_rows = [
        ["#", "ชื่อจุด", "จุดประสงค์", "การทำงาน", "ตารางต้นทาง / ปลายทาง"],
        ["1.1", "ป้ายโหมด \"เพิ่มใหม่\"",
         "บอกว่าเป็นการเพิ่มกฎใหม่",
         "จำนวนเอกสารที่เลือกแสดงเป็น \"N SELECTED\"",
         "—"],
        ["1.2", "ช่อง Document Number (ใส่ได้หลายเลข)",
         "ระบุเลขที่เอกสาร 10 หลักที่จะซ่อน",
         "พิมพ์เลข 10 หลัก → กด Enter / Tab / \",\" เพื่อเพิ่มเป็นป้าย (chip) "
         "· วางหลายเลขพร้อมกันได้ · Backspace ลบตัวล่าสุด",
         "ตรวจสอบกับ `dbo.gold_sap_gl_trans` (Lakehouse) ตอนกดบันทึก — ต้องเป็นเลขเอกสารที่มีอยู่จริงใน SAP"],
        ["1.2a", "การตรวจรูปแบบ (Format)",
         "กันเลขผิดรูปแบบ",
         "ถ้าไม่ใช่เลข 10 หลัก จะขึ้นข้อความสีแดง \"Format ผิด: ต้องเป็นเลข 10 หลัก\"",
         "—"],
        ["1.3", "ช่อง Fiscal Year",
         "ปีงบประมาณที่จะซ่อน",
         "กรอกปี ค.ศ. (2020–2099)",
         "—"],
        ["1.4", "ช่อง Month",
         "เดือนที่จะซ่อน",
         "เลือกเดือน 1–12 (ปฏิทินงบ)",
         "—"],
        ["1.5", "ปุ่ม บันทึก",
         "บันทึกกฎการซ่อน",
         "ตรวจรูปแบบ → ตรวจกับ Lakehouse → สร้างหลายแถว (เอกสารที่เลือกแต่ละตัว × งวด) "
         "· คู่ที่มีอยู่แล้วจะถูกข้าม/แจ้งเตือน (รหัส 409)",
         "ปลายทาง: `cfg_master.hide_document_number`"],
    ]
    parts.append(table(editor_rows, DESC_WIDTHS))

    # ---- Section 2: Mapping records -------------------------------------
    parts.append(heading("ส่วนที่ 2 — Mapping records (การ์ดรายการ)"))
    parts.append(image_para(rids["04"], *img_meta["04"][1], 104, "hd_04_records"))
    records_rows = [
        ["#", "ชื่อจุด", "จุดประสงค์", "การทำงาน", "ตารางต้นทาง / ปลายทาง"],
        ["2.1", "ช่องค้นหา (Search)",
         "กรองการ์ด",
         "ค้นหาตาม Document / Year / Month ทันทีขณะพิมพ์",
         "กรองข้อมูลฝั่งหน้าเว็บ"],
        ["2.2", "คำอธิบายสี + ตัวนับ (Legend + count)",
         "บอกสีประจำ Document / Period และจำนวน",
         "แสดง \"x / y mappings\" + บรรทัดสรุป \"x Documents · y hidden entries · z Periods\"",
         "—"],
        ["2.3", "การ์ด (จัดกลุ่มตามงวด Period)",
         "แสดง / เพิ่ม / ลบ กฎการซ่อน",
         "แต่ละการ์ด = 1 งวด (เช่น \"Mar 2026 ×3\" / \"2026-03\" / HIDES 3 DOCUMENTS) พร้อมเลขเอกสารที่ซ่อนในงวดนั้น",
         "ต้นทาง: `cfg_master.hide_document_number` (GET /list, period = YYYY-MM)"],
        ["2.3a", "ปุ่มเพิ่ม (ไอคอนดินสอ)",
         "เพิ่มเอกสารในงวดนั้น",
         "ดึงงวดขึ้นไปที่ฟอร์มด้านบนเพื่อเพิ่มเลขเอกสาร",
         "—"],
        ["2.3b", "ปุ่มลบ (ไอคอนถังขยะ)",
         "ลบกฎการซ่อนของงวดนั้น",
         "มีการยืนยันก่อนลบ · เป็นการลบถาวร (hard delete)",
         "ปลายทาง: ลบแถวใน `cfg_master.hide_document_number` (คลิกป้าย × บนเลขเอกสาร = ลบทีละรายการ)"],
    ]
    parts.append(table(records_rows, DESC_WIDTHS))

    # ---- Save ------------------------------------------------------------
    parts.append(heading("การบันทึก"))
    parts.append(image_para(rids["05"], *img_meta["05"][1], 105, "hd_05_save",
                            width_in=3.6))
    save_rows = [
        ["#", "ชื่อจุด", "จุดประสงค์", "การทำงาน", "ตารางต้นทาง / ปลายทาง"],
        ["3.1", "แจ้งบันทึกสำเร็จ",
         "ยืนยันผลการบันทึก",
         "หน้าต่าง \"บันทึกสำเร็จ\" สรุปจำนวน เช่น \"บันทึก N รายการ · งวด (สร้าง X · ข้ามเพราะมีอยู่แล้ว Y)\" "
         "พร้อมรายการ Action / Documents / Period",
         "—"],
    ]
    parts.append(table(save_rows, DESC_WIDTHS))

    # ---- Data sources ----------------------------------------------------
    parts.append(heading("สรุปแหล่งข้อมูล (Data sources)"))
    src_rows = [
        ["ตาราง", "คำอธิบาย", "บทบาทในหน้านี้"],
        ["`cfg_master.hide_document_number` (doc_num, fiscal_year, fiscal_month — คีย์หลัก 3 คอลัมน์)",
         "ตารางเก็บกฎ \"ซ่อนเอกสารในงวด\" บน Fabric SQL Database",
         "ปลายทางของการบันทึก/ลบ และต้นทางของการ์ด (ข้อ 2.3)"],
        ["`dbo.gold_sap_gl_trans` (accounting_doc_number)",
         "ข้อมูล G/L transactions จาก SAP บน Fabric Lakehouse (SQL Analytics Endpoint, อ่านอย่างเดียว)",
         "ใช้ตรวจสอบว่าเลขเอกสารมีอยู่จริงก่อนบันทึก (ข้อ 1.5) · "
         "การคำนวณ Not hidden / SAP Total จะเชื่อมต่อในเวอร์ชัน React (demo แสดง 0)"],
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
    parts.append(_sign_table(sign_rows, SIGN_WIDTHS))

    return "".join(parts)


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
                size_half_pt=(18 if is_header else 18),
            )
            tr.append(tcell(content, width_dxa=col_widths_dxa[ci], fill=fill))
        tr.append('</w:tr>')
        tbl.append("".join(tr))
    tbl.append('</w:tbl>')
    tbl.append(para(run("", size_half_pt=8), space_after=80))
    return "".join(tbl)


# --------------------------------------------------------------------------- #
# Static OOXML parts (VERBATIM)
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

    order = ["01", "02", "03", "04", "05"]
    media_names = {
        "01": "image1.png", "02": "image2.png", "03": "image3.png",
        "04": "image4.png", "05": "image5.png",
    }
    rids = {k: f"rId{i+10}" for i, k in enumerate(order)}  # rId10..rId14
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
