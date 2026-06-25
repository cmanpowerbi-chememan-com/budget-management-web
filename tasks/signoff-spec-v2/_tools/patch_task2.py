#!/usr/bin/env python
"""Fix remaining run-split TASK-002 edits."""
import shutil, zipfile

DOC = "word/document.xml"
BASE = "requirement_spec/1_software_dev/1.1_frontend/signoff_spec/version2"

def patch(path, pairs):
    with zipfile.ZipFile(path) as z:
        xml = z.read(DOC).decode("utf-8")
    report = []
    for find, repl, exp in pairs:
        n = xml.count(find)
        if n != exp:
            report.append(f"  ?? {find[:40]!r} count={n} expect={exp}")
        else:
            xml = xml.replace(find, repl)
            report.append(f"  ok x{n}: {find[:40]!r}")
    tmp = path + ".tmp"
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename == DOC:
                continue
            zout.writestr(item, zin.read(item.filename))
        zout.writestr(DOC, xml.encode("utf-8"))
    shutil.move(tmp, path)
    return report

spec_a = f"{BASE}/SpecA_หน้าหลัก_สิทธิ์_v3.docx"
spec_c = f"{BASE}/SpecC_Master_Tables_v3.docx"

a = patch(spec_a, [
    ("orgcode </w:t></w:r><w:r w:rsidRPr=\"00577CA6\"><w:rPr><w:rFonts w:ascii=\"CordiaUPC\" w:eastAsia=\"CordiaUPC\" w:hAnsi=\"CordiaUPC\" w:cs=\"CordiaUPC\"/><w:color w:val=\"FF0000\"/><w:szCs w:val=\"24\"/><w:cs/></w:rPr><w:t xml:space=\"preserve\">และฝ่าย) ",
     "(รวมจาก orgcode ∪ ฝ่าย) ", 1),
    ("ดูรายละเอียดในเอกสาร </w:t></w:r><w:r w:rsidRPr=\"00ED00F6\"><w:rPr><w:rFonts w:ascii=\"CordiaUPC\" w:eastAsia=\"CordiaUPC\" w:hAnsi=\"CordiaUPC\" w:cs=\"CordiaUPC\"/><w:color w:val=\"000000\" w:themeColor=\"text1\"/><w:szCs w:val=\"24\"/><w:highlight w:val=\"yellow\"/></w:rPr><w:t>approval)",
     "C-Level — ดูเอกสารกระบวนการอนุมัติ (Approval Workflow))", 1),
    ("per-diem engine </w:t></w:r><w:r w:rsidRPr=\"00CE2D01\"><w:rPr><w:rFonts w:ascii=\"CordiaUPC\" w:hAnsi=\"CordiaUPC\" w:cs=\"CordiaUPC\"/><w:szCs w:val=\"24\"/><w:cs/></w:rPr><w:t xml:space=\"preserve\">ในเอกสาร </w:t></w:r><w:r w:rsidRPr=\"00CE2D01\"><w:rPr><w:rFonts w:ascii=\"CordiaUPC\" w:hAnsi=\"CordiaUPC\" w:cs=\"CordiaUPC\"/><w:szCs w:val=\"24\"/></w:rPr><w:t>02",
     "per-diem engine ในเอกสาร 02 — ฟอร์มย่อยใส่รายละเอียดงบ Special GL Subform", 1),
    ("Pending — GL </w:t></w:r><w:r w:rsidRPr=\"0075549F\"><w:rPr><w:rFonts w:ascii=\"CordiaUPC\" w:eastAsia=\"CordiaUPC\" w:hAnsi=\"CordiaUPC\" w:cs=\"CordiaUPC\"/><w:szCs w:val=\"24\"/><w:cs/></w:rPr><w:t>ปกติ (มียอด)",
     "Pending — GL ปกติ (มียอด) — หมายเหตุ: สัญลักษณ์ ①–④ อ้างถึงชั้นข้อมูลในตารางหลัก ไม่ใช่ตำแหน่งในภาพ", 1),
    ("รายละเอียด </w:t></w:r><w:r w:rsidRPr=\"00B847D7\"><w:rPr><w:rFonts w:ascii=\"CordiaUPC\" w:eastAsia=\"CordiaUPC\" w:hAnsi=\"CordiaUPC\" w:cs=\"CordiaUPC\"/><w:szCs w:val=\"24\"/></w:rPr><w:t xml:space=\"preserve\">GL </w:t></w:r><w:r w:rsidRPr=\"00B847D7\"><w:rPr><w:rFonts w:ascii=\"CordiaUPC\" w:eastAsia=\"CordiaUPC\" w:hAnsi=\"CordiaUPC\" w:cs=\"CordiaUPC\"/><w:szCs w:val=\"24\"/><w:cs/></w:rPr><w:t>กลุ่มพิเศษอยู่ใน</w:t></w:r><w:commentRangeStart w:id=\"2\"/><w:r w:rsidRPr=\"001618A6\"><w:rPr><w:rFonts w:ascii=\"CordiaUPC\" w:eastAsia=\"CordiaUPC\" w:hAnsi=\"CordiaUPC\" w:cs=\"CordiaUPC\"/><w:szCs w:val=\"24\"/><w:highlight w:val=\"yellow\"/><w:cs/></w:rPr><w:t xml:space=\"preserve\">เอกสาร </w:t></w:r><w:r w:rsidRPr=\"001618A6\"><w:rPr><w:rFonts w:ascii=\"CordiaUPC\" w:eastAsia=\"CordiaUPC\" w:hAnsi=\"CordiaUPC\" w:cs=\"CordiaUPC\"/><w:szCs w:val=\"24\"/><w:highlight w:val=\"yellow\"/></w:rPr><w:t>02",
     "(รายละเอียด GL กลุ่มพิเศษอยู่ในเอกสาร 02 — ฟอร์มย่อยใส่รายละเอียดงบ Special GL Subform", 1),
])
print("SpecA patch:")
print("\n".join(a))

c = patch(spec_c, [
    ("row-visibility ของ dashboard ", "row-visibility (ADR-0010) ของ dashboard ", 1),
])
print("SpecC patch:")
print("\n".join(c))
