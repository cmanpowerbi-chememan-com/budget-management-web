# 0007 Orgcode-CostCenter Master

หน้าจัดการ mapping ระหว่าง **Cost Center** กับ **SAP Orgcode** แบบ many-to-many

> 🔒 **เฉพาะผู้ดูแลระบบ** (Azure AD group: `master-table-admins` · 3 คน)

---

## ภาพรวม

| ส่วนประกอบ | เทคโนโลยี | จุดประสงค์ |
|------------|-----------|------------|
| Frontend | Vanilla HTML/JS | UI ฟอร์ม + ตาราง |
| Frontend Host | Azure Static Web Apps | Host + Azure AD auth |
| Backend | Azure Function (Python) | CRUD API |
| Database | Microsoft Fabric Lakehouse | Delta tables (`cfg_master.*`) |
| Reference Data | OneLake | Sync จาก SAP ทุกคืน |

### โครงสร้างข้อมูล

ใช้ **1 ตารางเดียว** (junction table):

- **`cfg_master.orgcode_costcenter`** — composite PK `(cost_center, orgcode)`

ไม่มี dimension table แยก เพราะเป็น pure relationship — แต่ละ row คือ "pair" ที่ unique

### Many-to-Many Pattern

```
Cost Center 10SP010000  ←→  Orgcode 1110000  (row 1)
                       ←→  Orgcode 1130000  (row 2)  
                       ←→  Orgcode 1410000  (row 3)

Cost Center 10SP012000  ←→  Orgcode 1110000  (row 4)  ← orgcode ซ้ำกับ row 1 ได้
                       ←→  Orgcode 1120000  (row 5)
```

1 Cost Center → หลาย Orgcodes (ได้)  
1 Orgcode → หลาย Cost Centers (ได้)  
แต่ (Cost Center, Orgcode) pair → unique เสมอ

---

## การ Deploy

ส่วนใหญ่เหมือนกับ 0003 — ดู `0003-gl-group/README.md` สำหรับขั้นตอนทั่วไป

ที่ต่าง:
- API base path: `/api/master/orgcode-costcenter` (ไม่ใช่ `/api/master/gl-group`)
- Reference table: `cfg_master.sap_orgcode_ref` (ไม่ใช่ `sap_gl_code_ref`)
- ไม่มี dimension table — schema ง่ายกว่า

### Database Schema

```python
with open("sql/01_create_tables.sql") as f:
    for stmt in f.read().split(";"):
        if stmt.strip():
            spark.sql(stmt)
```

---

## การใช้งาน

### 1. เพิ่ม Mapping

1. กรอก Cost Center (auto-uppercase, รับเฉพาะ A-Z + 0-9)
2. เลือก Orgcode จาก dropdown (search ได้)
3. กด **Save**

**Validation:**
- ถ้าพิมพ์ตัวอักษรแปลกใน Cost Center → input flash แดง 600ms
- ถ้า pair `(Cost Center, Orgcode)` มีอยู่แล้ว → reject (Fail Fast)
- ⚠️ Cost Center เดียวกัน + Orgcode คนละตัว = **ไม่ใช่ duplicate** (เพิ่มได้)

### 2. ลบ Mapping

1. กด **Delete** ในแถว
2. Modal "ยืนยันลบ" ขึ้นมา
3. กด **ลบ** → ระบบลบทันที (hard delete)

> ⚠️ ระบบลบเฉพาะ **pair นั้น** เท่านั้น  
> ถ้าต้องการลบ Orgcodes ทั้งหมดของ Cost Center → ต้องลบทีละ row

### 3. ไม่มี Edit Mode

Junction table มีแค่ 2 columns ซึ่งทั้งคู่เป็น PK → ไม่มีอะไรให้แก้ ถ้าผิด ให้ลบแล้วเพิ่มใหม่

---

## การแก้ไขปัญหา

### Error: "DUPLICATE_KEY" (409)

**สาเหตุ:** Pair (Cost Center, Orgcode) นี้มีอยู่ในฐานข้อมูลแล้ว

**ตัวอย่าง:**
- มี row `(10SP010000, 1110000)` อยู่
- คุณกด Save `(10SP010000, 1110000)` อีก → reject
- แต่ถ้า Save `(10SP010000, 1130000)` → OK (เพราะ orgcode ต่าง)

### Error: "Cost Center format invalid" (400)

**สาเหตุ:** Cost Center มีตัวอักษรที่ไม่ใช่ A-Z หรือ 0-9

**วิธีแก้:** ใช้เฉพาะตัวอักษรภาษาอังกฤษพิมพ์ใหญ่ + ตัวเลข

### หาก Cost Center หายไปทั้งกลุ่ม

⚠️ **ถ้าพี่หรือ admin คนอื่นเผลอลบ → ใช้ Delta Time Travel กู้ภายใน 7 วัน**

```sql
-- ดูสถานะเมื่อ 1 ชั่วโมงก่อน
SELECT * FROM cfg_master.orgcode_costcenter
TIMESTAMP AS OF current_timestamp() - INTERVAL 1 HOUR
WHERE cost_center = '10SP010000';
```

---

## โครงสร้างไฟล์

```
0007-orgcode-costcenter/
├── frontend/
│   ├── HTML-MODIFICATIONS.md
│   ├── api-client.js
│   └── 0007-orgcode-costcenter.js
│
├── backend/
│   ├── function_app.py
│   ├── auth.py
│   ├── db.py
│   ├── models.py
│   ├── requirements.txt
│   └── handlers/
│       ├── list_handler.py
│       ├── save_handler.py
│       ├── delete_handler.py
│       └── reference_handler.py
│
├── sql/
│   ├── 01_create_tables.sql       ← composite PK CREATE TABLE
│   ├── 02_seed_reference.sql      ← (empty)
│   ├── 03_merge_upsert.sql        ← MERGE with both PK in ON
│   └── 04_hard_delete.sql         ← DELETE with both PK in WHERE
│
├── tests/
│   ├── pytest.ini
│   ├── test_handlers.py           ← composite PK behavior tests
│   └── test_merge_logic.py        ← SQL pattern verification
│
├── deploy/
│   ├── staticwebapp.config.json
│   ├── github-actions.yml
│   └── local.settings.json.template
│
├── spec.yml                        ← skill input spec
└── README.md                       ← ไฟล์นี้
```

---

## หมายเหตุสำคัญ

### Composite PK = สิ่งที่ทำให้ skill v2 มีคุณค่า

หน้านี้คือ **เหตุผลหลัก** ที่ skill v1 ใช้ไม่ได้:
- skill v1 generate MERGE แค่ `ON t.pk = s.pk` (single column)
- เมื่อมี Cost Center เดียวมีหลาย Orgcodes → MERGE fail ด้วย `DELTA_MULTIPLE_SOURCE_ROW_MATCHING_TARGET_ROW_IN_MERGE`

skill v2 สร้าง `ON t.cost_center = s.cost_center AND t.orgcode = s.orgcode` → ผ่าน

### ไม่มี Edit, ไม่มี Audit

- Junction table ไม่มีอะไรให้ Edit (ทุก column เป็น PK)
- ไม่เก็บ updated_by/updated_at (locked decision #16)
- ถ้าต้อง debug → ใช้ Delta Time Travel

---

## ติดต่อ

**เจ้าของระบบ:** Volks (Senior Data Engineer)  
**ทีม:** Data Engineering — Chememan  
**Repository:** `tanasedw/web-chememan-master`
