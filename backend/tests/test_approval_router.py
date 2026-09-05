"""Unit tests for the A6 approval endpoints — POST /approval/submit|approve|
reject, GET /approval/status. DB always mocked; the state machine itself is
unit-tested in test_approval.py — these tests only prove the router wiring:
auth, error-code -> HTTP-status mapping, and the 502 DB-unavailable path.
"""
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

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
    SubmitEligibility,
)
from app.auth import get_current_user_email
from app.deadline import YEAR_NOT_OPEN, YEAR_OPEN
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
    ), patch("app.routers.approval.submit_department", return_value=_fake_state()), patch(
        "app.routers.approval.is_post_deadline", return_value=False
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/submit", json={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 200
    assert response.json()["status"] == PENDING_APPROVER1


def test_submit_response_includes_is_post_deadline(client):
    """Multi-endpoint contract pin (SIT defect 2026-08-14 fix): `is_post_deadline`
    must be populated on the SUBMIT response too, not just GET /status --
    the frontend refetches nothing between a submit click and its own
    button-visibility recheck, so a stale/absent value here would show a
    doomed submit button again right after the one that just succeeded."""
    _override_auth("filler@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock()
    ), patch(
        "app.routers.approval.submit_department", return_value=_fake_state()
    ), patch("app.routers.approval.is_post_deadline", return_value=True):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/submit", json={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 200
    assert response.json()["is_post_deadline"] is True


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
    server's own detail, the same `_run` dict-based mapping idiom every
    other approval error already uses."""
    _override_auth("filler@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock()
    ), patch(
        "app.routers.approval.submit_department",
        side_effect=DepartmentEmptyError("This department has no budget data yet, so it cannot be submitted."),
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/submit", json={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 400
    assert response.json()["detail"] == "This department has no budget data yet, so it cannot be submitted."


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
    ), patch("app.routers.approval.is_post_deadline", return_value=False):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/approve", json={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 200
    assert response.json()["status"] == APPROVED


def test_approve_response_includes_is_post_deadline(client):
    _override_auth("manager@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.approve_department", return_value=_fake_state(status=APPROVED)
    ), patch("app.routers.approval.is_post_deadline", return_value=False):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/approve", json={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 200
    assert response.json()["is_post_deadline"] is False


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
    ), patch("app.routers.approval.is_post_deadline", return_value=False):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post(
            "/approval/reject", json={"department": DEPT, "fiscal_year": FY, "reason": "bad numbers"}
        )
    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"


def test_reject_response_includes_is_post_deadline(client):
    _override_auth("manager@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.reject_department", return_value=_fake_state(status="REJECTED", reject_reason="bad")
    ), patch("app.routers.approval.is_post_deadline", return_value=True):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post(
            "/approval/reject", json={"department": DEPT, "fiscal_year": FY, "reason": "bad numbers"}
        )
    assert response.status_code == 200
    assert response.json()["is_post_deadline"] is True


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
    ), patch("app.routers.approval.is_post_deadline", return_value=False):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/approval/status", params={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 200
    assert response.json()["status"] == "DRAFT"


def test_status_is_post_deadline_true_when_past_deadline(client):
    """SIT defect 2026-08-14 fix: `GET /approval/status` must expose whether
    `fiscal_year` is past its submission deadline — the frontend's `canSubmit`
    uses this to decide whether the admin post-deadline override door
    (`app.approval.submit_department`'s `ACTION_ADMIN_OVERRIDE_DEADLINE`
    branch, the only one exempt from `_ensure_admin_overwrite_allowed`) will
    actually succeed before showing the button. Router sets it AFTER calling
    `get_approval_status` (same seam as `current_approver_name`), never
    inside `app.approval`'s pure state-machine functions -- adding an
    unconditional DB lookup there would break test_approval.py's finite
    mocked side_effect sequences (see `_notify_after_transition`'s own
    docstring for the same reasoning)."""
    _override_auth("filler@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock()
    ), patch("app.routers.approval.authorize_status_view"), patch(
        "app.routers.approval.resolve_submitter", return_value=(None, None)
    ), patch(
        "app.routers.approval.get_approval_status",
        return_value=_fake_state(status=PENDING_APPROVER2, current_position=2),
    ), patch("app.routers.approval.is_post_deadline", return_value=True):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/approval/status", params={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 200
    assert response.json()["is_post_deadline"] is True


def test_status_is_post_deadline_false_when_not_past_deadline(client):
    _override_auth("filler@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock()
    ), patch("app.routers.approval.authorize_status_view"), patch(
        "app.routers.approval.resolve_submitter", return_value=(None, None)
    ), patch(
        "app.routers.approval.get_approval_status",
        return_value=_fake_state(status=PENDING_APPROVER2, current_position=2),
    ), patch("app.routers.approval.is_post_deadline", return_value=False):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/approval/status", params={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 200
    assert response.json()["is_post_deadline"] is False


def test_status_includes_can_submit_true_with_no_reason(client):
    """SIT defect fix #2 (2026-08-16): `GET /approval/status` surfaces the
    server's own submit verdict instead of leaving the frontend to re-derive
    admin authorization from `status`/`is_post_deadline` alone."""
    _override_auth("admin@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock()
    ), patch("app.routers.approval.authorize_status_view"), patch(
        "app.routers.approval.resolve_submitter", return_value=(None, None)
    ), patch(
        "app.routers.approval.get_approval_status",
        return_value=_fake_state(status="DRAFT", current_position=None),
    ), patch("app.routers.approval.is_post_deadline", return_value=False), patch(
        "app.routers.approval.evaluate_submit_eligibility",
        return_value=SubmitEligibility(can_submit=True),
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/approval/status", params={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 200
    assert response.json()["can_submit"] is True
    assert response.json()["submit_blocked_reason"] is None


def test_status_includes_can_submit_false_with_reason(client):
    """The refused admin shape (SIT defect #2, case (a) -- not a filler,
    department not orphan, no Template-2 rows, cycle still open): the
    machine-readable reason travels with the verdict so the UI can explain
    itself instead of just hiding a control silently."""
    _override_auth("admin@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock()
    ), patch("app.routers.approval.authorize_status_view"), patch(
        "app.routers.approval.resolve_submitter", return_value=(None, None)
    ), patch(
        "app.routers.approval.get_approval_status",
        return_value=_fake_state(status="DRAFT", current_position=None),
    ), patch("app.routers.approval.is_post_deadline", return_value=False), patch(
        "app.routers.approval.evaluate_submit_eligibility",
        return_value=SubmitEligibility(can_submit=False, reason="admin_cannot_submit_in_cycle"),
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/approval/status", params={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 200
    assert response.json()["can_submit"] is False
    assert response.json()["submit_blocked_reason"] == "admin_cannot_submit_in_cycle"


def test_status_can_submit_fails_closed_when_eligibility_lookup_errors(client):
    """Never-cut: a broken eligibility lookup must never fail an
    already-successful GET /status -- `can_submit` simply stays at its
    fail-closed default `False` (never a stale/unknown `True`)."""
    _override_auth("admin@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock()
    ), patch("app.routers.approval.authorize_status_view"), patch(
        "app.routers.approval.resolve_submitter", return_value=(None, None)
    ), patch(
        "app.routers.approval.get_approval_status",
        return_value=_fake_state(status="DRAFT", current_position=None),
    ), patch("app.routers.approval.is_post_deadline", return_value=False), patch(
        "app.routers.approval.evaluate_submit_eligibility", side_effect=RuntimeError("db down"),
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/approval/status", params={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 200
    assert response.json()["can_submit"] is False


def test_submit_response_includes_can_submit(client):
    """Multi-endpoint contract pin (same convention as
    `test_submit_response_includes_is_post_deadline`): `can_submit` travels
    on every endpoint that returns `ApprovalStatusState`, not just GET
    /status, so the button never goes stale after the caller's own action."""
    _override_auth("filler@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock()
    ), patch(
        "app.routers.approval.submit_department",
        return_value=_fake_state(status=PENDING_APPROVER1, current_position=1),
    ), patch("app.routers.approval.is_post_deadline", return_value=False), patch(
        "app.routers.approval.evaluate_submit_eligibility",
        return_value=SubmitEligibility(can_submit=False, reason="invalid_approval_state"),
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/submit", json={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 200
    assert response.json()["can_submit"] is False
    assert response.json()["submit_blocked_reason"] == "invalid_approval_state"


# ---------------------------------------------------------------------------
# `can_submit` wiring gap closed (gate review, 2026-08-16): the earlier tests
# above only asserted `evaluate_submit_eligibility` on 2 of the 5 endpoints
# that carry `can_submit` (status, submit), and NONE of them proved WHICH
# identity gets evaluated -- the entire reason this feature is auth-safe is
# that it is always the CALLER's own email/scope, never `state.submitter_email`
# (a different person could easily have submitted the record being viewed).
# ---------------------------------------------------------------------------

_NOT_THE_CALLER = "not-the-caller@chememan.com"  # every fixture state below is "submitted by" this email


def _can_submit_endpoint_cases():
    """One case per endpoint returning `ApprovalStatusState` — the pieces
    that differ (patch targets, request shape) are captured directly;
    `evaluate_submit_eligibility` and `resolve_scope` are added identically
    for every case by the test itself below, matching the router's own
    convention that `_set_can_submit` runs identically on all 5."""
    return [
        pytest.param(
            "caller-submit@chememan.com", "post", "/approval/submit",
            {"json": {"department": DEPT, "fiscal_year": FY}},
            {
                "app.routers.approval.submit_department": {
                    "return_value": _fake_state(status=PENDING_APPROVER1, current_position=1, submitter_email=_NOT_THE_CALLER)
                },
                "app.routers.approval.is_post_deadline": {"return_value": False},
            },
            id="submit",
        ),
        pytest.param(
            "caller-approve@chememan.com", "post", "/approval/approve",
            {"json": {"department": DEPT, "fiscal_year": FY}},
            {
                "app.routers.approval.approve_department": {
                    "return_value": _fake_state(status=APPROVED, submitter_email=_NOT_THE_CALLER)
                },
                "app.routers.approval.is_post_deadline": {"return_value": False},
            },
            id="approve",
        ),
        pytest.param(
            "caller-reject@chememan.com", "post", "/approval/reject",
            {"json": {"department": DEPT, "fiscal_year": FY, "reason": "bad numbers"}},
            {
                "app.routers.approval.reject_department": {
                    "return_value": _fake_state(status="REJECTED", reject_reason="bad numbers", submitter_email=_NOT_THE_CALLER)
                },
                "app.routers.approval.is_post_deadline": {"return_value": False},
            },
            id="reject",
        ),
        pytest.param(
            "caller-override@chememan.com", "post", "/approval/override-step",
            {"json": {"department": DEPT, "fiscal_year": FY}},
            {
                "app.routers.approval.admin_override_step": {
                    "return_value": _fake_state(
                        status=PENDING_APPROVER2, current_position=2, current_approver_empcode="101032",
                        submitter_email=_NOT_THE_CALLER, approver1_empcode="200",
                    )
                },
                "app.routers.approval.notifications.notify_step_overridden": {},
                "app.routers.approval.notifications.notify_turn": {},
                "app.routers.approval.is_post_deadline": {"return_value": False},
            },
            id="override-step",
        ),
        pytest.param(
            "caller-status@chememan.com", "get", "/approval/status",
            {"params": {"department": DEPT, "fiscal_year": FY}},
            {
                "app.routers.approval.authorize_status_view": {},
                "app.routers.approval.resolve_submitter": {"return_value": (None, None)},
                "app.routers.approval.get_approval_status": {
                    "return_value": _fake_state(status="DRAFT", current_position=None, submitter_email=_NOT_THE_CALLER)
                },
                "app.routers.approval.is_post_deadline": {"return_value": False},
            },
            id="status",
        ),
    ]


@pytest.mark.parametrize("caller_email, http_method, path, request_kwargs, extra_patches", _can_submit_endpoint_cases())
def test_can_submit_travels_on_every_endpoint_for_the_callers_own_identity(
    client, caller_email, http_method, path, request_kwargs, extra_patches,
):
    """Closes 2 gaps at once (gate review, 2026-08-16): (1) only 2 of 5
    endpoints had a `can_submit` contract pin before this — now all 5 are
    parametrized together so they can never silently drift apart again; (2)
    NOTHING previously asserted `evaluate_submit_eligibility`'s call_args, so
    nothing actually PROVED the security-load-bearing property that makes
    this feature auth-safe in the first place: the verdict is computed for
    the CALLER's own identity, never `state.submitter_email`. Every fixture
    state above is "submitted by" `_NOT_THE_CALLER` -- if the wiring ever
    regressed to evaluating that field instead of the authenticated caller,
    this assertion fails immediately."""
    _override_auth(caller_email)
    with ExitStack() as stack, patch("app.routers.approval.get_fabric_conn") as mock_conn:
        mock_conn.return_value.__enter__.return_value = MagicMock()
        stack.enter_context(patch("app.routers.approval.resolve_scope", return_value=MagicMock(is_admin=True)))
        for target, kwargs in extra_patches.items():
            stack.enter_context(patch(target, **kwargs))
        mock_eligibility = stack.enter_context(
            patch("app.routers.approval.evaluate_submit_eligibility", return_value=SubmitEligibility(can_submit=True))
        )
        response = getattr(client, http_method)(path, **request_kwargs)

    assert response.status_code == 200
    assert response.json()["can_submit"] is True
    mock_eligibility.assert_called_once()
    # args = (conn, department, fiscal_year, email, scope) -- args[3] is the
    # identity that was ACTUALLY evaluated.
    assert mock_eligibility.call_args.args[3] == caller_email
    assert mock_eligibility.call_args.args[3] != _NOT_THE_CALLER


@pytest.mark.parametrize(
    "caller_email, http_method, path, request_kwargs, extra_patches",
    [
        pytest.param(
            "filler@chememan.com", "post", "/approval/submit",
            {"json": {"department": DEPT, "fiscal_year": FY}},
            {
                "app.routers.approval.submit_department": {
                    "return_value": _fake_state(status=PENDING_APPROVER1, current_position=1)
                },
                "app.routers.approval.is_post_deadline": {"return_value": False},
            },
            id="submit",
        ),
        pytest.param(
            "jakkaritw@chememan.com", "post", "/approval/override-step",
            {"json": {"department": DEPT, "fiscal_year": FY}},
            {
                "app.routers.approval.admin_override_step": {
                    "return_value": _fake_state(
                        status=PENDING_APPROVER2, current_position=2, current_approver_empcode="101032",
                        approver1_empcode="200",
                    )
                },
                "app.routers.approval.notifications.notify_step_overridden": {},
                "app.routers.approval.notifications.notify_turn": {},
                "app.routers.approval.is_post_deadline": {"return_value": False},
            },
            id="override-step",
        ),
        pytest.param(
            "filler@chememan.com", "get", "/approval/status",
            {"params": {"department": DEPT, "fiscal_year": FY}},
            {
                "app.routers.approval.authorize_status_view": {},
                "app.routers.approval.resolve_submitter": {"return_value": (None, None)},
                "app.routers.approval.get_approval_status": {
                    "return_value": _fake_state(status="DRAFT", current_position=None)
                },
                "app.routers.approval.is_post_deadline": {"return_value": False},
            },
            id="status",
        ),
    ],
)
def test_can_submit_reuses_the_scope_already_resolved_this_request(
    client, caller_email, http_method, path, request_kwargs, extra_patches,
):
    """Perf regression guard (gate review, 2026-08-16): `submit`/
    `override-step`/`status` each already resolve `scope` once for their own
    logic before `_set_can_submit` runs -- it must REUSE that object, not pay
    a SECOND full `resolve_scope` (up to 5 round-trips: `_FILL_SQL`,
    `_MANAGER_SEE_ADD_SQL`, `resolve_submitter`,
    `departments_pending_for_empcode`, `cost_centers_for_departments`) on
    `GET /approval/status` — the app's hottest endpoint (fires on every
    ฝ่าย switch and after every action). `approve`/`reject` are NOT in this
    list: they never had a scope in hand to begin with, so their single
    `resolve_scope` call inside `_set_can_submit` is not a regression to
    guard against.

    Proven two ways so a future "resolved once, but a NEW, coincidentally-
    equal scope" refactor cannot slip past: `resolve_scope` is asserted
    called exactly ONCE, and the object `evaluate_submit_eligibility`
    receives IS (identity, not `==`) the one `resolve_scope` returned."""
    scope_sentinel = MagicMock(is_admin=True)  # is_admin=True also satisfies override-step's own admin gate
    _override_auth(caller_email)
    with ExitStack() as stack, patch("app.routers.approval.get_fabric_conn") as mock_conn:
        mock_conn.return_value.__enter__.return_value = MagicMock()
        mock_resolve_scope = stack.enter_context(
            patch("app.routers.approval.resolve_scope", return_value=scope_sentinel)
        )
        for target, kwargs in extra_patches.items():
            stack.enter_context(patch(target, **kwargs))
        mock_eligibility = stack.enter_context(
            patch("app.routers.approval.evaluate_submit_eligibility", return_value=SubmitEligibility(can_submit=True))
        )
        response = getattr(client, http_method)(path, **request_kwargs)

    assert response.status_code == 200
    mock_resolve_scope.assert_called_once()
    # args = (conn, department, fiscal_year, email, scope)
    assert mock_eligibility.call_args.args[4] is scope_sentinel


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
    ) as mock_notify, patch("app.routers.approval.is_post_deadline", return_value=False):
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
    ), patch("app.routers.approval.is_post_deadline", return_value=False):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/submit", json={"department": DEPT, "fiscal_year": FY})

    assert response.status_code == 200
    assert response.json()["notification_warning"] is not None


def test_approve_notifies_next_approver_when_still_pending(client):
    _override_auth("manager@chememan.com")
    state = _fake_state(status=PENDING_APPROVER2, current_position=2, current_approver_empcode="101032")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.approve_department", return_value=state
    ), patch("app.routers.approval.notifications.notify_turn") as mock_notify, patch(
        "app.routers.approval.is_post_deadline", return_value=False
    ):
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
    ) as mock_approved, patch("app.routers.approval.is_post_deadline", return_value=False):
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
    ) as mock_approved, patch("app.routers.approval.is_post_deadline", return_value=False):
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
    ), patch("app.routers.approval.is_post_deadline", return_value=False):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/approve", json={"department": DEPT, "fiscal_year": FY})

    assert response.status_code == 200
    assert response.json()["notification_warning"] is not None


def test_reject_notifies_the_last_submitter(client):
    _override_auth("manager@chememan.com")
    state = _fake_state(status="REJECTED", reject_reason="bad numbers", submitter_email="filler@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.reject_department", return_value=state
    ), patch("app.routers.approval.notifications.notify_reject") as mock_notify, patch(
        "app.routers.approval.is_post_deadline", return_value=False
    ):
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
    ), patch("app.routers.approval.notifications.notify_reject") as mock_notify, patch(
        "app.routers.approval.is_post_deadline", return_value=False
    ):
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
    ), patch("app.routers.approval.notifications.notify_approved") as mock_approved, patch(
        "app.routers.approval.is_post_deadline", return_value=False
    ):
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
    ) as mock_turn, patch("app.routers.approval.is_post_deadline", return_value=False):
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


def test_override_step_response_includes_is_post_deadline(client):
    _override_auth("jakkaritw@chememan.com")
    state = _fake_state(
        status=PENDING_APPROVER2, current_position=2, current_approver_empcode="101032",
        submitter_email="filler@chememan.com", approver1_empcode="200",
    )
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock(is_admin=True)
    ), patch("app.routers.approval.admin_override_step", return_value=state), patch(
        "app.routers.approval.notifications.notify_step_overridden"
    ), patch("app.routers.approval.notifications.notify_turn"), patch(
        "app.routers.approval.is_post_deadline", return_value=False
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/override-step", json={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 200
    assert response.json()["is_post_deadline"] is False


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
    ), patch("app.routers.approval.notifications.notify_turn") as mock_turn, patch(
        "app.routers.approval.is_post_deadline", return_value=False
    ):
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
    ), patch("app.routers.approval.is_post_deadline", return_value=False):
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
    ), patch("app.routers.approval.fiscal_year_state", return_value=YEAR_OPEN):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/approval/locked-departments", params={"fiscal_year": FY})
    assert response.status_code == 200
    assert response.json() == {"departments": ["Accounting"], "year_not_open": False}


def test_locked_departments_no_fill_scope_returns_empty_and_skips_the_extra_queries(client):
    """A caller with no Fill cost center (e.g. a pure admin, or a see_only
    manager) has nothing to check — short-circuit without even querying
    fetch_departments/fetch_locked_departments."""
    _override_auth("nobody@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock(fill_cost_centers=[])
    ), patch("app.routers.approval.fetch_departments") as mock_fetch_departments, patch(
        "app.routers.approval.fetch_locked_departments"
    ) as mock_fetch_locked, patch("app.routers.approval.fiscal_year_state", return_value=YEAR_OPEN):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/approval/locked-departments", params={"fiscal_year": FY})
    assert response.status_code == 200
    assert response.json() == {"departments": [], "year_not_open": False}
    mock_fetch_departments.assert_not_called()
    mock_fetch_locked.assert_not_called()


def test_locked_departments_none_locked_returns_empty_list(client):
    _override_auth("filler@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock(fill_cost_centers=["CC1"])
    ), patch(
        "app.routers.approval.fetch_departments",
        return_value=[{"cost_center": "CC1", "department": "Accounting", "division": None, "c_level": None}],
    ), patch("app.routers.approval.fetch_locked_departments", return_value=frozenset()), patch(
        "app.routers.approval.fiscal_year_state", return_value=YEAR_OPEN
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/approval/locked-departments", params={"fiscal_year": FY})
    assert response.status_code == 200
    assert response.json() == {"departments": [], "year_not_open": False}


def test_locked_departments_year_not_open_for_a_non_admin_filler(client):
    """2026-08-08 3-state extension: a year-wide signal (not per-department)
    from the SAME `app.deadline.fiscal_year_state` the write path and A6's
    submit gate consult — feeds "+ เพิ่ม Transaction"'s pre-emptive check."""
    _override_auth("filler@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope",
        return_value=MagicMock(fill_cost_centers=["CC1"], is_admin=False),
    ), patch(
        "app.routers.approval.fetch_departments",
        return_value=[{"cost_center": "CC1", "department": "Accounting", "division": None, "c_level": None}],
    ), patch("app.routers.approval.fetch_locked_departments", return_value=frozenset()), patch(
        "app.routers.approval.fiscal_year_state", return_value=YEAR_NOT_OPEN
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/approval/locked-departments", params={"fiscal_year": FY})
    assert response.status_code == 200
    assert response.json() == {"departments": [], "year_not_open": True}


def test_locked_departments_year_not_open_applies_to_admin_too(client):
    """REVERSED by jakkaritw 2026-08-10 (was: always False for admin): a
    NOT_OPEN year is file-import-only, so the Add button must disable for an
    admin as well — the router consults `fiscal_year_state` for every
    caller."""
    _override_auth("admin@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope",
        return_value=MagicMock(fill_cost_centers=["CC1"], is_admin=True),
    ), patch(
        "app.routers.approval.fetch_departments",
        return_value=[{"cost_center": "CC1", "department": "Accounting", "division": None, "c_level": None}],
    ), patch("app.routers.approval.fetch_locked_departments", return_value=frozenset()), patch(
        "app.routers.approval.fiscal_year_state", return_value=YEAR_NOT_OPEN
    ) as mock_fiscal_year_state:
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/approval/locked-departments", params={"fiscal_year": FY})
    assert response.status_code == 200
    assert response.json() == {"departments": [], "year_not_open": True}
    mock_fiscal_year_state.assert_called_once()


def test_locked_departments_db_failure_maps_to_502(client):
    import pyodbc

    _override_auth("filler@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", side_effect=pyodbc.Error("connection lost")
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.get("/approval/locked-departments", params={"fiscal_year": FY})
    assert response.status_code == 502


def test_override_step_not_overridable_maps_to_409(client):
    """StepNotOverridableError (positions 2/3, or the only-active-position
    case) -> 409 whose detail the UI shows as-is."""
    _override_auth("jakkaritw@chememan.com")
    with patch("app.routers.approval.get_fabric_conn") as mock_conn, patch(
        "app.routers.approval.resolve_scope", return_value=MagicMock(is_admin=True)
    ), patch(
        "app.routers.approval.admin_override_step",
        side_effect=StepNotOverridableError("Cannot approve on their behalf — this step is under review by the Budget Department."),
    ):
        mock_conn.return_value.__enter__.return_value = MagicMock()
        response = client.post("/approval/override-step", json={"department": DEPT, "fiscal_year": FY})
    assert response.status_code == 409
    assert "Cannot approve on their behalf" in response.json()["detail"]
