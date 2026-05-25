# 0008 Hide Document Number Master

หน้าจัดการกฎ **ซ่อน SAP Document Number ในงวดบัญชีที่กำหนด** สำหรับ compliance, audit, และ closed period control

> 🔒 **เฉพาะผู้ดูแลระบบ** (Azure AD group: `master-table-admins` · 3 คน)

---

## ภาพรวม

หน้านี้ช่วยให้ controller "ปิดการมองเห็น" Document Number ใน specific fiscal periods เช่น:
- ช่วง audit
- งวดที่ closed แล้ว
- Adjustment entries

### โครงสร้างข้อมูล

ใช้ **1 ตารางเดียว** (composite PK 3 cols):

```
cfg_master.hide_document_number
├── doc_num      STRING  ┐
├── fiscal_year  INT     ├ Composite PK (3 cols)
└── fiscal_month INT     ┘
```

**ตัวอย่าง:** ต้องการ hide `5400005042` ในไตรมาส 1 ปี 2026 → 3 rows:
- `(5400005042, 2026, 1)`
- `(5400005042, 2026, 2)`
- `(5400005042, 2026, 3)`

### ทำไมเก็บ Year/Month แยกกัน

| Approach | Pro | Con |
|----------|-----|-----|
| **แยก INT (ที่ใช้)** | Filter เร็ว: `WHERE fiscal_year = 2026` | ต้อง concat ตอน display |
| รวมเป็น "2026-01" STRING | Display ง่าย | Query ช้า ต้อง SUBSTRING |
| รวมเป็น DATE 2026-01-01 | Date arithmetic ได้ | Day field ไม่จำเป็น |

Decision (locked): แยก INT เพราะ downstream queries (Power BI) filter ตาม fiscal_year บ่อย

---

## การ Deploy

ขั้นตอนเหมือน 0003/0007 — ดู `0003-gl-group/README.md` สำหรับ overview

ที่ต่าง:
- API base path: `/api/master/hide-document`
- Reference table: `cfg_master.sap_document_number_ref`
- Schema มี CHECK constraints (year 2020-2099, month 1-12)

---

## การใช้งาน

### 1. เพิ่ม Hide Rule

1. เลือก Document Number จาก dropdown (search ได้)
2. ใส่ Fiscal Year (2020-2099)
3. เลือก Fiscal Month (1-12)
4. กด **Save**

**Validation Layers (3 ชั้น):**
1. Frontend: input `min=2020 max=2099`, dropdown 1-12, dup check
2. Backend (Pydantic): `ge=2020 le=2099`, `ge=1 le=12`, dup check
3. SQL (CHECK constraint): `BETWEEN 2020 AND 2099`, `BETWEEN 1 AND 12`

### 2. ลบ Rule

1. กด **Delete** ในแถว
2. Modal "ยืนยันลบ" ขึ้น
3. กด **ลบ** → ระบบลบเฉพาะ triple นั้น

> ⚠️ **ระบบลบเฉพาะงวดเดียวที่เลือก** ไม่ใช่ทุก period ของ document นั้น

### 3. ไม่มี Edit Mode

ทั้ง 3 columns เป็น PK — ถ้าผิด ลบแล้วเพิ่มใหม่

---

## การแก้ไขปัญหา

### Error: "Year ต้องอยู่ระหว่าง 2020-2099" (400)

**สาเหตุ:** Pydantic หรือ SQL CHECK constraint ปฏิเสธ

**วิธีแก้:** ปี ต้องเป็น 2020-2099 (มี 3 layers ป้องกัน)

### Error: "DUPLICATE_KEY" (409)

**สาเหตุ:** Triple (doc, year, month) นี้มีอยู่แล้ว

**ตัวอย่าง:**
- มี row `(5400005042, 2026, 1)` อยู่
- กด Save `(5400005042, 2026, 1)` อีก → reject
- แต่ Save `(5400005042, 2026, 2)` → OK (เดือนต่าง)

### Document หายไปทั้งหมด

⚠️ ถ้าเผลอ delete หลาย rows → ใช้ Delta Time Travel กู้ภายใน 7 วัน

```sql
INSERT INTO cfg_master.hide_document_number
SELECT * FROM cfg_master.hide_document_number 
TIMESTAMP AS OF current_timestamp() - INTERVAL 1 HOUR
WHERE doc_num = '5400005042'
  AND NOT EXISTS (
      SELECT 1 FROM cfg_master.hide_document_number cur
      WHERE cur.doc_num = '5400005042'
        AND cur.fiscal_year = fiscal_year
        AND cur.fiscal_month = fiscal_month
  );
```

---

## โครงสร้างไฟล์

```
0008-hide-document/
├── frontend/
│   ├── HTML-MODIFICATIONS.md
│   ├── api-client.js
│   └── 0008-hide-document.js   ← handles year/month split + period formatting
│
├── backend/
│   ├── function_app.py
│   ├── auth.py
│   ├── db.py
│   ├── models.py               ← Pydantic ge/le validation
│   ├── requirements.txt
│   └── handlers/
│       ├── list_handler.py     ← SQL computes "YYYY-MM" via CONCAT+LPAD
│       ├── save_handler.py
│       ├── delete_handler.py
│       └── reference_handler.py
│
├── sql/
│   ├── 01_create_tables.sql    ← PK (3 cols) + CHECK constraints
│   ├── 02_seed_reference.sql
│   ├── 03_merge_upsert.sql     ← ON clause: 3 cols + 2 ANDs
│   └── 04_hard_delete.sql      ← WHERE: 3 cols + 2 ANDs
│
├── tests/
│   ├── pytest.ini
│   ├── test_handlers.py        ← range tests + composite PK tests
│   └── test_merge_logic.py     ← SQL pattern verification
│
├── deploy/
│   ├── staticwebapp.config.json
│   ├── github-actions.yml
│   └── local.settings.json.template
│
├── spec.yml
└── README.md
```

---

## หมายเหตุสำคัญ

### 3-Column Composite PK = Hardest Test Case

หน้านี้ test ความสามารถของ skill v2 ในเรื่อง:
- **PRIMARY KEY (col1, col2, col3)** — ไม่ใช่แค่ 1 หรือ 2
- **MERGE ON 3 columns + 2 ANDs**
- **DELETE WHERE 3 columns + 2 ANDs**
- **CHECK constraints from HTML range inputs**

ถ้า skill v2 ทำตรงนี้ผ่าน → ใช้ได้กับทุก composite PK pattern (1, 2, 3+ cols)

### Three-Layer Validation

| Layer | Where | What it checks |
|-------|-------|----------------|
| Frontend | HTML `<input min max>` + JS guards | UX feedback ทันที |
| Backend | Pydantic `ge=` `le=` | Reject bad payload |
| Database | SQL `CHECK BETWEEN` | Final defense |

ทั้ง 3 layers สอดคล้องกัน — ปี 2020-2099, เดือน 1-12

---

## ติดต่อ

**เจ้าของระบบ:** Volks (Senior Data Engineer)  
**ทีม:** Data Engineering — Chememan
