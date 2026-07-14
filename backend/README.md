# Backend (FastAPI) — A2 foundation

This is the **backend foundation only** (BUILD_PLAN.md A2): Entra Easy Auth identity
extraction, the two Fabric SQL connection factories, config, and two smoke endpoints
(`/health`, `/me`). No business endpoints yet — RLS (A3), the budget read path (A4),
writes (A5), and approval (A6) are separate, later increments.

## Local run (no-install machine — plain venv, no Docker)

```bash
cd backend
python -m venv venv          # or reuse the repo-root venv
venv\Scripts\activate         # Windows
pip install -r requirements.txt

copy .env.example .env        # then fill in real values
uvicorn app.main:app --reload
```

Visit `http://127.0.0.1:8000/health` and `http://127.0.0.1:8000/me`.

## Auth locally vs in production

In production (Azure Container Apps), Easy Auth sits in front of the app and injects
`x-ms-client-principal-name` = the logged-in user's email (ADR-0004) — the app trusts
that header as-is. Locally there is no Easy Auth, so set `APP_ENV=local` +
`DEV_AUTH_EMAIL=you@chememan.com` in `backend/.env` to stand in for it. Any other
`APP_ENV` value (or none) behaves like production: a missing header is a 401, and
`DEV_AUTH_EMAIL` is never honored — fail-closed by default.

To exercise the real header path locally, pass it manually:
```bash
curl -H "x-ms-client-principal-name: you@chememan.com" http://127.0.0.1:8000/me
```

## Tests

```bash
cd backend
pytest -v
```

All 25 tests are unit tests — pyodbc is fully mocked, no live DB required. Tests that
need a real Fabric SQL / gold warehouse connection would be marked
`@pytest.mark.integration` (excluded by default via `pytest.ini`); none exist yet in
this increment.

## Env vars (see `.env.example`)

| Var | Notes |
|---|---|
| `APP_ENV` | `local` enables the DEV auth override; anything else = production behavior |
| `DEV_AUTH_EMAIL` | local-only stand-in for the Easy Auth header |
| `FABRIC_SQL_SERVER` / `FABRIC_SQL_DATABASE` | the ONE Fabric SQL DB (`budget.*` + `dbo.*`) — **must be re-pointed to `fabric_sql_database`**, see `.env.example` comment |
| `GOLD_SQL_SERVER` / `GOLD_SQL_DATABASE` | SAP gold warehouse, read-only |
| `ENTRA_CLIENT_ID` / `ENTRA_CLIENT_SECRET` / `ENTRA_TENANT_ID` | Service Principal `cman-fabric-write` |

## Structure

```
backend/
  app/
    main.py            FastAPI app, wires routers
    config.py           pydantic-settings, fail-closed APP_ENV default
    auth.py             Easy Auth header dependency + local DEV override
    db.py               get_fabric_conn() / get_gold_conn() — lazy, context-managed
    routers/
      health.py          GET /health (+ ?deep=1 -> SELECT 1 on Fabric conn)
      me.py               GET /me -> {email, app_env}
  tests/                 pytest, pyodbc mocked throughout
  requirements.txt
  .env.example
  pytest.ini
```

## What A3 (RLS) plugs into

- `app.auth.get_current_user_email` already gives A3 a resolved, trusted email per
  request — RLS just adds a dependency that takes that email and resolves scope
  (`dbo.cc_filler_map` + `dbo.v_employee_budget_01`, see ADR-0019 / BUILD_PLAN A3).
- `app.db.get_fabric_conn()` is the one connection A3/A4 query against (both schemas
  live in it); `get_gold_conn()` is reserved for the SAP read-through (A4).
- No query beyond `SELECT 1` exists yet on purpose — A3/A4 own the real query contract.
