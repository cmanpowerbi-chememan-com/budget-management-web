# -*- coding: utf-8 -*-
"""
Generator for the Budget Closing Date User Sign-off Specification (.docx).

Module 10 — Part C, master-table editing (budget submission deadline per
fiscal year). When the closing date passes, the Submit Budget form locks
(read-only).

FIFTH master-table doc in the series. Reuses the proven OOXML + Pillow helpers
from build_master_currency_spec.py VERBATIM. Only content, image list, marker
coordinates (now loaded from bin/bcd_coords.json) and output filename differ.

IMPORTANT: this page is a DESIGN MOCKUP / DEMO — not wired to a backend yet.
Numbers in the screenshots are illustrative; storage table labelled
"วางแผน — รอยืนยัน".

HARD CONSTRAINTS honoured:
  - NO package installation. Only Python standard library + Pillow (installed).
  - The .docx is built BY HAND as Office Open XML (WordprocessingML).
  - Thai text uses Leelawadee UI on w:ascii / w:hAnsi / w:cs, with w:szCs == w:sz.
  - document.xml is UTF-8 encoded.

Re-runnable: run _capture_budget_closing_date.py first (writes PNGs + coords),
then this; deletes/overwrites outputs each run.
"""

import os
import json
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
DOCX_PATH = os.path.join(SIGNOFF_DIR, "06_budget_closing_date.docx")
COORDS_PATH = os.path.join(PROJECT_ROOT, "bin", "bcd_coords.json")

os.makedirs(ASSETS_DIR, exist_ok=True)

# Brand gold
GOLD = (201, 150, 61)          # #C9963D
GOLD_DARK = (140, 100, 35)     # darker outline for legibility
WHITE = (255, 255, 255)

NUM_FONT_PATH = r"C:\Windows\Fonts\arialbd.ttf"

THAI_FONT = "Leelawadee UI"    # ships with Windows, Thai-capable

with open(COORDS_PATH, encoding="utf-8") as _f:
    COORDS = json.load(_f)

# --------------------------------------------------------------------------- #
# Pillow annotation helpers (VERBATIM from master-currency generator)
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
    results["01"] = annotate("bcd_01_overview.png", "bcd_01_overview.png", COORDS["01"])
    results["02"] = annotate("bcd_02_editor.png", "bcd_02_editor.png", COORDS["02"])
    results["04"] = annotate("bcd_04_edit.png", "bcd_04_edit.png", COORDS["04"])
    results["03"] = annotate("bcd_03_records.png", "bcd_03_records.png", COORDS["03"])
    results["05"] = annotate("bcd_05_save.png", "bcd_05_save.png", COORDS["05"])
    results["06"] = annotate("bcd_06_delete.png", "bcd_06_delete.png", COORDS["06"])
    return results


# --------------------------------------------------------------------------- #
# OOXML (WordprocessingML) builders (VERBATIM from master-currency generator)
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
        run("ส่วน C — การแก้ไขข้อมูลตารางหลัก (Master Tables) · หน้า: Budget Closing Date "
            "(วันปิดรับข้อมูลงบประมาณ)",
            size_half_pt=24, bold=True, color="1E3A24"),
        space_after=160,
    ))

    meta_rows = [
        ["รายการ", "รายละเอียด"],
        ["เวอร์ชัน", "v0.2 (ฉบับร่าง)"],
        ["วันที่", "14 มิถุนายน 2569 (2026-06-14)"],
        ["ผู้จัดทำ", "ทีม Data Analytics"],
        ["สถานะ", "รออนุมัติจากผู้ใช้"],
        ["ขอบเขตเอกสาร",
         "อธิบายหน้า Budget Closing Date — กำหนดวันปิดรับข้อมูลงบประมาณรายปี "
         "(ปีละ 1 วัน) สำหรับผู้ดูแลระบบ และผลของวันปิดต่อฟอร์มกรอกงบประมาณ "
         "(เมื่อถึงวันปิด ระบบล็อกฟอร์มเป็น read-only สำหรับผู้กรอกทั่วไป — "
         "ผู้ดูแลระบบยังแก้ไข/ส่งได้ตาม ADR-0012)"],
        ["การแก้ไขล่าสุด",
         "v0.2 — เพิ่มข้อยกเว้น admin-override-after-deadline ตาม ADR-0012 "
         "(หลังวันปิด ผู้ดูแลระบบยังแก้ไข + ส่งงบของฝ่ายใดก็ได้ → APPROVED โดยตรง)"],
    ]
    parts.append(table(meta_rows, META_WIDTHS))

    # ---- Context ---------------------------------------------------------
    parts.append(heading("บริบทและขอบเขต (Context)"))
    parts.append(body_para(
        "หน้า Budget Closing Date เป็นหน้าสำหรับผู้ดูแลระบบ (Master Table Admins) เท่านั้น "
        "ใช้ให้ผู้ดูแลกำหนด วันปิดรับข้อมูลงบประมาณ ของแต่ละปีงบประมาณด้วยตนเอง ปีละ 1 วัน "
        "วันปิดรับไม่ตายตัว — เปลี่ยนได้ทุกปีตามแผนการทำงบประมาณ "
        "เมื่อถึงวันปิด ระบบจะล็อกฟอร์มกรอกงบประมาณ (Submit Budget) สำหรับ ผู้กรอกทั่วไป "
        "(ผู้ส่งงบระดับ L3/L4) ไม่ให้กรอกหรือแก้ไขเพิ่ม "
        "ระบบควบคุมสิทธิ์ด้วย Azure Entra ID group `master-table-admins`"
    ))
    parts.append(para(
        run("ข้อยกเว้นสำคัญ — การล็อกนี้ ไม่ใช่การล็อกทั้งระบบ (ตาม ADR-0012): "
            "ผู้ดูแลระบบ (admin allowlist 4 คน — นิภาพร / วราพร / จักรกฤษณ์ / ปิยะดา) "
            "ยังแก้ไขและ \"ส่ง\" งบของฝ่ายใดก็ได้หลังวันปิด → งบเข้าสถานะ APPROVED โดยตรง "
            "(ADMIN_OVERRIDE — ไม่ผ่านสายอนุมัติ เพราะผู้ดูแลคือผู้มีอำนาจงบประมาณ "
            "และเป็นผู้เดียวที่ใช้งานระบบได้หลังปิด) · "
            "ส่วนการนำเข้างบอนุมัติ (board_budget / approved-budget import) "
            "ไม่ถูกล็อกด้วยวันปิดนี้ (คนละ lifecycle)",
            size_half_pt=20, italic=True, color="8C6423"),
        space_before=40, space_after=80,
    ))
    parts.append(para(
        run("หมายเหตุ: หน้านี้เป็นหน้า demo ภายในโมดูล — หน้าจอแสดงป้าย "
            "\"DEMO · ข้อมูลตัวอย่าง — เวอร์ชันจริงจะเชื่อมต่อในแอป React\" "
            "ข้อมูลและวันที่ในภาพจึงเป็นข้อมูลตัวอย่าง ยังไม่เชื่อมต่อฐานข้อมูลจริง · "
            "ชื่อตารางที่เสนอ `cfg_master.budget_closing_date` (รอยืนยัน) "
            "และจะเชื่อมต่อจริงในเวอร์ชัน React",
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
    parts.append(image_para(rids["01"], *img_meta["01"][1], 101, "bcd_01_overview"))
    overview_rows = [
        ["#", "ชื่อจุด", "จุดประสงค์", "การทำงาน", "ตารางต้นทาง / ปลายทาง"],
        ["①", "แถบเมนูหลัก (Navigation)",
         "สลับไปหน้า Master อื่น + กลับหน้าแรก + สลับธีม",
         "ลิงก์ไปหน้า Master อื่นๆ ตามแถบเมนูด้านบนของภาพ · ปุ่มกลับหน้าแรก (Home) · ปุ่มสลับธีม (สว่าง/มืด)",
         "—"],
        ["②", "ส่วนหัวหน้า (Breadcrumb + ชื่อหน้า)",
         "บอกตำแหน่งและชื่อโมดูล",
         "breadcrumb \"Budget Closing Date\" + \"Module 10 · Submission Deadline\" + "
         "คำอธิบายว่าใช้กำหนดวันปิดรับข้อมูลงบประมาณของแต่ละปี",
         "—"],
        ["③", "ป้ายบอกการใช้งาน (Usage hint)",
         "บอกว่าวันปิดนี้ถูกนำไปใช้ที่ใด",
         "ระบุว่าใช้ควบคุม \"Submit Budget Form\" — ถึงวันปิด → form lock → read-only "
         "สำหรับผู้กรอกทั่วไป (L3/L4) · ข้อยกเว้น: ผู้ดูแลระบบยัง override แก้ไข + ส่งได้ "
         "หลังวันปิด → APPROVED โดยตรง (ADR-0012)",
         "ปลายทางการใช้งาน: หน้ากรอกงบประมาณ (Submit Budget)"],
        ["④", "แถบสรุปตัวเลข (Summary chips)",
         "สรุปภาพรวมแบบเรียลไทม์",
         "Years (จำนวนปีที่ตั้งวันปิด) · Latest (วันปิดของปีล่าสุด) · "
         "Open (จำนวนปีที่ยังเปิดรับ) · On close (Auto-lock — พฤติกรรมเมื่อถึงวันปิด)",
         "คำนวณจากข้อมูลในตาราง"],
        ["⑤", "ส่วนที่ 1 — กล่อง Deadline editor",
         "ฟอร์มเพิ่ม/แก้ไขวันปิดรับรายปี",
         "ดูรายละเอียดข้อ 1.1–1.4",
         "—"],
        ["⑥", "ส่วนที่ 2 — กล่อง Closing date records",
         "ตารางวันปิดรับแต่ละปี",
         "ดูรายละเอียดข้อ 2.1–2.5",
         "(วางแผน) `cfg_master.budget_closing_date`"],
    ]
    parts.append(table(overview_rows, DESC_WIDTHS))

    # ---- Section 1: Deadline editor -------------------------------------
    parts.append(heading("ส่วนที่ 1 — Deadline editor (กล่องเพิ่ม/แก้ไขวันปิดรับรายปี)"))
    parts.append(image_para(rids["02"], *img_meta["02"][1], 102, "bcd_02_editor"))
    parts.append(image_para(rids["04"], *img_meta["04"][1], 104, "bcd_04_edit"))
    editor_rows = [
        ["#", "ชื่อจุด", "จุดประสงค์", "การทำงาน", "ตารางต้นทาง / ปลายทาง"],
        ["1.1", "ป้ายโหมด (Mode badge)",
         "บอกว่ากำลัง \"เพิ่มใหม่\" หรือ \"แก้ไข\"",
         "โหมดเพิ่ม = ป้าย \"เพิ่มใหม่ · NEW\" · เมื่อกดปุ่มแก้ไขในตาราง จะเปลี่ยนเป็น "
         "\"แก้ไข · UPDATE\" และดึงค่าปีนั้นขึ้นมาในฟอร์ม (ดูภาพถัดไป) · "
         "ถ้าระหว่างแก้ไขผู้ใช้พิมพ์ปีอื่นที่ต่างจากเดิม ระบบจะออกจากโหมดแก้ไขกลับเป็น "
         "\"เพิ่มใหม่\" อัตโนมัติ (ป้ายจะไม่บอกผิด)",
         "—"],
        ["1.2", "ช่อง Fiscal Year",
         "ปีงบประมาณที่จะกำหนดวันปิด",
         "กรอกปี ค.ศ. (2015–2099) · ถ้าปีนั้นมีอยู่แล้ว การบันทึกจะเป็นการอัปเดตทับ",
         "—"],
        ["1.3", "ช่อง Closing Date · วันปิดรับข้อมูล",
         "วันสุดท้ายที่ผู้ใช้กรอก/แก้ไขงบได้",
         "เลือกวันที่จากปฏิทิน (date picker) ช่วง 2015-01-01 ถึง 2099-12-31 · "
         "หลังวันนี้ ฟอร์มกรอกงบของปีนั้นจะถูกล็อกสำหรับผู้กรอกทั่วไป (L3/L4) · "
         "ผู้ดูแลระบบยัง override แก้ไข + ส่งได้ → APPROVED โดยตรง (ADR-0012)",
         "ผู้ดูแลกำหนดเอง (ตามแผนการทำงบประมาณแต่ละปี)"],
        ["1.4", "ปุ่ม บันทึก / อัปเดต",
         "บันทึกวันปิดของปีนั้น",
         "ป้ายปุ่ม = \"บันทึก\" ในโหมดเพิ่ม / \"อัปเดต\" ในโหมดแก้ไข · "
         "1 ปี = 1 วันปิด (บันทึกซ้ำปีเดิม = อัปเดตทับค่าเดิม)",
         "ปลายทาง (วางแผน): `cfg_master.budget_closing_date`"],
    ]
    parts.append(table(editor_rows, DESC_WIDTHS))

    # ---- Section 2: Closing date records --------------------------------
    parts.append(heading("ส่วนที่ 2 — Closing date records (ตารางวันปิดแต่ละปี)"))
    parts.append(image_para(rids["03"], *img_meta["03"][1], 103, "bcd_03_records"))
    records_rows = [
        ["#", "ชื่อจุด", "จุดประสงค์", "การทำงาน", "ตารางต้นทาง / ปลายทาง"],
        ["2.1", "ช่องค้นหา (Search)",
         "กรองตาราง",
         "ค้นหาตามปีหรือวันที่ ทันทีขณะพิมพ์",
         "กรองข้อมูลฝั่งหน้าเว็บ"],
        ["2.2", "คำอธิบายสี + ตัวนับ (Legend + count)",
         "บอกสีประจำ Year / วันปิด และจำนวนปี",
         "แสดง \"x / y years\"",
         "—"],
        ["2.3", "คอลัมน์ Fiscal Year",
         "แสดงลำดับ + ปี + สถานะ",
         "หมายเลขลำดับแถว (01, 02, …) + ป้ายปี พร้อมแท็ก Current (ปีปัจจุบัน) / "
         "Historic (ปีที่ผ่านมา) / Forecast (ปีอนาคต) · "
         "คลิกหัวคอลัมน์เพื่อเรียงลำดับตามปีได้",
         "ต้นทาง (วางแผน): `cfg_master.budget_closing_date`"],
        ["2.4", "คอลัมน์ Closing Date",
         "แสดงวันปิด + สถานะการรับข้อมูล",
         "แสดงวัน + เดือน/ปี (เช่น 27 พ.ย. 2026) พร้อมป้ายสถานะ — "
         "\"เปิดรับ · เหลือ N วัน\" (ยังไม่ถึงวันปิด) / \"วันสุดท้ายวันนี้\" (ตรงวันปิดพอดี) / "
         "\"ปิดรับแล้ว\" (เลยวันปิด — ฟอร์มถูกล็อกสำหรับผู้กรอกทั่วไป L3/L4; "
         "ผู้ดูแลระบบยัง override แก้ไข + ส่งได้ → APPROVED โดยตรง ตาม ADR-0012) · "
         "คลิกหัวคอลัมน์เพื่อเรียงลำดับตามวันที่ได้",
         "—"],
        ["2.5", "ปุ่มจัดการ (Actions)",
         "แก้ไข / ลบ วันปิดรายปี",
         "2.5a ปุ่มแก้ไข → ดึงค่าขึ้นฟอร์มเป็นโหมด UPDATE · 2.5b ปุ่มลบ → เปิดหน้าต่างยืนยัน",
         "ปลายทาง (วางแผน): `cfg_master.budget_closing_date`"],
    ]
    parts.append(table(records_rows, DESC_WIDTHS))

    # ---- Save & delete ---------------------------------------------------
    parts.append(heading("การบันทึก & การลบ"))
    parts.append(image_para(rids["05"], *img_meta["05"][1], 105, "bcd_05_save",
                            width_in=4.2))
    parts.append(image_para(rids["06"], *img_meta["06"][1], 106, "bcd_06_delete",
                            width_in=4.2))
    save_rows = [
        ["#", "ชื่อจุด", "จุดประสงค์", "การทำงาน", "ตารางต้นทาง / ปลายทาง"],
        ["3.1", "แจ้งบันทึกสำเร็จ",
         "ยืนยันผลการบันทึก",
         "หัวข้อหน้าต่าง = \"บันทึกสำเร็จ\" เมื่อเพิ่มปีใหม่ (CREATE) / \"อัปเดตสำเร็จ\" "
         "เมื่อแก้ไขปีเดิม (UPDATE) · สรุป Action (CREATE/UPDATE) / Year / Closing date",
         "—"],
        ["3.2", "ยืนยันการลบ",
         "กันการลบผิดพลาด",
         "หน้าต่าง \"ยืนยันลบ\" พร้อมคำเตือนว่าเมื่อไม่มีวันปิด ฟอร์มของปีนั้นจะ"
         "เปิดรับตลอดจนกว่าจะตั้งใหม่",
         "ปลายทาง (วางแผน): ลบแถวใน `cfg_master.budget_closing_date`"],
    ]
    parts.append(table(save_rows, DESC_WIDTHS))

    # ---- Data sources ----------------------------------------------------
    parts.append(heading("สรุปแหล่งข้อมูล (Data sources)"))
    src_rows = [
        ["ตาราง / แหล่ง", "คำอธิบาย", "บทบาทในหน้านี้"],
        ["`cfg_master.budget_closing_date` (fiscal_year — คีย์หลัก, closing_date)",
         "(วางแผน — รอยืนยันชื่อ) ตารางเก็บวันปิดรับข้อมูลงบประมาณรายปี "
         "บน Fabric SQL Database",
         "ปลายทางของการบันทึก/ลบ และต้นทางของตาราง (ข้อ 2.3)"],
        ["หน้ากรอกงบประมาณ (Submit Budget Form)",
         "ผู้ใช้ปลายทางของวันปิด — เมื่อถึงวันปิดของปีนั้น ฟอร์มจะถูกล็อกเป็น read-only "
         "สำหรับผู้กรอกทั่วไป (L3/L4) กรอก/แก้ไขงบเพิ่มไม่ได้ · "
         "ข้อยกเว้น (ADR-0012): ผู้ดูแลระบบ 4 คนยังแก้ไข + ส่งงบของฝ่ายใดก็ได้หลังวันปิด → "
         "APPROVED โดยตรง (ADMIN_OVERRIDE ไม่ผ่านสายอนุมัติ) · "
         "การนำเข้างบอนุมัติ (board_budget) ไม่ถูกล็อกด้วยวันปิดนี้",
         "ปลายทางการใช้งานของวันปิดที่กำหนดในหน้านี้"],
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

    # logical order in document: 01, 02, 04 (edit), 03 (records), 05, 06
    order = ["01", "02", "04", "03", "05", "06"]
    media_names = {
        "01": "image1.png", "02": "image2.png", "04": "image3.png",
        "03": "image4.png", "05": "image5.png", "06": "image6.png",
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
