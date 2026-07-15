"""Unit tests for app.approval — A6 approval engine. DB always mocked
(`conn.cursor.return_value` is the ONE shared cursor mock, matching the
convention in test_write_model.py / test_rls.py).

Covers: chain resolution (self-skip + dedup + invalid-approver1 fallback,
ADR-0006), submit branch selection (normal chain vs admin direct-approve,
ADR-0012), step-gated approve/reject, reject-then-resubmit restarts the
whole chain, concurrent-approve race protection, and append-only logging.
"""
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pyodbc
import pytest

from app.approval import (
    ACTION_AUTO_ESCALATE,
    ACTION_AUTO_SUBMIT,
    APPROVED,
    AUTO_ESCALATE_THRESHOLD_DAYS,
    NIPAPORN_EMPCODE,
    PENDING_APPROVER1,
    PENDING_APPROVER2,
    PENDING_APPROVER3,
    REJECTED,
    WARAPORN_EMPCODE,
    AdminCannotSubmitInCycleError,
    ApprovalRecordNotFoundError,
    ConcurrentApprovalError,
    InvalidApprovalStateError,
    MidChainAdminOverwriteError,
    MissingReasonError,
    NotAuthorizedToViewDepartmentError,
    NotCurrentApproverError,
    NotFillerOfDepartmentError,
    PastDeadlineError,
    _active_positions,
    _bangkok_today,
    _current_step_started_at,
    _is_post_deadline,
    approve_department,
    authorize_status_view,
    auto_escalate_step,
    auto_submit_department,
    fetch_pending_rows,
    get_approval_status,
    is_step_stale,
    reject_department,
    resolve_chain,
    submit_department,
)
from app.rls import Scope

DEPT = "Accounting"
FY = 2027


def _scope(**overrides) -> Scope:
    defaults = dict(email="filler@chememan.com", is_admin=False, role="filler",
                     fill_cost_centers=["CC1"], see_cost_centers=["CC1"])
    defaults.update(overrides)
    return Scope(**defaults)


def _admin_scope(**overrides) -> Scope:
    defaults = dict(email="admin@chememan.com", is_admin=True, role="admin",
                     fill_cost_centers=[], see_cost_centers=[])
    defaults.update(overrides)
    return Scope(**defaults)


# ---------------------------------------------------------------------------
# _active_positions / resolve_chain — pure chain-resolution logic
# ---------------------------------------------------------------------------

def test_active_positions_full_chain_no_overlap():
    assert _active_positions("999", "200") == [1, 2, 3]


def test_active_positions_nipaporn_submits_own_department_collapses_to_one_step():
    """ADR-0006 worked example: Nipaporn's manager is Waraporn -> raw
    [Waraporn, Nipaporn(self), Waraporn(dup)] -> [Waraporn] only."""
    active = _active_positions(submitter_empcode=NIPAPORN_EMPCODE, approver1_empcode=WARAPORN_EMPCODE)
    assert active == [1]  # position 1 holds Waraporn; position 2 (Nipaporn) self-skipped; position 3 deduped


def test_active_positions_waraporn_submits_own_department_keeps_two_steps():
    """ADR-0006 worked example: Waraporn's manager is Piyada -> raw
    [Piyada, Nipaporn, Waraporn(self)] -> [Piyada, Nipaporn]."""
    active = _active_positions(submitter_empcode=WARAPORN_EMPCODE, approver1_empcode="101218")
    assert active == [1, 2]


def test_active_positions_invalid_approver1_fallback_merges_with_position_two():
    """approver1_empcode already forced to Nipaporn (ADR-0006 invalid-approver1
    fallback) -> position 1 wins the Nipaporn slot (earliest-step-kept), the
    canonical position 2 becomes the duplicate and is dropped -> chain jumps
    1 -> 3, skipping 2 entirely."""
    active = _active_positions(submitter_empcode="999", approver1_empcode=NIPAPORN_EMPCODE)
    assert active == [1, 3]


def test_active_positions_never_cut_empty_safety_net(monkeypatch: pytest.MonkeyPatch):
    """Contrived: force all 3 positions to collapse onto the submitter so the
    normal 3-distinct-constant guarantee cannot save it -- proves the
    defense-in-depth path in _active_positions truly can return []."""
    import app.approval as approval_module

    monkeypatch.setattr(approval_module, "NIPAPORN_EMPCODE", "SAME")
    monkeypatch.setattr(approval_module, "WARAPORN_EMPCODE", "SAME")
    assert approval_module._active_positions(submitter_empcode="SAME", approver1_empcode="SAME") == []


def test_resolve_chain_never_cut_fallback_when_active_positions_is_empty(monkeypatch: pytest.MonkeyPatch):
    import app.approval as approval_module

    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = ("999", "200")
    monkeypatch.setattr(approval_module, "_active_positions", lambda *a, **k: [])

    submitter_empcode, approver1_empcode, active = resolve_chain(conn, "someone@chememan.com")
    assert approver1_empcode == NIPAPORN_EMPCODE
    assert active == [1]


def test_resolve_chain_normal_case():
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = ("999", "200")
    submitter_empcode, approver1_empcode, active = resolve_chain(conn, "someone@chememan.com")
    assert submitter_empcode == "999"
    assert approver1_empcode == "200"
    assert active == [1, 2, 3]


def test_resolve_chain_filler_not_in_employee_view_falls_back_to_nipaporn():
    """ADR-0019: a Filler absent from dbo.v_employee_budget_01 still submits,
    but with no manager to resolve -> approver1 falls back to Nipaporn."""
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = None  # not found
    submitter_empcode, approver1_empcode, active = resolve_chain(conn, "typo@chememan.com")
    assert submitter_empcode is None
    assert approver1_empcode == NIPAPORN_EMPCODE
    assert active == [1, 3]  # position 2 (canonical Nipaporn) dedups away


def test_resolve_chain_manager_is_null_falls_back_to_nipaporn():
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = ("999", None)  # found, but no manager
    submitter_empcode, approver1_empcode, active = resolve_chain(conn, "orphan-manager@chememan.com")
    assert submitter_empcode == "999"
    assert approver1_empcode == NIPAPORN_EMPCODE


# ---------------------------------------------------------------------------
# submit_department
# ---------------------------------------------------------------------------

def test_submit_first_time_full_chain():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        None,             # _fetch_row -> no existing record
        None,             # _is_post_deadline -> no deadline row configured
        ("999", "200"),   # resolve_submitter
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]  # _department_cost_centers

    result = submit_department(conn, DEPT, FY, "filler@chememan.com", _scope(fill_cost_centers=["CC1"]))

    assert result.status == PENDING_APPROVER1
    assert result.submitter_empcode == "999"
    assert result.approver1_empcode == "200"
    assert result.current_position == 1
    conn.commit.assert_called_once()


def test_submit_first_time_concurrent_insert_race_raises_conflict_not_raw_502():
    """S2 gate fix: two concurrent first-time submits for the same
    (department, fiscal_year) race the PK on the INSERT — the loser must get
    the same ConcurrentApprovalError (-> 409) as the conditional-UPDATE race
    path, never an uncaught pyodbc error escaping as a raw 502."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        None,             # _fetch_row -> no existing record (both racers see this)
        None,             # _is_post_deadline -> no deadline row configured
        ("999", "200"),   # resolve_submitter
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]  # _department_cost_centers
    cursor.execute.side_effect = [None, None, None, None, pyodbc.IntegrityError("23000", "duplicate key")]

    with pytest.raises(ConcurrentApprovalError):
        submit_department(conn, DEPT, FY, "filler@chememan.com", _scope(fill_cost_centers=["CC1"]))
    conn.commit.assert_not_called()


def test_submit_blocked_while_pending_no_recall():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [_status_row(status=PENDING_APPROVER2)]
    cursor.fetchall.side_effect = [[("CC1",)]]

    with pytest.raises(InvalidApprovalStateError):
        submit_department(conn, DEPT, FY, "filler@chememan.com", _scope(fill_cost_centers=["CC1"]))
    conn.commit.assert_not_called()


def test_submit_blocked_when_approved_no_reapproval_needed():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [_status_row(status=APPROVED)]
    cursor.fetchall.side_effect = [[("CC1",)]]

    with pytest.raises(InvalidApprovalStateError):
        submit_department(conn, DEPT, FY, "filler@chememan.com", _scope(fill_cost_centers=["CC1"]))


def test_submit_allowed_after_reject_resubmit_restarts_chain():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        _status_row(status=REJECTED, reject_reason="fix numbers", rejected_by_empcode="200"),
        None,             # _is_post_deadline
        ("999", "200"),   # resolve_submitter
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]

    result = submit_department(conn, DEPT, FY, "filler@chememan.com", _scope(fill_cost_centers=["CC1"]))

    assert result.status == PENDING_APPROVER1
    assert result.reject_reason is None  # re-frozen from scratch, not resumed
    assert result.rejected_by_empcode is None
    assert result.approver1_actioned_at is None


def test_resubmit_update_is_conditioned_on_status_rejected():
    """S3 gate fix: the resubmit UPDATE must be a conditional
    `WHERE ... AND status = ?` (matching approve/reject's own conditional-
    UPDATE race guard), not an unconditional overwrite."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        _status_row(status=REJECTED, reject_reason="fix numbers", rejected_by_empcode="200"),
        None,             # _is_post_deadline
        ("999", "200"),   # resolve_submitter
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]
    cursor.rowcount = 1

    submit_department(conn, DEPT, FY, "filler@chememan.com", _scope(fill_cost_centers=["CC1"]))

    update_call = cursor.execute.call_args_list[-2]  # log insert is the last execute before commit
    update_sql = update_call.args[0]
    update_params = update_call.args[1:]
    assert "WHERE department = ? AND fiscal_year = ? AND status = ?" in update_sql
    assert update_params[-1] == REJECTED


def test_resubmit_concurrent_status_change_raises_conflict():
    """S3 gate fix: if another request already changed the status between
    the read and this UPDATE (e.g. two concurrent resubmits), the
    conditional UPDATE matches 0 rows -> ConcurrentApprovalError, never a
    silent overwrite."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        _status_row(status=REJECTED, reject_reason="fix numbers", rejected_by_empcode="200"),
        None,             # _is_post_deadline
        ("999", "200"),   # resolve_submitter
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]
    cursor.rowcount = 0  # someone else's concurrent action changed status first

    with pytest.raises(ConcurrentApprovalError):
        submit_department(conn, DEPT, FY, "filler@chememan.com", _scope(fill_cost_centers=["CC1"]))
    conn.commit.assert_not_called()


def test_submit_past_deadline_blocks_normal_user():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [None, (date(2020, 1, 1),)]  # existing=None, deadline already passed
    cursor.fetchall.side_effect = [[("CC1",)]]

    with pytest.raises(PastDeadlineError):
        submit_department(conn, DEPT, FY, "filler@chememan.com", _scope(fill_cost_centers=["CC1"]))


def test_submit_forbidden_for_non_filler_non_admin():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [None]  # _fetch_row only -- short-circuits right after
    cursor.fetchall.side_effect = [[("CC1",)]]  # dept has CCs, but caller Fills none of them

    with pytest.raises(NotFillerOfDepartmentError):
        submit_department(conn, DEPT, FY, "outsider@chememan.com", _scope(fill_cost_centers=["OTHER-CC"]))
    conn.commit.assert_not_called()


def test_admin_submit_via_template_2_door_logs_admin_submit():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        None,           # _fetch_row
        (1,),           # _department_has_admin_template_rows -> found
        ("500", None),  # resolve_submitter (admin)
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]

    result = submit_department(conn, DEPT, FY, "admin@chememan.com", _admin_scope())

    assert result.status == APPROVED
    assert result.approver1_empcode is None
    insert_sql = cursor.execute.call_args_list[-1].args[0]  # log insert is the last execute before commit
    assert "budget.approval_log" in insert_sql


def test_admin_submit_orphan_department_logs_admin_override():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        None,          # _fetch_row
        None,          # _department_has_admin_template_rows -> none
        ("500", None), # resolve_submitter
    ]
    cursor.fetchall.side_effect = [[]]  # orphan: zero cost centers for this department

    result = submit_department(conn, DEPT, FY, "admin@chememan.com", _admin_scope())
    assert result.status == APPROVED


def test_admin_submit_post_deadline_any_department_logs_admin_override():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        None,               # _fetch_row
        None,               # _department_has_admin_template_rows -> none
        (date(2020, 1, 1),),  # _is_post_deadline -> already passed
        ("500", None),      # resolve_submitter
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]  # department has real CCs (not orphan)

    result = submit_department(conn, DEPT, FY, "admin@chememan.com", _admin_scope())
    assert result.status == APPROVED


def test_admin_cannot_submit_normal_in_cycle_department_they_do_not_fill():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        None,             # _fetch_row
        None,             # _department_has_admin_template_rows -> none
        None,             # _is_post_deadline -> not passed
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]  # has real CCs -- not orphan

    with pytest.raises(AdminCannotSubmitInCycleError):
        submit_department(conn, DEPT, FY, "admin@chememan.com", _admin_scope())
    conn.commit.assert_not_called()


# ---------------------------------------------------------------------------
# B2 gate fix — fail-closed guard: ADMIN_SUBMIT (Template-2) and orphan
# branches must not silently overwrite a mid-chain/APPROVED record; the
# post-deadline branch is exempt (ADR-0012 override-everything, unchanged).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("blocked_status", [PENDING_APPROVER1, PENDING_APPROVER2, PENDING_APPROVER3, APPROVED])
def test_admin_submit_via_template_2_door_blocked_when_existing_is_mid_chain_or_approved(blocked_status):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        _status_row(status=blocked_status),  # _fetch_row -> existing mid-chain/approved record
        (1,),                                  # _department_has_admin_template_rows -> found
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]

    with pytest.raises(MidChainAdminOverwriteError):
        submit_department(conn, DEPT, FY, "admin@chememan.com", _admin_scope())
    conn.commit.assert_not_called()


def test_admin_submit_via_template_2_door_allowed_when_existing_is_rejected():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        _status_row(status=REJECTED, reject_reason="bad", rejected_by_empcode="200"),  # _fetch_row
        (1,),           # _department_has_admin_template_rows -> found
        ("500", None),  # resolve_submitter
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]

    result = submit_department(conn, DEPT, FY, "admin@chememan.com", _admin_scope())
    assert result.status == APPROVED


@pytest.mark.parametrize("blocked_status", [PENDING_APPROVER1, PENDING_APPROVER2, PENDING_APPROVER3, APPROVED])
def test_admin_submit_orphan_department_blocked_when_existing_is_mid_chain_or_approved(blocked_status):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        _status_row(status=blocked_status),  # _fetch_row
        None,                                  # _department_has_admin_template_rows -> none
    ]
    cursor.fetchall.side_effect = [[]]  # orphan: zero cost centers for this department

    with pytest.raises(MidChainAdminOverwriteError):
        submit_department(conn, DEPT, FY, "admin@chememan.com", _admin_scope())
    conn.commit.assert_not_called()


def test_admin_submit_orphan_department_allowed_when_existing_is_rejected():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        _status_row(status=REJECTED, reject_reason="bad", rejected_by_empcode="200"),  # _fetch_row
        None,           # _department_has_admin_template_rows -> none
        ("500", None),  # resolve_submitter
    ]
    cursor.fetchall.side_effect = [[]]  # orphan

    result = submit_department(conn, DEPT, FY, "admin@chememan.com", _admin_scope())
    assert result.status == APPROVED


@pytest.mark.parametrize("existing_status", [PENDING_APPROVER2, APPROVED])
def test_admin_submit_post_deadline_still_overrides_mid_chain_or_approved(existing_status):
    """Post-deadline branch keeps its override-everything behavior (ADR-0012)
    -- the B2 guard must NOT apply here, unlike the two branches above."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        _status_row(status=existing_status),  # _fetch_row
        None,                 # _department_has_admin_template_rows -> none
        (date(2020, 1, 1),),  # _is_post_deadline -> already passed
        ("500", None),        # resolve_submitter
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]  # has real CCs -- not orphan

    result = submit_department(conn, DEPT, FY, "admin@chememan.com", _admin_scope())
    assert result.status == APPROVED
    conn.commit.assert_called_once()


def test_nipaporn_dual_role_submits_her_own_department_uses_normal_chain_not_admin_branch():
    """Nipaporn is in ADMIN_EMAILS but also personally Fills this department
    -> must go through the normal chain (self-skip), never the admin
    direct-approve branch."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        None,                              # _fetch_row
        None,                              # _is_post_deadline
        (NIPAPORN_EMPCODE, WARAPORN_EMPCODE),  # resolve_submitter(nipaporn) -> her manager is Waraporn
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]
    nipaporn_scope = _admin_scope(email="nipapornt@chememan.com", fill_cost_centers=["CC1"])

    result = submit_department(conn, DEPT, FY, "nipapornt@chememan.com", nipaporn_scope)

    assert result.status == PENDING_APPROVER1  # single surviving step (Waraporn)
    assert result.approver1_empcode == WARAPORN_EMPCODE
    assert result.current_approver_empcode == WARAPORN_EMPCODE


# ---------------------------------------------------------------------------
# approve_department
# ---------------------------------------------------------------------------

def test_approve_no_record_raises_not_found():
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = None
    with pytest.raises(ApprovalRecordNotFoundError):
        approve_department(conn, DEPT, FY, "someone@chememan.com")


def test_approve_from_non_pending_status_raises_invalid_state():
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = _status_row(status=APPROVED)
    with pytest.raises(InvalidApprovalStateError):
        approve_department(conn, DEPT, FY, "someone@chememan.com")


def test_approve_wrong_person_is_forbidden():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        _status_row(status=PENDING_APPROVER1, approver1_empcode="200", submitter_empcode="999"),
        ("999", None),  # resolve_submitter(actor) -- this IS the submitter, not the approver
    ]
    with pytest.raises(NotCurrentApproverError):
        approve_department(conn, DEPT, FY, "submitter@chememan.com")
    conn.commit.assert_not_called()


def test_approve_advances_to_next_step():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        _status_row(status=PENDING_APPROVER1, approver1_empcode="200", submitter_empcode="999"),
        ("200", None),  # resolve_submitter(actor) -- matches approver1_empcode
    ]
    cursor.rowcount = 1

    result = approve_department(conn, DEPT, FY, "manager@chememan.com")

    assert result.status == PENDING_APPROVER2
    assert result.approver1_actioned_at is not None
    conn.commit.assert_called_once()


def test_approve_last_step_reaches_approved():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        _status_row(status=PENDING_APPROVER3, approver1_empcode="200", submitter_empcode="999"),
        (WARAPORN_EMPCODE, None),
    ]
    cursor.rowcount = 1

    result = approve_department(conn, DEPT, FY, "warapornt@chememan.com")
    assert result.status == APPROVED


def test_approve_skips_a_dropped_middle_position():
    """approver1_empcode was frozen == NIPAPORN_EMPCODE (invalid-approver1
    fallback) -> active=[1,3]; approving position 1 must jump straight to
    PENDING_APPROVER3, never PENDING_APPROVER2."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        _status_row(status=PENDING_APPROVER1, approver1_empcode=NIPAPORN_EMPCODE, submitter_empcode="999"),
        (NIPAPORN_EMPCODE, None),
    ]
    cursor.rowcount = 1

    result = approve_department(conn, DEPT, FY, "nipapornt@chememan.com")
    assert result.status == PENDING_APPROVER3


def test_approve_concurrent_race_raises_conflict():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        _status_row(status=PENDING_APPROVER1, approver1_empcode="200", submitter_empcode="999"),
        ("200", None),
    ]
    cursor.rowcount = 0  # someone else already actioned this step first

    with pytest.raises(ConcurrentApprovalError):
        approve_department(conn, DEPT, FY, "manager@chememan.com")


# ---------------------------------------------------------------------------
# reject_department
# ---------------------------------------------------------------------------

def test_reject_blank_reason_short_circuits_no_db_call():
    conn = MagicMock()
    with pytest.raises(MissingReasonError):
        reject_department(conn, DEPT, FY, "manager@chememan.com", "   ")
    conn.cursor.assert_not_called()


def test_reject_no_record_raises_not_found():
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = None
    with pytest.raises(ApprovalRecordNotFoundError):
        reject_department(conn, DEPT, FY, "manager@chememan.com", "bad numbers")


def test_reject_wrong_person_is_forbidden():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        _status_row(status=PENDING_APPROVER2, approver1_empcode="200", submitter_empcode="999"),
        ("999", None),  # not Nipaporn
    ]
    with pytest.raises(NotCurrentApproverError):
        reject_department(conn, DEPT, FY, "submitter@chememan.com", "bad numbers")


def test_reject_at_any_step_lands_on_rejected_with_reason():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        _status_row(status=PENDING_APPROVER2, approver1_empcode="200", submitter_empcode="999"),
        (NIPAPORN_EMPCODE, None),
    ]
    cursor.rowcount = 1

    result = reject_department(conn, DEPT, FY, "nipapornt@chememan.com", "numbers are wrong")

    assert result.status == REJECTED
    assert result.reject_reason == "numbers are wrong"
    assert result.rejected_by_empcode == NIPAPORN_EMPCODE
    conn.commit.assert_called_once()


def test_reject_concurrent_race_raises_conflict():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        _status_row(status=PENDING_APPROVER1, approver1_empcode="200", submitter_empcode="999"),
        ("200", None),
    ]
    cursor.rowcount = 0

    with pytest.raises(ConcurrentApprovalError):
        reject_department(conn, DEPT, FY, "manager@chememan.com", "bad")


# ---------------------------------------------------------------------------
# get_approval_status
# ---------------------------------------------------------------------------

def test_get_status_no_record_returns_draft():
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = None
    result = get_approval_status(conn, DEPT, FY)
    assert result.status == "DRAFT"
    assert result.current_position is None


def test_get_status_reports_current_approver_and_can_act():
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = _status_row(
        status=PENDING_APPROVER2, approver1_empcode="200", submitter_empcode="999"
    )
    result = get_approval_status(conn, DEPT, FY, caller_empcode=NIPAPORN_EMPCODE)
    assert result.current_position == 2
    assert result.current_approver_empcode == NIPAPORN_EMPCODE
    assert result.can_act is True

    result2 = get_approval_status(conn, DEPT, FY, caller_empcode="someone-else")
    assert result2.can_act is False


# ---------------------------------------------------------------------------
# authorize_status_view (B1 gate fix — GET /approval/status had no RLS)
# ---------------------------------------------------------------------------

def test_authorize_status_view_admin_bypasses_scope_check_no_db_call():
    conn = MagicMock()
    authorize_status_view(conn, DEPT, _admin_scope())  # must not raise
    conn.cursor.assert_not_called()


def test_authorize_status_view_in_scope_filler_ok():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [("CC1",)]  # department's real cost centers
    authorize_status_view(conn, DEPT, _scope(see_cost_centers=["CC1"]))  # must not raise


def test_authorize_status_view_out_of_scope_raises():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [("CC1",)]  # department's real cost centers
    with pytest.raises(NotAuthorizedToViewDepartmentError):
        authorize_status_view(conn, DEPT, _scope(see_cost_centers=["OTHER-CC"]))


def test_authorize_status_view_unknown_department_raises_the_same_error_as_out_of_scope():
    """A nonexistent department (0 rows in dbo.cc_filler_map) must be
    indistinguishable from a real out-of-scope one -- same exception either
    way, so a caller can never use this endpoint to enumerate departments."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []  # no cost centers found at all
    with pytest.raises(NotAuthorizedToViewDepartmentError):
        authorize_status_view(conn, "NoSuchDepartment", _scope(see_cost_centers=["CC1"]))


# ---------------------------------------------------------------------------
# S1 gate fix — deadline comparison anchored to Asia/Bangkok, not server-local
# ---------------------------------------------------------------------------

def test_is_post_deadline_inclusive_of_deadline_day_itself(monkeypatch: pytest.MonkeyPatch):
    """Pinning the existing inclusive/exclusive semantics: the deadline DAY
    itself is still open (not post-deadline); only the day AFTER it is.

    `_is_post_deadline`/`_bangkok_today` are now imported aliases of
    `app.deadline.is_post_deadline`/`bangkok_today` (extracted so `write_model`
    can reuse the identical check) — patch the real owning module, not the
    alias's origin module, or the monkeypatch has no effect on the imported
    function's own internal call."""
    import app.deadline as deadline_module

    pinned_today = date(2027, 6, 15)
    monkeypatch.setattr(deadline_module, "bangkok_today", lambda: pinned_today)

    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = (pinned_today,)  # deadline == today
    assert _is_post_deadline(conn, FY) is False

    conn2 = MagicMock()
    conn2.cursor.return_value.fetchone.return_value = (date(2027, 6, 14),)  # deadline == yesterday
    assert _is_post_deadline(conn2, FY) is True

    conn3 = MagicMock()
    conn3.cursor.return_value.fetchone.return_value = (date(2027, 6, 16),)  # deadline == tomorrow
    assert _is_post_deadline(conn3, FY) is False


def test_bangkok_today_returns_a_real_date_object():
    assert isinstance(_bangkok_today(), date)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _status_row(
    status: str,
    approver1_empcode: str | None = "200",
    submitter_empcode: str | None = "999",
    reject_reason: str | None = None,
    rejected_by_empcode: str | None = None,
) -> tuple:
    """Build a raw DB row tuple matching app.approval._STATUS_COLUMNS order."""
    now = datetime(2027, 1, 1, tzinfo=timezone.utc)
    return (
        DEPT, FY, status, submitter_empcode, "submitter@chememan.com", now,
        approver1_empcode, None, None, None, reject_reason, rejected_by_empcode, now,
    )


def _row_dict(
    status: str,
    approver1_empcode: str | None = "200",
    submitter_empcode: str | None = "999",
    submitted_at: datetime | None = None,
    approver1_actioned_at: datetime | None = None,
    approver2_actioned_at: datetime | None = None,
) -> dict:
    """Build a row dict in the shape `_fetch_row`/`fetch_pending_rows` return
    (keyed, not a raw tuple) -- used by the A11 job-facing tests below."""
    return {
        "department": DEPT, "fiscal_year": FY, "status": status,
        "submitter_empcode": submitter_empcode, "submitter_email": "submitter@chememan.com",
        "submitted_at": submitted_at or datetime(2027, 1, 1, tzinfo=timezone.utc),
        "approver1_empcode": approver1_empcode,
        "approver1_actioned_at": approver1_actioned_at, "approver2_actioned_at": approver2_actioned_at,
        "approver3_actioned_at": None, "reject_reason": None, "rejected_by_empcode": None,
        "_updated_at": datetime(2027, 1, 1, tzinfo=timezone.utc),
    }


# ---------------------------------------------------------------------------
# A11 — auto_submit_department (jobs/auto_submit.py's entry point)
# ---------------------------------------------------------------------------

def test_auto_submit_department_creates_first_step_and_logs_auto_submit():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        None,                    # _fetch_row -> no existing record (job's discovery already filtered this)
        (date(2020, 1, 1),),     # _is_post_deadline -> already passed
        ("999", "200"),          # resolve_submitter(last_editor_email)
    ]

    result = auto_submit_department(conn, DEPT, FY, "last-editor@chememan.com")

    assert result.status == PENDING_APPROVER1
    assert result.submitter_empcode == "999"
    assert result.submitter_email == "last-editor@chememan.com"
    assert result.approver1_empcode == "200"
    conn.commit.assert_called_once()
    log_call = cursor.execute.call_args_list[-1]
    assert "budget.approval_log" in log_call.args[0]
    assert ACTION_AUTO_SUBMIT in log_call.args


def test_auto_submit_department_raises_if_a_row_already_exists():
    """Defense-in-depth: the job's own discovery query should never call this
    for a department that already has a row, but this must not silently
    overwrite one if it somehow does."""
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = _status_row(status=PENDING_APPROVER1)

    with pytest.raises(InvalidApprovalStateError):
        auto_submit_department(conn, DEPT, FY, "last-editor@chememan.com")
    conn.commit.assert_not_called()


def test_auto_submit_department_concurrent_insert_race_raises_conflict():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [None, (date(2020, 1, 1),), ("999", "200")]
    # 3 dummy calls (_fetch_row, _is_post_deadline, resolve_submitter) then the INSERT raises.
    cursor.execute.side_effect = [None, None, None, pyodbc.IntegrityError("23000", "duplicate key")]

    with pytest.raises(ConcurrentApprovalError):
        auto_submit_department(conn, DEPT, FY, "last-editor@chememan.com")
    conn.commit.assert_not_called()


def test_auto_submit_department_self_skip_still_applies():
    """The last editor IS Nipaporn -> her own self-skip/dedup collapses the
    chain exactly like a normal submit would (ADR-0006 worked example)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [None, (date(2020, 1, 1),), (NIPAPORN_EMPCODE, WARAPORN_EMPCODE)]

    result = auto_submit_department(conn, DEPT, FY, "nipapornt@chememan.com")

    assert result.status == PENDING_APPROVER1  # single surviving step (Waraporn)
    assert result.current_approver_empcode == WARAPORN_EMPCODE


def test_auto_submit_department_raises_when_deadline_not_passed():
    """Defense-in-depth (this task): `jobs/auto_submit.py` already checks
    `is_post_deadline` before calling this function, but the function must
    refuse on its own too — never trust the caller as the only gate."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        None,                # _fetch_row -> no existing record
        (date(2099, 1, 1),),  # _is_post_deadline -> deadline configured, not yet passed
    ]

    with pytest.raises(InvalidApprovalStateError):
        auto_submit_department(conn, DEPT, FY, "last-editor@chememan.com")
    conn.commit.assert_not_called()


# ---------------------------------------------------------------------------
# A11 — auto_escalate_step (jobs/auto_escalate.py's entry point)
# ---------------------------------------------------------------------------

def test_auto_escalate_step_advances_to_next_position_and_logs():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.rowcount = 1
    row = _row_dict(status=PENDING_APPROVER1, approver1_empcode="200", submitter_empcode="999")

    result = auto_escalate_step(conn, DEPT, FY, row)

    assert result.status == PENDING_APPROVER2
    conn.commit.assert_called_once()
    log_call = cursor.execute.call_args_list[-1]
    assert "budget.approval_log" in log_call.args[0]
    assert ACTION_AUTO_ESCALATE in log_call.args


def test_auto_escalate_step_final_active_position_raises_invalid_state():
    """ADR-0006: never a silent jump to APPROVED just because someone was
    slow -- a stuck FINAL step is simply not escalated by this job."""
    conn = MagicMock()
    row = _row_dict(status=PENDING_APPROVER3, approver1_empcode="200", submitter_empcode="999")

    with pytest.raises(InvalidApprovalStateError):
        auto_escalate_step(conn, DEPT, FY, row)
    conn.commit.assert_not_called()


def test_auto_escalate_step_skips_a_dropped_middle_position():
    """active=[1,3] (invalid-approver1 fallback) -- escalating position 1
    must land on PENDING_APPROVER3 directly, same as a real approve would."""
    conn = MagicMock()
    conn.cursor.return_value.rowcount = 1
    row = _row_dict(status=PENDING_APPROVER1, approver1_empcode=NIPAPORN_EMPCODE, submitter_empcode="999")

    result = auto_escalate_step(conn, DEPT, FY, row)
    assert result.status == PENDING_APPROVER3


def test_auto_escalate_step_concurrent_race_raises_conflict():
    conn = MagicMock()
    conn.cursor.return_value.rowcount = 0
    row = _row_dict(status=PENDING_APPROVER1, approver1_empcode="200", submitter_empcode="999")

    with pytest.raises(ConcurrentApprovalError):
        auto_escalate_step(conn, DEPT, FY, row)


# ---------------------------------------------------------------------------
# _current_step_started_at / is_step_stale — the derived "turn start" signal
# (no dedicated per-step timestamp column exists on budget.approval_status;
# flagged in the final report, this is the safest derivation from existing
# columns, never a schema change).
# ---------------------------------------------------------------------------

def test_current_step_started_at_position1_is_submitted_at():
    submitted = datetime(2027, 1, 1, tzinfo=timezone.utc)
    row = _row_dict(status=PENDING_APPROVER1, submitted_at=submitted)
    assert _current_step_started_at(row) == submitted


def test_current_step_started_at_position2_uses_approver1_actioned_at_when_present():
    actioned = datetime(2027, 2, 1, tzinfo=timezone.utc)
    row = _row_dict(status=PENDING_APPROVER2, approver1_actioned_at=actioned)
    assert _current_step_started_at(row) == actioned


def test_current_step_started_at_position2_falls_back_to_submitted_at_when_position1_was_skipped():
    submitted = datetime(2027, 1, 1, tzinfo=timezone.utc)
    row = _row_dict(status=PENDING_APPROVER2, submitted_at=submitted, approver1_actioned_at=None)
    assert _current_step_started_at(row) == submitted


def test_current_step_started_at_position3_walks_back_through_skipped_positions():
    """position 2 was skipped (its actioned_at stays NULL forever) -> falls
    back to position 1's actioned_at, not straight to submitted_at."""
    p1_actioned = datetime(2027, 3, 1, tzinfo=timezone.utc)
    row = _row_dict(
        status=PENDING_APPROVER3, approver1_actioned_at=p1_actioned, approver2_actioned_at=None,
    )
    assert _current_step_started_at(row) == p1_actioned


def test_is_step_stale_true_past_threshold():
    submitted = datetime(2027, 1, 1, tzinfo=timezone.utc)
    row = _row_dict(status=PENDING_APPROVER1, submitted_at=submitted)
    now = submitted + timedelta(days=AUTO_ESCALATE_THRESHOLD_DAYS)
    assert is_step_stale(row, now) is True


def test_is_step_stale_false_before_threshold():
    submitted = datetime(2027, 1, 1, tzinfo=timezone.utc)
    row = _row_dict(status=PENDING_APPROVER1, submitted_at=submitted)
    now = submitted + timedelta(days=AUTO_ESCALATE_THRESHOLD_DAYS - 1)
    assert is_step_stale(row, now) is False


# ---------------------------------------------------------------------------
# fetch_pending_rows — read helper for the auto_escalate job's discovery pass
# ---------------------------------------------------------------------------

def test_fetch_pending_rows_returns_keyed_dicts_for_the_given_year():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchall.return_value = [_status_row(status=PENDING_APPROVER1)]

    rows = fetch_pending_rows(conn, FY)

    assert len(rows) == 1
    assert rows[0]["department"] == DEPT
    assert rows[0]["status"] == PENDING_APPROVER1
    query = cursor.execute.call_args.args[0]
    assert "budget.approval_status" in query
    assert "IN (?, ?, ?)" in query
