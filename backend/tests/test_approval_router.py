"""Unit tests for the A6 approval endpoints — POST /approval/submit|approve|
reject, GET /approval/status. DB always mocked; the state machine itself is
unit-tested in test_approval.py — these tests only prove the router wiring:
auth, error-code -> HTTP-status mapping, and the 502 DB-unavailable path.
"""
from unittest.mock import MagicMock, patch

from app.approval import (
    APPROVED,
    PENDING_APPROVER1,
    PENDING_APPROVER2,
    ApprovalRecordNotFoundError,
    ApprovalStatusState,
    DepartmentEmptyError,
    InvalidApprovalStateError,
    MidChainAdminOverwriteError,
    NotAuthorizedToViewDepartmentError,
    NotCurrentApproverError,
    NotFillerOfDepartmentError,
    StepNotOverridableError,
)
from app.auth import get_current_user_email
from app.main import app

DEPT = "Accounting"
FY = 2027


def _override_auth(email: str) -> None:
    app.dependency_overrides[get_current_user_email] = lambda: email


def _fake_state(**overrides) -> ApprovalStatusState:
    defaults = dict(department=DEPT, fiscal_year=FY, status=PENDING_APPROVER1)
    defaults.update(overrides)
    return ApprovalStatusState(**defaults)


def test_submit_401_without_auth(client):
    response = client.post("/approval/submit", json={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 401


def test_submit_success_returns_200(client):
    _override_auth("filler@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock()
    ), patch("app.routers.approval.submit_department", return_value=_fake_state()):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/submit", json={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 200
    assert response.json()["status"] == PENDING_APPROVER1


def test_submit_forbidden_maps_to_403(client):
    _override_auth("outsider@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock()
    ), patch(
        "app.routers.approval.submit_department",
        side_effect=NotFillerOfDepartmentError("outsider@chememan.com does not Fill any cost center of 'Accounting'"),
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/submit", json={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 403


def test_submit_department_empty_maps_to_400(client):
    """Bug 3 (2026-08-07 wave): `DepartmentEmptyError` -> 400 with the
    server's own Thai detail, the same `_run` dict-based mapping idiom every
    other approval error already uses."""
    _override_auth("filler@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock()
    ), patch(
        "app.routers.approval.submit_department",
        side_effect=DepartmentEmptyError("ฝ่ายนี้ยังไม่มีข้อมูลงบประมาณ จึงส่งอนุมัติไม่ได้"),
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/submit", json={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 400
    assert response.json()["detail"] == "ฝ่ายนี้ยังไม่มีข้อมูลงบประมาณ จึงส่งอนุมัติไม่ได้"


def test_submit_invalid_state_maps_to_409(client):
    _override_auth("filler@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock()
    ), patch(
        "app.routers.approval.submit_department",
        side_effect=InvalidApprovalStateError("Accounting/2027 is PENDING_APPROVER2 -- cannot submit"),
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/submit", json={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 409


def test_submit_db_failure_maps_to_502(client):
    import pyodbc

    _override_auth("filler@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", side_effect=pyodbc.Error("connection lost")
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/submit", json={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 502


def test_approve_success_returns_200(client):
    _override_auth("manager@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.approve_department", return_value=_fake_state(status=APPROVED)
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/approve", json={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 200
    assert response.json()["status"] == APPROVED


def test_approve_not_current_approver_maps_to_403(client):
    _override_auth("someone-else@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.approve_department",
        side_effect=NotCurrentApproverError("not the current approver"),
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/approve", json={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 403


def test_approve_no_record_maps_to_404(client):
    _override_auth("manager@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.approve_department",
        side_effect=ApprovalRecordNotFoundError("no approval record"),
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/approve", json={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 404


def test_reject_success_returns_200(client):
    _override_auth("manager@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.reject_department", return_value=_fake_state(status="REJECTED", reject_reason="bad")
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post(
            "/approval/reject", json={"department": DEPT, "fiscal_year": FY, "reason": "bad numbers"}
        )
    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"


def test_reject_requires_reason_field_422(client):
    _override_auth("manager@chememan.com")
    response = client.post("/approval/reject", json={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 422


def test_status_returns_draft_when_never_submitted(client):
    _override_auth("filler@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock()
    ), patch("app.routers.approval.authorize_status_view"), patch(
        "app.routers.approval.resolve_submitter", return_value=(None, None)
    ), patch(
        "app.routers.approval.get_approval_status",
        return_value=_fake_state(status="DRAFT", current_position=None),
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/approval/status", params={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 200
    assert response.json()["status"] == "DRAFT"


def test_status_401_without_auth(client):
    response = client.get("/approval/status", params={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 401


def test_status_forbidden_maps_to_403(client):
    """B1 gate fix: an out-of-scope (or nonexistent-department) caller must
    get 403 from GET /approval/status, never the raw record."""
    _override_auth("outsider@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock()
    ), patch(
        "app.routers.approval.authorize_status_view",
        side_effect=NotAuthorizedToViewDepartmentError("not authorized to view this department's approval status"),
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/approval/status", params={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 403


def test_submit_success_notifies_the_new_current_approver(client):
    """A12 turn-notify: landing on PENDING_APPROVER1 must trigger
    notify_turn for the resolved current approver."""
    _override_auth("filler@chememan.com")
    state = _fake_state(status=PENDING_APPROVER1, current_position=1, current_approver_empcode="200")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock()
    ), patch("app.routers.approval.submit_department", return_value=state), patch(
        "app.routers.approval.notifications.notify_turn"
    ) as mock_notify:
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/submit", json={"department": DEPT, "fiscal_year": FY})

    assert response.status_code == 200
    assert response.json().get("notification_warning") is None
    mock_notify.assert_called_once()
    assert mock_notify.call_args.kwargs["approver_empcode"] == "200"
    assert mock_notify.call_args.kwargs["department"] == DEPT


def test_submit_notification_failure_never_fails_the_request(client):
    """Never-cut: a notify_turn exception must not roll back or fail the
    already-committed transition -- 200 with a non-fatal warning field."""
    _override_auth("filler@chememan.com")
    state = _fake_state(status=PENDING_APPROVER1, current_position=1, current_approver_empcode="200")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock()
    ), patch("app.routers.approval.submit_department", return_value=state), patch(
        "app.routers.approval.notifications.notify_turn", side_effect=RuntimeError("graph down")
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/submit", json={"department": DEPT, "fiscal_year": FY})

    assert response.status_code == 200
    assert response.json()["notification_warning"] is not None


def test_approve_notifies_next_approver_when_still_pending(client):
    _override_auth("manager@chememan.com")
    state = _fake_state(status=PENDING_APPROVER2, current_position=2, current_approver_empcode="101032")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.approve_department", return_value=state
    ), patch("app.routers.approval.notifications.notify_turn") as mock_notify:
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/approve", json={"department": DEPT, "fiscal_year": FY})

    assert response.status_code == 200
    mock_notify.assert_called_once()
    assert mock_notify.call_args.kwargs["approver_empcode"] == "101032"


def test_approve_final_step_notifies_approved_not_turn(client):
    """current_position is None once status reaches APPROVED -- no approver
    left to notify_turn; the LAST approve fires notify_approved (4th
    notification, submitter confirmation) instead."""
    _override_auth("manager@chememan.com")
    state = _fake_state(
        status=APPROVED, current_position=None, current_approver_empcode=None,
        submitter_email="filler@chememan.com",
    )
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.approve_department", return_value=state
    ), patch("app.routers.approval.notifications.notify_turn") as mock_turn, patch(
        "app.routers.approval.notifications.notify_reject"
    ) as mock_reject, patch(
        "app.routers.approval.notifications.notify_approved"
    ) as mock_approved:
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/approve", json={"department": DEPT, "fiscal_year": FY})

    assert response.status_code == 200
    assert response.json().get("notification_warning") is None
    mock_turn.assert_not_called()
    mock_reject.assert_not_called()
    mock_approved.assert_called_once()
    assert mock_approved.call_args.kwargs["submitter_email"] == "filler@chememan.com"
    assert mock_approved.call_args.kwargs["department"] == DEPT
    assert mock_approved.call_args.kwargs["fiscal_year"] == FY


def test_approve_mid_chain_still_notifies_turn_not_approved(client):
    """Guard against regression: a mid-chain approve (status still
    PENDING_*) must keep firing notify_turn, never notify_approved."""
    _override_auth("manager@chememan.com")
    state = _fake_state(status=PENDING_APPROVER2, current_position=2, current_approver_empcode="101032")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.approve_department", return_value=state
    ), patch("app.routers.approval.notifications.notify_turn") as mock_turn, patch(
        "app.routers.approval.notifications.notify_approved"
    ) as mock_approved:
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/approve", json={"department": DEPT, "fiscal_year": FY})

    assert response.status_code == 200
    mock_turn.assert_called_once()
    mock_approved.assert_not_called()


def test_approve_final_step_notification_failure_never_fails_the_request(client):
    """Never-cut: a notify_approved exception must not roll back or fail the
    already-committed transition -- 200 with a non-fatal warning field."""
    _override_auth("manager@chememan.com")
    state = _fake_state(
        status=APPROVED, current_position=None, current_approver_empcode=None,
        submitter_email="filler@chememan.com",
    )
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.approve_department", return_value=state
    ), patch(
        "app.routers.approval.notifications.notify_approved", side_effect=RuntimeError("graph down")
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/approve", json={"department": DEPT, "fiscal_year": FY})

    assert response.status_code == 200
    assert response.json()["notification_warning"] is not None


def test_reject_notifies_the_last_submitter(client):
    _override_auth("manager@chememan.com")
    state = _fake_state(status="REJECTED", reject_reason="bad numbers", submitter_email="filler@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.reject_department", return_value=state
    ), patch("app.routers.approval.notifications.notify_reject") as mock_notify:
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post(
            "/approval/reject", json={"department": DEPT, "fiscal_year": FY, "reason": "bad numbers"}
        )

    assert response.status_code == 200
    mock_notify.assert_called_once()
    assert mock_notify.call_args.kwargs["submitter_email"] == "filler@chememan.com"
    assert mock_notify.call_args.kwargs["reason"] == "bad numbers"


def test_reject_passes_frozen_approver1_empcode_for_cc(client):
    """2026-07-31 revamp: reject mail cc's the frozen approver1 — the router
    must hand `state.approver1_empcode` to notify_reject (any layer)."""
    _override_auth("manager@chememan.com")
    state = _fake_state(
        status="REJECTED", reject_reason="bad numbers",
        submitter_email="filler@chememan.com", approver1_empcode="200",
    )
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.reject_department", return_value=state
    ), patch("app.routers.approval.notifications.notify_reject") as mock_notify:
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post(
            "/approval/reject", json={"department": DEPT, "fiscal_year": FY, "reason": "bad numbers"}
        )

    assert response.status_code == 200
    mock_notify.assert_called_once()
    assert mock_notify.call_args.kwargs["approver1_empcode"] == "200"


def test_approve_final_passes_frozen_approver1_empcode_for_cc(client):
    """2026-07-31 revamp: the final-approve confirmation cc's the frozen
    approver1 — the router must hand `state.approver1_empcode` to
    notify_approved."""
    _override_auth("manager@chememan.com")
    state = _fake_state(
        status=APPROVED, current_position=None, current_approver_empcode=None,
        submitter_email="filler@chememan.com", approver1_empcode="200",
    )
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.approve_department", return_value=state
    ), patch("app.routers.approval.notifications.notify_approved") as mock_approved:
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/approve", json={"department": DEPT, "fiscal_year": FY})

    assert response.status_code == 200
    mock_approved.assert_called_once()
    assert mock_approved.call_args.kwargs["approver1_empcode"] == "200"


def test_pending_for_me_401_without_auth(client):
    response = client.get("/approval/pending-for-me", params={"fiscal_year": FY})
    assert response.status_code == 401


def test_pending_for_me_returns_department_list(client):
    _override_auth("manager@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.list_departments_pending_my_approval", return_value=[DEPT, "Warehouse PB"]
    ) as mock_list:
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/approval/pending-for-me", params={"fiscal_year": FY})

    assert response.status_code == 200
    assert response.json() == {"departments": [DEPT, "Warehouse PB"]}
    assert mock_list.call_args.args[1] == FY
    assert mock_list.call_args.args[2] == "manager@chememan.com"


def test_pending_for_me_empty_list_when_caller_is_not_a_current_approver(client):
    _override_auth("filler@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.list_departments_pending_my_approval", return_value=[]
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/approval/pending-for-me", params={"fiscal_year": FY})

    assert response.status_code == 200
    assert response.json() == {"departments": []}


def test_pending_for_me_db_failure_maps_to_502(client):
    import pyodbc

    _override_auth("manager@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.list_departments_pending_my_approval", side_effect=pyodbc.Error("boom")
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/approval/pending-for-me", params={"fiscal_year": FY})

    assert response.status_code == 502


def test_submit_mid_chain_admin_overwrite_maps_to_409(client):
    """B2 gate fix: the new fail-closed guard's error must map to 409, same
    as the other approval-conflict cases."""
    _override_auth("admin@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock()
    ), patch(
        "app.routers.approval.submit_department",
        side_effect=MidChainAdminOverwriteError("Accounting/2027 is PENDING_APPROVER2 -- mid-approval"),
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/submit", json={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# POST /approval/override-step — ADR-0027 manual admin step-override
# ---------------------------------------------------------------------------

def test_override_step_401_without_auth(client):
    response = client.post("/approval/override-step", json={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 401


def test_override_step_non_admin_filler_maps_to_403(client):
    """ADR-0027: scope.is_admin is the ONLY gate — a plain filler, 403, and
    the state machine is never even called."""
    _override_auth("filler@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock(is_admin=False)
    ), patch("app.routers.approval.admin_override_step") as mock_override:
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/override-step", json={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 403
    mock_override.assert_not_called()


def test_override_step_non_admin_step2_approver_maps_to_403(client):
    """A step-2 approver who is NOT on the admin allowlist gets the same 403 —
    being a frozen approver somewhere grants no override right (admin-only)."""
    _override_auth("approver@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock(is_admin=False)
    ), patch("app.routers.approval.admin_override_step") as mock_override:
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/override-step", json={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 403
    mock_override.assert_not_called()


def test_override_step_admin_success_notifies_submitter_and_next_approver(client):
    """Admin caller -> 200, and notify_step_overridden fires with the SKIPPED
    approver's empcode (state.approver1_empcode — the override leaves it
    frozen); the next approver ALSO gets their normal notify_turn mail."""
    _override_auth("jakkaritw@chememan.com")
    state = _fake_state(
        status=PENDING_APPROVER2, current_position=2, current_approver_empcode="101032",
        submitter_email="filler@chememan.com", approver1_empcode="200",
    )
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock(is_admin=True)
    ), patch("app.routers.approval.admin_override_step", return_value=state) as mock_override, patch(
        "app.routers.approval.notifications.notify_step_overridden"
    ) as mock_overridden, patch(
        "app.routers.approval.notifications.notify_turn"
    ) as mock_turn:
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/override-step", json={"department": DEPT, "fiscal_year": FY})

    assert response.status_code == 200
    assert response.json()["status"] == PENDING_APPROVER2
    assert response.json().get("notification_warning") is None
    mock_override.assert_called_once()
    assert mock_override.call_args.args[3] == "jakkaritw@chememan.com"
    mock_overridden.assert_called_once()
    assert mock_overridden.call_args.kwargs["skipped_approver_empcode"] == "200"
    assert mock_overridden.call_args.kwargs["submitter_email"] == "filler@chememan.com"
    assert mock_overridden.call_args.kwargs["admin_email"] == "jakkaritw@chememan.com"
    mock_turn.assert_called_once()
    assert mock_turn.call_args.kwargs["approver_empcode"] == "101032"


def test_override_step_notification_failure_never_fails_the_request(client):
    """Never-cut: a notify_step_overridden exception must not roll back or
    fail the already-committed override — 200 with a non-fatal warning. AND
    (review fix): the two override sends must fail INDEPENDENTLY -- when
    notify_step_overridden raises, notify_turn must STILL fire for the
    approver the step just landed on, or the department goes silent again
    until the 7-day reminder (exactly the window ADR-0027 exists to clear)."""
    _override_auth("jakkaritw@chememan.com")
    state = _fake_state(
        status=PENDING_APPROVER2, current_position=2, current_approver_empcode="101032",
        submitter_email="filler@chememan.com", approver1_empcode="200",
    )
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock(is_admin=True)
    ), patch("app.routers.approval.admin_override_step", return_value=state), patch(
        "app.routers.approval.notifications.notify_step_overridden", side_effect=RuntimeError("graph down")
    ), patch("app.routers.approval.notifications.notify_turn") as mock_turn:
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/override-step", json={"department": DEPT, "fiscal_year": FY})

    assert response.status_code == 200
    assert response.json()["notification_warning"] is not None
    mock_turn.assert_called_once()  # the defect this test catches: notify_turn must still fire
    assert mock_turn.call_args.kwargs["approver_empcode"] == "101032"


def test_override_step_notify_turn_failure_still_sends_override_notice(client):
    """Mirror case: when notify_turn (the SECOND send) raises, the override
    notice (notify_step_overridden) must still have gone out -- 200 with a
    non-fatal warning, and notify_step_overridden must have been called."""
    _override_auth("jakkaritw@chememan.com")
    state = _fake_state(
        status=PENDING_APPROVER2, current_position=2, current_approver_empcode="101032",
        submitter_email="filler@chememan.com", approver1_empcode="200",
    )
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock(is_admin=True)
    ), patch("app.routers.approval.admin_override_step", return_value=state), patch(
        "app.routers.approval.notifications.notify_step_overridden"
    ) as mock_overridden, patch(
        "app.routers.approval.notifications.notify_turn", side_effect=RuntimeError("graph down")
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/override-step", json={"department": DEPT, "fiscal_year": FY})

    assert response.status_code == 200
    assert response.json()["notification_warning"] is not None
    mock_overridden.assert_called_once()  # the override notice must still have been sent


# ---------------------------------------------------------------------------
# GET /approval/locked-departments — "+ เพิ่ม Transaction" lock-awareness
# (2026-08-08 bug fix, ADR-0013 UI parity extension)
# ---------------------------------------------------------------------------

def test_locked_departments_401_without_auth(client):
    response = client.get("/approval/locked-departments", params={"fiscal_year": FY})
    assert response.status_code == 401


def test_locked_departments_returns_only_the_callers_own_locked_departments(client):
    """Intersection of (a) the departments the caller's OWN Fill cost
    centers belong to and (b) the server's locked set — a locked department
    the caller has no Fill cost center in must never appear (no leakage
    beyond what GET /scope/departments already reveals)."""
    _override_auth("filler@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope",
        return_value=MagicMock(fill_cost_centers=["CC1", "CC2"]),
    ), patch(
        "app.routers.approval.fetch_departments",
        return_value=[
            {"cost_center": "CC1", "department": "Accounting", "division": None, "c_level": None},
            {"cost_center": "CC2", "department": "Warehouse", "division": None, "c_level": None},
        ],
    ), patch(
        "app.routers.approval.fetch_locked_departments",
        return_value=frozenset({"Accounting", "Some Other Department"}),
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/approval/locked-departments", params={"fiscal_year": FY})
    assert response.status_code == 200
    assert response.json() == {"departments": ["Accounting"]}


def test_locked_departments_no_fill_scope_returns_empty_and_skips_the_extra_queries(client):
    """A caller with no Fill cost center (e.g. a pure admin, or a see_only
    manager) has nothing to check — short-circuit without even querying
    fetch_departments/fetch_locked_departments."""
    _override_auth("nobody@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock(fill_cost_centers=[])
    ), patch("app.routers.approval.fetch_departments") as mock_fetch_departments, patch(
        "app.routers.approval.fetch_locked_departments"
    ) as mock_fetch_locked:
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/approval/locked-departments", params={"fiscal_year": FY})
    assert response.status_code == 200
    assert response.json() == {"departments": []}
    mock_fetch_departments.assert_not_called()
    mock_fetch_locked.assert_not_called()


def test_locked_departments_none_locked_returns_empty_list(client):
    _override_auth("filler@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock(fill_cost_centers=["CC1"])
    ), patch(
        "app.routers.approval.fetch_departments",
        return_value=[{"cost_center": "CC1", "department": "Accounting", "division": None, "c_level": None}],
    ), patch("app.routers.approval.fetch_locked_departments", return_value=frozenset()):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/approval/locked-departments", params={"fiscal_year": FY})
    assert response.status_code == 200
    assert response.json() == {"departments": []}


def test_locked_departments_db_failure_maps_to_502(client):
    import pyodbc

    _override_auth("filler@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", side_effect=pyodbc.Error("connection lost")
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/approval/locked-departments", params={"fiscal_year": FY})
    assert response.status_code == 502


def test_override_step_not_overridable_maps_to_409_with_thai_detail(client):
    """StepNotOverridableError (positions 2/3, or the only-active-position
    case) -> 409 whose Thai detail the UI shows as-is."""
    _override_auth("jakkaritw@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock(is_admin=True)
    ), patch(
        "app.routers.approval.admin_override_step",
        side_effect=StepNotOverridableError("ไม่สามารถอนุมัติแทนได้ — ขั้นตอนนี้เป็นการพิจารณาของฝ่ายงบประมาณ"),
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/override-step", json={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 409
    assert "ไม่สามารถอนุมัติแทนได้" in response.json()["detail"]
