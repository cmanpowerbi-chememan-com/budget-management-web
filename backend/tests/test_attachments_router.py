"""Unit tests for the A10 attachments endpoints — GET /attachments,
POST /attachments/upload, GET /attachments/download-url. DB (scope
resolution) and the SharePoint transport (`app.attachments`) are both
mocked — no real Graph/SharePoint call, no live DB.
"""
from unittest.mock import MagicMock, patch

from app.attachments import (
    MAX_ATTACHMENT_BYTES,
    AttachmentInfo,
    AttachmentNotInFolderError,
    disallowed_type_message,
    DisallowedFileTypeError,
    FolderNotFoundError,
)
from app.auth import get_current_user_email
from app.main import app
from app.rls import Scope

DEPT = "Accounting"
FY = 2027


def _override_auth(email: str) -> None:
    app.dependency_overrides[get_current_user_email] = lambda: email


def _scope(**overrides) -> Scope:
    defaults = dict(email="filler@chememan.com", is_admin=False, role="filler",
                     fill_cost_centers=["CC1"], see_cost_centers=["CC1"])
    defaults.update(overrides)
    return Scope(**defaults)


def _admin_scope() -> Scope:
    return Scope(email="admin@chememan.com", is_admin=True, role="admin", fill_cost_centers=[], see_cost_centers=[])


def _fake_info() -> AttachmentInfo:
    return AttachmentInfo(
        item_id="item-1", name="budget.pdf", size=100,
        created_by="Somchai", created_at="2027-01-01T00:00:00Z", web_url="https://x/budget.pdf",
    )


# ---------------------------------------------------------------------------
# GET /attachments
# ---------------------------------------------------------------------------

def test_list_401_without_auth(client):
    response = client.get("/attachments", params={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 401


def test_list_success_for_a_department_in_see_scope(client):
    _override_auth("filler@chememan.com")
    with patch("app.routers.attachments.get_fabric_conn") as mock_conn, patch(
        "app.routers.attachments.resolve_scope", return_value=_scope()
    ), patch("app.routers.attachments._department_cost_centers", return_value={"CC1"}), patch(
        "app.routers.attachments.list_attachments", return_value=[_fake_info()]
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/attachments", params={"department": DEPT, "fiscal_year": FY})

    assert response.status_code == 200
    assert response.json() == [
        {"item_id": "item-1", "name": "budget.pdf", "size": 100,
         "created_by": "Somchai", "created_at": "2027-01-01T00:00:00Z", "web_url": "https://x/budget.pdf"}
    ]


def test_list_forbidden_when_department_outside_see_scope(client):
    _override_auth("outsider@chememan.com")
    with patch("app.routers.attachments.get_fabric_conn") as mock_conn, patch(
        "app.routers.attachments.resolve_scope", return_value=_scope(fill_cost_centers=[], see_cost_centers=["CCother"])
    ), patch("app.routers.attachments._department_cost_centers", return_value={"CC1"}):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/attachments", params={"department": DEPT, "fiscal_year": FY})

    assert response.status_code == 403


def test_list_admin_bypasses_scope_check(client):
    _override_auth("admin@chememan.com")
    with patch("app.routers.attachments.get_fabric_conn") as mock_conn, patch(
        "app.routers.attachments.resolve_scope", return_value=_admin_scope()
    ), patch("app.routers.attachments._department_cost_centers", return_value={"CC1"}), patch(
        "app.routers.attachments.list_attachments", return_value=[]
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/attachments", params={"department": DEPT, "fiscal_year": FY})

    assert response.status_code == 200
    assert response.json() == []


def test_list_admin_unknown_department_returns_404_instead_of_reaching_graph(client):
    """Blocker suggestion 1: an admin passing an unknown department must get
    a friendly 404, not sail through to Graph and get a confusing error."""
    _override_auth("admin@chememan.com")
    with patch("app.routers.attachments.get_fabric_conn") as mock_conn, patch(
        "app.routers.attachments.resolve_scope", return_value=_admin_scope()
    ), patch("app.routers.attachments._department_cost_centers", return_value=set()), patch(
        "app.routers.attachments.list_attachments"
    ) as mock_list:
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/attachments", params={"department": "No Such Dept", "fiscal_year": FY})

    assert response.status_code == 404
    mock_list.assert_not_called()


def test_list_folder_not_found_maps_to_502(client):
    _override_auth("filler@chememan.com")
    with patch("app.routers.attachments.get_fabric_conn") as mock_conn, patch(
        "app.routers.attachments.resolve_scope", return_value=_scope()
    ), patch("app.routers.attachments._department_cost_centers", return_value={"CC1"}), patch(
        "app.routers.attachments.list_attachments",
        side_effect=FolderNotFoundError("the folder does not exist yet"),
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/attachments", params={"department": DEPT, "fiscal_year": FY})

    assert response.status_code == 502


def test_list_db_failure_maps_to_502(client):
    import pyodbc

    _override_auth("filler@chememan.com")
    with patch("app.routers.attachments.get_fabric_conn") as mock_conn, patch(
        "app.routers.attachments.resolve_scope", side_effect=pyodbc.Error("connection lost")
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/attachments", params={"department": DEPT, "fiscal_year": FY})

    assert response.status_code == 502


# ---------------------------------------------------------------------------
# POST /attachments/upload
# ---------------------------------------------------------------------------

def test_upload_401_without_auth(client):
    response = client.post(
        "/attachments/upload",
        data={"department": DEPT, "fiscal_year": FY},
        files={"file": ("report.pdf", b"abc", "application/pdf")},
    )
    assert response.status_code == 401


def test_upload_success_when_caller_fills_the_department(client):
    _override_auth("filler@chememan.com")
    with patch("app.routers.attachments.get_fabric_conn") as mock_conn, patch(
        "app.routers.attachments.resolve_scope", return_value=_scope()
    ), patch("app.routers.attachments._department_cost_centers", return_value={"CC1"}), patch(
        "app.routers.attachments.upload_attachment", return_value=_fake_info()
    ) as mock_upload:
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post(
            "/attachments/upload",
            data={"department": DEPT, "fiscal_year": FY},
            files={"file": ("report.pdf", b"abc", "application/pdf")},
        )

    assert response.status_code == 200
    assert response.json()["item_id"] == "item-1"
    assert mock_upload.call_args.args[2] == "report.pdf"
    assert mock_upload.call_args.args[3] == b"abc"


def test_upload_forbidden_when_caller_only_sees_but_does_not_fill(client):
    """See-only must not be allowed to upload -- upload needs Fill scope."""
    _override_auth("see-only@chememan.com")
    with patch("app.routers.attachments.get_fabric_conn") as mock_conn, patch(
        "app.routers.attachments.resolve_scope",
        return_value=_scope(fill_cost_centers=[], see_cost_centers=["CC1"], role="see_only"),
    ), patch("app.routers.attachments._department_cost_centers", return_value={"CC1"}):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post(
            "/attachments/upload",
            data={"department": DEPT, "fiscal_year": FY},
            files={"file": ("report.pdf", b"abc", "application/pdf")},
        )

    assert response.status_code == 403


def test_upload_disallowed_file_type_maps_to_400(client):
    from app.attachments import DisallowedFileTypeError

    _override_auth("filler@chememan.com")
    with patch("app.routers.attachments.get_fabric_conn") as mock_conn, patch(
        "app.routers.attachments.resolve_scope", return_value=_scope()
    ), patch("app.routers.attachments._department_cost_centers", return_value={"CC1"}), patch(
        "app.routers.attachments.upload_attachment",
        side_effect=DisallowedFileTypeError("file type '.exe' is not allowed"),
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post(
            "/attachments/upload",
            data={"department": DEPT, "fiscal_year": FY},
            files={"file": ("malware.exe", b"abc", "application/octet-stream")},
        )

    assert response.status_code == 400


def test_upload_over_size_cap_rejected_via_content_length_before_reading_body(client):
    """Blocker suggestion 2: the declared Content-Length is checked BEFORE
    `file.file.read()` -- an over-limit upload never reaches scope
    resolution or the SharePoint transport."""
    _override_auth("filler@chememan.com")
    oversized_content = b"x" * (MAX_ATTACHMENT_BYTES + 1)
    with patch("app.routers.attachments.get_fabric_conn") as mock_conn, patch(
        "app.routers.attachments.upload_attachment"
    ) as mock_upload:
        response = client.post(
            "/attachments/upload",
            data={"department": DEPT, "fiscal_year": FY},
            files={"file": ("big.pdf", oversized_content, "application/pdf")},
        )

    assert response.status_code == 413
    mock_conn.assert_not_called()
    mock_upload.assert_not_called()


def test_upload_over_size_cap_413_detail_is_thai_with_correct_mb_sizes(client):
    """Bug 4: the 413 detail must be the agreed Thai sentence with the real
    declared size and the configured limit, both in MB -- never the old
    English 'bytes -- exceeds ... byte attachment limit' wording."""
    _override_auth("filler@chememan.com")
    declared_size = MAX_ATTACHMENT_BYTES + int(0.3 * 1024 * 1024)  # ~10.3 MB
    oversized_content = b"x" * declared_size
    with patch("app.routers.attachments.get_fabric_conn"), patch("app.routers.attachments.upload_attachment"):
        response = client.post(
            "/attachments/upload",
            data={"department": DEPT, "fiscal_year": FY},
            files={"file": ("big.pdf", oversized_content, "application/pdf")},
        )

    assert response.status_code == 413
    detail = response.json()["detail"]
    assert detail == "ไฟล์ใหญ่เกินกำหนด (10.3 MB) — อัปโหลดได้ไม่เกิน 10 MB"
    assert "bytes" not in detail
    assert "exceeds" not in detail


def test_upload_not_configured_maps_to_501(client):
    from app.attachments import AttachmentsNotConfiguredError

    _override_auth("filler@chememan.com")
    with patch("app.routers.attachments.get_fabric_conn") as mock_conn, patch(
        "app.routers.attachments.resolve_scope", return_value=_scope()
    ), patch("app.routers.attachments._department_cost_centers", return_value={"CC1"}), patch(
        "app.routers.attachments.upload_attachment",
        side_effect=AttachmentsNotConfiguredError("attachments storage is not configured"),
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post(
            "/attachments/upload",
            data={"department": DEPT, "fiscal_year": FY},
            files={"file": ("report.pdf", b"abc", "application/pdf")},
        )

    assert response.status_code == 501


# ---------------------------------------------------------------------------
# GET /attachments/download-url
# ---------------------------------------------------------------------------

def test_download_url_401_without_auth(client):
    response = client.get(
        "/attachments/download-url", params={"department": DEPT, "fiscal_year": FY, "item_id": "item-1"}
    )
    assert response.status_code == 401


def test_download_url_success(client):
    _override_auth("filler@chememan.com")
    with patch("app.routers.attachments.get_fabric_conn") as mock_conn, patch(
        "app.routers.attachments.resolve_scope", return_value=_scope()
    ), patch("app.routers.attachments._department_cost_centers", return_value={"CC1"}), patch(
        "app.routers.attachments.get_download_url", return_value="https://download.example/x"
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get(
            "/attachments/download-url", params={"department": DEPT, "fiscal_year": FY, "item_id": "item-1"}
        )

    assert response.status_code == 200
    assert response.json() == {"url": "https://download.example/x"}


def test_download_url_forbidden_outside_scope(client):
    _override_auth("outsider@chememan.com")
    with patch("app.routers.attachments.get_fabric_conn") as mock_conn, patch(
        "app.routers.attachments.resolve_scope", return_value=_scope(fill_cost_centers=[], see_cost_centers=["CCother"])
    ), patch("app.routers.attachments._department_cost_centers", return_value={"CC1"}):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get(
            "/attachments/download-url", params={"department": DEPT, "fiscal_year": FY, "item_id": "item-1"}
        )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /attachments (2026-08-10) — gated on Fill-or-admin, same as upload
# ---------------------------------------------------------------------------

def test_delete_401_without_auth(client):
    response = client.delete("/attachments", params={"department": DEPT, "fiscal_year": FY, "item_id": "item-1"})
    assert response.status_code == 401


def test_delete_success_for_a_filler_of_the_department(client):
    _override_auth("filler@chememan.com")
    with patch("app.routers.attachments.get_fabric_conn") as mock_conn, patch(
        "app.routers.attachments.resolve_scope", return_value=_scope()
    ), patch("app.routers.attachments._department_cost_centers", return_value={"CC1"}), patch(
        "app.routers.attachments.delete_attachment", return_value="budget.pdf"
    ) as mock_delete:
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.delete("/attachments", params={"department": DEPT, "fiscal_year": FY, "item_id": "item-1"})

    assert response.status_code == 200
    assert response.json() == {"deleted": True, "name": "budget.pdf"}
    mock_delete.assert_called_once_with(DEPT, FY, "item-1")


def test_delete_forbidden_for_a_see_only_caller(client):
    """A manager or approver who can READ the department's documents must not
    be able to delete them — delete uses the Fill gate, like upload, not the
    broader See gate that list/download use."""
    _override_auth("manager@chememan.com")
    with patch("app.routers.attachments.get_fabric_conn") as mock_conn, patch(
        "app.routers.attachments.resolve_scope",
        return_value=_scope(fill_cost_centers=[], see_cost_centers=["CC1"]),
    ), patch("app.routers.attachments._department_cost_centers", return_value={"CC1"}), patch(
        "app.routers.attachments.delete_attachment"
    ) as mock_delete:
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.delete("/attachments", params={"department": DEPT, "fiscal_year": FY, "item_id": "item-1"})

    assert response.status_code == 403
    mock_delete.assert_not_called()


def test_delete_admin_bypasses_scope_check(client):
    _override_auth("admin@chememan.com")
    with patch("app.routers.attachments.get_fabric_conn") as mock_conn, patch(
        "app.routers.attachments.resolve_scope", return_value=_admin_scope()
    ), patch("app.routers.attachments._department_cost_centers", return_value={"CC1"}), patch(
        "app.routers.attachments.delete_attachment", return_value="budget.pdf"
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.delete("/attachments", params={"department": DEPT, "fiscal_year": FY, "item_id": "item-1"})

    assert response.status_code == 200


def test_delete_unknown_department_is_404(client):
    _override_auth("filler@chememan.com")
    with patch("app.routers.attachments.get_fabric_conn") as mock_conn, patch(
        "app.routers.attachments.resolve_scope", return_value=_scope()
    ), patch("app.routers.attachments._department_cost_centers", return_value=set()), patch(
        "app.routers.attachments.delete_attachment"
    ) as mock_delete:
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.delete("/attachments", params={"department": "Nope", "fiscal_year": FY, "item_id": "item-1"})

    assert response.status_code == 404
    mock_delete.assert_not_called()


def test_delete_item_from_another_folder_maps_to_404_with_thai_detail(client):
    """`AttachmentNotInFolderError` -> 404 (not 403): the caller IS authorized
    for this department, the id simply is not one of its files, and a 403 would
    confirm the id exists elsewhere in the library."""
    _override_auth("filler@chememan.com")
    with patch("app.routers.attachments.get_fabric_conn") as mock_conn, patch(
        "app.routers.attachments.resolve_scope", return_value=_scope()
    ), patch("app.routers.attachments._department_cost_centers", return_value={"CC1"}), patch(
        "app.routers.attachments.delete_attachment",
        side_effect=AttachmentNotInFolderError("ไม่พบไฟล์นี้ในเอกสารของฝ่าย Accounting ปี 2027"),
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.delete("/attachments", params={"department": DEPT, "fiscal_year": FY, "item_id": "elsewhere"})

    assert response.status_code == 404
    assert response.json()["detail"] == "ไม่พบไฟล์นี้ในเอกสารของฝ่าย Accounting ปี 2027"


def test_upload_disallowed_type_detail_is_thai(client):
    """The message a filler hits most often must be Thai (2026-08-10)."""
    _override_auth("filler@chememan.com")
    with patch("app.routers.attachments.get_fabric_conn") as mock_conn, patch(
        "app.routers.attachments.resolve_scope", return_value=_scope()
    ), patch("app.routers.attachments._department_cost_centers", return_value={"CC1"}), patch(
        "app.routers.attachments.upload_attachment",
        side_effect=DisallowedFileTypeError(disallowed_type_message("txt")),
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/attachments/upload", data={"department": DEPT, "fiscal_year": str(FY)},
                               files={"file": ("note.txt", b"x", "text/plain")})

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail.startswith("ไฟล์ชนิด .txt อัปโหลดไม่ได้")
    assert "not allowed" not in detail
