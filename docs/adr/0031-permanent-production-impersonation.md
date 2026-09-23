# 31. Permanent production impersonation: jakkaritw may act as any Filler or direct manager

Date: 2026-09-23

Status: Accepted (jakkaritw, grill-with-docs 2026-09-23). Implemented 2026-09-23 (backend, TDD, combined gate APPROVE WITH SUGGESTIONS, follow-ups applied); not yet deployed.

## Context

Impersonation (`SIT_IMPERSONATE`, `backend/app/auth.py`) was built as a staging test aid
and later left on in production after the UAT round because production runs
`APP_ENV=uat` — the guard only refuses the literal value `production`. The target list was
a hand-typed environment value (8 emails), so every new person needed an env edit and a new
revision. After go-live the tool became jakkaritw's support instrument: reproducing what a
caller sees and doing their step for them.

## Decision

Impersonation stays on in production **permanently** and is widened:

- **Who:** jakkaritw only (the configured from-side; other admins still get 404).
- **As whom:** every Filler in the Cost Center ↔ Filler map plus each Filler's direct
  manager (Primary-row `manager_email`), read live from the database and cached — 95 people
  on 2026-09-23 (74 Fillers + 21 managers who are not Fillers). Nobody outside that set:
  the hand-typed list is dropped (loses `pornthipp`; `jakkaritw` stays reachable because
  "no selection" always means "yourself").
- **What:** full action — save, submit, approve, reject — including approving as a step-2/3
  approver to final `APPROVED`. This is a separate power from Step override (ADR-0027); the
  override's limits apply to the override button only.
- **Record:** whatever is done while impersonating is recorded and mailed as the
  impersonated person's own action. No real-actor column, no audit table, no mail footer.
- **Switch:** production keeps `APP_ENV=uat` as the on-switch.

The reason given for accepting the risk: exactly one person can ever use it.

## Considered Options

- View-only impersonation (writes refused) — rejected: support needs to act, not only see.
- Time-boxed (turn off after the FY2027 cycle) — rejected in favour of permanent.
- Audit table `budget.impersonation_log` / real-actor column / "done by jakkaritw on behalf
  of …" mail line — all rejected: the impersonated identity is the record.
- Dedicated `IMPERSONATION_ENABLED` switch with `APP_ENV=production` — rejected: keep
  `APP_ENV=uat`.
- Keeping the hand-typed extras list alongside the live list — rejected.

## Consequences

- `budget.approval_log`, `pending_budget._user` and every notification name the
  impersonated person; the only trace of the real actor is one INFO line per request in the
  container log, which does not survive a restart. Nobody can later prove from the data
  whether a manager approved personally or jakkaritw did it as them.
- Staging and production share one database, so impersonating on staging also changes real
  data and sends real mail.
- `setup/smoke_prd.py` check P1-05 (`app_env == "production"`) stays red by design — a red
  P1-05 is this ADR, not an outage.
- The picker page keeps the UAT banner ("ระบบจะบันทึกชื่อผู้ที่ถูกสวมสิทธิ์ ไม่ใช่ชื่อผู้ที่กดจริง").
- Do not "fix" `APP_ENV=uat` on production or re-offer turning impersonation off; reverse
  this ADR instead.
