# SIT-000 — ตารางหัว run log (อ่านสดเมื่อ 2026-08-07 ~13:44 เวลาไทย)

อ่านด้วย az CLI ในฐานะ jakkaritw@chememan.com · subscription `CMAN Azure Subscription`
(`b92b1763-cfa4-4e9f-ab74-e21dbb8e5b21`) · resource group `CMAN-BUDGET-MNGT-WEB-RG` · **อ่านอย่างเดียว ไม่แก้ค่าใด ๆ**

| หัวข้อ | staging | production |
|---|---|---|
| FQDN | `cman-budget-web-stg.kindstone-f34836dd.southeastasia.azurecontainerapps.io` | `cman-budget-web-prd.kindstone-f34836dd.southeastasia.azurecontainerapps.io` |
| revision ที่รันอยู่ | `cman-budget-web-stg--0000029` (created 2026-08-05T15:30:36Z, traffic 100, Healthy) | `cman-budget-web-prd--0000015` (created 2026-08-05T15:32:31Z, traffic 100, Healthy) |
| image ที่ทดสอบ | `cmanbudgetacr.azurecr.io/budget-web:1bbddcb` | `cmanbudgetacr.azurecr.io/budget-web:1bbddcb` |
| **image สำหรับ rollback** (อ่านสด ไม่ได้คัดจากแผน) | `cmanbudgetacr.azurecr.io/budget-web:d0672fc` ← rev `--0000028` (2026-08-05T09:40:34Z, inactive) | `cmanbudgetacr.azurecr.io/budget-web:d0672fc` ← rev `--0000014` (2026-08-05T09:41:54Z, inactive) |
| min / max replicas | 0 / 2 (cold start วัดได้ 21.36 วินาที) | 2 / 2 (อุ่นตลอด — วัดได้ 0.47 วินาที) |
| activeRevisionsMode | Single | Single |
| Easy Auth | `platform.enabled=True` · cookie `timeToExpiration=14:00:00` · unauthenticated → `RedirectToLoginPage` (`azureactivedirectory`) | เหมือนกันทุกค่า |
| `GET /health` แบบไม่มี cookie | **401 Unauthorized** · body ว่าง (size=0) · 21.36 s | **401 Unauthorized** · body ว่าง (size=0) · 0.47 s |
| Entra resource_id ที่ Easy Auth ประกาศ | `7035aa47-0398-4b71-8411-7fc372e82123` | `61d5d556-ee48-44f7-91b3-b8e05d6419aa` (**คนละ app registration → cookie ข้ามสภาพแวดล้อมไม่ได้**) |
| จำนวน env keys | 11 | 11 (ชื่อคีย์เหมือนกันทุกตัว) |
| `APP_ENV` | `production` | `production` |
| `ADMIN_EMAILS` | 3 รายการ: jakkaritw@chememan.com, nipapornt@chememan.com, warapornt@chememan.com | เหมือนกันทุกตัวอักษร |
| `GL_EDIT_BY_ENABLED` | `true` | `true` |
| `APP_BASE_URL` | `https://cman-budget-web-stg.kindstone-f34836dd.southeastasia.azurecontainerapps.io` | `https://cman-budget-web-prd.kindstone-f34836dd.southeastasia.azurecontainerapps.io` |
| `NOTIFICATIONS_DRY_RUN` | **ไม่มีคีย์นี้** → ใช้ default ในโค้ด `True` (`backend/app/config.py:64`) | **ไม่มีคีย์นี้** → เหมือนกัน |
| ผู้ส่งอีเมลของแอป | ไม่มี env override → default ในโค้ด `cmanpowerbi@chememan.com` | เหมือนกัน |
| Fabric SQL / gold DW | `FABRIC_SQL_SERVER` · `FABRIC_SQL_DATABASE` · `GOLD_SQL_SERVER` · `GOLD_SQL_DATABASE` **ตรงกันทุกตัวกับ production** (เทียบแบบ string equality) | เหมือนกัน — **ไม่มี sandbox แยก** |
| ACR | `cmanbudgetacr` — tag `1bbddcb` และ `d0672fc` ยังมีอยู่ทั้งคู่ (rollback ทำได้จริง) | เหมือนกัน |
| watermark SAP (`GET /budget/sap-coverage?year=2026`) | **ยังไม่ได้อ่าน** — ต้องใช้ตัวตน admin ผ่าน Easy Auth (ดู SIT-001) | **ยังไม่ได้อ่าน** |

## ข้อสังเกต

1. `APP_ENV=production` บน **staging** ด้วย — **ถูกต้องตามที่ออกแบบ ไม่ใช่ข้อผิดพลาด**
   `backend/app/config.py:3-4,37,149` ตั้ง default เป็น `production` แบบ fail-closed และค่านี้ถูกใช้
   ที่เดียวคือ property `is_local` ซึ่งเปิดทาง `DEV_AUTH_EMAIL` ฉะนั้น staging ที่เป็น `production`
   แปลว่า override ตัวตนแบบ local ถูกปิดสนิททั้งสองสภาพแวดล้อม
2. `az containerapp revision list` **แบบไม่ใส่ `--all` คืนมาแค่ 1 revision** (เฉพาะที่ active)
   ต้องใส่ `--all` ถึงจะเห็น revision เก่า (stg 30 รายการ · prd 16 รายการ) — ขั้นตอนหา rollback image
   ต้องใช้ `--all` ไม่งั้นจะสรุปผิดว่า "ไม่มี revision ให้ย้อนกลับ"
3. `LOG_LEVEL` **ไม่มีในรายการ env ของทั้งสอง app** แม้จะถูกเพิ่มตอนแก้ perf (c2bd552)

## แฟ้มหลักฐานในโฟลเดอร์นี้

| ไฟล์ | ขั้นตอน |
|---|---|
| `step1_show_stg.json` · `step1_show_prd.json` | 1 — revision / image / replicas / FQDN |
| `step2_env_cman-budget-web-*.masked.txt` | 2 — รายการ env ครบ (ค่าที่เป็นความลับปิดเป็น `<set>`) |
| `step3_auth_cman-budget-web-*.txt` | 3 — Easy Auth |
| `step4_health_anon_stg.txt` · `step4_health_anon_prd.txt` | 4 — header ดิบของ curl แบบไม่ล็อกอิน |
| `step5_revisions_stg.json` · `step5_revisions_prd.json` · `step5_acr_tags.json` | 5 — rollback image |
