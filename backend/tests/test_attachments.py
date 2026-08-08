"""Unit tests for app.attachments — A10 SharePoint attachments (spec R1). No
real network ever: every Graph call goes through `httpx.get/put/post`,
monkeypatched at the module level (same convention as test_notifications.py)
— this file NEVER hits a real SharePoint site."""
from unittest.mock import MagicMock

import pytest

from app.attachments import (
    ALLOWED_EXTENSIONS,
    MAX_ATTACHMENT_BYTES,
    AttachmentsNotConfiguredError,
    AttachmentTransportError,
    DisallowedFileTypeError,
    FileTooLargeError,
    FolderNotFoundError,
    get_download_url,
    list_attachments,
    sanitize_attachment_filename,
    sanitize_department_folder,
    too_large_message,
    upload_attachment,
    validate_upload,
)
from app.config import Settings

TOKEN_JSON = {"access_token": "tok-123"}
SITE_JSON = {"id": "site-1"}
DRIVES_JSON = {"value": [{"id": "drive-1", "name": "Budgeting and Management"}]}


def _settings(**overrides) -> Settings:
    defaults = dict(
        _env_file=None,
        entra_tenant_id="tenant-1",
        entra_client_id="client-1",
        entra_client_secret="secret-1",
        attachments_site_hostname="chememan.sharepoint.com",
        attachments_site_name="CMANDWPRD",
        attachments_library_name="Budgeting and Management",
        attachments_root_folder="เอกสาร ฝ่าย",
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _resp(status_code: int, json_body: dict | None = None, text: str = ""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body or {}
    resp.text = text
    return resp


# ---------------------------------------------------------------------------
# sanitize_department_folder
# ---------------------------------------------------------------------------

def test_sanitize_replaces_illegal_chars_with_dash():
    assert sanitize_department_folder("Global Demand/supply Planning") == "Global Demand-supply Planning"


def test_sanitize_replaces_every_illegal_character():
    assert sanitize_department_folder('a\\b/c:d*e?f"g<h>i|j') == "a-b-c-d-e-f-g-h-i-j"


def test_sanitize_keeps_thai_and_ordinary_characters_unchanged():
    assert sanitize_department_folder("บัญชี การเงิน 2027") == "บัญชี การเงิน 2027"


# ---------------------------------------------------------------------------
# validate_upload
# ---------------------------------------------------------------------------

def test_validate_upload_accepts_every_allowed_extension():
    for ext in ALLOWED_EXTENSIONS:
        validate_upload(f"report.{ext}", 100)  # must not raise


def test_validate_upload_rejects_disallowed_extension():
    with pytest.raises(DisallowedFileTypeError):
        validate_upload("malware.exe", 100)


def test_validate_upload_rejects_file_over_the_size_cap():
    with pytest.raises(FileTooLargeError):
        validate_upload("big.pdf", MAX_ATTACHMENT_BYTES + 1)


def test_validate_upload_over_cap_message_is_thai_with_correct_sizes():
    """Bug 4 (2026-08-07/08 production defect): the old message was English
    ('bytes -- exceeds ... byte attachment limit') and unreadable (a
    ten-digit byte count). Real over-limit size, both numbers in MB."""
    actual_bytes = int(12.3 * 1024 * 1024)  # rounds to exactly "12.3 MB"
    with pytest.raises(FileTooLargeError) as exc_info:
        validate_upload("big.pdf", actual_bytes)
    assert str(exc_info.value) == "ไฟล์ใหญ่เกินกำหนด (12.3 MB) — อัปโหลดได้ไม่เกิน 10 MB"


def test_validate_upload_accepts_file_exactly_at_the_cap():
    validate_upload("exact.pdf", MAX_ATTACHMENT_BYTES)  # must not raise, boundary is inclusive


# ---------------------------------------------------------------------------
# too_large_message — shared Thai copy for BOTH size checks on the upload
# path (this module's byte-accurate backstop and the router's fast
# Content-Length pre-check), so the two can never disagree in wording.
# ---------------------------------------------------------------------------

def test_too_large_message_uses_one_decimal_for_the_actual_size():
    actual_bytes = int(12.3 * 1024 * 1024)
    assert too_large_message(actual_bytes) == "ไฟล์ใหญ่เกินกำหนด (12.3 MB) — อัปโหลดได้ไม่เกิน 10 MB"


def test_too_large_message_renders_a_round_limit_without_a_trailing_decimal():
    # MAX_ATTACHMENT_BYTES (10 * 1024*1024) is a round number in MB -- must
    # read "10 MB", not "10.0 MB".
    assert "10 MB" in too_large_message(MAX_ATTACHMENT_BYTES + 1)
    assert "10.0 MB" not in too_large_message(MAX_ATTACHMENT_BYTES + 1)


def test_too_large_message_mb_base_matches_how_the_limit_is_defined():
    # MAX_ATTACHMENT_BYTES is defined as 10 * 1024 * 1024 -- the printed
    # limit must equal that exactly, which only holds for a MiB-style
    # (1024*1024) conversion, not a decimal (1000*1000) one.
    assert MAX_ATTACHMENT_BYTES == 10 * 1024 * 1024
    assert "10 MB" in too_large_message(MAX_ATTACHMENT_BYTES + 1)


# ---------------------------------------------------------------------------
# sanitize_attachment_filename (security fix — filename smuggled into the
# Graph URL path, which uses ':' as its own delimiter)
# ---------------------------------------------------------------------------

def test_sanitize_filename_replaces_colon_like_other_illegal_chars():
    assert sanitize_attachment_filename("evil:x.pdf") == "evil-x.pdf"


def test_sanitize_filename_defangs_backslash_traversal_sequences():
    result = sanitize_attachment_filename("..\\..\\x.pdf")
    assert "\\" not in result
    assert not result.startswith(".")


def test_sanitize_filename_rejects_reserved_device_name_case_insensitive():
    with pytest.raises(DisallowedFileTypeError):
        sanitize_attachment_filename("CON.pdf")
    with pytest.raises(DisallowedFileTypeError):
        sanitize_attachment_filename("con.PDF")


def test_sanitize_filename_strips_surrounding_dots_and_spaces():
    assert sanitize_attachment_filename("  ..report.pdf  ") == "report.pdf"


def test_sanitize_filename_rejects_empty_after_sanitizing():
    with pytest.raises(DisallowedFileTypeError):
        sanitize_attachment_filename("....")


def test_validate_upload_sanitizes_before_checking_the_extension():
    # ':' is stripped first, so the extension check sees 'evil-x.pdf', not
    # a name that would otherwise still look malformed.
    assert validate_upload("evil:x.pdf", 100) == "evil-x.pdf"


# ---------------------------------------------------------------------------
# not-configured guard
# ---------------------------------------------------------------------------

def test_list_attachments_raises_not_configured_when_site_hostname_blank(monkeypatch):
    calls = []
    monkeypatch.setattr("app.attachments.httpx.get", lambda *a, **k: calls.append((a, k)))
    monkeypatch.setattr("app.attachments.httpx.post", lambda *a, **k: calls.append((a, k)))

    with pytest.raises(AttachmentsNotConfiguredError):
        list_attachments("Accounting", 2027, settings=_settings(attachments_site_hostname=""))

    assert calls == []  # zero HTTP calls — fails before any Graph call


# ---------------------------------------------------------------------------
# list_attachments
# ---------------------------------------------------------------------------

def _install_happy_transport(monkeypatch, children_json: dict):
    def _fake_post(url, **kwargs):
        assert "oauth2" in url
        return _resp(200, TOKEN_JSON)

    def _fake_get(url, **kwargs):
        if "/sites/" in url and "/drives" not in url:
            return _resp(200, SITE_JSON)
        if url.endswith("/drives"):
            return _resp(200, DRIVES_JSON)
        return _resp(200, children_json)

    monkeypatch.setattr("app.attachments.httpx.post", _fake_post)
    monkeypatch.setattr("app.attachments.httpx.get", _fake_get)


def test_list_attachments_returns_items_from_the_folder(monkeypatch):
    children = {
        "value": [
            {
                "id": "item-1", "name": "budget.pdf", "size": 1234,
                "createdBy": {"user": {"displayName": "Somchai"}},
                "createdDateTime": "2027-01-01T00:00:00Z", "webUrl": "https://x/budget.pdf",
            }
        ]
    }
    _install_happy_transport(monkeypatch, children)

    items = list_attachments("Accounting", 2027, settings=_settings())

    assert len(items) == 1
    assert items[0].name == "budget.pdf"
    assert items[0].created_by == "Somchai"
    assert items[0].size == 1234


def test_list_attachments_uses_the_sanitized_folder_path(monkeypatch):
    captured_paths = []

    def _fake_post(url, **kwargs):
        return _resp(200, TOKEN_JSON)

    def _fake_get(url, **kwargs):
        if "/drives" not in url and "/sites/" in url:
            return _resp(200, SITE_JSON)
        if url.endswith("/drives"):
            return _resp(200, DRIVES_JSON)
        captured_paths.append(url)
        return _resp(200, {"value": []})

    monkeypatch.setattr("app.attachments.httpx.post", _fake_post)
    monkeypatch.setattr("app.attachments.httpx.get", _fake_get)

    list_attachments("Global Demand/supply Planning", 2027, settings=_settings())

    assert len(captured_paths) == 1
    assert "เอกสาร ฝ่าย/Global Demand-supply Planning/2027" in captured_paths[0]


def test_list_attachments_folder_missing_raises_folder_not_found(monkeypatch):
    def _fake_post(url, **kwargs):
        return _resp(200, TOKEN_JSON)

    def _fake_get(url, **kwargs):
        if "/drives" not in url and "/sites/" in url:
            return _resp(200, SITE_JSON)
        if url.endswith("/drives"):
            return _resp(200, DRIVES_JSON)
        return _resp(404, {}, text="not found")

    monkeypatch.setattr("app.attachments.httpx.post", _fake_post)
    monkeypatch.setattr("app.attachments.httpx.get", _fake_get)

    with pytest.raises(FolderNotFoundError):
        list_attachments("Orphan Dept", 2027, settings=_settings())


def test_list_attachments_site_lookup_failure_raises_transport_error(monkeypatch):
    monkeypatch.setattr("app.attachments.httpx.post", lambda url, **k: _resp(200, TOKEN_JSON))
    monkeypatch.setattr("app.attachments.httpx.get", lambda url, **k: _resp(500, {}, text="boom"))

    with pytest.raises(AttachmentTransportError):
        list_attachments("Accounting", 2027, settings=_settings())


def test_list_attachments_no_matching_library_raises_transport_error(monkeypatch):
    def _fake_get(url, **kwargs):
        if "/drives" not in url and "/sites/" in url:
            return _resp(200, SITE_JSON)
        if url.endswith("/drives"):
            return _resp(200, {"value": [{"id": "drive-x", "name": "Some Other Library"}]})
        return _resp(200, {"value": []})

    monkeypatch.setattr("app.attachments.httpx.post", lambda url, **k: _resp(200, TOKEN_JSON))
    monkeypatch.setattr("app.attachments.httpx.get", _fake_get)

    with pytest.raises(AttachmentTransportError, match="Budgeting and Management"):
        list_attachments("Accounting", 2027, settings=_settings())


# ---------------------------------------------------------------------------
# upload_attachment
# ---------------------------------------------------------------------------

def test_upload_attachment_rejects_disallowed_extension_before_any_http_call(monkeypatch):
    calls = []
    monkeypatch.setattr("app.attachments.httpx.get", lambda *a, **k: calls.append(a))
    monkeypatch.setattr("app.attachments.httpx.post", lambda *a, **k: calls.append(a))
    monkeypatch.setattr("app.attachments.httpx.put", lambda *a, **k: calls.append(a))

    with pytest.raises(DisallowedFileTypeError):
        upload_attachment("Accounting", 2027, "malware.exe", b"x", settings=_settings())

    assert calls == []


def test_upload_attachment_puts_content_to_the_expected_path(monkeypatch):
    put_calls = []

    def _fake_put(url, **kwargs):
        put_calls.append((url, kwargs))
        return _resp(201, {
            "id": "item-9", "name": "report.pdf", "size": 3,
            "createdBy": {"user": {"displayName": "Somchai"}},
            "createdDateTime": "2027-01-01T00:00:00Z", "webUrl": "https://x/report.pdf",
        })

    def _fake_get(url, **kwargs):
        if "/drives" not in url and "/sites/" in url:
            return _resp(200, SITE_JSON)
        return _resp(200, DRIVES_JSON)

    monkeypatch.setattr("app.attachments.httpx.post", lambda url, **k: _resp(200, TOKEN_JSON))
    monkeypatch.setattr("app.attachments.httpx.get", _fake_get)
    monkeypatch.setattr("app.attachments.httpx.put", _fake_put)

    info = upload_attachment("Accounting", 2027, "report.pdf", b"abc", settings=_settings())

    assert info.item_id == "item-9"
    assert len(put_calls) == 1
    url, kwargs = put_calls[0]
    assert "เอกสาร ฝ่าย/Accounting/2027/report.pdf" in url
    assert kwargs["content"] == b"abc"


def test_upload_attachment_folder_missing_raises_folder_not_found(monkeypatch):
    def _fake_get(url, **kwargs):
        if "/drives" not in url and "/sites/" in url:
            return _resp(200, SITE_JSON)
        return _resp(200, DRIVES_JSON)

    monkeypatch.setattr("app.attachments.httpx.post", lambda url, **k: _resp(200, TOKEN_JSON))
    monkeypatch.setattr("app.attachments.httpx.get", _fake_get)
    monkeypatch.setattr("app.attachments.httpx.put", lambda url, **k: _resp(404, {}, text="not found"))

    with pytest.raises(FolderNotFoundError):
        upload_attachment("Orphan Dept", 2027, "report.pdf", b"abc", settings=_settings())


def test_upload_attachment_never_puts_a_raw_colon_in_the_filename_segment(monkeypatch):
    """A filename containing ':' (Graph's own path delimiter) must never
    reach the Graph URL unsanitized/unescaped -- otherwise it would corrupt
    the request path (`root:/<path>/<filename>:/content`)."""
    put_calls = []

    def _fake_put(url, **kwargs):
        put_calls.append(url)
        return _resp(201, {
            "id": "item-9", "name": "evil-x.pdf", "size": 1,
            "createdBy": {"user": {"displayName": "Somchai"}},
            "createdDateTime": "2027-01-01T00:00:00Z", "webUrl": "https://x/evil-x.pdf",
        })

    def _fake_get(url, **kwargs):
        if "/drives" not in url and "/sites/" in url:
            return _resp(200, SITE_JSON)
        return _resp(200, DRIVES_JSON)

    monkeypatch.setattr("app.attachments.httpx.post", lambda url, **k: _resp(200, TOKEN_JSON))
    monkeypatch.setattr("app.attachments.httpx.get", _fake_get)
    monkeypatch.setattr("app.attachments.httpx.put", _fake_put)

    upload_attachment("Accounting", 2027, "evil:x.pdf", b"x", settings=_settings())

    assert len(put_calls) == 1
    url = put_calls[0]
    assert url.endswith(":/content")
    filename_segment = url[: -len(":/content")].rsplit("/", 1)[-1]
    assert ":" not in filename_segment
    assert filename_segment == "evil-x.pdf"


# ---------------------------------------------------------------------------
# get_download_url
# ---------------------------------------------------------------------------

def test_get_download_url_returns_the_graph_download_url(monkeypatch):
    def _fake_get(url, **kwargs):
        if "/drives" not in url and "/sites/" in url:
            return _resp(200, SITE_JSON)
        if url.endswith("/drives"):
            return _resp(200, DRIVES_JSON)
        return _resp(200, {"@microsoft.graph.downloadUrl": "https://download.example/x"})

    monkeypatch.setattr("app.attachments.httpx.post", lambda url, **k: _resp(200, TOKEN_JSON))
    monkeypatch.setattr("app.attachments.httpx.get", _fake_get)

    url = get_download_url("Accounting", 2027, "item-1", settings=_settings())

    assert url == "https://download.example/x"


def test_get_download_url_missing_item_raises_folder_not_found(monkeypatch):
    def _fake_get(url, **kwargs):
        if "/drives" not in url and "/sites/" in url:
            return _resp(200, SITE_JSON)
        if url.endswith("/drives"):
            return _resp(200, DRIVES_JSON)
        return _resp(404, {}, text="not found")

    monkeypatch.setattr("app.attachments.httpx.post", lambda url, **k: _resp(200, TOKEN_JSON))
    monkeypatch.setattr("app.attachments.httpx.get", _fake_get)

    with pytest.raises(FolderNotFoundError):
        get_download_url("Accounting", 2027, "missing-item", settings=_settings())


def test_get_download_url_missing_url_field_raises_transport_error(monkeypatch):
    def _fake_get(url, **kwargs):
        if "/drives" not in url and "/sites/" in url:
            return _resp(200, SITE_JSON)
        if url.endswith("/drives"):
            return _resp(200, DRIVES_JSON)
        return _resp(200, {"id": "item-1"})  # no downloadUrl field

    monkeypatch.setattr("app.attachments.httpx.post", lambda url, **k: _resp(200, TOKEN_JSON))
    monkeypatch.setattr("app.attachments.httpx.get", _fake_get)

    with pytest.raises(AttachmentTransportError):
        get_download_url("Accounting", 2027, "item-1", settings=_settings())
