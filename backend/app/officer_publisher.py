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
import re
import time
from collections.abc import Callable
from urllib.parse import quote

import httpx

from app.attachments import GRAPH_BASE, _get_graph_token, _resolve_site_and_drive
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

OFFICER_FOLDER_NAME = "officer review"

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

# 423 (Excel has the file locked open) and 409 with error.code=='resourceLocked'
# both mean "someone has it open" — retry with backoff, honoring Retry-After.
# 429/503/504 are the usual transient-Graph set (mirrors
# `app.notifications._post_send_mail`'s retry, but this file never imports
# it — notifications.py is on the zero-edit list, and the retryable status
# set here is a superset anyway).
_RETRY_BACKOFF_SECONDS = (10, 30, 60, 120)
_TIMEOUT_SECONDS = 60.0


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
    raw = resp.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _is_retryable(resp: httpx.Response) -> bool:
    if resp.status_code in (423, 429, 503, 504):
        return True
    if resp.status_code == 409:
        try:
            code = resp.json().get("error", {}).get("code")
        except ValueError:
            code = None
        return code == "resourceLocked"
    return False


def _get_or_create_folder(token: str, drive_id: str, *, sleep: Callable[[float], None]) -> str:
    """Returns the `officer review/` folder's item id. Creates it once if
    missing (404 -> POST, 409 there means a parallel run already created it
    — re-GET and proceed). Verifies the resolved item really is a folder
    named exactly `officer review`, sitting DIRECTLY under the drive root —
    the structural write-scope guard (PRD story 26): this publisher must be
    physically unable to resolve any other folder."""
    headers = {"Authorization": f"Bearer {token}"}
    resp = httpx.get(f"{GRAPH_BASE}/drives/{drive_id}/root:/{quote(OFFICER_FOLDER_NAME, safe='')}", headers=headers, timeout=_TIMEOUT_SECONDS)
    if resp.status_code == 404:
        create_resp = httpx.post(
            f"{GRAPH_BASE}/drives/{drive_id}/root/children",
            headers={**headers, "Content-Type": "application/json"},
            json={"name": OFFICER_FOLDER_NAME, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"},
            timeout=_TIMEOUT_SECONDS,
        )
        if create_resp.status_code == 409:
            resp = httpx.get(f"{GRAPH_BASE}/drives/{drive_id}/root:/{quote(OFFICER_FOLDER_NAME, safe='')}", headers=headers, timeout=_TIMEOUT_SECONDS)
        elif create_resp.status_code in (200, 201):
            resp = create_resp
        else:
            raise OfficerPublishError(f"could not create '{OFFICER_FOLDER_NAME}' folder: {create_resp.status_code} {create_resp.text}")
    if resp.status_code != 200:
        raise OfficerPublishError(f"could not resolve '{OFFICER_FOLDER_NAME}' folder: {resp.status_code} {resp.text}")

    item = resp.json()
    if "folder" not in item:
        raise OfficerPublishError(f"'{OFFICER_FOLDER_NAME}' resolved to a non-folder item — refusing to publish")
    if item.get("name") != OFFICER_FOLDER_NAME:
        raise OfficerPublishError(f"resolved item name {item.get('name')!r} != {OFFICER_FOLDER_NAME!r} — refusing to publish")
    parent_path = (item.get("parentReference") or {}).get("path", "")
    if not parent_path.rstrip("/").endswith("root:"):
        raise OfficerPublishError(f"'{OFFICER_FOLDER_NAME}' is not a direct child of the library root (parent path {parent_path!r}) — refusing to publish")
    return item["id"]


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

    token = _get_graph_token(settings)
    _site_id, drive_id = _resolve_site_and_drive(token, settings)
    folder_id = _get_or_create_folder(token, drive_id, sleep=sleep)

    url = f"{GRAPH_BASE}/drives/{drive_id}/items/{folder_id}:/{quote(filename, safe='')}:/content?@microsoft.graph.conflictBehavior=replace"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/octet-stream"}

    last_error = None
    for attempt, backoff in enumerate((0, *_RETRY_BACKOFF_SECONDS)):
        if backoff:
            sleep(backoff)
        try:
            resp = httpx.put(url, headers=headers, content=xlsx_bytes, timeout=_TIMEOUT_SECONDS)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = str(exc)
            logger.warning("officer_publisher: PUT attempt %d transport error: %s", attempt + 1, exc)
            continue
        if resp.status_code in (200, 201):
            item = resp.json()
            if (item.get("parentReference") or {}).get("id") != folder_id:
                raise OfficerPublishError(
                    f"published item's parentReference.id {item.get('parentReference', {}).get('id')!r} "
                    f"!= expected folder id {folder_id!r} — refusing to trust the write"
                )
            return item["webUrl"]
        if not _is_retryable(resp):
            raise OfficerPublishError(f"publish PUT failed: {resp.status_code} {resp.text}")
        last_error = f"{resp.status_code} {resp.text}"
        retry_after = _retry_after_seconds(resp)
        if retry_after is not None:
            sleep(retry_after)
        logger.warning("officer_publisher: PUT attempt %d retryable failure: %s", attempt + 1, last_error)

    raise OfficerPublishError(f"publish failed after {len(_RETRY_BACKOFF_SECONDS) + 1} attempts — last error: {last_error}")
