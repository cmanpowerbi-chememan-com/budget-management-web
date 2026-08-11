"""FastAPI app entrypoint — A2 backend foundation, A3 RLS scope resolution,
A4 main-table read path (`GET /budget`), A5 budget write path
(`PUT /budget/rows`, `PUT /budget/detail`, `POST|PUT /budget/trip`), A6
approval engine (`POST /approval/submit|approve|reject`, `GET /approval/status`),
A8 reference-data pickers (`GET /budget/gl-accounts`, `GET /scope/departments`),
A9 subform read-only support (`GET /budget/detail`, `GET /budget/trip`).
A10 approval UI support (`GET /approval/pending-for-me`) + SharePoint
attachments (`GET /attachments`, `POST /attachments/upload`,
`GET /attachments/download-url`).
A14 — serves the built frontend (`frontend/out`, Next.js static export;
previously `frontend/dist` under Vite) from this same app; see
`app/static.py`. Mounted LAST so no API route can ever be shadowed.

Perf fix 3 — startup warmup (see `_run_warmup`): live-measured on PRD, the
FIRST request in each worker process pays fabric conn open 2.86s + gold conn
open 2.01s (vs 0.70s / 1.45s warm) plus the uncached SAP reads. The lifespan
handler fires a daemon-thread warmup so that cost lands at process start,
never on the first real user.
"""
import logging
import threading
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, Request, Response

from app.config import get_settings
from app.db import get_fabric_conn, get_gold_conn
from app.logging_config import configure_logging
from app.routers import approval, attachments, budget, budget_write, health, me, reference, scope, subform
from app.sap import fetch_sap_actuals_cached, resolve_sap_coverage_cached
from app.static import mount_frontend

# Runs once per module import — i.e. once per uvicorn worker process (each
# `--workers N` process imports `app.main` fresh) — so every app logger is
# wired to stdout before the lifespan/warmup below ever logs anything. See
# `app/logging_config.py` for why this is needed at all.
configure_logging(get_settings().log_level)

logger = logging.getLogger(__name__)


def _run_warmup() -> None:
    """Warm the fabric + gold connection pools and prime both SAP TTL
    caches. Runs on a daemon thread (see `_start_warmup_if_enabled`), never
    on the request-handling path, so it can never block startup or the
    Container Apps probe. Must never crash startup: any exception here only
    means the first real request pays the cold-start cost again."""
    total_start = time.monotonic()
    try:
        step_start = time.monotonic()
        with get_fabric_conn():
            pass
        logger.info("warmup: fabric conn opened in %.2fs", time.monotonic() - step_start)

        step_start = time.monotonic()
        with get_gold_conn():
            pass
        logger.info("warmup: gold conn opened in %.2fs", time.monotonic() - step_start)

        step_start = time.monotonic()
        board_year = date.today().year
        # ADR-0020 amendment 2026-08-11: fetch_sap_actuals_cached also needs
        # the transactional connection (dbo.hide_document read) — opened
        # here alongside gold_conn, priming both pools together.
        with get_fabric_conn() as fabric_conn, get_gold_conn() as conn:
            fetch_sap_actuals_cached(conn, fabric_conn, fiscal_year=board_year)
            resolve_sap_coverage_cached(conn, fiscal_year=board_year)
        logger.info(
            "warmup: SAP caches primed for fiscal_year=%s in %.2fs",
            board_year,
            time.monotonic() - step_start,
        )
    except Exception as exc:  # noqa: BLE001 -- warmup must never crash startup
        logger.warning("warmup failed, first real request will pay the cold-start cost: %s", exc)
    finally:
        logger.info("warmup: total elapsed %.2fs", time.monotonic() - total_start)


def _start_warmup_if_enabled() -> None:
    """Startup entrypoint (called from the lifespan handler below). When
    `warmup_enabled` is False, does nothing at all — no thread, no
    connection factory call. Otherwise spawns `_run_warmup` on a daemon
    thread so startup is never blocked."""
    if not get_settings().warmup_enabled:
        return
    threading.Thread(target=_run_warmup, daemon=True).start()


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    _start_warmup_if_enabled()
    yield


app = FastAPI(title="Budget Management Web API", lifespan=_lifespan)

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
