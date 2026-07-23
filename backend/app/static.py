"""Serve the frontend build output — `frontend/out` (Next.js export),
previously `frontend/dist` (Vite) — from this same FastAPI app: one Container
App serves API + frontend, Easy Auth handles login at the platform layer
(A14 step 1).

`mount_frontend` must be called AFTER every API router is included. Starlette
resolves routes by iterating its route list in registration order and using
the first full match — so as long as this is called last, no API route can
ever be shadowed by the SPA mount/catch-all, by construction (not by
prefix-matching tricks).
"""
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

# Top-level path segments owned by the API. The SPA catch-all must never
# resolve one of these to index.html, even for an unmatched sub-path (e.g. a
# typo'd `/budget/xyz` should 404 like a normal missing API route, not
# silently serve HTML) — checked defensively in addition to registration
# order, since FastAPI's own /docs /openapi.json /redoc routes already exist
# before this module ever runs.
_RESERVED_API_PREFIXES = frozenset(
    {"health", "me", "scope", "budget", "approval", "attachments", "docs", "openapi.json", "redoc"}
)

_NO_CACHE_HEADERS = {"Cache-Control": "no-cache"}
_LONG_CACHE_HEADER = "public, max-age=31536000, immutable"


def _is_reserved_api_path(path: str) -> bool:
    first_segment = path.split("/", 1)[0]
    return first_segment in _RESERVED_API_PREFIXES


def _is_contained(candidate: Path, static_dir: Path) -> bool:
    """True if `candidate` resolves to a path inside `static_dir`.

    `full_path` comes straight from the URL (already percent-decoded by the
    ASGI server, so `%2e%2e` arrives as `..`), so a naive `static_dir /
    full_path` join can escape the static directory entirely (CWE-22 path
    traversal / arbitrary file read) — e.g. `/%2e%2e/secret.txt`. Resolving
    both sides and checking containment catches every encoding/separator
    variant (`../`, backslash, doubled, deep) uniformly, instead of trying
    to blocklist traversal substrings in the raw string.
    """
    resolved = candidate.resolve()
    static_root = static_dir.resolve()
    return resolved == static_root or static_root in resolved.parents


class _LongCacheStaticFiles(StaticFiles):
    """Hashed build assets (e.g. /assets/app-<hash>.js) are immutable — safe
    to cache for a year. No new dependency: just a thin override of
    Starlette's own StaticFiles response."""

    async def get_response(self, path: str, scope: dict) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = _LONG_CACHE_HEADER
        return response


def mount_frontend(app: FastAPI, static_dir: Path) -> bool:
    """Mount the built SPA if `static_dir` (e.g. `frontend/out`) exists.

    Returns True if mounted, False if the directory (or its index.html) is
    missing — the normal local-dev case where the Next.js dev server serves
    the frontend on its own port. Never raises: a missing static dir is not a
    startup error.
    """
    index_file = static_dir / "index.html"
    if not static_dir.is_dir() or not index_file.is_file():
        logger.info("Static frontend not found at %s — running API-only (local dev).", static_dir)
        return False

    assets_dir = static_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", _LongCacheStaticFiles(directory=assets_dir), name="spa-assets")

    next_static_dir = static_dir / "_next" / "static"
    if next_static_dir.is_dir():
        # Next.js export layout: hashed assets live under /_next/static (no assets/ dir).
        app.mount("/_next/static", _LongCacheStaticFiles(directory=next_static_dir), name="spa-next-static")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> Response:
        if _is_reserved_api_path(full_path):
            raise HTTPException(status_code=404)

        candidate = static_dir / full_path
        if full_path and candidate.is_file() and _is_contained(candidate, static_dir):
            return FileResponse(candidate)

        # Only extension-less paths are client-side routes (e.g. a deep link
        # like /some/dept-view). A missing OR out-of-bounds (traversal)
        # path WITH an extension is treated the same as a real broken asset
        # reference — 404 it, never mask it as an SPA route or serve it.
        if Path(full_path).suffix:
            raise HTTPException(status_code=404)

        return FileResponse(index_file, headers=_NO_CACHE_HEADERS)

    logger.info("Static frontend mounted from %s", static_dir)
    return True
