"""FastAPI app entrypoint — A2 backend foundation + A3 RLS scope resolution.

Business endpoints for budget read/write/approval are A4-A6 — not built here.
"""
from fastapi import FastAPI

from app.routers import health, me, scope

app = FastAPI(title="Budget Management Web API")

app.include_router(health.router)
app.include_router(me.router)
app.include_router(scope.router)
