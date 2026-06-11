# -*- coding: utf-8 -*-
"""
Generator for the Edit Org & Cost center User Sign-off Specification (.docx).

Module 07 — Part C, master-table editing (Orgcode <-> Cost Center mapping).

This is the SECOND doc in the series. It reuses the proven OOXML + Pillow
helpers from build_edit_gl_group_spec.py VERBATIM. Only content, image list,
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
DOCX_PATH = os.path.join(SIGNOFF_DIR, "07_edit_orgcode_costcenter_spec.docx")

os.makedirs(ASSETS_DIR, exist_ok=True)

# Brand gold
GOLD = (201, 150, 61)          # #C9963D
GOLD_DARK = (140, 100, 35)     # darker outline for legibility
WHITE = (255, 255, 255)

NUM_FONT_PATH = r"C:\Windows\Fonts\arialbd.ttf"

THAI_FONT = "Leelawadee UI"    # ships with Windows, Thai-capable

# --------------------------------------------------------------------------- #
# Pillow annotation helpers (VERBATIM from gl-group generator)
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
    results["01"] = annotate(
        "verify_01_load.png", "occ_01_overview.png",
        [
            {"label": "1", "cx": 25, "cy": 32, "tx": 130, "ty": 32},
            {"label": "2", "cx": 25, "cy": 135, "tx": 55, "ty": 143},
            {"label": "3", "cx": 700, "cy": 276, "tx": 742, "ty": 276},
            {"label": "4", "cx": 25, "cy": 352, "tx": 70, "ty": 352},
            {"label": "5", "cx": 25, "cy": 581, "tx": 70, "ty": 581},
        ],
    )

    # 02 cost center multi-select — pill labels
    results["02"] = annotate(
        "verify_03_cc_selected.png", "occ_02_cc.png",
        [
            {"label": "1.1", "cx": 305, "cy": 326, "tx": 250, "ty": 346, "shape": "pill"},
            {"label": "1.2", "cx": 45, "cy": 461, "tx": 75, "ty": 461, "shape": "pill"},
        ],
    )

    # 03 orgcode input + Save button — pill labels
    results["03"] = annotate(
        "verify_04_org_selected.png", "occ_03_org.png",
        [
            {"label": "1.3", "cx": 575, "cy": 485, "tx": 595, "ty": 485, "shape": "pill"},
            {"label": "1.4", "cx": 1157, "cy": 447, "tx": 1157, "ty": 485, "shape": "pill"},
        ],
    )

    # 04 records / search / view switch — pill labels
    results["04"] = annotate(
        "verify_05_by_org.png", "occ_04_records.png",
        [
            {"label": "2.1", "cx": 45, "cy": 641, "tx": 75, "ty": 641, "shape": "pill"},
            {"label": "2.2", "cx": 1062, "cy": 641, "tx": 1090, "ty": 641, "shape": "pill"},
            {"label": "2.3", "cx": 45, "cy": 705, "tx": 80, "ty": 701, "shape": "pill"},
        ],
    )

    # 05 cards crop — pill labels (small image ~414x320)
    results["05"] = annotate(
        "Screenshot 2026-06-02 172232.png", "occ_05_cards.png",
        [
            {"label": "2.4", "cx": 78, "cy": 92, "tx": 78, "ty": 116, "shape": "pill"},
            {"label": "2.4a", "cx": 300, "cy": 92, "tx": 308, "ty": 116, "shape": "pill"},
            {"label": "2.4b", "cx": 372, "cy": 92, "tx": 346, "ty": 116, "shape": "pill"},
            {"label": "2.4c", "cx": 20, "cy": 200, "tx": 60, "ty": 200, "shape": "pill"},
        ],
    )

    # 06 save result — circled number
    results["06"] = annotate(
        "verify_06_save.png", "occ_06_save.png",
        [
            {"label": "3.1", "cx": 700, "cy": 276, "tx": 742, "ty": 276, "shape": "pill"},
        ],
    )

    # 07 duplicate modal — pill label
    results["07"] = annotate(
        "verify_07_duplicate.png", "occ_07_duplicate.png",
        [
            {"label": "3.2", "cx": 640, "cy": 250, "tx": 640, "ty": 285, "shape": "pill"},
        ],
    )

    return results


# --------------------------------------------------------------------------- #
# OOXML (WordprocessingML) builders (VERBATIM from gl-group generator)
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
        run("ส่วน C — การแก้ไขข้อมูลตารางหลัก (Master Tables) · หน้า: Edit Org & Cost center",
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
        "หน้า Edit Org & Cost center เป็นหน้าสำหรับผู้ดูแลระบบ (Master Table Admins) เท่านั้น "
        "ใช้จับคู่ Orgcode (หน่วยงาน) กับ Cost Center แบบหลายต่อหลาย (many-to-many) "
        "เพื่อใช้กำหนดสิทธิ์การมองเห็นข้อมูล (RLS) และจัดกลุ่มรายงานงบประมาณตามหน่วยงาน "
        "ระบบควบคุมสิทธิ์ด้วย Azure Entra ID group `master-table-admins` "
        "ฐานข้อมูลใช้ Microsoft Fabric SQL Database (schema `cfg_master`)."
    ))
    parts.append(para(
        run("หมายเหตุ: หน้านี้ไม่มีโหมดแก้ไข (Edit) — การแก้ไขทำโดยลบคู่เดิมแล้วเพิ่มใหม่; "
            "และเพิ่ม Cost Center ได้ทีละหลายตัว",
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
    parts.append(image_para(rids["01"], *img_meta["01"][1], 101, "occ_01_overview"))
    overview_rows = [
        ["#", "ชื่อจุด", "จุดประสงค์", "การทำงาน", "ตารางต้นทาง / ปลายทาง"],
        ["①", "แถบเมนูหลัก (Navigation)",
         "สลับไปหน้า Master อื่น + กลับหน้าแรก + สลับธีม",
         "ลิงก์ไปหน้า Master อื่นๆ ตามแถบเมนูด้านบนของภาพ · ปุ่มกลับหน้าแรก (Home) · ปุ่มสลับธีม (สว่าง/มืด)",
         "—"],
        ["②", "ส่วนหัวหน้า (Breadcrumb + ชื่อหน้า)",
         "บอกตำแหน่งและชื่อโมดูล",
         "breadcrumb \"Orgcode & Cost Center Mapping\" + \"Module 07 · Master Data\"",
         "—"],
        ["③", "แถบสรุปตัวเลข (Summary chips)",
         "สรุปสถานะการจับคู่แบบเรียลไทม์",
         "Cost Centers (CC ที่จับคู่แล้ว) · Orgcodes (หน่วยงานที่จับคู่แล้ว) · "
         "Unmapped (หน่วยงานที่ยังไม่จับคู่) · SAP Total (จำนวน Orgcode ทั้งหมด)",
         "อ่านจาก `cfg_master.orgcode_costcenter_map` + `dbo.mas_employee_data`"],
        ["④", "ส่วนที่ 1 — กล่อง Mapping editor",
         "ฟอร์มเพิ่มการจับคู่",
         "ดูรายละเอียดข้อ 1.1–1.4",
         "—"],
        ["⑤", "ส่วนที่ 2 — กล่อง Mapping records",
         "การ์ดแสดงผลการจับคู่",
         "ดูรายละเอียดข้อ 2.1–2.4",
         "`cfg_master.orgcode_costcenter_map`"],
    ]
    parts.append(table(overview_rows, DESC_WIDTHS))

    # ---- Section 1: Mapping editor --------------------------------------
    parts.append(heading("ส่วนที่ 1 — Mapping editor (กล่องเพิ่มการจับคู่)"))
    parts.append(image_para(rids["02"], *img_meta["02"][1], 102, "occ_02_cc"))
    parts.append(image_para(rids["03"], *img_meta["03"][1], 103, "occ_03_org"))
    editor_rows = [
        ["#", "ชื่อจุด", "จุดประสงค์", "การทำงาน", "ตารางต้นทาง / ปลายทาง"],
        ["1.1", "ป้ายโหมด \"เพิ่มใหม่\"",
         "บอกว่าเป็นการเพิ่มคู่ใหม่",
         "หน้านี้ไม่มีโหมดแก้ไข — การแก้ไขทำโดยลบคู่เดิมแล้วเพิ่มใหม่",
         "—"],
        ["1.2", "ช่อง Cost Center (เลือกได้หลายตัว)",
         "เลือก Cost Center ที่จะผูกกับหน่วยงาน",
         "พิมพ์ค้นหา แล้วคลิกเลือกได้หลายตัว แต่ละตัวกลายเป็นป้าย (chip) "
         "กดเครื่องหมาย × เพื่อลบได้ · แต่ละคู่จะถูกบันทึกแยกเป็นคนละแถว",
         "ต้นทาง: `dbo.gold_sap_m_cost_center` (Fabric Lakehouse, อ่านอย่างเดียว)"],
        ["1.3", "ช่อง Orgcode · จาก SAP (เลือกตัวเดียว)",
         "เลือกหน่วยงานที่จะรับ Cost Center",
         "พิมพ์ค้นหารหัสหรือชื่อหน่วยงาน เลือกได้ 1 หน่วยงาน · "
         "1 Orgcode รับได้หลาย Cost Center",
         "ต้นทาง: `dbo.mas_employee_data` (รหัสหน่วยงาน + ชื่อหน่วยงานภาษาไทย)"],
        ["1.4", "ปุ่ม บันทึก",
         "บันทึกทุกคู่ (Cost Center ที่เลือกแต่ละตัว × Orgcode)",
         "สร้างหลายแถวพร้อมกัน · ถ้าคู่ใดมีอยู่แล้วจะถูกแจ้งเตือน (รหัส 409)",
         "ปลายทาง: `cfg_master.orgcode_costcenter_map`"],
    ]
    parts.append(table(editor_rows, DESC_WIDTHS))

    # ---- Section 2: Mapping records -------------------------------------
    parts.append(heading("ส่วนที่ 2 — Mapping records (การ์ดรายการ)"))
    parts.append(image_para(rids["04"], *img_meta["04"][1], 104, "occ_04_records"))
    parts.append(image_para(rids["05"], *img_meta["05"][1], 105, "occ_05_cards",
                            width_in=3.2))
    records_rows = [
        ["#", "ชื่อจุด", "จุดประสงค์", "การทำงาน", "ตารางต้นทาง / ปลายทาง"],
        ["2.1", "ช่องค้นหา (Search)",
         "กรองการ์ด",
         "กรองตาม Cost Center / Orgcode / ชื่อหน่วยงาน ทันทีขณะพิมพ์",
         "กรองข้อมูลฝั่งหน้าเว็บ"],
        ["2.2", "คำอธิบายสี + ตัวนับ (Legend + count)",
         "บอกสีประจำ Cost Center / Orgcode และจำนวนคู่ที่แสดง",
         "แสดง \"x / y mappings\"",
         "—"],
        ["2.3", "สวิตช์มุมมอง BY COST CENTER / BY ORGCODE",
         "สลับการจัดกลุ่มการ์ด",
         "BY COST CENTER: การ์ด = 1 Cost Center → Orgcode หลายตัว · "
         "BY ORGCODE: การ์ด = 1 Orgcode → Cost Center หลายตัว (พร้อมบรรทัดสรุปจำนวน)",
         "—"],
        ["2.4", "การ์ด chip-grid",
         "แสดง / เพิ่ม / ลบ การจับคู่",
         "แต่ละการ์ด = คีย์หลัก (เช่น `10SP010000 ×3`) พร้อมป้ายของอีกฝั่ง "
         "(เช่น 1110000 ฝ่ายบัญชี)",
         "ต้นทาง: `cfg_master.orgcode_costcenter_map` เชื่อมกับ `dbo.mas_employee_data` "
         "(join) ผ่าน `GET /api/master/orgcode-costcenter/list`"],
        ["2.4a", "ปุ่มเพิ่ม (ไอคอนดินสอ)",
         "เพิ่มการจับคู่ใหม่ของคีย์นั้น",
         "ดึงคีย์ขึ้นไปที่ฟอร์มด้านบนเพื่อเลือกอีกฝั่งเพิ่ม (ไม่ใช่การแก้ไขค่าเดิม)",
         "—"],
        ["2.4b", "ปุ่มลบการ์ด (ไอคอนถังขยะ)",
         "ลบทุกการจับคู่ของคีย์นั้น",
         "มีหน้าต่างยืนยันก่อนลบ",
         "ปลายทาง: ลบหลายแถวใน `cfg_master.orgcode_costcenter_map`"],
        ["2.4c", "ป้าย × (chip)",
         "ลบการจับคู่ทีละคู่",
         "คลิกเครื่องหมาย × บนป้าย",
         "ปลายทาง: ลบ 1 แถวใน `cfg_master.orgcode_costcenter_map`"],
    ]
    parts.append(table(records_rows, DESC_WIDTHS))

    # ---- Save & duplicate guard -----------------------------------------
    parts.append(heading("การบันทึก & การกันข้อมูลซ้ำ"))
    parts.append(image_para(rids["06"], *img_meta["06"][1], 106, "occ_06_save"))
    parts.append(image_para(rids["07"], *img_meta["07"][1], 107, "occ_07_duplicate"))
    save_rows = [
        ["#", "ชื่อจุด", "จุดประสงค์", "การทำงาน", "ตารางต้นทาง / ปลายทาง"],
        ["3.1", "ผลหลังบันทึก",
         "ยืนยันบันทึกสำเร็จ",
         "ตัวเลขสรุปอัปเดต + ฟอร์มถูกล้างอัตโนมัติ + การ์ดที่เพิ่งเพิ่มถูกไฮไลต์",
         "—"],
        ["3.2", "แจ้งเตือนข้อมูลซ้ำ",
         "กันการบันทึกคู่ที่มีอยู่แล้ว",
         "หน้าต่าง \"ข้อมูลซ้ำ\" แสดงข้อความ \"คู่ (Cost Center, Orgcode) มีอยู่แล้ว\" — "
         "ตรวจทั้งฝั่งหน้าเว็บและฝั่ง backend (409)",
         "—"],
    ]
    parts.append(table(save_rows, DESC_WIDTHS))

    # ---- Data sources ----------------------------------------------------
    parts.append(heading("สรุปแหล่งข้อมูล (Data sources)"))
    src_rows = [
        ["ตาราง", "คำอธิบาย", "บทบาทในหน้านี้"],
        ["`cfg_master.orgcode_costcenter_map` (orgcode, cost_center — UNIQUE)",
         "ตารางจับคู่หลัก (junction table, many-to-many) บน Fabric SQL Database",
         "ปลายทางของการบันทึก/ลบ และต้นทางของการ์ด (ข้อ 2.4)"],
        ["`dbo.mas_employee_data` (orgcode, orgnameth)",
         "ข้อมูลพนักงาน/หน่วยงาน บน Fabric SQL Database",
         "ต้นทางของ dropdown Orgcode (ข้อ 1.3) และชื่อหน่วยงานที่แสดงในการ์ด"],
        ["`dbo.gold_sap_m_cost_center` (cost_center_id, cost_center_name)",
         "ทะเบียน Cost Center จาก SAP บน Fabric Lakehouse (SQL Analytics Endpoint, "
         "อ่านอย่างเดียว)",
         "ต้นทางของ dropdown Cost Center (ข้อ 1.2)"],
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

    order = ["01", "02", "03", "04", "05", "06", "07"]
    media_names = {
        "01": "image1.png", "02": "image2.png", "03": "image3.png",
        "04": "image4.png", "05": "image5.png", "06": "image6.png",
        "07": "image7.png",
    }
    rids = {k: f"rId{i+10}" for i, k in enumerate(order)}  # rId10..rId16
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
