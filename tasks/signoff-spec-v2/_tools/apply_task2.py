#!/usr/bin/env python
"""Apply TASK-002 judgment edits including run-split XML fragments."""
import json, os, re, shutil, zipfile

DOC = "word/document.xml"
BASE = "requirement_spec/1_software_dev/1.1_frontend/signoff_spec/version2"

def load_xml(path):
    with zipfile.ZipFile(path) as z:
        return z.read(DOC).decode("utf-8")

def write_docx(src, dst, xml):
    tmp = dst + ".tmp"
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename == DOC:
                continue
            zout.writestr(item, zin.read(item.filename))
        zout.writestr(DOC, xml.encode("utf-8"))
    shutil.move(tmp, dst)

def apply_edits(path, edits, report):
    xml = load_xml(path)
    for e in edits:
        find, repl = e["find"], e["replace"]
        n = xml.count(find)
        if n == 0:
            report.append(f"  !! NOT FOUND: {find[:60]!r}...")
            continue
        exp = e.get("expect")
        if exp is not None and n != exp:
            report.append(f"  ?? count {n} != expect {exp}")
        xml = xml.replace(find, repl)
        report.append(f"  ok x{n}: {find[:50]!r}")
    write_docx(path, path, xml)

def main():
    report = []

    spec_a = os.path.join(BASE, "SpecA_หน้าหลัก_สิทธิ์_v3.docx")
    apply_edits(spec_a, [
        {"find": "orgcode และฝ่าย) ", "replace": "(รวมจาก orgcode ∪ ฝ่าย) ", "expect": 1},
        {"find": "Acting)", "replace": "Acting) — ทั้งสองดึงจากตารางพนักงานเดียวกัน (mas_employee_data) แยกด้วยคอลัมน์ posstatus ไม่มี master แยก; ผู้รักษาการ (Acting) เห็น Cost center ของ orgcode ที่รักษาการนั้นด้วย", "expect": 1},
        {"find": "ดูรายละเอียดในเอกสาร approval)", "replace": "C-Level — ดูเอกสารกระบวนการอนุมัติ (Approval Workflow))", "expect": 1},
        {"find": "per-diem engine ในเอกสาร 02", "replace": "per-diem engine ในเอกสาร 02 — ฟอร์มย่อยใส่รายละเอียดงบ Special GL Subform", "expect": 1},
        {"find": 'ผู้อนุมัติเห็นป้ายสถานะ รออนุมัติ/อนุมัติแล้ว ต่อฝ่าย พร้อมสวิตช์ "เฉพาะที่รออนุมัติ"',
         "replace": 'ผู้อนุมัติเห็นป้ายสถานะ รออนุมัติ/อนุมัติแล้ว ต่อฝ่าย พร้อมสวิตช์ "เฉพาะที่รออนุมัติ" (ดูภาพประกอบ: ตัวเลือกฝ่าย (เปิด) — มุมมองผู้อนุมัติ, ภาพประกอบ 5.4) — เช่น ฝ่าย Solution Delivery แสดงป้าย "รออนุมัติ (2)"; เปิดสวิตช์ "เฉพาะที่รออนุมัติ" แล้วรายการเหลือเฉพาะฝ่ายที่ค้างที่ขั้นอนุมัติของผู้ใช้คนนั้น', "expect": 1},
        {"find": 'ปุ่ม "ใส่รายละเอียดงบทำการ" (Special รหัสบัญชี (GL))',
         "replace": 'ปุ่ม "ใส่รายละเอียดงบทำการ" (Special รหัสบัญชี (GL)) (ปุ่มมีไอคอนเครื่องหมายบวกนำหน้า ข้อความบนปุ่ม = "ใส่รายละเอียดงบทำการ"; เป็นปุ่มในแถวของ GL กลุ่มพิเศษ ไม่ใช่ปุ่มบนแถบเครื่องมือ)', "expect": 1},
        {"find": "Pending — GL ปกติ (มียอด)", "replace": "Pending — GL ปกติ (มียอด) — หมายเหตุ: สัญลักษณ์ ①–④ อ้างถึงชั้นข้อมูลในตารางหลัก ไม่ใช่ตำแหน่งในภาพ", "expect": 1},
        {"find": "C-Level: ดูเอกสาร 10 + เอกสารกระบวนการอนุมัติ (Approval Workflow) กระบวนการทำงาน",
         "replace": "C-Level: ดูเอกสารกระบวนการอนุมัติ (Approval Workflow)", "expect": 1},
        # run-split (ดูเอกสาร 02) in table bullet
        {"find": "(ดูเอกสาร </w:t></w:r><w:r w:rsidRPr=\"00491CAE\"><w:rPr><w:rFonts w:ascii=\"CordiaUPC\" w:eastAsia=\"CordiaUPC\" w:hAnsi=\"CordiaUPC\" w:cs=\"CordiaUPC\"/><w:color w:val=\"000000\" w:themeColor=\"text1\"/><w:szCs w:val=\"24\"/><w:highlight w:val=\"yellow\"/></w:rPr><w:t>02)",
         "replace": "(ดูเอกสาร 02 — ฟอร์มย่อยใส่รายละเอียดงบ Special GL Subform)", "expect": 1},
        # run-split (รายละเอียด GL กลุ่มพิเศษอยู่ในเอกสาร 02)
        {"find": "รายละเอียด </w:t></w:r><w:r w:rsidRPr=\"001618A6\"><w:rPr><w:rFonts w:ascii=\"CordiaUPC\" w:eastAsia=\"CordiaUPC\" w:hAnsi=\"CordiaUPC\" w:cs=\"CordiaUPC\"/><w:color w:val=\"000000\" w:themeColor=\"text1\"/><w:szCs w:val=\"24\"/></w:rPr><w:t xml:space=\"preserve\">GL </w:t></w:r><w:r w:rsidRPr=\"001618A6\"><w:rPr><w:rFonts w:ascii=\"CordiaUPC\" w:eastAsia=\"CordiaUPC\" w:hAnsi=\"CordiaUPC\" w:cs=\"CordiaUPC\"/><w:color w:val=\"000000\" w:themeColor=\"text1\"/><w:szCs w:val=\"24\"/></w:rPr><w:t>กลุ่มพิเศษอยู่ใน</w:t></w:r><w:commentRangeStart w:id=\"2\"/><w:r w:rsidRPr=\"001618A6\"><w:rPr><w:rFonts w:ascii=\"CordiaUPC\" w:eastAsia=\"CordiaUPC\" w:hAnsi=\"CordiaUPC\" w:cs=\"CordiaUPC\"/><w:color w:val=\"000000\" w:themeColor=\"text1\"/><w:szCs w:val=\"24\"/></w:rPr><w:t>เอกสาร </w:t></w:r><w:r w:rsidRPr=\"001618A6\"><w:rPr><w:rFonts w:ascii=\"CordiaUPC\" w:eastAsia=\"CordiaUPC\" w:hAnsi=\"CordiaUPC\" w:cs=\"CordiaUPC\"/><w:color w:val=\"000000\" w:themeColor=\"text1\"/><w:szCs w:val=\"24\"/></w:rPr><w:t>02",
         "replace": "(รายละเอียด GL กลุ่มพิเศษอยู่ในเอกสาร 02 — ฟอร์มย่อยใส่รายละเอียดงบ Special GL Subform", "expect": 1},
    ], report)
    report.append("SpecA done")

    spec_b = os.path.join(BASE, "SpecB_GL_Subform_v3.docx")
    apply_edits(spec_b, [
        {"find": "ส่วน B: หน้ากรอกงบประมาณ: Module 02: ฟอร์มย่อยใส่รายละเอียด (Special กลุ่มรหัสบัญชี Subform)", "replace": "", "expect": 1},
        {"find": "โหมดอ่านอย่างเดียวของฟอร์มย่อย (Read-only lock)", "replace": "โหมดอ่านอย่างเดียวของฟอร์มย่อย (Read-only lock · ADR-0013)", "expect": 1},
        {"find": "6.3) โหมดอ่านอย่างเดียวของ Trip Manager (Read-only lock)", "replace": "6.3) โหมดอ่านอย่างเดียวของ Trip Manager (Read-only lock · ADR-0013)", "expect": 1},
        {"find": "เบี้ยเลี้ยงคำนวณใหม่ทุกครั้งที่อ่าน (Recompute-on-read):", "replace": "เบี้ยเลี้ยงคำนวณใหม่ทุกครั้งที่อ่าน (Recompute-on-read · ADR-0015):", "expect": 1},
        {"find": "v0.3: เพิ่มโหมดอ่านอย่างเดียว", "replace": "v0.3: เพิ่มโหมดอ่านอย่างเดียว (ADR-0013)", "expect": 1},
        {"find": "แล้วเฉลี่ยลงเดือนที่เลือก แก้ตัวเลขรายเดือนไม่ได้", "replace": "แล้วเฉลี่ยลงเดือนที่เลือก แก้ตัวเลขรายเดือนไม่ได้ · การแบ่งลงเดือน: แต่ละเดือนปัดทศนิยม 2 ตำแหน่ง เดือนสุดท้ายที่เลือกรับเศษที่เหลือ เพื่อให้ผลรวมทั้งปีเท่ายอดเต็มพอดี (ADR-0005)", "expect": 1},
        {"find": "Forklift: Excavator: Loader: Crane: Water Truck: Road Sweeper Truck …", "replace": "Forklift: Tractor: Excavator: Loader: Crane: Water Truck: Road Sweeper Truck", "expect": 1},
        {"find": "(recompute-on-read)", "replace": "(recompute-on-read · ADR-0015)", "expect": 1},
    ], report)
    report.append("SpecB done")

    spec_c = os.path.join(BASE, "SpecC_Master_Tables_v3.docx")
    apply_edits(spec_c, [
        {"find": "บัญชี Azure AD ของบริษัท group `master-table-admins`", "replace": "Microsoft Entra ID (เดิม Azure AD) group `master-table-admins`", "expect": 4},
        {"find": "แสดง \"Module 03: Master Data\"", "replace": "แสดง \"Module 03 · Master Data\"", "expect": 1},
        {"find": "Module 07: Master Data", "replace": "Module 07 · Master Data", "expect": 1},
        {"find": "Module 08: Document Hiding", "replace": "Module 08 · Document Hiding", "expect": 1},
        {"find": "Module 09: Exchange Rate", "replace": "Module 09 · Exchange Rate", "expect": 1},
        {"find": "Module 10: Submission Deadline", "replace": "Module 10 · Submission Deadline", "expect": 1},
        {"find": ": first year", "replace": "— first year", "expect": 1},
        {"find": "แก้ไข/ส่งได้ตาม)", "replace": "แก้ไข/ส่งได้ตาม ADR-0012)", "expect": 1},
        {"find": "ไม่ใช่การล็อกทั้งระบบ (ตาม): ผู้ดูแลระบบ (allowlist 4 คน", "replace": "ไม่ใช่การล็อกทั้งระบบ (ตาม ADR-0012): ผู้ดูแลระบบ (admin allowlist 4 คน", "expect": 1},
        {"find": "v0.2: เพิ่มข้อยกเว้น ผู้ดูแลระบบ-override-after-deadline ตาม (", "replace": "v0.2: เพิ่มข้อยกเว้น ผู้ดูแลระบบ-override-after-deadline ตาม ADR-0012 (", "expect": 1},
        {"find": "ส่งได้ → APPROVED โดยตรง ตาม):", "replace": "ส่งได้ → APPROVED โดยตรง ตาม ADR-0012):", "expect": 1},
        {"find": "ที่ไม่มีเจ้าของ (ตาม)", "replace": "ที่ไม่มีเจ้าของ (ตาม ADR-0007)", "expect": 1},
        {"find": "เสริมกับกฎ row-visibility และตัวกรอง Actuals มาตรฐานใน CLAUDE.md", "replace": "เสริมกับกฎ row-visibility (ADR-0010) และตัวกรอง Actuals มาตรฐานใน CLAUDE.md", "expect": 1},
        {"find": "เสริมกับกฎ row-visibility ของ dashboard และตัวกรอง Actuals มาตรฐานใน CLAUDE.md", "replace": "เสริมกับกฎ row-visibility (ADR-0010) ของ dashboard และตัวกรอง Actuals มาตรฐานใน CLAUDE.md", "expect": 1},
        {"find": "เหตุผล: Currency Master มีอัตราเดียวต่อปี", "replace": "เหตุผล (ADR-0015): Currency Master มีอัตราเดียวต่อปี", "expect": 1},
        {"find": "แทนที่โมเดล snapshot + re-approval เดิม ที่ถูกยกเลิกแล้ว", "replace": "แทนที่โมเดล snapshot + re-approval เดิม (ADR-0011) ที่ถูกยกเลิกแล้ว", "expect": 1},
        {"find": "ปรับหัวข้อ \"ผลกระทบเมื่อแก้ไขอัตรา\" ให้ตรงกับ (recompute-on-read):", "replace": "ปรับหัวข้อ \"ผลกระทบเมื่อแก้ไขอัตรา\" ให้ตรงกับ ADR-0015 (recompute-on-read):", "expect": 1},
        {"find": "เนื้อหา v0.3 อิงโมเดล snapshot/ ซึ่งถูกแทนที่แล้วใน v0.4)", "replace": "เนื้อหา v0.3 อิงโมเดล snapshot/ADR-0011 ซึ่งถูกแทนที่แล้วใน v0.4)", "expect": 1},
    ], report)
    report.append("SpecC done")

    print("\n".join(report))

if __name__ == "__main__":
    main()
