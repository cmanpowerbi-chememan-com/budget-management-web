# syntax=docker/dockerfile:1
#
# Budget Management Web — production image (A14).
# ONE Container App serves both the FastAPI backend AND the built React SPA
# (StaticFiles + SPA-fallback wired in app/main.py via env STATIC_DIR).
#
# BUILD CONTEXT MUST BE THE REPO ROOT, not backend/ — this Dockerfile COPYs
# both frontend/ and backend/, so paths below are root-relative on purpose.
# Build from the repo root, e.g. (see docs/deploy/A14_RUNBOOK.md for the full
# az acr build command run from Azure Cloud Shell):
#
#   az acr build --registry <acr-name> --image budget-web:<tag> \
#     --file backend/Dockerfile .
#
# Wrong context (e.g. `--file Dockerfile .` from inside backend/) fails with
# "frontend": not found / COPY failed: file not found.

# ---------------------------------------------------------------------------
# Stage 1 — build the Next.js static export
# ---------------------------------------------------------------------------
FROM node:24-alpine AS frontend-build

WORKDIR /fe

# Copy lockfile + manifest first for layer caching — only re-runs `npm ci`
# when dependencies actually change, not on every source edit.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# CI=true -> plain, non-interactive Next build logs so streamed output can
# never re-trigger the Windows az CLI colorama/cp1252 crash (G5): Next's
# interactive/animated build output includes unicode that crashed the local
# Windows az CLI's colorama layer mid-stream during `az acr build` (the same
# crash class hit by vite's default log level previously), which cancels the
# ACR run even though the build itself succeeded.
ENV CI=true
RUN npm run build:ci

# ---------------------------------------------------------------------------
# Stage 2 — Python runtime (FastAPI + pyodbc + Microsoft ODBC Driver 17)
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

# Microsoft ODBC Driver 17 for SQL Server — the ODBC driver NAME string
# ("ODBC Driver 17 for SQL Server") is hardcoded in backend/app/db.py, so this
# MUST be msodbcsql17, not 18. Base image is pinned to -bookworm (Debian 12)
# so the Microsoft apt repo config below always matches the OS codename.
#
# FIXED 2026-07-16 — real `az acr build` (run cm3) failed here with:
#   GPG error: NO_PUBKEY EB3E94ADBE1229CF / repository is not signed
# Root cause: bookworm's apt does not accept an ASCII-armored key dropped in
# /etc/apt/trusted.gpg.d (the old `microsoft.asc` approach below). Fix:
# dearmor the key into a binary keyring under /usr/share/keyrings/ and
# reference it explicitly via `signed-by=` on the repo's deb line (verified
# against the live https://packages.microsoft.com/config/debian/12/prod.list
# content on 2026-07-16 — same signed-by path + `bookworm main` suite).
RUN apt-get update -qq \
    && apt-get install -y --no-install-recommends curl gnupg ca-certificates unixodbc unixodbc-dev \
    && curl -sSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64,arm64,armhf signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update -qq \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql17 \
    && apt-get purge -y --auto-remove curl gnupg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps first for layer caching.
# backend/requirements.txt is PINNED as of 2026-07-16 (all 7 direct deps
# exact versions — fastapi 0.139.0, python-multipart 0.0.32, etc.). Keep it
# pinned; do not relax back to unpinned ranges.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# App code (only what runs in prod — tests/, .env, __pycache__ etc are kept
# out via .dockerignore at the repo root).
COPY backend/app ./app
COPY backend/jobs ./jobs

# Built frontend from stage 1 -> served by FastAPI StaticFiles at STATIC_DIR.
COPY --from=frontend-build /fe/out ./static

ENV STATIC_DIR=/app/static \
    APP_ENV=production \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Least-privilege runtime user (07-security-checklist #7).
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# --workers 2: sized for the lean start-up profile (0.5 vCPU / 1Gi, see
# A14_RUNBOOK.md). pyodbc calls block the worker's event loop, so >1 worker
# lets a second request proceed while another blocks on a Fabric SQL/SAP
# round-trip; 2 keeps the memory footprint (uvicorn+FastAPI+pyodbc baseline
# per worker) comfortably inside 1Gi. Revisit alongside CPU/mem if concurrent
# usage grows past the pilot cohort.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
