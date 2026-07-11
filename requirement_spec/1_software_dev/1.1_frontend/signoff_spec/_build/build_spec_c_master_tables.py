# -*- coding: utf-8 -*-
"""
Generator for the consolidated "Spec C — การจัดการตารางข้อมูลหลัก (Master Tables)"
User Sign-off Specification (.docx).

This describes the 6 admin-maintained master datasets that are edited via Excel
workbooks on SharePoint (site CMANDWPRD) and synced into Fabric
(cman-dw-ws / modern_lh_cman_dw). There is no web UI — each dataset is one
Excel file with a fixed column structure and a set of data-entry rules.

HARD CONSTRAINTS honoured (same class of doc as the other _build/ generators):
  - NO package installation. Only Python standard library + Pillow (already present).
  - The .docx is built BY HAND as Office Open XML (WordprocessingML) via zipfile + str XML.
  - Thai text uses Leelawadee UI on w:ascii / w:hAnsi / w:cs, with w:szCs == w:sz.
  - document.xml is UTF-8 encoded.
  - Company logo is read from _build/assets/spec_c_logo.jpeg (extracted once from the
    original web-era doc; self-contained so the generator can overwrite its own output).

Re-runnable: overwrites the output doc each run.
"""

import os
import io
import html
import zipfile
from PIL import Image

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
PROJECT_ROOT = r"c:\04.budget_management_web"
SIGNOFF_DIR = os.path.join(
    PROJECT_ROOT,
    "requirement_spec", "1_software_dev", "1.1_frontend", "signoff_spec",
)
LADDAWAN_DIR = os.path.join(SIGNOFF_DIR, "laddawan")
LOGO_SRC = os.path.join(os.path.dirname(__file__), "assets", "spec_c_logo.jpeg")
OUT_DOCX = os.path.join(LADDAWAN_DIR, "Spec C การจัดการตารางข้อมูลหลัก_V1.0.docx")

THAI_FONT = "Leelawadee UI"

# Palette (blue family, matching the V1.0 Word theme headings 0F4761)
HEAD_BLUE = "0F4761"
SUB_BLUE = "1F3864"
BLACK = "000000"
GREY = "6B7280"
TH_FILL = "D6E4F0"   # table header fill (light blue)
TH_TEXT = "0F4761"

# SharePoint links (site CMANDWPRD) — verbatim, load-bearing
LINK_GL = "https://chememan.sharepoint.com/:x:/s/CMANDWPRD/IQC_moVDDg3hTLkmVE8i-KYBAeVh14KV4uhYkSRbGEVa_ms?e=hcrYBo"
LINK_ORG = "https://chememan.sharepoint.com/:x:/s/CMANDWPRD/IQDVasYILWvzSaH8sgE9lqUAAcJPgGg0B1xBJJpPZBwc1gk?e=cGfeL0"
LINK_CLOSE = "https://chememan.sharepoint.com/:x:/s/CMANDWPRD/IQDwbW1vIBaHQbSIzrv7vwo9AfTn_dPM9PmCx2FokcR9HGg?e=ha7NC4"
LINK_CUR = "https://chememan.sharepoint.com/:x:/s/CMANDWPRD/IQA0wcT05ktLSrjC-K-gadGmAd7yL95o84OkEBkTsZK0pzo?e=S1seqp"
LINK_HIDE = "https://chememan.sharepoint.com/:x:/s/CMANDWPRD/IQCKsUvacFkxR7bsed47XApVAbIvUW7EUHdQ5JqDVI4v83U?e=klfvSS"
LINK_FILLER = "https://chememan.sharepoint.com/:x:/r/sites/CMANDWPRD/_layouts/15/Doc.aspx?sourcedoc=%7B0A67CF18-2BFB-4D99-A8A4-BF2E9EF3A000%7D&file=cc%20dept.xlsx"

FABRIC_WS = "cman-dw-ws"
FABRIC_LH = "modern_lh_cman_dw"

# --------------------------------------------------------------------------- #
# OOXML low-level helpers
# --------------------------------------------------------------------------- #
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
EMU_PER_PX = 9525
EMU_PER_IN = 914400


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


def run(text, size_half_pt=24, bold=False, color=None, italic=False):
    rpr = run_props(size_half_pt, bold=bold, color=color, italic=italic)
    return f'<w:r>{rpr}<w:t xml:space="preserve">{esc(text)}</w:t></w:r>'


def para(runs_xml, align=None, space_before=0, space_after=120, shading=None,
         keep_next=False, page_break_before=False):
    ppr = ['<w:pPr>']
    if page_break_before:
        ppr.append('<w:pageBreakBefore/>')
    ppr.append(
        f'<w:rFonts w:ascii="{THAI_FONT}" w:hAnsi="{THAI_FONT}" w:cs="{THAI_FONT}"/>'
    )
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
    return para(
        run(text, size_half_pt=32, bold=True, color=HEAD_BLUE),
        space_before=(0 if page_break_before else 320), space_after=120,
        keep_next=True, page_break_before=page_break_before,
    )


def subheading(text):
    return para(
        run(text, size_half_pt=26, bold=True, color=SUB_BLUE),
        space_before=160, space_after=60, keep_next=True,
    )


def label_para(text):
    return para(
        run(text, size_half_pt=24, bold=True, color=BLACK),
        space_before=100, space_after=40,
    )


def body_para(text, size_half_pt=24, space_after=120, color=None):
    return para(run(text, size_half_pt=size_half_pt, color=color),
                space_after=space_after)


def bullet(text, size_half_pt=24):
    return para(run("•  " + text, size_half_pt=size_half_pt), space_after=50)


def link_para(label, url):
    """Label (bold) + URL (plain, verbatim) on one paragraph."""
    return para(
        run(label + "  ", size_half_pt=24, bold=True, color=BLACK)
        + run(url, size_half_pt=20, color="0563C1"),
        space_before=40, space_after=120,
    )


# ------- tables ------------------------------------------------------------ #
def tcell(content_xml, width_dxa=None, fill=None):
    tc_pr = ['<w:tcPr>']
    if width_dxa:
        tc_pr.append(f'<w:tcW w:w="{width_dxa}" w:type="dxa"/>')
    else:
        tc_pr.append('<w:tcW w:w="0" w:type="auto"/>')
    if fill:
        tc_pr.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>')
    tc_pr.append('<w:tcMar><w:top w:w="40" w:type="dxa"/><w:bottom w:w="40" w:type="dxa"/>'
                 '<w:left w:w="90" w:type="dxa"/><w:right w:w="90" w:type="dxa"/></w:tcMar>')
    tc_pr.append('<w:vAlign w:val="center"/>')
    tc_pr.append('</w:tcPr>')
    return f'<w:tc>{"".join(tc_pr)}{content_xml}</w:tc>'


def cell_para(text, bold=False, color=None, size_half_pt=20, align=None):
    return para(
        run(text, size_half_pt=size_half_pt, bold=bold, color=color),
        align=align, space_after=20, space_before=20,
    )


def table(rows, col_widths_dxa):
    """rows: list[list[str]]. First row = header."""
    tbl = ['<w:tbl>']
    tbl.append('<w:tblPr>')
    tbl.append('<w:tblW w:w="5000" w:type="pct"/>')
    tbl.append(
        '<w:tblBorders>'
        '<w:top w:val="single" w:sz="4" w:space="0" w:color="9DB7D5"/>'
        '<w:left w:val="single" w:sz="4" w:space="0" w:color="9DB7D5"/>'
        '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="9DB7D5"/>'
        '<w:right w:val="single" w:sz="4" w:space="0" w:color="9DB7D5"/>'
        '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="C7D6EA"/>'
        '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="C7D6EA"/>'
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
            fill = TH_FILL if is_header else None
            content = cell_para(
                cell, bold=is_header,
                color=(TH_TEXT if is_header else None),
                size_half_pt=(20 if is_header else 20),
            )
            tr.append(tcell(content, width_dxa=col_widths_dxa[ci], fill=fill))
        tr.append('</w:tr>')
        tbl.append("".join(tr))
    tbl.append('</w:tbl>')
    tbl.append(para(run("", size_half_pt=8), space_after=80))
    return "".join(tbl)


def sign_table(rows, col_widths_dxa):
    """Signature table: data rows tall for handwriting."""
    tbl = ['<w:tbl>']
    tbl.append('<w:tblPr><w:tblW w:w="5000" w:type="pct"/>')
    tbl.append(
        '<w:tblBorders>'
        '<w:top w:val="single" w:sz="4" w:space="0" w:color="9DB7D5"/>'
        '<w:left w:val="single" w:sz="4" w:space="0" w:color="9DB7D5"/>'
        '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="9DB7D5"/>'
        '<w:right w:val="single" w:sz="4" w:space="0" w:color="9DB7D5"/>'
        '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="C7D6EA"/>'
        '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="C7D6EA"/>'
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
            trpr.append('<w:trHeight w:val="1000" w:hRule="atLeast"/>')
        trpr.append('</w:trPr>')
        tr.append("".join(trpr))
        for ci, cell in enumerate(row):
            fill = TH_FILL if is_header else None
            content = cell_para(
                cell, bold=is_header,
                color=(TH_TEXT if is_header else None),
                size_half_pt=20,
            )
            tr.append(tcell(content, width_dxa=col_widths_dxa[ci], fill=fill))
        tr.append('</w:tr>')
        tbl.append("".join(tr))
    tbl.append('</w:tbl>')
    tbl.append(para(run("", size_half_pt=8), space_after=80))
    return "".join(tbl)


def cover_logo_para(rid, px_w, px_h, target_px_w=170):
    """Centered logo on the cover, scaled by width keeping aspect."""
    cx = int(target_px_w * EMU_PER_PX)
    cy = int(cx * (px_h / px_w))
    drawing = (
        f'<w:r><w:rPr><w:rFonts w:ascii="{THAI_FONT}" w:hAnsi="{THAI_FONT}" '
        f'w:cs="{THAI_FONT}"/></w:rPr><w:drawing>'
        '<wp:inline distT="0" distB="0" distL="0" distR="0" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
        f'<wp:extent cx="{cx}" cy="{cy}"/>'
        '<wp:effectExtent l="0" t="0" r="0" b="0"/>'
        '<wp:docPr id="500" name="cover_logo"/>'
        '<wp:cNvGraphicFramePr><a:graphicFrameLocks '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'noChangeAspect="1"/></wp:cNvGraphicFramePr>'
        '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:nvPicPr><pic:cNvPr id="500" name="cover_logo"/><pic:cNvPicPr/></pic:nvPicPr>'
        f'<pic:blipFill><a:blip r:embed="{rid}" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
        '<a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
        f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
        '</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>'
    )
    ppr = (
        f'<w:pPr><w:rFonts w:ascii="{THAI_FONT}" w:hAnsi="{THAI_FONT}" '
        f'w:cs="{THAI_FONT}"/><w:spacing w:before="480" w:after="240"/>'
        f'<w:jc w:val="center"/></w:pPr>'
    )
    return f'<w:p>{ppr}{drawing}</w:p>'


# --------------------------------------------------------------------------- #
# Reusable content fragments
# --------------------------------------------------------------------------- #
ADMIN_INTRO = "ผู้ที่ได้รับสิทธิ์แก้ไขไฟล์ Excel บน SharePoint (4 คน)"
ADMINS = [
    "นิภาพร ทองกิ่ง — nipapornt@chememan.com",
    "วราพร ติรสิทธิ์ — warapornt@chememan.com",
    "ปิยะดา ดวงพลจันทร์ — piyadad@chememan.com",
    "ทีม Data and Analytics — jakkaritw@chememan.com",
]


def admin_block():
    parts = [label_para(ADMIN_INTRO)]
    for a in ADMINS:
        parts.append(bullet(a))
    parts.append(body_para(
        "การเข้าถึงและสิทธิ์แก้ไขไฟล์ควบคุมด้วยสิทธิ์ของไฟล์/โฟลเดอร์บน SharePoint "
        "(site CMANDWPRD) โดยตรง เฉพาะผู้ที่ได้รับสิทธิ์ข้างต้นเท่านั้นที่แก้ไขไฟล์ได้ "
        "ทั้งนี้ SharePoint บันทึกประวัติการแก้ไข (version history) ของไฟล์ให้อัตโนมัติ",
        space_after=140,
    ))
    return "".join(parts)


def sync_block(extra=None):
    txt = (
        f"ข้อมูลในไฟล์ Excel นี้จะถูกซิงค์เข้าสู่คลังข้อมูลกลางบน Microsoft Fabric "
        f"(workspace `{FABRIC_WS}`, lakehouse `{FABRIC_LH}`) เพื่อให้ระบบงบประมาณและรายงานนำไปใช้งานจริง "
    )
    if extra:
        txt += extra + " "
    txt += "รอบเวลาการซิงค์และการตรวจสอบความถูกต้องของข้อมูล (validation) อยู่ระหว่างการออกแบบ"
    return subheading("การซิงค์ข้อมูลเข้าใช้งานจริง (Data sync)") + body_para(txt, space_after=160)


# Column-width presets (content width ~ 9600 dxa for A4 with 1134 margins)
COL3_EXCEL = [2500, 3400, 3700]      # คอลัมน์ | ความหมาย | กติกา/เงื่อนไข
COL3_IMPACT = [900, 3900, 4800]      # ลำดับ | เหตุการณ์ | ผลที่เกิดขึ้น
SIGN_WIDTHS = [1500, 2700, 2900, 1300, 1200]  # บทบาท|ชื่อ|ตำแหน่ง|ลายเซ็น|วันที่


# --------------------------------------------------------------------------- #
# Document body
# --------------------------------------------------------------------------- #
def build_body(logo_rid, logo_size):
    p = []

    # ---- COVER ----------------------------------------------------------- #
    p.append(cover_logo_para(logo_rid, logo_size[0], logo_size[1]))
    cover_lines = [
        "บริษัท เคมีแมน จำกัด (มหาชน)",
        "เอกสารยืนยันข้อกำหนด เพื่อลงนามอนุมัติ",
        "(User Sign-off Specification)",
        "Spec C การจัดการตารางข้อมูลหลัก (Master Tables)",
        "Data Warehouse and BI Dashboard Budgeting and Management",
    ]
    for i, line in enumerate(cover_lines):
        p.append(para(
            run(line, size_half_pt=28, bold=True, color=BLACK),
            align="center", space_before=(40 if i else 120), space_after=40,
        ))
    # short cover note about how the datasets are maintained
    p.append(para(
        run(
            "เอกสารฉบับนี้อธิบายข้อมูลหลัก (Master Tables) จำนวน 6 ชุด ที่ผู้ดูแลระบบดูแลผ่าน "
            "ไฟล์ Excel บน SharePoint (site CMANDWPRD) และซิงค์เข้าสู่ Microsoft Fabric "
            "เพื่อให้ระบบงบประมาณและรายงานนำไปใช้งาน",
            size_half_pt=22, color=GREY),
        align="center", space_before=240, space_after=40,
    ))

    # ==================================================================== #
    # Spec C-1: GL Account Group
    # ==================================================================== #
    p.append(section_heading(
        "Spec C-1: กลุ่มรหัสบัญชี (GL Account Group)", page_break_before=True))
    p.append(subheading("บริบทและขอบเขต (Context)"))
    p.append(body_para(
        "ข้อมูลชุดนี้ใช้จับคู่รหัสบัญชี (GL Code ซึ่งอ้างอิงจาก SAP) เข้ากับกลุ่มรหัสบัญชี "
        "(GL Group) เพื่อจัดหมวดหมู่รายการบัญชีในรายงานงบประมาณ ผู้ดูแลระบบดูแลข้อมูลนี้ผ่าน "
        "ไฟล์ Excel หนึ่งไฟล์บน SharePoint"
    ))
    p.append(admin_block())

    p.append(subheading("ไฟล์ Excel"))
    p.append(link_para("ตำแหน่งไฟล์ (SharePoint site CMANDWPRD):", LINK_GL))
    p.append(label_para("โครงสร้างคอลัมน์"))
    p.append(table([
        ["คอลัมน์", "ความหมาย", "กติกา / เงื่อนไขข้อมูล"],
        ["รหัสบัญชี (GL Code)",
         "รหัสบัญชีจาก SAP ที่ต้องการจัดกลุ่ม",
         "ต้องเป็นรหัสที่มีอยู่จริงใน SAP · 1 รหัสบัญชีมีได้เพียง 1 แถว (ห้ามซ้ำ)"],
        ["กลุ่มรหัสบัญชี (GL Group)",
         "ชื่อกลุ่มที่รหัสบัญชีนั้นสังกัด พิมพ์ชื่อกลุ่มลงในเซลล์ได้โดยตรง",
         "ใช้ชื่อกลุ่มเดิมซ้ำได้ในหลายแถว (หลายรหัสอยู่กลุ่มเดียวกัน) · "
         "ต้องสะกดชื่อกลุ่มให้ตรงกันทุกแถว เพราะชื่อที่สะกดต่างกันถือเป็นคนละกลุ่ม"],
    ], COL3_EXCEL))

    p.append(subheading("หลักการสำคัญ / กติกาการกรอกข้อมูล"))
    p.append(bullet("1 รหัสบัญชี จับคู่กับกลุ่มได้เพียง 1 กลุ่มเท่านั้น — ห้ามมีรหัสบัญชีซ้ำหลายแถว"))
    p.append(bullet("รหัสบัญชีทุกตัวต้องมีอยู่จริงใน SAP"))
    p.append(bullet(
        "ชื่อกลุ่มพิมพ์ลงในเซลล์โดยตรง (ไม่มีตารางรหัสกลุ่มแยกต่างหาก) จึงต้องสะกดชื่อกลุ่มให้ตรงกัน "
        "ทุกแถวที่อยู่กลุ่มเดียวกัน"))
    p.append(bullet(
        "ปัจจุบันมี 18 กลุ่ม ครอบคลุมรหัสบัญชี 137 รายการ"))
    p.append(sync_block())

    # ==================================================================== #
    # Spec C-2: Budget Closing Date
    # ==================================================================== #
    p.append(section_heading(
        "Spec C-2: วันปิดรับข้อมูลงบประมาณ (Budget Closing Date)",
        page_break_before=True))
    p.append(subheading("บริบทและขอบเขต (Context)"))
    p.append(body_para(
        "ข้อมูลชุดนี้ใช้กำหนดวันปิดรับข้อมูลงบประมาณของแต่ละปีงบประมาณ โดยกำหนดได้ปีละ 1 วัน "
        "วันปิดรับไม่ตายตัวและเปลี่ยนแปลงได้ทุกปีตามแผนการจัดทำงบประมาณ ผู้ดูแลระบบดูแลข้อมูลนี้ "
        "ผ่านไฟล์ Excel หนึ่งไฟล์บน SharePoint"
    ))
    p.append(admin_block())

    p.append(subheading("ไฟล์ Excel"))
    p.append(link_para("ตำแหน่งไฟล์ (SharePoint site CMANDWPRD):", LINK_CLOSE))
    p.append(label_para("โครงสร้างคอลัมน์"))
    p.append(table([
        ["คอลัมน์", "ความหมาย", "กติกา / เงื่อนไขข้อมูล"],
        ["ปีงบประมาณ (Fiscal Year)",
         "ปีงบประมาณ (ค.ศ.) ที่จะกำหนดวันปิด",
         "คีย์หลัก · 1 ปีงบประมาณมีได้เพียง 1 แถว (ห้ามซ้ำปี)"],
        ["วันปิดรับข้อมูล (Closing Date)",
         "วันสุดท้ายที่ผู้กรอกทั่วไปกรอกหรือแก้ไขงบของปีนั้นได้",
         "รูปแบบวันที่ · 1 ปีงบประมาณ = 1 วันปิด"],
    ], COL3_EXCEL))

    p.append(subheading("หลักการสำคัญ / กติกาการกรอกข้อมูล"))
    p.append(bullet("1 ปีงบประมาณกำหนดวันปิดได้เพียง 1 วัน (ห้ามมีปีซ้ำ)"))
    p.append(bullet("วันปิดของแต่ละปีเปลี่ยนแปลงได้ตามแผนการจัดทำงบประมาณของปีนั้น"))

    p.append(subheading("การนำไปใช้ปลายทาง (Downstream)"))
    p.append(body_para(
        "เมื่อถึงวันปิดรับของปีนั้น ระบบจะล็อกฟอร์มกรอกงบประมาณ (Submit Budget Form) "
        "ให้เป็นอ่านอย่างเดียวสำหรับผู้กรอกทั่วไป (ระดับ L3/L4 และ L2 จำนวน 3 คน) "
        "ไม่ให้กรอกหรือแก้ไขเพิ่มเติม"
    ))
    p.append(body_para(
        "ข้อยกเว้นสำคัญ (ตาม ADR-0012): การล็อกนี้ไม่ใช่การล็อกทั้งระบบ ผู้ดูแลระบบทั้ง 4 คน "
        "ยังสามารถแก้ไขและส่งงบของฝ่ายใดก็ได้หลังวันปิด โดยงบจะเข้าสถานะ APPROVED โดยตรง "
        "(ADMIN_OVERRIDE) ไม่ผ่านสายการอนุมัติ เนื่องจากผู้ดูแลระบบเป็นผู้มีอำนาจงบประมาณและเป็น "
        "ผู้เดียวที่ใช้งานระบบได้หลังวันปิด นอกจากนี้ การนำเข้างบอนุมัติ (board budget) ไม่ถูกล็อก "
        "ด้วยวันปิดนี้ เนื่องจากเป็นคนละกระบวนการกัน",
        space_after=160,
    ))
    p.append(sync_block())

    # ==================================================================== #
    # Spec C-3: Org Code <-> Cost Center
    # ==================================================================== #
    p.append(section_heading(
        "Spec C-3: การจับคู่หน่วยงานกับ Cost Center (Org Code ↔ Cost Center)",
        page_break_before=True))
    p.append(subheading("บริบทและขอบเขต (Context)"))
    p.append(body_para(
        "ข้อมูลชุดนี้เป็นการจับคู่หน่วยงาน (Orgcode) กับ Cost Center แบบหลายต่อหลาย "
        "(many-to-many) ใช้เป็นข้อมูลอ้างอิงเชิงองค์กร (organizational reference) สำหรับการจัดกลุ่ม "
        "และอ้างอิงหน่วยงานในรายงานงบประมาณ ผู้ดูแลระบบดูแลข้อมูลนี้ผ่านไฟล์ Excel หนึ่งไฟล์บน SharePoint"
    ))
    p.append(body_para(
        "หมายเหตุ: การกำหนดสิทธิ์การมองเห็นและกรอกข้อมูล (RLS) ของระบบงบประมาณ ใช้ไฟล์ "
        "\"Cost Center ↔ ผู้กรอก\" (Spec C-6) เป็นแหล่งข้อมูลเดียว ไม่ได้ใช้ไฟล์ชุดนี้ "
        "ไฟล์ชุดนี้จึงมีบทบาทเป็นข้อมูลอ้างอิงและการจัดกลุ่มในรายงานเท่านั้น",
        space_after=140,
    ))
    p.append(admin_block())

    p.append(subheading("ไฟล์ Excel"))
    p.append(link_para("ตำแหน่งไฟล์ (SharePoint site CMANDWPRD):", LINK_ORG))
    p.append(label_para("โครงสร้างคอลัมน์"))
    p.append(table([
        ["คอลัมน์", "ความหมาย", "กติกา / เงื่อนไขข้อมูล"],
        ["หน่วยงาน (Orgcode)",
         "รหัสหน่วยงานจาก SAP",
         "1 หน่วยงานผูกกับ Cost Center ได้หลายตัว (แยกเป็นหลายแถว)"],
        ["Cost Center",
         "รหัส Cost Center ที่ผูกกับหน่วยงานในแถวนั้น",
         "1 Cost Center ผูกกับหลายหน่วยงานได้เช่นกัน"],
    ], COL3_EXCEL))

    p.append(subheading("หลักการสำคัญ / กติกาการกรอกข้อมูล"))
    p.append(bullet("1 แถว = 1 คู่ (หน่วยงาน, Cost Center) — ห้ามมีคู่ซ้ำกัน"))
    p.append(bullet("ความสัมพันธ์เป็นแบบหลายต่อหลาย: 1 หน่วยงานผูกได้หลาย Cost Center และในทางกลับกัน"))
    p.append(bullet(
        "หน่วยงานหรือ Cost Center ที่ยังไม่ถูกจับคู่ มีผลเฉพาะความครบถ้วนของข้อมูลอ้างอิงในรายงานเท่านั้น "
        "ไม่กระทบต่อสิทธิ์การมองเห็นหรือกรอกข้อมูล (ซึ่งกำหนดโดยไฟล์ Spec C-6)"))
    p.append(sync_block())

    # ==================================================================== #
    # Spec C-4: Hide Document Number
    # ==================================================================== #
    p.append(section_heading(
        "Spec C-4: การซ่อนเลขที่เอกสาร (Hide Document Number)",
        page_break_before=True))
    p.append(subheading("บริบทและขอบเขต (Context)"))
    p.append(body_para(
        "ข้อมูลชุดนี้ใช้กำหนดว่าเลขที่เอกสาร SAP รายการใด ในงวดใด (ปี + เดือน) ที่ไม่ต้องการให้นับรวม "
        "ในยอด Actuals ของรายงานงบประมาณและ Dashboard ตัวอย่างการใช้งาน เช่น งวดที่ปิดบัญชีแล้ว "
        "รายการที่อยู่ระหว่างการตรวจสอบ หรือรายการปรับปรุงที่ไม่ควรนำมาเปรียบเทียบกับงบประมาณ "
        "ผู้ดูแลระบบดูแลข้อมูลนี้ผ่านไฟล์ Excel หนึ่งไฟล์บน SharePoint"
    ))
    p.append(admin_block())

    p.append(subheading("ไฟล์ Excel"))
    p.append(link_para("ตำแหน่งไฟล์ (SharePoint site CMANDWPRD):", LINK_HIDE))
    p.append(label_para("โครงสร้างคอลัมน์"))
    p.append(table([
        ["คอลัมน์", "ความหมาย", "กติกา / เงื่อนไขข้อมูล"],
        ["เลขที่เอกสาร (Document Number)",
         "เลขที่เอกสาร SAP ที่ต้องการซ่อนออกจากการคำนวณ Actuals",
         "ต้องเป็นตัวเลข 10 หลัก · ต้องมีอยู่จริงใน SAP"],
        ["ปีงบประมาณ (Fiscal Year)",
         "ปีงบประมาณ (ค.ศ.) ของงวดที่จะซ่อน",
         "ระบุร่วมกับเดือนเพื่อกำหนดงวด"],
        ["เดือน (Month)",
         "เดือนของงวดที่จะซ่อน",
         "ค่า 1–12 ตามปฏิทินงบประมาณ"],
    ], COL3_EXCEL))

    p.append(subheading("หลักการสำคัญ / กติกาการกรอกข้อมูล"))
    p.append(bullet(
        "ระบบไม่ได้ลบข้อมูลใน SAP แต่เพิ่มเงื่อนไขกรองออกตอนคำนวณยอด Actuals เท่านั้น "
        "ข้อมูลต้นทางใน SAP/Lakehouse ยังคงอยู่ครบถ้วน"))
    p.append(bullet(
        "1 เอกสาร + 1 งวด = 1 แถว หากต้องการซ่อนเอกสารเดิมในหลายงวด ต้องบันทึกแยกทีละแถว"))
    p.append(bullet("เลขที่เอกสารเป็นตัวเลข 10 หลัก และต้องมีอยู่จริงใน SAP"))

    p.append(subheading("การนำไปใช้ปลายทาง (Downstream consumption)"))
    p.append(body_para(
        "เมื่อบันทึกกฎการซ่อนแล้ว ระบบจะตัดเอกสารที่ซ่อนออกจากการคำนวณ Actuals โดยอัตโนมัติทุกครั้ง "
        "ที่มีการ Query ข้อมูล ผลลัพธ์คือเอกสารเหล่านั้นจะไม่ปรากฏในยอด Actuals ที่นำไปเปรียบเทียบ "
        "กับงบประมาณบน Dashboard และรายงาน"
    ))
    p.append(body_para(
        "กฎนี้ทำงานร่วมกับตัวกรอง Actuals มาตรฐานอื่นที่มีอยู่แล้ว เช่น การตัดรายการประเภท "
        "doc_type = 'CO', Cost Center ที่ยกเว้น และ assignment = 'TFRS16'",
        space_after=160,
    ))
    p.append(sync_block())

    # ==================================================================== #
    # Spec C-5: Master Currency
    # ==================================================================== #
    p.append(section_heading(
        "Spec C-5: อัตราแลกเปลี่ยนหลัก (Master Currency)",
        page_break_before=True))
    p.append(subheading("บริบทและขอบเขต (Context)"))
    p.append(body_para(
        "ข้อมูลชุดนี้ใช้กำหนดอัตราแลกเปลี่ยนเฉลี่ยรายปี (USD → THB) โดยกำหนดได้ปีละ 1 ค่า "
        "เพื่อนำไปคำนวณเบี้ยเลี้ยงการเดินทางต่างประเทศในกลุ่มค่าใช้จ่าย Travelling Expense "
        "ผู้ดูแลระบบดูแลข้อมูลนี้ผ่านไฟล์ Excel หนึ่งไฟล์บน SharePoint"
    ))
    p.append(admin_block())

    p.append(subheading("ไฟล์ Excel"))
    p.append(link_para("ตำแหน่งไฟล์ (SharePoint site CMANDWPRD):", LINK_CUR))
    p.append(label_para("โครงสร้างคอลัมน์"))
    p.append(table([
        ["คอลัมน์", "ความหมาย", "กติกา / เงื่อนไขข้อมูล"],
        ["ปีงบประมาณ (Fiscal Year)",
         "ปีงบประมาณ (ค.ศ.) ที่จะกำหนดอัตรา",
         "คีย์หลัก · 1 ปีงบประมาณมีได้เพียง 1 แถว"],
        ["อัตราแลกเปลี่ยนเฉลี่ย USD → THB (Avg Rate)",
         "อัตราเฉลี่ยทั้งปี เช่น 32.45 หมายถึง 1 USD = 32.45 THB",
         "1 ปีงบประมาณ = 1 อัตรา · ค่าที่รับได้อยู่ในช่วง 20.00–60.00"],
    ], COL3_EXCEL))

    p.append(subheading("หลักการสำคัญ / กติกาการกรอกข้อมูล"))
    p.append(bullet("1 ปีงบประมาณกำหนดอัตราได้เพียง 1 ค่า"))
    p.append(bullet("ค่าที่รับได้อยู่ในช่วง 20.00–60.00 (บาทต่อ 1 ดอลลาร์สหรัฐ)"))

    p.append(subheading("ผลกระทบเมื่อแก้ไขอัตรา (Impact of changing a rate)"))
    p.append(body_para(
        "อัตราในไฟล์นี้ใช้คำนวณเฉพาะเบี้ยเลี้ยง (per-diem) การเดินทางต่างประเทศเท่านั้น ตามสูตร: "
        "จำนวนวัน × อัตราเบี้ยเลี้ยงต่อวัน (USD) × อัตราแลกเปลี่ยน ส่วนค่าตั๋วเครื่องบิน ค่าที่พัก และ "
        "ค่าใช้จ่ายเดินทางอื่น ผู้ใช้กรอกเป็นเงินบาท (THB) เองโดยตรง จึงไม่ผูกกับอัตรานี้และไม่เปลี่ยนแปลง "
        "ตามอัตรา รายการในประเทศ (สกุล THB) ก็ไม่ใช้อัตรานี้เช่นกัน"
    ))
    p.append(body_para(
        "หลักการสำคัญ: เบี้ยเลี้ยงต่างประเทศคำนวณใหม่ทุกครั้งจากอัตราของปีนั้น ไม่มีการเก็บตัวเลขตายตัว "
        "(ไม่มี snapshot และไม่มีคอลัมน์ fx_rate_used) ระบบเก็บเฉพาะข้อมูลทริป (ผู้เดินทาง ตำแหน่ง "
        "ปลายทาง จำนวนวัน เดือน) ส่วนยอดเบี้ยเลี้ยง THB คำนวณจากอัตราของปีนั้นเสมอ"
    ))
    p.append(table([
        ["ลำดับ", "เหตุการณ์", "ผลที่เกิดขึ้น"],
        ["1", "ผู้ดูแลระบบแก้ไขอัตราของปีในไฟล์ Excel เช่น จาก 30 เป็น 35",
         "อัตราใหม่ถูกซิงค์เข้าระบบ โดยแก้ไขได้ที่ไฟล์นี้เพียงที่เดียว"],
        ["2", "เบี้ยเลี้ยงต่างประเทศของปีนั้นทุกหน่วยงาน",
         "คำนวณใหม่ทันทีด้วยอัตรา 35 รวมถึงงบที่อนุมัติแล้ว (APPROVED) โดยไม่ต้องเปิดฟอร์ม "
         "ไม่ต้อง Save และไม่ต้อง Submit ใหม่"],
        ["3", "ค่าตั๋ว / ค่าที่พัก / ค่าใช้จ่ายเดินทางอื่น",
         "ไม่เปลี่ยนแปลง เนื่องจากเป็นยอด THB ที่กรอกเองโดยตรง ไม่ผูกกับอัตรา"],
        ["4", "ฟอร์มกรอกงบ (OPEX) ส่วนการเดินทางต่างประเทศ",
         "แสดงอัตราแบบอ่านอย่างเดียว และคำนวณเบี้ยเลี้ยงสดตามอัตราปัจจุบัน "
         "ฟอร์มกรอกงบไม่มีช่องแก้ไขอัตรา"],
        ["5", "Dashboard / Gold (Phase 2)",
         "ยอดเบี้ยเลี้ยงเป็นค่า ณ อัตราที่ Pipeline รันรอบนั้น ซึ่งอาจเปลี่ยนได้แม้ไม่มีการส่งอนุมัติใหม่ "
         "โดยอธิบายการกระทบยอดด้วยเหตุผล \"อัตราของปีถูกแก้ไข\""],
    ], COL3_IMPACT))
    p.append(body_para(
        "เหตุผล (ADR-0015): อัตราแลกเปลี่ยนหลักกำหนดอัตราเดียวต่อปี และแก้ไขได้เฉพาะผู้ดูแลฝ่ายงบประมาณ "
        "ที่ได้รับสิทธิ์เท่านั้น การคำนวณใหม่ทันทีทำให้งบของปีเดียวกันทุกหน่วยงานสอดคล้องกับอัตราจริง "
        "โดยไม่ต้องเปิดหรือส่งอนุมัติทีละงบ",
        space_after=160,
    ))
    p.append(sync_block())

    # ==================================================================== #
    # Spec C-6: Cost Center <-> Filler map (NEW)
    # ==================================================================== #
    p.append(section_heading(
        "Spec C-6: การกำหนดผู้กรอกงบต่อ Cost Center (Cost Center ↔ ผู้กรอก)",
        page_break_before=True))
    p.append(subheading("บริบทและขอบเขต (Context)"))
    p.append(body_para(
        "ข้อมูลชุดนี้กำหนดว่าแต่ละ Cost Center ใครมีสิทธิ์กรอก (fill) ข้อมูลงบประมาณของ Cost Center "
        "นั้น และใครมีสิทธิ์มองเห็น (see) เป็นแหล่งข้อมูลเดียว (single source of truth) สำหรับสิทธิ์ "
        "การมองเห็นและการกรอกข้อมูลในระบบงบประมาณหลัก การถูกระบุเป็นผู้กรอกของ Cost Center ใด "
        "จะได้สิทธิ์กรอกของ Cost Center นั้นโดยตรง ไม่มีการตรวจสอบระดับตำแหน่งหรือ role เพิ่มเติม "
        "ผู้ดูแลระบบดูแลข้อมูลนี้ผ่านไฟล์ Excel หนึ่งไฟล์บน SharePoint"
    ))
    p.append(admin_block())

    p.append(subheading("ไฟล์ Excel"))
    p.append(link_para("ตำแหน่งไฟล์ — cc dept.xlsx (SharePoint site CMANDWPRD):", LINK_FILLER))
    p.append(label_para("โครงสร้างคอลัมน์"))
    p.append(table([
        ["คอลัมน์", "ความหมาย", "กติกา / เงื่อนไขข้อมูล"],
        ["Cost Center",
         "รหัส Cost Center ที่ต้องการกำหนดผู้กรอก",
         "คีย์หลัก · 1 Cost Center มีได้เพียง 1 แถว"],
        ["คนกรอกข้อมูล (Filler)",
         "อีเมลของผู้ที่ได้รับสิทธิ์กรอกงบของ Cost Center นั้น",
         "ระบุได้ตั้งแต่ 1 อีเมลขึ้นไปในเซลล์เดียว โดยคั่นแต่ละอีเมลด้วยเครื่องหมายจุลภาค (,)"],
    ], COL3_EXCEL))

    p.append(subheading("หลักการสำคัญ / กติกาการกรอกข้อมูล"))
    p.append(bullet(
        "สิทธิ์กรอก (fill) = อีเมลที่ปรากฏในแถวของ Cost Center นั้นเท่านั้น — "
        "ถูกระบุคือได้สิทธิ์กรอกทันที ไม่มีเงื่อนไขระดับตำแหน่งเพิ่มเติม"))
    p.append(bullet(
        "สิทธิ์มองเห็น (see) = ผู้กรอกของ Cost Center นั้น รวมกับผู้จัดการโดยตรงของผู้กรอกแต่ละคน "
        "(ดูจากข้อมูลพนักงาน `mas_employee_data.managerempcode`) โดยผู้จัดการมองเห็นได้แต่กรอกไม่ได้ "
        "เว้นแต่จะถูกระบุเป็นผู้กรอกด้วย"))
    p.append(bullet(
        "Cost Center ที่ไม่มีผู้กรอกเลย จะตกไปที่ผู้ดูแลระบบ (Admin fallback) เช่นเดียวกับหน่วยงาน "
        "ที่ไม่มีผู้รับผิดชอบ — ไม่มีใครกรอก/มองเห็นได้จนกว่าจะเพิ่มอีเมลผู้กรอกลงในแถวนั้น"))
    p.append(bullet(
        "การกำหนดสายการอนุมัติหลังส่งงบ (ผู้จัดการโดยตรงของผู้ส่ง → คุณนิภาพร → คุณวราพร) "
        "ไม่เปลี่ยนแปลง ไฟล์นี้กำหนดเฉพาะว่าใครกรอก/มองเห็นได้ ไม่เกี่ยวกับผู้อนุมัติ"))
    p.append(sync_block(
        extra="ทั้งนี้ แถวที่เว้นช่องผู้กรอกว่างไว้จะถูกข้ามเฉพาะแถวนั้นตอนซิงค์ ส่วนแถวอื่นในไฟล์ยังซิงค์ตามปกติ"))

    # ==================================================================== #
    # Sign-off
    # ==================================================================== #
    p.append(section_heading("ช่องลงนามอนุมัติ", page_break_before=True))
    sign_rows = [
        ["บทบาท", "ชื่อ-นามสกุล", "ตำแหน่ง", "ลายเซ็น", "วันที่"],
        ["ผู้จัดทำ", "Jakkarit Wanichkamonnull",
         "Senior STEM - Data & Analytics", "", "11/07/2026"],
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
# Header / Footer (self-contained, no theme/style dependency)
# --------------------------------------------------------------------------- #
def header_xml(logo_rid, logo_size, target_px_w=90):
    cx = int(target_px_w * EMU_PER_PX)
    cy = int(cx * (logo_size[1] / logo_size[0]))
    logo_run = (
        f'<w:r><w:rPr><w:rFonts w:ascii="{THAI_FONT}" w:hAnsi="{THAI_FONT}" '
        f'w:cs="{THAI_FONT}"/></w:rPr><w:drawing>'
        '<wp:inline distT="0" distB="0" distL="0" distR="0" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
        f'<wp:extent cx="{cx}" cy="{cy}"/>'
        '<wp:effectExtent l="0" t="0" r="0" b="0"/>'
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
        '</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>'
    )
    logo_p = (
        f'<w:p><w:pPr><w:rFonts w:ascii="{THAI_FONT}" w:hAnsi="{THAI_FONT}" '
        f'w:cs="{THAI_FONT}"/><w:spacing w:after="0"/></w:pPr>{logo_run}</w:p>'
    )
    lines = [
        "เอกสารยืนยันข้อกำหนด เพื่อลงนามอนุมัติ",
        "Data Warehouse and BI Dashboard Budgeting and Management",
        "Spec C การจัดการตารางข้อมูลหลัก (Master Tables)",
    ]
    line_ps = "".join(
        para(run(t, size_half_pt=16, color=GREY), align="right", space_after=0)
        for t in lines
    )
    body = logo_p + line_ps
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        f'{body}</w:hdr>'
    )


def footer_xml():
    left = run("Data Warehouse and BI Dashboard Budgeting and Management",
               size_half_pt=18, color=GREY)
    # right cell: หน้าที่ {PAGE}
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
        '<w:fldChar w:fldCharType="end"/></w:r>'
    )
    # 2-col borderless table: left text, right page number
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
        '</w:tr></w:tbl>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'{tbl}</w:ftr>'
    )


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
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/header1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>'
        '<Override PartName="/word/footer1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
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


def document_rels_xml():
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rIdImg" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
        'Target="media/image1.jpeg"/>'
        '<Relationship Id="rIdHdr" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" '
        'Target="header1.xml"/>'
        '<Relationship Id="rIdFtr" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" '
        'Target="footer1.xml"/>'
        '</Relationships>'
    )


def header_rels_xml():
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rIdHdrLogo" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
        'Target="media/image1.jpeg"/>'
        '</Relationships>'
    )


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
        '</w:sectPr>'
        '</w:body></w:document>'
    )


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    print("[1/4] Loading company logo asset ...")
    with open(LOGO_SRC, "rb") as f:
        logo_bytes = f.read()
    logo_size = Image.open(io.BytesIO(logo_bytes)).size
    print(f"      logo {logo_size}")

    print("[2/4] Building OOXML parts ...")
    body = build_body("rIdImg", logo_size)
    doc_xml = document_xml(body)
    hdr_xml = header_xml("rIdHdrLogo", logo_size)
    ftr_xml = footer_xml()

    print("[3/4] Writing .docx zip ...")
    if os.path.exists(OUT_DOCX):
        os.remove(OUT_DOCX)
    with zipfile.ZipFile(OUT_DOCX, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types_xml())
        z.writestr("_rels/.rels", root_rels_xml())
        z.writestr("word/document.xml", doc_xml.encode("utf-8"))
        z.writestr("word/_rels/document.xml.rels", document_rels_xml())
        z.writestr("word/header1.xml", hdr_xml.encode("utf-8"))
        z.writestr("word/_rels/header1.xml.rels", header_rels_xml())
        z.writestr("word/footer1.xml", ftr_xml.encode("utf-8"))
        z.writestr("word/media/image1.jpeg", logo_bytes)

    print(f"[4/4] DONE: {OUT_DOCX}  ({os.path.getsize(OUT_DOCX)} bytes)")


if __name__ == "__main__":
    main()
