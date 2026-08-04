"""Guards the one same-origin 3xx vector the frontend's session-expiry
detection (`frontend/src/api/client.ts`, `redirect: 'manual'`, 2026-08-04)
cannot tell apart from Easy Auth's cross-origin login redirect.

`apiFetch` calls `fetch(..., { redirect: 'manual' })`, so ANY 3xx response —
same-origin or cross-origin — resolves as an opaque `Response`
(`type:'opaqueredirect'`, `status:0`): the browser erases the status code,
headers and `Location` before JS ever sees it. That is exactly the shape
Easy Auth's cross-origin login redirect produces, so `apiFetch` treats it as
"session expired" and raises the dialog. A FastAPI/Starlette
`redirect_slashes` 307/308 on a trailing-slash mismatch produces the SAME
opaque shape — indistinguishable from the real thing at the fetch layer —
which is why this suite asserts no frontend-called route ever answers 3xx.

This guard has real teeth in the API-only configuration this suite actually
runs in: the CI `backend-tests` job never builds `frontend/out` (gitignored),
so `mount_frontend` (`backend/app/static.py`) finds no static dir and the SPA
catch-all is never mounted — a slash-mismatched path here genuinely resolves
to a bare 307/308. In the production image the catch-all IS mounted, so the
same mismatched path instead resolves to 200 `index.html` (Starlette matches
routes by registration order; the catch-all is always registered last) —
production itself can't produce this failure, but nothing stops a future
route from being added there without going through the catch-all, and this
test is the guard that catches it at the layer where it can still occur.
Every (method, path) pair the frontend actually calls (mirrored from
`frontend/src/api/*.ts` + `useAuth.ts` + `useScope.ts`) must resolve
directly — never via a redirect — regardless of auth outcome.
"""
from fastapi.testclient import TestClient

# (method, path) pairs mirroring every `apiFetch(...)` call site in the
# frontend, minus query strings (irrelevant to route *matching*/redirect
# behavior). Path params never appear — every one of these routes is a
# static path.
FRONTEND_API_CALLS = [
    ("GET", "/me"),
    ("GET", "/scope"),
    ("GET", "/scope/departments"),
    ("GET", "/budget"),
    ("GET", "/budget/sap-coverage"),
    ("GET", "/budget/gl-accounts"),
    ("GET", "/budget/detail"),
    ("GET", "/budget/trip"),
    ("PUT", "/budget/rows"),
    ("PUT", "/budget/detail"),
    ("POST", "/budget/trip"),
    ("PUT", "/budget/trip"),
    ("DELETE", "/budget/rows"),
    ("DELETE", "/budget/detail"),
    ("DELETE", "/budget/trip"),
    ("POST", "/approval/submit"),
    ("POST", "/approval/approve"),
    ("POST", "/approval/reject"),
    ("POST", "/approval/override-step"),
    ("GET", "/approval/pending-for-me"),
    ("GET", "/approval/status"),
    ("GET", "/reference/travelers"),
    ("GET", "/reference/countries"),
    ("GET", "/attachments"),
    ("POST", "/attachments/upload"),
    ("GET", "/attachments/download-url"),
]


def test_no_frontend_api_path_ever_redirects(client: TestClient):
    for method, path in FRONTEND_API_CALLS:
        response = client.request(method, path, follow_redirects=False)
        assert not (300 <= response.status_code < 400), (
            f"{method} {path} answered {response.status_code} (a redirect) — "
            "in a browser this is indistinguishable from Easy Auth's "
            "cross-origin 302 and would raise a false session-expiry dialog"
        )
