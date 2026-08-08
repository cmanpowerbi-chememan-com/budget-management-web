"""SharePoint attachments (A10, spec R1) — GET /attachments (list), POST
/attachments/upload, GET /attachments/download-url. Storage is SharePoint
only (`app.attachments`) — no DB write here, only a scope-authorization
read against `dbo.cc_filler_map` before every call.

Authorization (mirrors the See/Fill split used everywhere else in this app):
- list / download-url: caller must be admin OR See at least one cost center
  of the department (broad read, matches `authorize_status_view` in
  `app.approval`).
- upload: caller must be admin OR Fill at least one cost center of the
  department (matches `write_model._ensure_write_scope`'s Fill-or-admin gate).
"""
import logging

import pyodbc
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel

from app.attachments import (
    ERROR_CODE_BY_EXCEPTION,
    ERROR_HTTP_STATUS,
    MAX_ATTACHMENT_BYTES,
    get_download_url,
    list_attachments,
    too_large_message,
    upload_attachment,
)
from app.auth import get_current_user_email
from app.db import get_fabric_conn
from app.rls import Scope, resolve_scope

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/attachments")


class AttachmentInfoResponse(BaseModel):
    item_id: str
    name: str
    size: int
    created_by: str | None = None
    created_at: str | None = None
    web_url: str | None = None


class DownloadUrlResponse(BaseModel):
    url: str


def _department_cost_centers(conn: pyodbc.Connection, department: str) -> set[str]:
    """Same one-line query as `app.approval._department_cost_centers` —
    duplicated deliberately (below the project's 3-call-site threshold for
    extracting a shared helper, `11-code-standards`)."""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT DISTINCT cost_center FROM dbo.cc_filler_map WHERE department = ?", department)
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return {r[0] for r in rows}


def _authorize(conn: pyodbc.Connection, department: str, scope: Scope, *, require_fill: bool) -> None:
    # Always resolve the department first -- including for admins. Without
    # this, an admin passing an unknown/mistyped department name sailed
    # straight through to Graph and got a raw, confusing folder-not-found
    # error instead of a clear "no such department".
    dept_ccs = _department_cost_centers(conn, department)
    if not dept_ccs:
        raise HTTPException(status_code=404, detail=f"department {department!r} not found")
    if scope.is_admin:
        return
    caller_ccs = set(scope.fill_cost_centers) if require_fill else set(scope.see_cost_centers)
    if not dept_ccs & caller_ccs:
        verb = "upload to" if require_fill else "view"
        raise HTTPException(status_code=403, detail=f"you are not authorized to {verb} attachments for this department")


def _run(action):
    try:
        return action()
    except pyodbc.Error as exc:
        logger.exception("attachments action failed (DB)")
        raise HTTPException(status_code=502, detail="Database unavailable, please try again later") from exc
    except tuple(ERROR_CODE_BY_EXCEPTION) as exc:
        code = ERROR_CODE_BY_EXCEPTION[type(exc)]
        raise HTTPException(status_code=ERROR_HTTP_STATUS[code], detail=str(exc)) from exc


def _reject_if_declared_too_large(request: Request) -> None:
    """Cheap fast-fail on the declared `Content-Length` header, BEFORE
    `file.file.read()` loads the (already-parsed) upload into memory. Not a
    substitute for the real, byte-accurate check in `validate_upload` --
    a missing/lying header just falls through to that backstop."""
    declared = request.headers.get("content-length")
    if declared is None:
        return
    try:
        declared_bytes = int(declared)
    except ValueError:
        return
    if declared_bytes > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=413, detail=too_large_message(declared_bytes))


@router.get("", response_model=list[AttachmentInfoResponse])
def attachments(
    department: str = Query(...),
    fiscal_year: int = Query(...),
    email: str = Depends(get_current_user_email),
):
    def _action():
        with get_fabric_conn() as conn:
            scope = resolve_scope(email, conn)
            _authorize(conn, department, scope, require_fill=False)
        items = list_attachments(department, fiscal_year)
        return [AttachmentInfoResponse(**vars(item)) for item in items]

    return _run(_action)


@router.post("/upload", response_model=AttachmentInfoResponse)
def upload(
    request: Request,
    department: str = Form(...),
    fiscal_year: int = Form(...),
    file: UploadFile = File(...),
    email: str = Depends(get_current_user_email),
):
    def _action():
        _reject_if_declared_too_large(request)
        with get_fabric_conn() as conn:
            scope = resolve_scope(email, conn)
            _authorize(conn, department, scope, require_fill=True)
        content = file.file.read()
        item = upload_attachment(department, fiscal_year, file.filename, content)
        return AttachmentInfoResponse(**vars(item))

    return _run(_action)


@router.get("/download-url", response_model=DownloadUrlResponse)
def download_url(
    department: str = Query(...),
    fiscal_year: int = Query(...),
    item_id: str = Query(...),
    email: str = Depends(get_current_user_email),
):
    def _action():
        with get_fabric_conn() as conn:
            scope = resolve_scope(email, conn)
            _authorize(conn, department, scope, require_fill=False)
        url = get_download_url(department, fiscal_year, item_id)
        return DownloadUrlResponse(url=url)

    return _run(_action)
