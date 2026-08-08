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
from urllib.parse import quote

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# App-layer rules (spec §4b / brief): allowed extensions and a size cap.
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({"pdf", "xlsx", "xls", "png", "jpg", "jpeg"})
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10 MB

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


class AttachmentTransportError(RuntimeError):
    """A Graph call failed for a reason other than the folder being missing
    (auth, network, unexpected status) — always surfaced loudly, never
    silently swallowed."""


ERROR_HTTP_STATUS: dict[str, int] = {
    "attachments_not_configured": 501,
    "folder_not_found": 502,
    "disallowed_file_type": 400,
    "file_too_large": 400,
    "attachment_transport_error": 502,
}

ERROR_CODE_BY_EXCEPTION: dict[type[Exception], str] = {
    AttachmentsNotConfiguredError: "attachments_not_configured",
    FolderNotFoundError: "folder_not_found",
    DisallowedFileTypeError: "disallowed_file_type",
    FileTooLargeError: "file_too_large",
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
        raise DisallowedFileTypeError(f"filename {filename!r} is empty after removing illegal characters")
    basename = name.rsplit(".", 1)[0] if "." in name else name
    if basename.upper() in _RESERVED_DEVICE_NAMES:
        raise DisallowedFileTypeError(f"filename {filename!r} uses a reserved device name ({basename.upper()})")
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
        raise DisallowedFileTypeError(
            f"file type '.{ext}' is not allowed — allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
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


def get_download_url(department: str, fiscal_year: int, item_id: str, *, settings: Settings | None = None) -> str:
    """Returns a pre-authenticated, time-limited Graph download URL
    (`@microsoft.graph.downloadUrl`) for one item — the frontend opens it
    directly, no file bytes stream through this backend."""
    settings = settings or get_settings()
    _require_configured(settings)
    token = _get_graph_token(settings)
    _site_id, drive_id = _resolve_site_and_drive(token, settings)

    resp = httpx.get(
        f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if resp.status_code == 404:
        raise FolderNotFoundError(f"attachment {item_id!r} not found for ฝ่าย {department!r}, year {fiscal_year}")
    if resp.status_code != 200:
        raise AttachmentTransportError(f"Graph item lookup failed: {resp.status_code} {resp.text}")

    url = resp.json().get("@microsoft.graph.downloadUrl")
    if not url:
        raise AttachmentTransportError(f"Graph item {item_id!r} has no download URL")
    return url
