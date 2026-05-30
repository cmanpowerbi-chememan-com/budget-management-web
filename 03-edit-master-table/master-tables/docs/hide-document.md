# Hide Document Number Master (Module 0008)

หน้าจัดการกฎ **ซ่อน SAP Document Number ในงวดบัญชีที่กำหนด** — composite PK 3 cols

ใช้สำหรับ compliance, audit, closed-period control: controller "ปิดการมองเห็น" Document Number ใน specific fiscal periods (ช่วง audit, งวด closed, adjustment entries)

## Entity

| Field | Type | Range |
|-------|------|-------|
| `doc_num` | NVARCHAR(30) | PK, 10 digits expected (regex `^[0-9]{10}$` at API layer) |
| `fiscal_year` | INT | PK, 2020–2099 (CHECK constraint) |
| `fiscal_month` | INT | PK, 1–12 (CHECK constraint) |

**Storage**: `cfg_master.hide_document_number` (Fabric SQL DB)
**Reference (validate)**: `dbo.gold_sap_gl_trans.accounting_doc_number` (Lakehouse SQL Endpoint)

### ตัวอย่าง

ต้องการ hide `5400005042` ในไตรมาส 1 ปี 2026 → 3 rows:
- `(5400005042, 2026, 1)`
- `(5400005042, 2026, 2)`
- `(5400005042, 2026, 3)`

## API

Base path: `/api/master/hide-document`

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/list` | All hide rules (with computed `period` = `YYYY-MM`) |
| POST | `/save` | Create new triple — 409 if duplicate |
| DELETE | `/delete` | Hard delete; returns `{deleted: rowcount}` for ghost detection |
| POST | `/validate-docs` | Check if doc numbers exist in `dbo.gold_sap_gl_trans` |

### `/validate-docs` body

```json
{ "codes": ["5400005042", "5400005043", ...] }
```

Returns:
```json
{ "valid": ["5400005042"], "invalid": ["5400005043"] }
```

Cap: 200 codes per request.

## UI

- Page: `/hide-document.html`
- Role: `master-table-admins`
- Pattern: free-text chip input (10-digit doc numbers) + Enter/comma/space to add → Save validates against Lakehouse first
- Multi-doc save: 1 form action → N rows (1 doc per row × shared year/month)

## Validation (3 layers)

| Layer | What |
|-------|------|
| Frontend | regex `^[0-9]{10}$` + paste-multi parse |
| Backend Pydantic | `pattern=r"^[0-9]{10}$"`, `fiscal_year ge=2020 le=2099`, `fiscal_month ge=1 le=12` |
| DB CHECK | `BETWEEN 2020 AND 2099` + `BETWEEN 1 AND 12` |

Plus server-side validate against Lakehouse: doc number must exist in `dbo.gold_sap_gl_trans`.

## Notes

- **No audit columns** — 2-admin policy
- **Hard delete** — no soft-delete; DB has no time travel (Fabric SQL DB, not Lakehouse Delta)
- **`with get_lakehouse_conn()` pattern is FORBIDDEN** — use `fetchall_lakehouse()` from `db.py` (the cached thread-local conn would close on `with` exit, breaking subsequent requests including 0007's dropdowns)
