# -*- coding: utf-8 -*-
"""Validator for 01_main_web_app_spec.docx (hand-written OOXML).

Checks (stdlib only):
  1. Required zip parts present.
  2. Every .xml/.rels part parses as well-formed XML.
  3. Every r:embed resolves to a relationship whose Target media file exists.
  4. media file count == distinct r:embed refs (no orphan / no missing media).
  5. sz == szCs on every run that has a sz (Thai cs-font correctness).
  6. Confirmed-decision strings present; stale TBC/v0.1 strings absent.
"""
import sys
import zipfile
import re
import xml.etree.ElementTree as ET

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DOCX = (
    r"c:\04.budget_management_web\requirement_spec\1_software_dev"
    r"\1.1_frontend\signoff_spec\01_main_web_app_spec.docx"
)

REQUIRED_PARTS = [
    "[Content_Types].xml",
    "_rels/.rels",
    "word/document.xml",
    "word/_rels/document.xml.rels",
]
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def main():
    ok = True
    with zipfile.ZipFile(DOCX) as z:
        names = set(z.namelist())

        print("[1] Required parts:")
        for p in REQUIRED_PARTS:
            present = p in names
            ok &= present
            print(f"    {'OK ' if present else 'MISSING'}  {p}")

        print("[2] XML well-formedness:")
        xml_parts = [n for n in names if n.endswith(".xml") or n.endswith(".rels")]
        for n in sorted(xml_parts):
            try:
                ET.fromstring(z.read(n))
                print(f"    OK    {n}")
            except ET.ParseError as e:
                ok = False
                print(f"    FAIL  {n}  -> {e}")

        doc = z.read("word/document.xml")
        doc_root = ET.fromstring(doc)

        print("[3] r:embed -> relationship -> media target:")
        embeds = set()
        for el in doc_root.iter():
            v = el.get(f"{{{R_NS}}}embed")
            if v:
                embeds.add(v)
        rels_root = ET.fromstring(z.read("word/_rels/document.xml.rels"))
        rel_targets = {r.get("Id"): r.get("Target")
                       for r in rels_root.findall(f"{{{PKG_REL_NS}}}Relationship")}
        if not embeds:
            ok = False
            print("    FAIL  no r:embed found")
        resolved_media = set()
        for rid in sorted(embeds):
            t = rel_targets.get(rid)
            if t is None:
                ok = False
                print(f"    FAIL  {rid} -> no relationship")
                continue
            mp = "word/" + t.replace("\\", "/")
            exists = mp in names
            ok &= exists
            if exists:
                resolved_media.add(mp)
            print(f"    {'OK ' if exists else 'FAIL'}  {rid} -> {t} -> "
                  f"{'present' if exists else 'MISSING'}")

        print("[4] media count == distinct r:embed refs:")
        media_files = {n for n in names if n.startswith("word/media/")}
        match = (len(media_files) == len(embeds) == len(resolved_media))
        ok &= match
        print(f"    {'OK ' if match else 'FAIL'}  media_files={len(media_files)} "
              f"embeds={len(embeds)} resolved={len(resolved_media)}")
        orphans = media_files - resolved_media
        if orphans:
            ok = False
            print(f"    FAIL  orphan media (no embed): {sorted(orphans)}")

        print("[5] sz == szCs on every run:")
        text = doc.decode("utf-8")
        # match each <w:rPr>...</w:rPr> block, compare sz/szCs vals within it
        bad = 0
        total_with_sz = 0
        for rpr in re.findall(r"<w:rPr>.*?</w:rPr>", text, flags=re.S):
            sz = re.search(r'<w:sz w:val="(\d+)"/>', rpr)
            szcs = re.search(r'<w:szCs w:val="(\d+)"/>', rpr)
            if sz:
                total_with_sz += 1
                if not szcs or szcs.group(1) != sz.group(1):
                    bad += 1
        szcs_ok = (bad == 0 and total_with_sz > 0)
        ok &= szcs_ok
        print(f"    {'OK ' if szcs_ok else 'FAIL'}  runs_with_sz={total_with_sz} "
              f"mismatches={bad}")

        print("[6] Content correctness (confirmed decisions in, stale text out):")
        # XML-escapes <,>,& in run text; unescape so checks match human-readable text
        from html import unescape
        text = unescape(text)
        must_have = [
            "ผู้กรอก (L3/L4) → managerempcode → นิภาพร ทองกิ่ง → วราพร ติรสิทธิ์",  # approval chain (v0.3 wording)
            "approved_budget_<ปี>.csv",        # filename pattern
            "direct-to-table",                            # decision 1
            "Replace by Year",                            # decision 2
            "7) ข้อสรุปการออกแบบ",  # section 7 heading (parenthetical removed 2026-06-04)
            "v0.7",
            # v0.4 additions (2026-06-05): login bar redesigned to V3 hierarchy
            "0) การเข้าสู่ระบบ & สิทธิ์การเห็นข้อมูล (Login & Role)",  # login section
            "ใช้คอลัมน์ สายงาน/ฝ่าย ไม่ใช่ Description",  # point 8 conclusion (V3 wording)
            "3.1) ใครเห็น / ใครกรอก / การ Submit",  # point 2 matrix heading
            "8) การส่งข้อมูล (Submit)",  # point 6 section
            "10) ประสิทธิภาพเมื่อ Admin เห็นทุก CC",  # point 9 section
            # v0.5 additions (2026-06-12): Approved read-only + admin-zone + new tools
            "11) เครื่องมือบน toolbar",  # section 11
            "Import ไม่ขึ้นกับตัวกรองปี/ฝ่าย",  # import-not-scoped-by-filter warning
            "สีฟ้า · read-only",  # Approved read-only label
            "Admin มี 4 คน",  # admin count fix (was 3)
            "ระบบจริงไม่มีปุ่มสลับผู้ใช้",  # no user-switcher in production
            "แถบนี้แสดงเฉพาะ Admin",  # admin-zone hidden for non-admin
            "กฎการแสดงแถว",  # row-visibility rule (ADR-0010)
            "SAP actual (ตัวนำ)",  # SAP-actual-led visibility
            # v0.6 additions (2026-06-13): wired mockup — approve-on-main-page flow
            "12) อนุมัติบนหน้าหลัก — ไม่มีหน้า inbox แยก",  # approve-on-main-page (no inbox)
            "13) ตัวเลือกฝ่าย (ฝ่าย-picker) = หน่วยอนุมัติ",  # ฝ่าย-picker = approval unit
            "14) ปุ่ม 🛡️ โหมด Admin",  # overlay admin-mode toggle
            "15) Master FX เป็น read-only ที่หน้านี้",  # FX read-only (owned by Module 09)
            "16) การล็อกการแก้ไข ตามสถานะ × บทบาท",  # edit-lock by status × role
            "recompute-on-read",  # FX per-diem recompute
            "ADMIN_OVERRIDE",  # admin direct-approve log code
            # v0.7 additions (2026-06-14): RLS SEE-scope corrected to ADR-0007 union model
            "ADR-0007",  # cite the authoritative ADR for the union see-scope
            "FILL ⊆ SEE",  # invariant kept (fill never exceeds see)
        ]
        must_not = [
            "Open Questions",
            "ยังไม่สรุป",  # "ยังไม่สรุป"
            "v0.1 (ฉบับร่าง",        # "v0.1 (ฉบับร่าง"
            "v0.6 (ฉบับร่าง",        # superseded — doc bumped to v0.7 (RLS union fix)
            "v0.5",                  # superseded
            "v0.4",                  # superseded
            "v0.3",                  # superseded
            "Admin ส่งได้เฉพาะ CC ของตัวเอง",   # OLD admin-submit rule (superseded by 2-mode, ADR-0012)
            "cc name ที่แสดง",       # old point-8 wording (pre-V3) must be gone
            "(Confirmed · 2026-06-04)",   # removed parenthetical
            "2 ข้อที่เคยค้าง",            # removed intro line
            "ไม่ใช่ชื่อคอลัมน์",          # redundant footnote removed
            "หรือกรอกมือที่ช่องนี้",       # OLD: Approved editable claim — must be gone
            "import .csv (หลัก) หรือแก้มือช่องสีฟ้า",  # OLD: Approved manual-edit claim
            "Admin มี 3 คน",              # OLD admin count — fixed to 4
            "อีเมลอยู่ที่ตัวสลับผู้ใช้",   # OLD: email-on-switcher claim (no switcher in real app)
            "พร้อมตัวสลับผู้ใช้ (เดโม่) ที่มีอีเมล",  # OLD overview switcher wording
        ]
        # NOTE: '_file_path' intentionally still appears in section 6/7 NOTES that
        # state file-related control columns are NOT stored (direct-to-table) — so it
        # is not in must_not. The Control Columns TABLE no longer has it as a row.
        for s in must_have:
            f = s in text
            ok &= f
            print(f"    {'OK ' if f else 'FAIL'}  present: {s!r}")
        for s in must_not:
            absent = s not in text
            ok &= absent
            print(f"    {'OK ' if absent else 'FAIL'}  absent : {s!r}")

    print("\nRESULT:", "ALL CHECKS PASSED" if ok else "VALIDATION FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
