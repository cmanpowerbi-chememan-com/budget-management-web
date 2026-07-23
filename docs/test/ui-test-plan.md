# UI Test Plan — Budget Management Web (OPEX) · ฉบับละเอียด

แผนทดสอบหน้า UI ทุกจุด แบ่งเป็น **12 หัวข้อใหญ่ (Part) · 96 หัวข้อย่อย (Test Items)**
ครบทั้ง 6 special GL groups แยกละเอียดรายกลุ่ม + เทียบ DB ทุก flow ที่เขียนข้อมูล
เกณฑ์ผ่านของทุกข้อ: ผลบนหน้าจอตรง expected **และ** DB ตรงตามหลักฐานที่ระบุ (Part 11)
สภาพแวดล้อม: dev server (Vite) + staging backend + Fabric SQL (shared test DB)

---

## Part 1 — Smoke & App Shell (5 items)

| # | Test | Expected |
|---|------|----------|
| 1.1 | เปิดแอปครั้งแรก (cold start) | โหลดสำเร็จภายใน ~20 วิ (staging ตื่น) ไม่มีหน้าขาวค้าง |
| 1.2 | ตัวตนบน user bar | ชื่อ/email/สายงาน/ฝ่าย/จำนวน CC/GL ตรง scope |
| 1.3 | role (filler/see_only/admin) | ปุ่มและสิทธิ์ตรง role |
| 1.4 | API grid ล้มเหลว | error banner ไทย + ปุ่มลองใหม่ (ไม่ silent-empty) |
| 1.5 | /scope ล้มเหลว | error state ชัด ไม่ค้างโหลด |

## Part 2 — ตัวกรอง & การนำทาง (7 items)

| # | Test | Expected |
|---|------|----------|
| 2.1 | Forced default ฝ่าย | เลือกฝ่ายแรกตามตัวอักษรอัตโนมัติ ไม่มีสถานะว่าง |
| 2.2 | ค้นหาฝ่าย + Enter | เหลือ 1 ฝ่าย → ไฮไลต์ → Enter เลือกได้ |
| 2.3 | Esc ปิด panel | ปิดโดยไม่เลือก |
| 2.4 | Deep-link `?dept=&year=` | เปิดตรงฝ่าย/ปี; ฝ่ายนอก scope ถูกเมิน |
| 2.5 | Year picker | label = ปีฐาน Y, Pending = Y+1 ตรง legend |
| 2.6 | ฟิลเตอร์ CC/GL/GL Group/Remark | substring case-insensitive, subtotal เฉพาะชุดที่เห็น |
| 2.7 | ฟิลเตอร์ STATUS | `sap`/`งบ`/`pending` เหลือแถวที่ layer นั้นมีค่า (รวมกรณี 0 แถว) |

## Part 3 — ตารางงบหลัก (9 items)

| # | Test | Expected |
|---|------|----------|
| 3.1 | 3 layer ต่อแถว | SAP/Approved/Pending ครบ label ถูก |
| 3.2 | แยก COST (5xxx) / SG&A (6xxx) | 2 section ยอดรวมไม่ปน (never-cut) |
| 3.3 | แถว รวม {group} + รวมทั้งหมด·ฝั่ง | ยอดตรงผลรวมย่อย ไม่มีเส้นหนักเกิน |
| 3.4 | Frozen 5 คอลัมน์ | scroll แล้วติดอยู่ เส้นคั่นต่อเนื่องทั้งตาราง |
| 3.5 | พื้นหลัง/เส้นแถว | เซลล์ STATUS เต็มความสูงแถว ไม่มีกล่องลอย |
| 3.6 | ลากความกว้าง + persist | จำค่าใน localStorage, Reset คืน fit-to-content |
| 3.7 | ซ่อน/แสดงคอลัมน์ (collapse) | colSpan ถูกทั้ง expanded/collapsed |
| 3.8 | เดือนปัจจุบันไฮไลต์ | คอลัมน์เดือนปัจจุบันถูกเน้น |
| 3.9 | ช่อง Pending ของ GL special | แสดงปุ่ม "แก้ไขผ่านฟอร์มย่อย" แทน input ตรง |

## Part 4 — แก้ไขแบบ inline (6 items)

| # | Test | Expected | เทียบ DB |
|---|------|----------|---------|
| 4.1 | พิมพ์ตัวเลขช่อง Pending แล้ว blur | บันทึก + ช่องคงค่า | `pending_budget.mXX` ตรง, `_user` ถูก |
| 4.2 | สร้าง pending จากแถวที่มีแต่ SAP/board | insert แถวใหม่สำเร็จ | แถวใหม่ใน `pending_budget` (template='USER') |
| 4.3 | แก้ remark แล้ว blur | ข้อความติด | `pending_budget.remark` ตรงตัวอักษรไทย |
| 4.4 | 409 conflict | refetch + ข้อความไทย ไม่ทับคนอื่น | ค่าใน DB = ของผู้เขียนก่อน |
| 4.5 | แก้แถวนอก Fill scope | input disable/ไม่มี | ไม่มี request ยิงออก |
| 4.6 | แก้ขณะฝ่ายล็อก (PENDING_*) | แก้ไม่ได้จนถูกตีกลับ | — |

## Part 5 — + เพิ่ม Transaction (6 items)

| # | Test | Expected |
|---|------|----------|
| 5.1 | ค้นหา GL ด้วยรหัส/ชื่อ/กลุ่ม | กรองครบ 3 แบบ, Enter เลือกตัวแรก, Esc ปิด |
| 5.2 | ค้นไม่เจอ | "ไม่พบ GL Code ที่ค้นหา" บันทึกไม่ได้จนเลือกจากลิสต์ |
| 5.3 | GL special ไม่โผล่ | 6 กลุ่ม special ถูกตัดออก |
| 5.4 | CC เฉพาะ Fill scope | dropdown เฉพาะ CC ที่มีสิทธิ์ |
| 5.5 | สร้าง (CC, GL) ซ้ำ | error "รายการนี้มีอยู่ในตารางแล้ว" ไม่ยิง API |
| 5.6 | สร้างสำเร็จ | แถวใหม่ในตาราง + ลง `pending_budget` |

---

## Part 6 — Special GL Groups ทั้ง 6 กลุ่ม (ละเอียดรายกลุ่ม) (34 items)

### เกณฑ์ร่วมทุกกลุ่ม (ใช้กับ 6A–6E) (5 items)

| # | Test | Expected |
|---|------|----------|
| 6.0.1 | โครงตาราง | คอลัมน์เดือน JAN–DEC + แถว MONTHLY TOTAL ขยับตามที่พิมพ์ + footer `Rows: N · Year total: ฿X` |
| 6.0.2 | ปุ่มบันทึกปุ่มเดียว (save-all) | บันทึกทุกแถวครั้งเดียว สำเร็จหมด → ปิด modal |
| 6.0.3 | partial failure | แถวพังมีข้อความแดงระบุเลขแถว แถวอื่นรอด modal ไม่ปิด |
| 6.0.4 | ลบรายการ (ไอคอนถังขยะ) | confirm ไทย → ลบ detail + parent recompute = SUM เหลือ |
| 6.0.5 | หลังเซฟ ช่อง grid | Pending cell = SUM(detail) จาก server ตรง DB (ดู Part 11.3) |

### 6A — Entertainment (5 items)

| # | Test | Expected |
|---|------|----------|
| 6A.1 | GL external (…030) | dropdown ประเภทการรับรอง = Customer / Business partner / หน่วยงานราชการ / อื่นๆ (4 ตัว) |
| 6A.2 | GL internal (…031) | dropdown = พนักงานบริษัท / กรรมการบริษัท (2 ตัว) ห้ามมีชุด external |
| 6A.3 | ฟิลด์ รายละเอียด | พิมพ์อิสระ เก็บลง `meta_json.รายละเอียด` |
| 6A.4 | เลือก + พิมพ์ + เซฟ | `pending_budget_detail.meta_json` มีประเภท + รายละเอียดตรง |
| 6A.5 | เปิดซ้ำรายการเดิม | ค่าเดิมแสดงครบ (select + text restore) |

### 6B — Lease & Rental (7 items)

| # | Test | Expected |
|---|------|----------|
| 6B.1 | GL รถ (…060) | ประเภทรถ = Car/Van/Trucks; ทะเบียนรถ = 7 ทะเบียน + อื่นๆ |
| 6B.2 | อื่นๆ แล้วไม่พิมพ์ทะเบียน | บล็อกเซฟ "กรุณาพิมพ์ทะเบียนรถ" ไม่ยิง API |
| 6B.3 | อื่นๆ + พิมพ์ทะเบียนเอง | ค่าที่ส่ง = ที่พิมพ์ ไม่ใช่คำว่า อื่นๆ |
| 6B.4 | เปิดซ้ำทะเบียนนอกลิสต์ | select แสดง อื่นๆ + ทะเบียนเดิม pre-fill |
| 6B.5 | GL เครื่องจักร (…030) | ประเภทรถ = 11 ชนิดเครื่องจักร; ทะเบียนรถ LOCKED (—) |
| 6B.6 | GL อื่น (010/020/040/050/999) | ประเภทรถ + ทะเบียนรถ LOCKED ทั้งคู่ |
| 6B.7 | สถานที่ใช้งาน + กิจกรรม | dropdown BK/TK/KK/PB/RY + text; ลง `meta_json` ครบ 4 ฟิลด์ |

### 6C — Professional & Legal Fee (3 items)

| # | Test | Expected |
|---|------|----------|
| 6C.1 | ฟิลด์ Project + รายละเอียด | text ล้วน ไม่มี dropdown |
| 6C.2 | เซฟหลายแถว | แต่ละแถวลง detail แยกกัน meta ตรงแถว |
| 6C.3 | เดือนที่กรอก | m01–m12 ลงตรงตำแหน่ง total = Σ |

### 6D — Public Relation & Donation (3 items)

| # | Test | Expected |
|---|------|----------|
| 6D.1 | ฟิลด์เดียว รายละเอียด | คอลัมน์ meta เดียว text |
| 6D.2 | เซฟว่าง meta | บันทึกได้ (meta_json null/ว่าง) ยอดลงถูก |
| 6D.3 | เซฟพร้อมรายละเอียด | `meta_json.รายละเอียด` ตรง |

### 6E — Training & Seminar (3 items)

| # | Test | Expected |
|---|------|----------|
| 6E.1 | ฟิลด์ หลักสูตรอบรม + Method | text + dropdown Inhouse/Public |
| 6E.2 | เซฟทั้งสองฟิลด์ | `meta_json` ครบ 2 ฟิลด์ตรง |
| 6E.3 | เปิดซ้ำ | Method ที่เลือกไว้ restore ถูก |

### 6F — Travelling Expense (Trip Manager) (8 items)

| # | Test | Expected |
|---|------|----------|
| 6F.1 | สร้างทริปครบฟิลด์ | traveler(dropdown+position auto) / destination(auto country_group) / days / travel months / side → เซฟ 1 ครั้งออกครบทริป+4 lines |
| 6F.2 | เบี้ยเลี้ยง server-only | ไม่มีเลข client ก่อนเซฟ; หลังเซฟ = days × rate × FX จาก server (เช็ค `is_auto_calc=1`) |
| 6F.3 | manual 3 ประเภท | พาหนะ/ที่พัก/อื่น ลง GL ตาม side×type ถูก (ดู Part 11.4) |
| 6F.4 | เดือนนอกเหนือ travel months | เป็น 0/ล็อก ไม่ส่งค่า |
| 6F.5 | side lock ฝ่ายฝั่งเดียว | non-admin เปลี่ยนไม่ได้ admin เปลี่ยนได้ |
| 6F.6 | แก้ทริปเดิม | บันทึกด้วย lock token; 409 → โหลดใหม่ |
| 6F.7 | ลบทริป | confirm ไทย → ลบทริป+cascade 4 lines+parent ว่างถูกเก็บ (ดู Part 11.5) |
| 6F.8 | double-click บันทึก | ไม่เกิดทริปซ้ำ (client_token idempotent) |

---

## Part 7 — ลบแถวบนตาราง (Row Delete) (4 items)

| # | Test | Expected |
|---|------|----------|
| 7.1 | ปุ่มลบเฉพาะแถวที่เข้าเงื่อนไข | editable + ไม่มี SAP/Approved + ไม่ใช่ Travelling + มี pending จริง (updated_at non-null) |
| 7.2 | confirm ไทย + ลบ | แถวหาย grid + หาย `pending_budget` (+detail) |
| 7.3 | แถว Travelling ไม่มีปุ่มลบ | ลบผ่าน Trip Manager เท่านั้น |
| 7.4 | แถว board-only (ไม่มี pending จริง) | ไม่มีปุ่มลบ (กัน 422 lock token ว่าง) |

## Part 8 — วงจรอนุมัติ (Approval) (9 items)

| # | Test | Expected |
|---|------|----------|
| 8.1 | ส่งอนุมัติ | confirm สรุปฝ่าย/ปี/จำนวนแถว → PENDING_APPROVER1 + log SUBMIT |
| 8.2 | อนุมัติครบ 3 ขั้น | a1→a2→a3 ถึง APPROVED + log APPROVE ครบ |
| 8.3 | ตีกลับขั้น 1 (direct manager) | เหตุผลบังคับ → REJECTED + เหตุผล + คนตี ลง log |
| 8.4 | ตีกลับขั้น 2 (budget owner) | REJECTED โดยคนขั้น 2 |
| 8.5 | ตีกลับขั้น 3 (C-level) | REJECTED โดยคนขั้น 3 |
| 8.6 | edit + resubmit หลังถูกตีกลับ | grid ปลดล็อก แก้ได้ ส่งใหม่ลง log RESUBMIT |
| 8.7 | สิทธิ์ปุ่มตามบทบาท | filler=ส่งเฉพาะฝ่ายตัวเอง, approver=อนุมัติ/ตีกลับเฉพาะขั้นตัวเอง |
| 8.8 | chip + ตำแหน่ง | chip เหนือปุ่ม ล่างขวาใต้ตาราง ข้อความตรงสถานะ/ขั้น |
| 8.9 | badge รออนุมัติ บน picker | ฝ่ายที่รอเราอนุมัติมี pill |

## Part 9 — แนบไฟล์ (Attachments) (4 items)

| # | Test | Expected |
|---|------|----------|
| 9.1 | อัปโหลด png/pdf/xlsx ≤ 10MB | ขึ้นลิสต์ + ลง SharePoint `{root}/{ฝ่าย}/{ปี}/` |
| 9.2 | นามสกุล/ขนาดเกิน | ปฏิเสธข้อความไทย ไม่ยิงขึ้น SharePoint |
| 9.3 | เปิด/ดาวน์โหลด | ลิงก์ download.aspx ใช้ได้จริง |
| 9.4 | สิทธิ์ | เฉพาะ filler ฝ่ายนั้น/admin — นอก scope = 403 |

---

## Part 10 — บทบาท & สถานะอ่านอย่างเดียว (4 items)

| # | Test | Expected |
|---|------|----------|
| 10.1 | see_only user | อ่านได้ทุกอย่าง แก้/ลบ/ส่งไม่ได้ ไม่มีปุ่ม |
| 10.2 | admin view | เห็นทุกฝ่าย + โซน admin (FX master read-only) |
| 10.3 | หลังส่งอนุมัติ (PENDING_*) | grid ล็อก + subform อ่านอย่างเดียว จนถูกตีกลับ |
| 10.4 | admin-only GL (edit_by=admin) | user ธรรมดาไม่เห็น GL นั้นเลย (ซ่อนจาก master) |

---

## Part 11 — เทียบข้อมูล UI ↔ DB (Reconcile ละเอียด) (10 items)

ตารางเป้าหมาย: `budget.pending_budget` (parent) · `budget.pending_budget_detail` (lines) · `budget.budget_trip` · `budget.approval_status` · `budget.approval_log` · SharePoint (ไฟล์)

| # | Flow | สิ่งที่ต้องตรงใน DB | SQL ตรวจ |
|---|------|---------------------|-----------|
| 11.1 | พิมพ์ตรง normal GL | แถว parent ใหม่/เดิม, เดือนตรง, `total_year`=Σ, `template='USER'`, `_user`=ผู้กรอก | `SELECT * FROM budget.pending_budget WHERE cost_center=@cc AND gl_account=@gl AND fiscal_year=@fy` |
| 11.2 | แก้ remark | `remark` ตรงตัวอักษร (ไทยไม่เพี้ยน), ยอดเดือนไม่เปลี่ยน | 同上 ดูคอลัมน์ `remark` |
| 11.3 | เซฟ subform (6A–6E) | 1 line/แถว: `trip_id IS NULL`, `gl_group` ถูก, เดือนตรง, `meta_json` ครบฟิลด์, **`parent = SUM(detail)` ทุกเดือน** | `SELECT p.gl_account, p.m01, (SELECT SUM(d.m01) FROM budget.pending_budget_detail d WHERE d.cost_center=p.cost_center AND d.gl_account=p.gl_account AND d.fiscal_year=p.fiscal_year) AS detail_sum FROM budget.pending_budget p` |
| 11.4 | เซฟทริป | `budget_trip` 1 แถว (field ครบ, side ถูก) + **4 lines ผูก trip_id เดียวกัน**: per-diem `is_auto_calc=1` (=days×rate×FX) + manual 3 ตัว; parent ทุก GL = SUM | `SELECT * FROM budget.budget_trip WHERE trip_id=@id` + `SELECT gl_account, m01, is_auto_calc FROM budget.pending_budget_detail WHERE trip_id=@id` |
| 11.5 | ลบ detail/ทริป | line หาย; parent recompute=SUM เหลือ; **ไม่เหลือ line → parent ว่างถูกลบเว้นมี remark** | `SELECT COUNT(*) FROM budget.pending_budget_detail WHERE trip_id=@id` ต้อง 0 + parent ตามเงื่อนไข |
| 11.6 | ส่ง/อนุมัติ/ตีกลับ | `approval_status` สถานะปัจจุบันถูก + ทุก action ลง `approval_log` เรียงลำดับ (SUBMIT→APPROVE/REJECT→RESUBMIT) พร้อม actor/เวลา/เหตุผล | `SELECT action, action_by_email, previous_status, new_status, comment FROM budget.approval_log WHERE department=@d AND fiscal_year=@fy ORDER BY log_id` |
| 11.7 | ตัวเลข per-diem | = `days × per_diem_rate(job_level, group) × FX(group>1)` เทียบ `dbo.per_diem_rate`/`dbo.master_currency_rate` | `SELECT rate_domestic, rate_asian, rate_other FROM dbo.per_diem_rate WHERE job_level=@pos` |
| 11.8 | แนบไฟล์ | item อยู่ใน SharePoint path `{root}/{ฝ่าย}/{ปี}/{filename}` ขนาดตรง | เปิดลิงก์ web_url จาก `GET /attachments` |
| 11.9 | ลบแถว grid | parent หาย + detail ของแถวนั้นหาย (cascade) แถวอื่นไม่กระทบ | count ก่อน/หลังทั้ง 2 ตาราง |
| 11.10 | สร้าง transaction ใหม่ | parent แถวใหม่ยอด 0 remark NULL ปรากฏใน grid ทันที | 同上 11.1 |

## Part 12 — Regression Guards (อัตโนมัติประกอบมือ) (5 items)

| # | Test | Expected |
|---|------|----------|
| 12.1 | unit suite frontend ผ่านทั้งหมด | `npm test` เขียว (ปัจจุบัน 475) |
| 12.2 | unit suite backend ผ่านทั้งหมด | `pytest` เขียว (ปัจจุบัน 672) hermetic ทุกเครื่อง |
| 12.3 | e2e journey suite | `npm run test:e2e` ผ่าน (filler/approver/admin/edge) |
| 12.4 | tsc + lint สะอาด | `npm run build` สำเร็จ ไม่มี warning |
| 12.5 | smoke หลัง deploy staging | /health ok + เปิด grid + subform + submit ได้จริงบน staging |

---

### สรุปจำนวน
- **หัวข้อใหญ่ (Part): 12**
- **หัวข้อย่อย (Test items): 96**
  - Part 1–5: shell/นำทาง/ตาราง/inline/เพิ่มรายการ = 33
  - Part 6: special groups ครบ 6 กลุ่ม (เกณฑ์ร่วม 5 + 6A×5 + 6B×7 + 6C×3 + 6D×3 + 6E×3 + 6F×8) = 34
  - Part 7–10: ลบแถว/อนุมัติ/แนบไฟล์/บทบาท = 21
  - Part 11: reconcile UI↔DB ละเอียด = 10
  - Part 12: regression guards = 5
