# UI Test Plan — ผลการทดสอบจริง (2026-07-22)

แหล่งอ้างอิง: `docs/test/ui-test-plan.md`
สภาพแวดล้อมที่ทดสอบ: **http://127.0.0.1:5180** (dev server ที่รันด้วย `vite.review.config.ts`)

> **สำคัญ — เซิร์ฟเวอร์ที่พอร์ต 5180 ไม่ได้ต่อกับ backend ในเครื่อง**
> `vite.review.config.ts` proxy ทุก API namespace ไปที่ **staging container**
> `cman-budget-web-stg.kindstone-f34836dd.southeastasia.azurecontainerapps.io`
> พร้อมยัด header `x-ms-client-principal-name: suchanyay@chememan.com` ให้อัตโนมัติ
> ทุก request ผลการทดสอบทั้งหมดจึงเป็นผลของ **staging backend + Fabric SQL ตัวจริง**
> (ไม่ใช่ uvicorn :8000 ในเครื่อง ซึ่ง feature-flag ต่างกัน — ดูข้อ 10.4)

## สรุปตัวเลข

| กลุ่ม | จำนวนข้อ | ผ่าน | ไม่ผ่าน | ไม่ได้รัน |
|-------|---------|------|--------|-----------|
| Part 1–5 (shell / ตัวกรอง / ตาราง / inline edit / เพิ่มรายการ) | 33 | 33 | 0 | 0 |
| Part 6 (special GL ครบ 6 กลุ่ม) | 34 | 34 | 0 | 0 |
| Part 7–10 (ลบแถว / อนุมัติ / แนบไฟล์ / บทบาท) | 21 | 18 | 1 | 2 |
| Part 11 (reconcile UI ↔ DB) | 10 | 9 | 0 | 1 |
| Part 12 (regression guards) | 5 | 4 | 1 | 0 |
| **รวม** | **103** | **98** | **2** | **3** |

หมายเหตุ: หัวเรื่องในแผนเขียนว่า 96 ข้อ แต่ตารางย่อยของแผนเองรวมได้ **103** ข้อ
(33 + 34 + 21 + 10 + 5) — ใช้ 103 เป็นตัวตั้ง

ผลรายข้อแบบเต็ม (พร้อมหลักฐานต่อข้อ) อยู่ใน `docs/test/ui-test-results-2026-07-22.jsonl`

## ข้อที่ไม่ผ่าน

### 10.4 — GL เฉพาะแอดมิน ยังไม่ถูกซ่อนบน staging (config drift, ไม่ใช่บั๊กโค้ด)
`dbo.gl_group` มี 12 แถวที่ `edit_by='admin'` แต่ `GET /budget/gl-accounts` บน staging
คืน GL ครบ 146 รายการให้ filler (suchanyay) — เท่ากับที่ admin เห็น
backend ในเครื่อง (ตั้ง `GL_EDIT_BY_ENABLED=true`) คืน 134 รายการอย่างถูกต้อง
→ ต้องเปิด env `GL_EDIT_BY_ENABLED` ที่ container ของ staging

### 12.3 — e2e journey suite 20/23
- filler 1.1 และ approver 2.1 หา `combobox` ชื่อ `/ปีงบประมาณ/` แต่ `YearPicker`
  ใช้ aria-label ใหม่ว่า `ปีฐาน (SAP/Approved · Pending = ปีถัดไป)` → **selector เก่า**
  ตกยุคหลังรีดีไซน์ ไม่ใช่บั๊กแอป
- edge-states 4.1 คาดว่า caller ที่ไม่มีสิทธิ์ (`role='none'`) ต้องไม่ยิง
  `/scope/departments` เลย แต่ของจริงยิง 1 ครั้ง (`UserBar` → `useOwnDepartments`)
  → พฤติกรรมเปลี่ยนจริง (ไม่รั่วข้อมูล เพราะ response เป็นลิสต์ว่าง)
- รอบแรกที่รันพร้อม vitest + browser test อื่น timeout 22/23 ข้อตอน "setting up page"
  suite นี้ต้องรันตอนเครื่องว่าง

## ข้อที่ไม่ได้รัน (ตั้งใจ)

- **9.1 อัปโหลดไฟล์จริง** — เขียนไฟล์ลง SharePoint ของบริษัทจริง และแอปไม่มี endpoint ลบ
  จึงเก็บกวาดไม่ได้ ขอให้ jakkaritw ยืนยันก่อน (ทางอ้อมตรวจแล้วผ่านข้อ 9.2 และ 9.4)
- **9.3 เปิด/ดาวน์โหลดไฟล์** — โฟลเดอร์ `Solution Delivery/2027/` ยังไม่มีไฟล์ (list ตอบ 200 ลิสต์ว่าง)
- **11.8 reconcile ไฟล์แนบ** — สืบเนื่องจาก 9.1

## ข้อสังเกตเพิ่ม (ไม่ได้อยู่ในแผน แต่เจอระหว่างทดสอบ)

1. **ผู้อนุมัติขั้น 2/3 เข้าไม่ถึงฝ่ายที่ตัวเองต้องอนุมัติผ่านหน้าเว็บ**
   Nipaporn (ขั้น 2) และ Waraporn (ขั้น 3) ต้องอนุมัติ `Solution Delivery`
   แต่ `10IT012000` ไม่อยู่ใน See scope ของทั้งคู่ (มี 7 CC ไม่มี CC นี้)
   → ฝ่ายนี้ไม่โผล่ใน ฝ่าย-picker ของเขา กดอนุมัติจากหน้าเว็บไม่ได้เลย
   การทดสอบขั้น 2/3 จึงต้องยิงผ่าน API ตรง ๆ
   (`/approval/pending-for-me` บอกว่ามีงานรอ แต่หน้าเว็บพาไปที่ฝ่ายนั้นไม่ได้)
2. **`vite.review.config.ts` เขียนทับ header ตัวตนเสมอ** — ทดสอบหลาย persona บนพอร์ต 5180
   ไม่ได้ ต้องรัน dev server ตัวที่สอง (ทำไว้ชั่วคราวแล้วลบทิ้ง) จึงจะทดสอบ
   approver / admin / see-only ผ่าน UI ได้
3. **React StrictMode ทำให้ subform โหลดซ้ำ 2 รอบ** (dev เท่านั้น) — ถ้าพิมพ์ก่อน response
   รอบสองมาถึง ค่าที่พิมพ์จะถูกทับหายเงียบ ๆ ใน production build ไม่มีอาการนี้
   แต่เป็นกับดักของทั้งคนเทสและ automation
4. **`GET /budget/detail` ไม่คืนฟิลด์ `is_auto_calc`** — ตรวจข้อ 6F.2 จาก API ไม่ได้
   ต้องยืนยันที่ DB (ยืนยันแล้วว่า `is_auto_calc=1`)

## ข้อมูลทดสอบ & การเก็บกวาด

ทดสอบบน cost center `10IT012000` (ฝ่าย Solution Delivery) ปีงบ 2027 ด้วย DB ที่ใช้ร่วมกัน
ทุกอย่างที่สร้างระหว่างเทสถูกลบคืนหมดแล้ว:

- `budget.pending_budget` / `pending_budget_detail` / `budget_trip` ของ CC นี้ ปี 2027 = **0 แถว**
- `budget.approval_status` + `approval_log` ของ (Solution Delivery, 2027) ลบแล้ว
  (ก่อนเริ่มเทส `approval_log` ทั้งตารางมี 0 แถว และฝ่ายนี้ยังไม่มีแถว status → กลับสู่สภาพเดิม)
- แถวเดิมจากเซสชันก่อนหน้า (`6210900060` remark "ทดสอบ remark ลง DB" สร้าง 2026-07-21 19:53)
  ถูกใช้ทดสอบข้อ 4.1/4.3 แล้วลบไปพร้อมกัน — ถ้าต้องการเก็บไว้ ต้องสร้างใหม่
- ไม่มีการเขียนไฟล์ใด ๆ ลง SharePoint

## วิธีรันซ้ำ

harness (Playwright + pyodbc) เก็บไว้ที่
`C:\Users\JAKKAR~1\AppData\Local\Temp\claude\c--04-budget-management-web\7cd31361-efda-4862-a4ef-c05810a8c1fb\scratchpad\uitest\`
คัดลอกทั้งโฟลเดอร์ไปวางใน `frontend/` (ต้องอยู่ในนั้นเพื่อ resolve `playwright`) แล้วสั่ง
`node t1_shell.mjs` … `node t6_roles.mjs`, `python -X utf8 reconcile.py`, ปิดท้ายด้วย `node cleanup.mjs`
