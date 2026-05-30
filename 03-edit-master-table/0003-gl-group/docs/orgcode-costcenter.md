# Orgcode & Cost Center Master (Module 0007)

หน้าจัดการ mapping ระหว่าง **Orgcode (SAP)** กับ **Cost Center** — junction table (composite PK 2 cols)

## Entity

| Field | Type | Note |
|-------|------|------|
| `cost_center` | NVARCHAR | PK, format `^[0-9A-Z]+$` (auto-uppercase) |
| `orgcode` | NVARCHAR | PK, references `cfg_master.sap_orgcode_ref` |

**Storage**: `cfg_master.orgcode_costcenter_map` (Fabric SQL DB)
**Reference**: `cfg_master.sap_orgcode_ref` (code, name)

## API

Base path: `/api/master/orgcode-costcenter`

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/list` | All mapping rows |
| POST | `/save` | Create new (orgcode, cost_center) pair — 409 if duplicate |
| DELETE | `/delete` | Hard delete by composite key |
| GET | `/reference/orgcodes` | Picklist from `cfg_master.sap_orgcode_ref` |

## UI

- Page: `/orgcode-costcenter.html`
- Role: `master-table-admins` (per `staticwebapp.config.json`)
- Pattern: form (1 orgcode + 1 cost center) → save → table refresh
- Multi-select chip layout for CC bulk-add (feat 0563b73)

## Validation

| Layer | Check |
|-------|-------|
| Frontend | regex `^[0-9A-Z]+$` + auto-uppercase on input |
| Backend | Pydantic `pattern=r"^[0-9A-Z]+$"` |
| DB | NVARCHAR length only — relies on API layer |

## Notes

- **No dimension tables** — pure junction
- **No "edit" mode** — pair either exists or doesn't; modify = delete + re-add
- **No audit columns** — 2-admin policy (see project-context.md)
