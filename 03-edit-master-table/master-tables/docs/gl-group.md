# 0003 GL Group Master

หน้าจัดการ mapping ระหว่าง **SAP GL Code** กับ **GL Group** สำหรับใช้สร้างรายงานสรุปบัญชี

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

ใช้ 2 ตาราง:

- **`cfg_master.gl_group_dim`** — รายชื่อ GL Group (group_id UUID + group_name)
- **`cfg_master.gl_group_mapping`** — จับคู่ gl_code → group_id (1:1)

แยก dim ออกมาเพื่อให้ rename group ทำได้ง่าย (UPDATE 1 row แทน UPDATE หลาย row)

### Reference Data

อ่านอย่างเดียวจาก `cfg_master.sap_gl_code_ref` ที่ sync จาก SAP ทุกคืน  
ไม่สร้างใหม่ในโปรเจกต์นี้

---

## ความต้องการ

### Software ที่ต้องติดตั้ง

- Python 3.11+
- Azure Functions Core Tools v4
- Azure CLI
- Node.js 20+ (สำหรับ Static Web Apps CLI)
- Git

### Azure Resources ที่ต้องเตรียม

| Resource | จุดประสงค์ |
|----------|------------|
| Static Web App (Standard plan) | Host frontend + route protection |
| Function App (Python, Consumption) | API backend |
| Microsoft Entra ID App Registration | Azure AD authentication |
| Key Vault | เก็บ `AAD_CLIENT_SECRET` |
| Fabric Workspace + Lakehouse | Database |
| Azure AD Group `master-table-admins` | RBAC group (เพิ่ม user เข้าไป) |

---

## การ Deploy

### 1. สร้าง Database Schema

เปิด Fabric Notebook ใน workspace ที่ต้องการ แล้วรัน:

```python
%%sql
-- รัน /sql/01_create_tables.sql
```

หรือผ่าน Spark:

```python
with open("sql/01_create_tables.sql") as f:
    for stmt in f.read().split(";"):
        if stmt.strip():
            spark.sql(stmt)
```

### 2. ตั้งค่า Azure AD App Registration

1. Microsoft Entra ID → App registrations → New registration
   - Name: `web-chememan-master`
   - Redirect URI: `https://web.chememan.com/.auth/login/aad/callback`
2. Certificates & secrets → New client secret → เก็บ value
3. Token configuration → Add optional claim → ID → `groups`
   - เลือก Group ID (ไม่ใช่ Group name)
4. Manifest → set `"groupMembershipClaims": "SecurityGroup"`
5. เก็บ `client_id`, `client_secret`, `tenant_id` ไป Key Vault

### 3. สร้าง Azure AD Group

```bash
az ad group create --display-name "master-table-admins" --mail-nickname master-table-admins

# เพิ่มสมาชิก 3 คน
az ad group member add --group "master-table-admins" --member-id <volks-user-id>
az ad group member add --group "master-table-admins" --member-id <business-user-1-id>
az ad group member add --group "master-table-admins" --member-id <business-user-2-id>
```

### 4. Deploy Backend (Azure Function)

```bash
cd backend
cp ../deploy/local.settings.json.template local.settings.json
# แก้ค่า AAD_TENANT_ID, AAD_AUDIENCE, FABRIC_*

pip install -r requirements.txt
func start                              # test ที่ localhost:7071

# Deploy ขึ้น production
func azure functionapp publish web-chememan-master-api
```

### 5. Deploy Frontend (Static Web Apps)

```bash
# Push ไป GitHub repo
git add .
git commit -m "Initial deploy 0003 GL Group Master"
git push origin main

# GitHub Actions จะ deploy อัตโนมัติตาม deploy/github-actions.yml
```

### 6. ตั้งค่า CORS ของ Function

```bash
az functionapp cors add \
  --name web-chememan-master-api \
  --resource-group rg-chememan-web \
  --allowed-origins "https://web.chememan.com"
```

⚠️ ห้ามใช้ `*` — ดู `security-checklist.md` ข้อ 5

---

## การใช้งาน

### 1. เข้าระบบ

ไปที่ `https://web.chememan.com/master/gl-group`

- ถ้ายังไม่ login → redirect ไป Microsoft login
- ถ้า login แล้วแต่ไม่อยู่ใน `master-table-admins` → redirect ไป `/access-denied.html`
- ถ้าเป็น admin → เข้าหน้าได้

### 2. เพิ่ม Mapping

1. เลือก SAP GL Code จาก dropdown (search ได้)
2. พิมพ์ชื่อ GL Group:
   - ถ้ามีอยู่แล้วใน dropdown → เลือก
   - ถ้าเป็นชื่อใหม่ → พิมพ์เลย ระบบจะสร้าง group ใหม่อัตโนมัติ (inline create new)
3. กด **Save**

ถ้า GL Code นี้มี mapping อยู่แล้ว → ระบบจะ reject (Fail Fast)  
ต้องกด refresh แล้วใช้ Edit แทน

### 3. แก้ไข Mapping

1. กด **Edit** ในแถวที่ต้องการ
2. ฟอร์มด้านบนจะเติมค่าเดิมให้
3. แก้ค่า → กด Save (จะเป็น UPDATE mode, ข้าม duplicate check)

### 4. ลบ Mapping

1. กด **Delete** ในแถว
2. Modal "ยืนยันลบ" ขึ้นมา
3. กด **ลบ** → ระบบลบทันที (hard delete)

> ⚠️ การลบไม่สามารถ undo ผ่าน UI ได้  
> ถ้าลบผิด → ใช้ Delta Time Travel กู้ภายใน 7 วัน (ติดต่อ Volks)

---

## การแก้ไขปัญหา

### Error: "DUPLICATE_KEY" (409)

**สาเหตุ:** GL Code นี้มี mapping อยู่ในฐานข้อมูลแล้ว แต่ในตารางที่หน้าจอยังไม่เห็น (cache เก่า)  
**วิธีแก้:** กด refresh หน้า → ถ้าจะแก้ค่าเดิม ใช้ Edit แทน Save ใหม่

### Error: "Forbidden — admin role required" (403)

**สาเหตุ:** บัญชี Azure AD ของคุณไม่อยู่ใน group `master-table-admins`  
**วิธีแก้:** ติดต่อ Volks ขอเพิ่มสิทธิ์

### Error: "เซสชันหมดอายุ" (401)

**สาเหตุ:** Azure AD token หมดอายุ (ปกติ 1 ชม.) แล้ว refresh ไม่สำเร็จ  
**วิธีแก้:** Logout แล้ว login ใหม่

### ตาราง render ช้า (>2 วินาที)

**สาเหตุ:** Azure Function Consumption Plan เพิ่ม cold start หลังไม่ใช้นาน  
**วิธีแก้:**
- รอ 3-5 วินาทีรอบแรกของวัน
- หรือ upgrade เป็น Premium Plan (~$150/เดือน) ตัด cold start

### Frontend ไม่อ่านข้อมูล (เห็นตารางว่าง)

**สาเหตุที่เป็นไปได้:**
- CORS ไม่ถูก config → เปิด DevTools → Console เห็น CORS error
- Azure Function ล่ม → เปิด Application Insights ดู error
- Fabric Lakehouse permission → ดู Azure Function log

---

## โครงสร้างไฟล์

```
0003-gl-group/
├── frontend/
│   ├── HTML-MODIFICATIONS.md      ← วิธีแก้ HTML เดิม
│   ├── api-client.js              ← fetch wrapper + auth
│   └── 0003-gl-group.js           ← logic หลัก (replace inline script)
│
├── backend/
│   ├── function_app.py            ← route registration
│   ├── auth.py                    ← JWT validation
│   ├── db.py                      ← Spark connection
│   ├── models.py                  ← Pydantic schemas
│   ├── requirements.txt
│   └── handlers/
│       ├── list_handler.py
│       ├── save_handler.py
│       ├── delete_handler.py
│       └── reference_handler.py
│
├── sql/
│   ├── 01_create_tables.sql       ← DDL พร้อม audit warning
│   ├── 02_seed_reference.sql      ← (empty for this entity)
│   ├── 03_merge_upsert.sql        ← MERGE templates
│   └── 04_hard_delete.sql         ← DELETE template
│
├── tests/
│   ├── pytest.ini
│   ├── test_handlers.py           ← unit tests with mocks
│   └── test_merge_logic.py        ← SQL pattern verification
│
├── deploy/
│   ├── staticwebapp.config.json   ← RBAC routes
│   ├── github-actions.yml         ← CI/CD pipeline
│   └── local.settings.json.template
│
└── README.md                       ← ไฟล์นี้
```

---

## หมายเหตุสำคัญ

### Audit ถูกปิดโดยตั้งใจ

ระบบนี้ **ไม่เก็บ** `updated_by`, `updated_at` ใน schema  
ถ้าต้องการรู้ว่าใครแก้เมื่อไหร่ → ใช้ Delta Time Travel ภายใน 7 วัน

ดูเหตุผลใน `references/decision-log.md` ข้อ #16 ของ skill

### Composite Key ไม่ได้ใช้กับหน้านี้

หน้านี้ใช้ Single PK (`gl_code`) เท่านั้น  
ถ้าต้องการดู pattern composite key → ดูที่ `0007-orgcode-costcenter` (2 cols) หรือ `0008-hide-document` (3 cols)

### Cost-saving

ใช้ Consumption Plan + Single-region (Southeast Asia)  
ถ้า downtime หรือ cold start เป็นปัญหา → upgrade เป็น Premium Plan ตาม `decision-log.md` ข้อ #18

---

## ติดต่อ

**เจ้าของระบบ:** Volks (Senior Data Engineer)  
**ทีม:** Data Engineering — Chememan  
**Repository:** `tanasedw/web-chememan-master`

หากเจอ bug → เปิด issue ใน GitHub พร้อมแนบ:
- Screenshot
- Console log (F12 → Console tab)
- เวลาที่เกิด (เพื่อเช็ค Application Insights)
