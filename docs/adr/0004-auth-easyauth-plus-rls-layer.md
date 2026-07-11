# 4. Auth = Container Apps EasyAuth (all users) + separate RLS layer

Date: 2026-06-06
Status: Accepted. **Note (2026-07-11, ADR-0019):** the RLS lookup chain in the
Decision below (`orgcode_costcenter_map → cost_center list`) is superseded — RLS now
resolves via the Cost Center↔Filler map. The auth/authentication layer (EasyAuth,
`ADMIN_EMAILS` as role flag) is unaffected.

## Context

The deployed master-tables module is an **admin-only** app: SWA built-in auth injects
`x-ms-client-principal-name`, and `auth.py` rejects (403) any email not in
`ADMIN_EMAILS`. The new main app moves to React + FastAPI on **Azure Container Apps**
(ADR-0002), where SWA built-in auth no longer exists, AND it must serve **all 275
users** — each seeing a different Cost Center scope, with division/department shown on
login. So the master-tables auth model (allowlist as a hard gate) does not fit.

## Decision

Two separate layers:

- **Authentication** — Azure Container Apps **built-in auth (EasyAuth)** with Entra ID.
  It injects the same `x-ms-client-principal-*` headers as SWA/App Service, so the
  header-reading logic in `auth.py` is reused almost verbatim. Every authenticated
  company user passes — authentication is NOT gated by `ADMIN_EMAILS`.
- **Authorization / RLS** — done by the app AFTER auth: `email →
  mas_employee_data (empcode, orgcode, division, department) →
  orgcode_costcenter_map → cost_center list`. `ADMIN_EMAILS` becomes only a **role
  flag** (in list = admin sees-all overlay; not in list = regular user scoped to own
  CCs). The login bar's division/department/CC come from this lookup, not from EasyAuth.

## Consequences

- Minimal auth code change; identity plumbing reused.
- The allowlist's meaning flips between the two apps (gate vs flag) — must not be
  copy-pasted blindly.
- Token plumbing (MSAL.js + JWT validation) is avoided; React needs no auth library.
- Resolution order after authentication:
  1. `email ∈ ADMIN_EMAILS` → admin sees-all overlay, **no `mas_employee_data` lookup
     required** (admin identity never depends on the RLS chain — covers jakkaritw /
     Data Analytics who may not be a budget actor).
  2. else, has `mas_employee_data` row → normal RLS scope (own CCs).
  3. else (authenticated but no row: L5/Gritsman/Vietnam excluded at sync, new hires
     not yet synced, service accounts) → **blocked with a friendly message**
     ("ไม่พบหน่วยงานของคุณในระบบ ติดต่อ budget dept"), no data shown.

### One admin-gating mechanism: ADMIN_EMAILS everywhere
All admin gating (main app, master-tables, the Master Currency page in spec doc 09)
uses the **`ADMIN_EMAILS` allowlist** — NOT Entra ID groups. Doc 09 proposed an Entra
group `master-table-admins`; that is dropped for consistency with the deployed
master-tables module and the same 4-person admin set. (Doc 09's build script still
says "Entra group" — fix that line when sign-off docs are next regenerated; regen is
deferred.) Trade-off: allowlist is simpler and already proven here; Entra-group
management is more "standard" but adds a second mechanism for no real gain at this scale.

### Email-match gotchas (the lookup key is email)
- `mas_employee_data.email` is stored with **mixed case** (`Arreeyat@chememan.com` vs
  `nipapornt@chememan.com`); the EasyAuth UPN is typically lower-case. Match
  **case-insensitively** (`LOWER()` both sides) or valid users get silently blocked.
- Match against the company-email column `email` (col 54), NOT `pemail` (personal,
  col 62). Employees whose only email is personal (e.g. `*.so03@gmail.com`) cannot
  log in at all — gmail is not an Entra identity. Known/accepted.
