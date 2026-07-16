"""FastAPI app entrypoint — A2 backend foundation, A3 RLS scope resolution,
A4 main-table read path (`GET /budget`), A5 budget write path
(`PUT /budget/rows`, `PUT /budget/detail`, `POST|PUT /budget/trip`), A6
approval engine (`POST /approval/submit|approve|reject`, `GET /approval/status`),
A8 reference-data pickers (`GET /budget/gl-accounts`, `GET /scope/departments`),
A9 subform read-only support (`GET /budget/detail`, `GET /budget/trip`).
A10 approval UI support (`GET /approval/pending-for-me`) + SharePoint
attachments (`GET /attachments`, `POST /attachments/upload`,
`GET /attachments/download-url`).
A14 — serves the built React SPA (`frontend/dist`) from this same app; see
`app/static.py`. Mounted LAST so no API route can ever be shadowed.
"""
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from app.config import get_settings
from app.routers import approval, attachments, budget, budget_write, health, me, reference, scope, subform
from app.static import mount_frontend

app = FastAPI(title="Budget Management Web API")

# Content-Security-Policy deliberately NOT set yet — it would break the
# Vite/React SPA (inline/module asset loading); add as a follow-up.
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}


@app.middleware("http")
async def add_security_headers(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Set the security response headers on EVERY response (API, errors,
    /health, SPA files) — named (not a closure) so tests can attach it to
    isolated SPA test apps."""
    response = await call_next(request)
    for name, value in _SECURITY_HEADERS.items():
        response.headers[name] = value
    return response


app.include_router(health.router)
app.include_router(me.router)
app.include_router(scope.router)
app.include_router(budget.router)
app.include_router(budget_write.router)
app.include_router(approval.router)
app.include_router(reference.router)
app.include_router(subform.router)
app.include_router(attachments.router)

mount_frontend(app, get_settings().static_dir_path)
