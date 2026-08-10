"""SharePoint attachments per (ฝ่าย, fiscal_year) — A10, spec R1
(`docs/specs/budget-transactional-data-model.md` §4b).

Storage = SharePoint only, there is no DB table (the folder path itself is
the index: uploader + timestamp come free from Graph's `createdBy`/
`createdDateTime`). Destination is CONFIRMED (2026-07-13, not a guess):
site `CMANDWPRD`, library `Budgeting and Management`, folder
`เอกสาร ฝ่าย/<ฝ่าย>/<year>/`. All 114 ฝ่าย × the 2 in-cycle planning years are
already pre-created there — this module never creates a folder, a missing
one is a loud, Thai-explained error (never a silent empty list).

Auth pattern mirrors `notifications.py` (same service principal
`cman-fabric-write`, `Sites.ReadWrite.All`, client-credentials via `httpx`).
The token-fetch helper is intentionally duplicated rather than imported from
`notifications.py` — two call sites is below the project's "3+ call sites"
threshold for extracting a shared abstraction (`11-code-standards`); a third
caller should trigger pulling both into one `graph_auth` module.
"""
import logging
import re
from dataclasses import dataclass
from urllib.parse import quote, unquote

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# App-layer rules (spec §4b / brief): allowed extensions and a size cap.
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({"pdf", "xlsx", "xls", "png", "jpg", "jpeg"})
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10 MB

# The admin master workbooks. They sit at the ROOT of the same
# `Budgeting and Management` library the attachment folders live in, so an
# attachment endpoint handed the right drive-item id could otherwise reach them.
#
# jakkaritw, 2026-08-10, verbatim: "ห้ามยุ่งเด็ดขาด ... ถ้าจะแก้ไขต้องเข้าไป
# หลังบ้าน sharepoint หน้าเวปเข้าถึงไฟล์พวกนี้ไม่ได้" — the web app must never
# read, download or delete them; the only way to change one is through
# SharePoint itself, by the admin. The daily sync then reads them into `dbo.*`.
#
# `_fetch_item_in_folder`'s folder check ALREADY excludes the library root, so
# this name list is deliberate belt-and-braces: it states the rule where a
# future reader will see it, and keeps holding if the folder logic is ever
# loosened. Matched case-insensitively on the file name alone (a copy of one of
# these placed anywhere is refused too — cheaper than being clever, and no
# legitimate department attachment needs one of these exact names).
PROTECTED_MASTER_FILENAMES: frozenset[str] = frozenset({
    "cc dept.xlsx",
    "gl group_gl th name.xlsx",
    "วันปิดรับข้อมูลงบประมาณ.xlsx",
    "ค่าเบี้ยเลี้ยง.xlsx",
})

# SharePoint-illegal path characters (spec §4b, confirmed 2026-07-13) —
# replaced with '-'. Only one real ฝ่าย needed this ("Global Demand/supply
# Planning" -> "Global Demand-supply Planning"); the function is
# deterministic so the app never needs a per-ฝ่าย alias table.
_ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|]')

# Windows/SharePoint reserved device basenames (case-insensitive, with or
# without an extension) — SharePoint refuses these outright regardless of
# the app's own extension whitelist.
_RESERVED_DEVICE_NAMES: frozenset[str] = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


class AttachmentsNotConfiguredError(RuntimeError):
    """Site/library/root-folder settings are blank — never guess a
    SharePoint location (see config.py's `attachments_*` settings)."""


class FolderNotFoundError(RuntimeError):
    """The `<ฝ่าย>/<year>` folder does not exist under the configured root.
    Folders are pre-created by the admin (spec §4b) — this app never
    creates one on the fly, so a 404 here means a real setup gap, surfaced
    loudly rather than as a silent empty file list."""


class DisallowedFileTypeError(ValueError):
    """Extension not in `ALLOWED_EXTENSIONS`."""


class FileTooLargeError(ValueError):
    """File exceeds `MAX_ATTACHMENT_BYTES`."""


class AttachmentNotInFolderError(ValueError):
    """The `item_id` given by the caller does not live in the
    `<ฝ่าย>/<year>` folder they were authorized for.

    Why this exists (2026-08-10): the caller supplies a raw Graph drive-item
    id, and the router's `_authorize` only proves they may act on THAT
    DEPARTMENT — it cannot know whether the id belongs to that department's
    folder. Without this check, any authorized filler could pass any id in
    the whole `Budgeting and Management` library and reach another
    department's file, or one of the admin master workbooks. Harmless-ish for
    a download, unacceptable for the delete added the same day, so BOTH
    item-id paths now verify folder membership first."""


def _format_attachment_mb(num_bytes: int) -> str:
    """`num_bytes` -> `"<N[.d]> MB"`, base 1024*1024 (MiB) -- matches how
    `MAX_ATTACHMENT_BYTES` is defined above (`10 * 1024 * 1024`), so the
    printed limit always equals the configured one exactly (a 1000*1000
    conversion would print "10.5 MB" for a 10 MiB cap — wrong). Rounds to
    one decimal place, then drops a trailing ".0" so a round number reads
    naturally ("10 MB", not "10.0 MB") — the SAME rule for both the actual
    file size and the limit, so the two numbers in the "too large" message
    can never look formatted differently."""
    mb = num_bytes / (1024 * 1024)
    text = f"{mb:.1f}"
    if text.endswith(".0"):
        text = text[:-2]
    return f"{text} MB"


def too_large_message(actual_bytes: int) -> str:
    """Thai copy (jakkaritw-approved wording) for a file over
    `MAX_ATTACHMENT_BYTES` — shared by BOTH size checks on the upload path
    (the router's fast Content-Length pre-check and this module's own
    byte-accurate backstop below) so the two can never disagree in
    wording (bug 4, 2026-08-07/08: the old text was English and printed a
    raw ten-digit byte count)."""
    return f"ไฟล์ใหญ่เกินกำหนด ({_format_attachment_mb(actual_bytes)}) — อัปโหลดได้ไม่เกิน {_format_attachment_mb(MAX_ATTACHMENT_BYTES)}"


def allowed_extensions_text() -> str:
    """The allowed list as the user should read it: dotted, comma-separated,
    stable order (`.jpeg, .jpg, .pdf, .png, .xls, .xlsx`). One source for
    every message that has to name the list."""
    return ", ".join(f".{ext}" for ext in sorted(ALLOWED_EXTENSIONS))


def disallowed_type_message(ext: str) -> str:
    """Thai copy for a rejected extension (2026-08-10: the size message was
    already Thai since bug 4, but this one was still English —
    `"file type '.txt' is not allowed — allowed: jpeg, jpg, ..."` — which is
    what a filler actually hits most often, since a wrong file type is a far
    commoner mistake than a 10 MB file). Names the offending extension AND
    the allowed list, so the user does not have to guess what to convert to."""
    got = f".{ext}" if ext else "(ไม่มีนามสกุล)"
    return f"ไฟล์ชนิด {got} อัปโหลดไม่ได้ — อัปโหลดได้เฉพาะ {allowed_extensions_text()}"


class AttachmentTransportError(RuntimeError):
    """A Graph call failed for a reason other than the folder being missing
    (auth, network, unexpected status) — always surfaced loudly, never
    silently swallowed."""


ERROR_HTTP_STATUS: dict[str, int] = {
    "attachments_not_configured": 501,
    "folder_not_found": 502,
    "disallowed_file_type": 400,
    "file_too_large": 400,
    # 404, not 403: the caller IS authorized for this department, the id just
    # is not one of its files — telling them "forbidden" would confirm the id
    # exists somewhere else in the library.
    "attachment_not_in_folder": 404,
    "attachment_transport_error": 502,
}

ERROR_CODE_BY_EXCEPTION: dict[type[Exception], str] = {
    AttachmentsNotConfiguredError: "attachments_not_configured",
    FolderNotFoundError: "folder_not_found",
    DisallowedFileTypeError: "disallowed_file_type",
    FileTooLargeError: "file_too_large",
    AttachmentNotInFolderError: "attachment_not_in_folder",
    AttachmentTransportError: "attachment_transport_error",
}


@dataclass
class AttachmentInfo:
    item_id: str
    name: str
    size: int
    created_by: str | None
    created_at: str | None
    web_url: str | None


def sanitize_department_folder(department: str) -> str:
    """ฝ่าย -> SharePoint-safe folder name (spec §4b): replace any of
    ``\\ / : * ? " < > |`` with ``-``, keep everything else (including Thai).
    Deterministic — no per-ฝ่าย alias table needed."""
    return _ILLEGAL_CHARS.sub("-", department)


def sanitize_attachment_filename(filename: str) -> str:
    """Uploaded filename -> Graph-path-safe name. MUST run before the name is
    ever interpolated into a Graph URL: Graph itself uses ``:`` as its path
    delimiter (``root:/<path>/<filename>:/content``), so an unsanitized
    ``:`` (or ``\\ / * ? " < > |``) would corrupt the request path, not just
    fail to upload. Applies the same char policy as
    `sanitize_department_folder`, then strips leading/trailing dots and
    spaces (Windows/SharePoint trim these silently — without this step a
    name like ``"..report.pdf  "`` would keep the traversal-looking dots),
    and rejects reserved Windows device basenames (`_RESERVED_DEVICE_NAMES`,
    case-insensitive, with or without extension), which SharePoint refuses
    outright.

    Raises `DisallowedFileTypeError` (the module's existing 400 validation
    error) when nothing usable remains, or when the basename is reserved.
    """
    name = _ILLEGAL_CHARS.sub("-", filename).strip(" .")
    if not name:
        raise DisallowedFileTypeError("ชื่อไฟล์ใช้ไม่ได้ — กรุณาเปลี่ยนชื่อไฟล์แล้วอัปโหลดใหม่")
    basename = name.rsplit(".", 1)[0] if "." in name else name
    if basename.upper() in _RESERVED_DEVICE_NAMES:
        raise DisallowedFileTypeError(
            f"ชื่อไฟล์ '{basename}' เป็นชื่อสงวนของระบบ ใช้ไม่ได้ — กรุณาเปลี่ยนชื่อไฟล์แล้วอัปโหลดใหม่"
        )
    return name


def _require_configured(settings: Settings) -> None:
    if not (settings.attachments_site_hostname and settings.attachments_site_name and settings.attachments_library_name):
        raise AttachmentsNotConfiguredError(
            "attachments storage is not configured — set ATTACHMENTS_SITE_HOSTNAME / "
            "ATTACHMENTS_SITE_NAME / ATTACHMENTS_LIBRARY_NAME (ask jakkaritw for the target)"
        )


def _folder_path(department: str, fiscal_year: int, settings: Settings) -> str:
    root = settings.attachments_root_folder.strip("/")
    dept_folder = sanitize_department_folder(department)
    return f"{root}/{dept_folder}/{fiscal_year}"


def validate_upload(filename: str, size: int) -> str:
    """Sanitizes `filename` (`sanitize_attachment_filename`) and validates
    the (sanitized) extension + `size`. Returns the sanitized filename —
    callers MUST use this returned name everywhere downstream (never the
    raw `filename`), so a malicious/malformed name can never reach the
    Graph upload path. Raises `DisallowedFileTypeError`/`FileTooLargeError`
    — checked BEFORE any Graph call, so a rejected upload never even
    fetches a token."""
    safe_filename = sanitize_attachment_filename(filename)
    ext = safe_filename.rsplit(".", 1)[-1].lower() if "." in safe_filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise DisallowedFileTypeError(disallowed_type_message(ext))
    if size > MAX_ATTACHMENT_BYTES:
        raise FileTooLargeError(too_large_message(size))
    return safe_filename


def _get_graph_token(settings: Settings) -> str:
    url = f"https://login.microsoftonline.com/{settings.entra_tenant_id}/oauth2/v2.0/token"
    data = {
        "client_id": settings.entra_client_id,
        "client_secret": settings.entra_client_secret,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }
    resp = httpx.post(url, data=data, timeout=30)
    if resp.status_code != 200:
        raise AttachmentTransportError(f"Graph token request failed: {resp.status_code} {resp.text}")
    return resp.json()["access_token"]


def _resolve_site_id(token: str, hostname: str, site_name: str) -> str:
    resp = httpx.get(
        f"{GRAPH_BASE}/sites/{hostname}:/sites/{site_name}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise AttachmentTransportError(f"Graph site lookup failed: {resp.status_code} {resp.text}")
    return resp.json()["id"]


def _resolve_drive_id(token: str, site_id: str, library_name: str) -> str:
    resp = httpx.get(f"{GRAPH_BASE}/sites/{site_id}/drives", headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if resp.status_code != 200:
        raise AttachmentTransportError(f"Graph drive list failed: {resp.status_code} {resp.text}")
    drives = resp.json().get("value", [])
    for drive in drives:
        if drive.get("name", "").strip().lower() == library_name.strip().lower():
            return drive["id"]
    raise AttachmentTransportError(f"no document library named {library_name!r} found on the configured site")


def _resolve_site_and_drive(token: str, settings: Settings) -> tuple[str, str]:
    site_id = _resolve_site_id(token, settings.attachments_site_hostname, settings.attachments_site_name)
    drive_id = _resolve_drive_id(token, site_id, settings.attachments_library_name)
    return site_id, drive_id


def _item_to_info(item: dict) -> AttachmentInfo:
    created = item.get("createdBy", {}).get("user", {})
    return AttachmentInfo(
        item_id=item["id"],
        name=item["name"],
        size=item.get("size", 0),
        created_by=created.get("displayName"),
        created_at=item.get("createdDateTime"),
        web_url=item.get("webUrl"),
    )


def list_attachments(department: str, fiscal_year: int, *, settings: Settings | None = None) -> list[AttachmentInfo]:
    """Lists the files already in `<root>/<ฝ่าย>/<year>/`. `FolderNotFoundError`
    when that folder does not exist (spec: pre-created, never auto-created
    here) — never a silently empty list masking a real setup gap."""
    settings = settings or get_settings()
    _require_configured(settings)
    token = _get_graph_token(settings)
    _site_id, drive_id = _resolve_site_and_drive(token, settings)
    path = _folder_path(department, fiscal_year, settings)

    resp = httpx.get(
        f"{GRAPH_BASE}/drives/{drive_id}/root:/{path}:/children",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if resp.status_code == 404:
        raise FolderNotFoundError(
            f"the folder '{path}' does not exist yet — ask the admin to create it for ฝ่าย {department!r}, year {fiscal_year}"
        )
    if resp.status_code != 200:
        raise AttachmentTransportError(f"Graph folder listing failed: {resp.status_code} {resp.text}")

    return [_item_to_info(item) for item in resp.json().get("value", [])]


def upload_attachment(
    department: str, fiscal_year: int, filename: str, content: bytes, *, settings: Settings | None = None
) -> AttachmentInfo:
    """Uploads `content` as `filename` into `<root>/<ฝ่าย>/<year>/`. Validates
    + sanitizes the filename and validates size BEFORE any Graph call
    (`validate_upload`) — the SANITIZED name (never the raw one) is used to
    build the Graph URL, and its final path segment is percent-encoded, so
    an uploaded name can never smuggle a Graph path-delimiter (``:``) or
    other illegal character into the request. A simple PUT is used (Graph
    supports this up to 250 MB) — well within the 10 MB cap, no
    resumable-upload session needed."""
    safe_filename = validate_upload(filename, len(content))
    settings = settings or get_settings()
    _require_configured(settings)
    token = _get_graph_token(settings)
    _site_id, drive_id = _resolve_site_and_drive(token, settings)
    path = _folder_path(department, fiscal_year, settings)

    resp = httpx.put(
        f"{GRAPH_BASE}/drives/{drive_id}/root:/{path}/{quote(safe_filename, safe='')}:/content",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/octet-stream"},
        content=content,
        timeout=60,
    )
    if resp.status_code == 404:
        raise FolderNotFoundError(
            f"the folder '{path}' does not exist yet — ask the admin to create it for ฝ่าย {department!r}, year {fiscal_year}"
        )
    if resp.status_code not in (200, 201):
        raise AttachmentTransportError(f"Graph upload failed: {resp.status_code} {resp.text}")

    return _item_to_info(resp.json())


def _fetch_item_in_folder(
    token: str, drive_id: str, department: str, fiscal_year: int, item_id: str, settings: Settings
) -> dict:
    """Fetches one drive item AND proves it sits directly inside
    `<root>/<ฝ่าย>/<year>/` before the caller is allowed to do anything with
    it (`AttachmentNotInFolderError` otherwise).

    The membership test compares Graph's `parentReference.path` — which comes
    back shaped like `/drives/<id>/root:/เอกสาร ฝ่าย/Data & Analytic/2027`
    and MAY be percent-encoded — against the folder this department/year
    resolves to. `unquote` first, then require the path to END WITH
    `root:/<expected>`: an exact tail match, so a sibling folder whose name
    merely starts the same ("2027-old") cannot pass, and a file nested one
    level deeper does not either."""
    resp = httpx.get(
        f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    # 400 as well as 404: the id comes from the caller, so a MALFORMED one is
    # just as much "no such file here" as a well-formed-but-missing one. Graph
    # answers 400 invalidRequest for a garbage id, and letting that through as a
    # transport error would report 502 "server problem" for what is really bad
    # input (seen live on staging 2026-08-10 while testing this guard).
    if resp.status_code in (400, 404):
        raise AttachmentNotInFolderError(f"ไม่พบไฟล์นี้ในเอกสารของฝ่าย {department} ปี {fiscal_year}")
    if resp.status_code != 200:
        raise AttachmentTransportError(f"Graph item lookup failed: {resp.status_code} {resp.text}")

    item = resp.json()
    name = item.get("name") or ""
    if name.strip().lower() in {n.lower() for n in PROTECTED_MASTER_FILENAMES}:
        # Second, explicit line of defence — see PROTECTED_MASTER_FILENAMES.
        # Logged at WARNING because reaching this means something asked the web
        # app for a master workbook, which no legitimate flow ever does.
        logger.warning(
            "attachments: REFUSED access to protected master %r (item_id=%s, department=%r, year=%s)",
            name, item_id, department, fiscal_year,
        )
        raise AttachmentNotInFolderError(f"ไม่พบไฟล์นี้ในเอกสารของฝ่าย {department} ปี {fiscal_year}")

    expected = _folder_path(department, fiscal_year, settings)
    parent_path = unquote(item.get("parentReference", {}).get("path") or "")
    if not parent_path.endswith(f"root:/{expected}"):
        logger.warning(
            "attachments: item %r lives in %r, not in %r — refusing (department=%r, year=%s)",
            item_id, parent_path, expected, department, fiscal_year,
        )
        raise AttachmentNotInFolderError(f"ไม่พบไฟล์นี้ในเอกสารของฝ่าย {department} ปี {fiscal_year}")
    return item


def get_download_url(department: str, fiscal_year: int, item_id: str, *, settings: Settings | None = None) -> str:
    """Returns a pre-authenticated, time-limited Graph download URL
    (`@microsoft.graph.downloadUrl`) for one item — the frontend opens it
    directly, no file bytes stream through this backend. The item must belong
    to this department/year folder (`_fetch_item_in_folder`)."""
    settings = settings or get_settings()
    _require_configured(settings)
    token = _get_graph_token(settings)
    _site_id, drive_id = _resolve_site_and_drive(token, settings)

    item = _fetch_item_in_folder(token, drive_id, department, fiscal_year, item_id, settings)
    url = item.get("@microsoft.graph.downloadUrl")
    if not url:
        raise AttachmentTransportError(f"Graph item {item_id!r} has no download URL")
    return url


def delete_attachment(
    department: str, fiscal_year: int, item_id: str, *, settings: Settings | None = None
) -> str:
    """Deletes one attachment from `<root>/<ฝ่าย>/<year>/` and returns the
    deleted file's name (so the caller can name it in a confirmation).

    Added 2026-08-10 after the SIT attachment run: there was no delete path at
    all, so a filler who uploaded the wrong file had to ask an admin to remove
    it through SharePoint by hand. Folder membership is verified FIRST
    (`_fetch_item_in_folder`) — never trust a caller-supplied drive-item id on
    a destructive call. Graph answers 204 on success; a 404 at this point means
    someone else deleted it between the check and the call, which is the
    desired end state, so it is treated as success rather than an error."""
    settings = settings or get_settings()
    _require_configured(settings)
    token = _get_graph_token(settings)
    _site_id, drive_id = _resolve_site_and_drive(token, settings)

    item = _fetch_item_in_folder(token, drive_id, department, fiscal_year, item_id, settings)
    name = item.get("name", item_id)

    resp = httpx.delete(
        f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if resp.status_code not in (200, 204, 404):
        raise AttachmentTransportError(f"Graph delete failed: {resp.status_code} {resp.text}")
    logger.info(
        "attachments: deleted %r from %s/%s (item_id=%s, graph_status=%s)",
        name, department, fiscal_year, item_id, resp.status_code,
    )
    return name
