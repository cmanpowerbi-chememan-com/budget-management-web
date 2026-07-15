"""FastAPI app entrypoint — A2 backend foundation, A3 RLS scope resolution,
A4 main-table read path (`GET /budget`), A5 budget write path
(`PUT /budget/rows`, `PUT /budget/detail`, `POST|PUT /budget/trip`), A6
approval engine (`POST /approval/submit|approve|reject`, `GET /approval/status`).
"""
from fastapi import FastAPI

from app.routers import approval, budget, budget_write, health, me, scope

app = FastAPI(title="Budget Management Web API")

app.include_router(health.router)
app.include_router(me.router)
app.include_router(scope.router)
app.include_router(budget.router)
app.include_router(budget_write.router)
app.include_router(approval.router)
