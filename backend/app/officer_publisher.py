"""SharePoint publisher — Module 2 of PRD #34 (issue #34).

Publishes the officer-review workbook to ONE file in ONE dedicated folder:
site `CMANDWPRD`, library `Budgeting and Management`, folder
`officer review/`, file `budget_FY<yyyy>_officer_latest.xlsx` — created if
missing, otherwise overwritten in place (`conflictBehavior=replace`, so the
SharePoint item id never changes and version history accumulates there).

Only the Graph token + site/drive resolution is shared with
`app.attachments` (issue #34: "Only the Graph token, site and drive
resolution is shared with the attachments module") — `_get_graph_token` and
`_resolve_site_and_drive` are imported UNCHANGED, `attachments.py` is never
edited. This module never imports `upload_attachment` (it builds its path
under `เอกสาร ฝ่าย/<ฝ่าย>/<year>` and is not reusable here) and never touches
`_is_inside_attachments_root` (that guard's only callers are download/delete
on the attachments path; this publisher gets its OWN guard below, scoped to
`officer review/` only).

This is an explicit, owner-approved exception to the 2026-08-10 rule "ทุกไฟล์
บน Path ห้ามยุ่ง ยกเว้นเอกสารฝ่าย" — see `docs/adr/0032-officer-review-robot.md`.
The web app's attachment guard (limited to `เอกสาร ฝ่าย/`) is unchanged.
"""
import logging
import math
import re
import time
from collections.abc import Callable
from typing import TypeVar
from urllib.parse import quote

import httpx

from app.attachments import GRAPH_BASE, AttachmentTransportError, _get_graph_token, _resolve_site_and_drive
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

OFFICER_FOLDER_NAME = "officer review"

T = TypeVar("T")

# The 8 admin master workbooks (memory `project_protected_master_files.md`,
# test_attachments.py::ROOT_MASTERS) — the published filename must match
# NEITHER these NOR `approved_budget_<yyyy>.xlsx` (PRD story 27), so no
# downstream sync can ever mistake this file for an input.
ROOT_MASTER_FILENAMES = frozenset({
    "cc dept.xlsx", "cc orgcode.xlsx", "country.xlsx", "gl group_gl th name.xlsx",
    "ค่าเบี่ยเลี้ยง.xlsx", "ซ่อนเอกสาร.xlsx", "วันปิดรับข้อมูลงบประมาณ.xlsx",
    "อัตราแลกเปลี่ยนเฉลี่ยรายปี.xlsx",
})
_APPROVED_BUDGET_RE = re.compile(r"approved_budget_(\d{4})\.xlsx")
# L2 fix round 4 (finding 3): a Graph `error.code` is caller-supplied text
# that reaches a log line — pattern-check it the same way `_q()`'s SQL guard
# constrains its own inputs, instead of trusting Graph to only ever send a
# short identifier-shaped string.
_GRAPH_ERROR_CODE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")

# 423 (Excel has the file locked open) and 409 with error.code=='resourceLocked'
# both mean "someone has it open" — retry with backoff, honoring Retry-After.
# 429/503/504 are the usual transient-Graph set (mirrors
# `app.notifications._post_send_mail`'s retry, but this file never imports
# it — notifications.py is on the zero-edit list, and the retryable status
# set here is a superset anyway).
_RETRY_BACKOFF_SECONDS = (10, 30, 60, 120)
_RETRY_AFTER_CAP_SECONDS = 120.0
_TIMEOUT_SECONDS = 60.0
_TOTAL_ATTEMPTS = 1 + len(_RETRY_BACKOFF_SECONDS)


class OfficerPublishError(RuntimeError):
    """The publish failed after exhausting retries, or a structural guard
    (filename, folder identity, parent-id) refused to proceed."""


def officer_filename(planning_year: int) -> str:
    name = f"budget_FY{planning_year}_officer_latest.xlsx"
    if _APPROVED_BUDGET_RE.match(name):
        raise OfficerPublishError(f"refusing filename {name!r} — matches approved_budget_<yyyy>.xlsx")
    if name in ROOT_MASTER_FILENAMES:
        raise OfficerPublishError(f"refusing filename {name!r} — matches a protected master filename")
    return name


def _retry_after_seconds(resp: httpx.Response) -> float | None:
    """N7 fix round 2026-09-24: `float()` happily parses `"nan"`/`"inf"`/
    `"-5"` without raising `ValueError` — a malformed or hostile
    `Retry-After` header used to reach `time.sleep` unvalidated (`nan`
    crashes it, `-5`/`-inf` are meaningless as a wait). Any non-finite or
    negative value is treated the SAME as a missing header — ignored, so the
    caller falls back to its own fixed backoff step (still capped at
    `_RETRY_AFTER_CAP_SECONDS` for a legitimate large value)."""
    raw = resp.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return value


def _graph_error_code(resp: httpx.Response) -> str:
    """NEW-2 fix round 3: the ONLY per-response detail any warning or
    `OfficerPublishError` message below may carry — never `resp.text`
    (which can hold a SharePoint lock message naming the user holding the
    file, or echo other Graph-supplied text; this log is public, see
    `officer-review.yml`). Parses `error.code` from the JSON body if
    present and well-formed, else `"-"` — never raises on a malformed or
    non-JSON body.

    L2 fix round 4 (finding 3): the previous version assumed the body was
    always `{"error": {"code": ...}}` — a body that is a JSON list, or
    `{"error": "some string"}`, or `{"error": null}` all raised a bare
    `AttributeError`/`TypeError` straight out of this "never raises"
    helper (Graph does not promise this shape on every error path, e.g. a
    gateway-level failure). Now tolerant of ANY JSON shape, and the code
    itself is pattern-checked (`_GRAPH_ERROR_CODE_RE`) so an oversized or
    free-text 'code' Graph might one day send can never reach a log line
    unconstrained."""
    try:
        body = resp.json()
    except ValueError:
        return "-"
    if not isinstance(body, dict):
        return "-"
    error = body.get("error")
    if not isinstance(error, dict):
        return "-"
    code = error.get("code")
    if not isinstance(code, str) or not _GRAPH_ERROR_CODE_RE.match(code):
        return "-"
    return code


def _parse_json_body(resp: httpx.Response, *, description: str) -> dict:
    """NEW-6 fix round 3: a Graph response that returns 2xx with a
    malformed/non-JSON body (seen on a folder-create 201) used to raise a
    bare `json.JSONDecodeError` (a `ValueError`) straight out of this
    module — uncaught by the caller's `except OfficerPublishError`, it
    escaped all the way to `jobs.officer_review.main`'s outer handler and
    exited 2 ("unexpected exception") instead of the correct PUBLISH FAIL
    (exit 1). Wraps the parse so this is always a normal
    `OfficerPublishError` — type name only, never the body text."""
    try:
        return resp.json()
    except ValueError as exc:
        raise OfficerPublishError(f"{description}: response body was not valid JSON (type={type(exc).__name__})") from exc


def _is_retryable(resp: httpx.Response) -> bool:
    if resp.status_code in (423, 429, 503, 504):
        return True
    if resp.status_code == 409:
        return _graph_error_code(resp) == "resourceLocked"
    return False


def _call_with_retry(call: Callable[[], httpx.Response], *, description: str, sleep: Callable[[float], None]) -> httpx.Response:
    """OPS-1/OPS-4: retry ONE Graph HTTP call (this module's own GET/POST/PUT
    — never `app.attachments`' functions, see `_step_with_retry` for those)
    on a transport error or a retryable status (423/429/503/504, 409
    resourceLocked). `Retry-After` REPLACES the fixed backoff step for that
    wait (never adds to it), capped at `_RETRY_AFTER_CAP_SECONDS`; there is
    no sleep after the FINAL attempt. Returns the response UNCHANGED on a
    non-retryable status (including a plain 404 — some callers, e.g. the
    folder GET, still need to branch on that) — only raises
    `OfficerPublishError` once every attempt failed on a transport error or
    a retryable status."""
    last_error: str | None = None
    for attempt in range(_TOTAL_ATTEMPTS):
        resp: httpx.Response | None = None
        try:
            resp = call()
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            # NEW-2 fix round 3: never `str(exc)` — an httpx transport
            # error's text can embed the request URL/host; type name only.
            last_error = f"status=- code=- type={type(exc).__name__}"
            logger.warning("officer_publisher: %s attempt %d transport error type=%s", description, attempt + 1, type(exc).__name__)
        else:
            if not _is_retryable(resp):
                return resp
            # NEW-2 fix round 3: never `resp.text` — status code + parsed
            # Graph `error.code` only (see `_graph_error_code`).
            code = _graph_error_code(resp)
            last_error = f"status={resp.status_code} code={code}"
            logger.warning("officer_publisher: %s attempt %d retryable failure status=%d code=%s", description, attempt + 1, resp.status_code, code)
        if attempt == _TOTAL_ATTEMPTS - 1:
            break
        retry_after = _retry_after_seconds(resp) if resp is not None else None
        wait = min(retry_after, _RETRY_AFTER_CAP_SECONDS) if retry_after is not None else _RETRY_BACKOFF_SECONDS[attempt]
        sleep(wait)
    raise OfficerPublishError(f"{description} failed after {_TOTAL_ATTEMPTS} attempts — last error: {last_error}")


def _step_with_retry(step: Callable[[], T], *, description: str, sleep: Callable[[float], None]) -> T:
    """OPS-1: retry a Graph resolution step from `app.attachments`
    (`_get_graph_token` / `_resolve_site_and_drive`, zero-edit — neither
    exposes a status code or `Retry-After`, only `AttachmentTransportError`
    on any non-2xx or a raw `httpx` transport error) with the SAME fixed
    backoff sequence as `_call_with_retry` — no `Retry-After` to honor here,
    so every wait uses the plain schedule; no sleep after the FINAL
    attempt."""
    last_error: str | None = None
    for attempt in range(_TOTAL_ATTEMPTS):
        try:
            return step()
        except (AttachmentTransportError, httpx.TimeoutException, httpx.TransportError) as exc:
            # NEW-2 fix round 3: never `str(exc)` — `AttachmentTransportError`
            # (zero-edit `app.attachments`) builds its text as
            # `f"... {resp.status_code} {resp.text}"`, so printing it here
            # would leak whatever Graph put in the response body. Type name only.
            last_error = type(exc).__name__
            logger.warning("officer_publisher: %s attempt %d failed type=%s", description, attempt + 1, last_error)
            if attempt == _TOTAL_ATTEMPTS - 1:
                break
            sleep(_RETRY_BACKOFF_SECONDS[attempt])
    raise OfficerPublishError(f"{description} failed after {_TOTAL_ATTEMPTS} attempts — last error type={last_error}")


def _get_or_create_folder(token: str, drive_id: str, *, sleep: Callable[[float], None]) -> str:
    """Returns the `officer review/` folder's item id. Creates it once if
    missing (404 -> POST, 409 there means a parallel run already created it
    — re-GET and proceed). Verifies the resolved item really is a folder
    named exactly `officer review`, sitting DIRECTLY under the drive root —
    the structural write-scope guard (PRD story 26): this publisher must be
    physically unable to resolve any other folder."""
    headers = {"Authorization": f"Bearer {token}"}
    get_url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{quote(OFFICER_FOLDER_NAME, safe='')}"
    # OPS-1/OPS-4: every Graph call below retries transient failures
    # (429/503/504/423, or a transport error) with backoff, `Retry-After`
    # honored — `sleep` is finally used for what it was always meant for.
    resp = _call_with_retry(
        lambda: httpx.get(get_url, headers=headers, timeout=_TIMEOUT_SECONDS),
        description=f"'{OFFICER_FOLDER_NAME}' folder GET", sleep=sleep,
    )
    if resp.status_code == 404:
        create_resp = _call_with_retry(
            lambda: httpx.post(
                f"{GRAPH_BASE}/drives/{drive_id}/root/children",
                headers={**headers, "Content-Type": "application/json"},
                json={"name": OFFICER_FOLDER_NAME, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"},
                timeout=_TIMEOUT_SECONDS,
            ),
            description=f"'{OFFICER_FOLDER_NAME}' folder create POST", sleep=sleep,
        )
        if create_resp.status_code == 409:
            resp = _call_with_retry(
                lambda: httpx.get(get_url, headers=headers, timeout=_TIMEOUT_SECONDS),
                description=f"'{OFFICER_FOLDER_NAME}' folder re-GET after 409", sleep=sleep,
            )
        elif create_resp.status_code in (200, 201):
            resp = create_resp
        else:
            # NEW-2 fix round 3: status code + parsed Graph `error.code`
            # only — never `create_resp.text` (see `_graph_error_code`).
            raise OfficerPublishError(
                f"could not create '{OFFICER_FOLDER_NAME}' folder: status={create_resp.status_code} code={_graph_error_code(create_resp)}"
            )
    # N1 fix round 2026-09-24: a 201 Created from the POST above is success,
    # not a failure — the code used to fall through to this check, see it was
    # not exactly 200, and raise `OfficerPublishError` on the VERY FIRST real
    # publish (the folder never exists before then, so this branch always ran
    # on week 1). `create_resp` (200 or 201) is a valid DriveItem body either
    # way — same shape the GET below returns.
    if resp.status_code not in (200, 201):
        raise OfficerPublishError(
            f"could not resolve '{OFFICER_FOLDER_NAME}' folder: status={resp.status_code} code={_graph_error_code(resp)}"
        )

    item = _parse_json_body(resp, description=f"'{OFFICER_FOLDER_NAME}' folder body")
    # L2 fix round 4 (finding 3): a non-dict body (e.g. a JSON list) used to
    # raise a bare AttributeError on the very next `.get` call below.
    if not isinstance(item, dict) or "folder" not in item:
        raise OfficerPublishError(f"'{OFFICER_FOLDER_NAME}' resolved to a non-folder item — refusing to publish")
    # L2 fix round 4 (finding 7): never print the Graph-supplied `name` value
    # — "folder name mismatch" says everything an operator needs (which
    # structural guard tripped) without echoing arbitrary Graph text into a
    # public log.
    if item.get("name") != OFFICER_FOLDER_NAME:
        raise OfficerPublishError(f"'{OFFICER_FOLDER_NAME}' folder name mismatch — refusing to publish")
    parent_ref = item.get("parentReference")
    # L2 fix round 4 (finding 3): `parentReference: null` (present but None)
    # is a valid JSON shape Graph could send — `isinstance` catches that the
    # same as a missing key. Finding 7: never print `parentReference.path`.
    parent_path = parent_ref.get("path", "") if isinstance(parent_ref, dict) else ""
    if not isinstance(parent_path, str) or not parent_path.rstrip("/").endswith("root:"):
        raise OfficerPublishError(f"'{OFFICER_FOLDER_NAME}' parent mismatch — refusing to publish")
    folder_id = item.get("id")
    if not isinstance(folder_id, str) or not folder_id:
        raise OfficerPublishError(f"'{OFFICER_FOLDER_NAME}' folder body missing id — refusing to publish")
    return folder_id


def publish_officer_workbook(
    xlsx_bytes: bytes,
    *,
    planning_year: int,
    settings: Settings | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Publish `xlsx_bytes` as `budget_FY<planning_year>_officer_latest.xlsx`
    inside `officer review/`. Returns the file's `webUrl`. Never deletes
    anything. Raises `OfficerPublishError` on any FAIL — the caller
    (`jobs.officer_review`) must treat that as "no publish, no mail"."""
    settings = settings or get_settings()
    filename = officer_filename(planning_year)

    # OPS-1: token fetch and site/drive resolution now retry transient
    # failures too — before this fix, only the PUT below did, so a transient
    # 503 anywhere earlier in the flow escaped as an unmapped exception
    # instead of a clean "no publish, no mail" `OfficerPublishError`.
    token = _step_with_retry(lambda: _get_graph_token(settings), description="Graph token fetch", sleep=sleep)
    _site_id, drive_id = _step_with_retry(
        lambda: _resolve_site_and_drive(token, settings), description="site/drive resolution", sleep=sleep
    )
    folder_id = _get_or_create_folder(token, drive_id, sleep=sleep)

    url = f"{GRAPH_BASE}/drives/{drive_id}/items/{folder_id}:/{quote(filename, safe='')}:/content?@microsoft.graph.conflictBehavior=replace"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/octet-stream"}

    resp = _call_with_retry(
        lambda: httpx.put(url, headers=headers, content=xlsx_bytes, timeout=_TIMEOUT_SECONDS),
        description="publish PUT", sleep=sleep,
    )
    if resp.status_code not in (200, 201):
        # NEW-2 fix round 3: status code + parsed Graph `error.code` only —
        # never `resp.text`.
        raise OfficerPublishError(f"publish PUT failed: status={resp.status_code} code={_graph_error_code(resp)}")
    item = _parse_json_body(resp, description="publish PUT response body")
    # L2 fix round 4 (finding 3): tolerate any JSON shape — a non-dict body,
    # a null/missing `parentReference`, or a missing `id`/`webUrl` must all
    # raise `OfficerPublishError` (exit 1), never a bare KeyError/AttributeError.
    # Finding 7: never print the parentReference.id VALUE — "parent mismatch"
    # names which guard tripped without echoing Graph-supplied ids.
    if not isinstance(item, dict):
        raise OfficerPublishError("publish PUT response body was not a JSON object — refusing to trust the write")
    parent_ref = item.get("parentReference")
    parent_id = parent_ref.get("id") if isinstance(parent_ref, dict) else None
    if parent_id != folder_id:
        raise OfficerPublishError("published item parent mismatch — refusing to trust the write")
    web_url, item_id = item.get("webUrl"), item.get("id")
    if not isinstance(web_url, str) or not web_url or not isinstance(item_id, str) or not item_id:
        raise OfficerPublishError("publish PUT response missing id/webUrl — refusing to trust the write")
    return web_url
