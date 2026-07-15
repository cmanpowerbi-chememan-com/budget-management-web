"""FastAPI app entrypoint — A2 backend foundation, A3 RLS scope resolution,
A4 main-table read path (`GET /budget`).

Budget write (A5) and approval (A6) endpoints are not built here yet.
"""
from fastapi import FastAPI

from app.routers import budget, health, me, scope

app = FastAPI(title="Budget Management Web API")

app.include_router(health.router)
app.include_router(me.router)
app.include_router(scope.router)
app.include_router(budget.router)
