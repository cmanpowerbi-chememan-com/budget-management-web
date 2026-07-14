"""FastAPI app entrypoint — A2 backend foundation (auth + connection layer only).

Business endpoints (RLS/read/write/approval) are A3-A6 — not built here.
"""
from fastapi import FastAPI

from app.routers import health, me

app = FastAPI(title="Budget Management Web API")

app.include_router(health.router)
app.include_router(me.router)
