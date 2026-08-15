"""Unit tests for app.approval — A6 approval engine. DB always mocked
(`conn.cursor.return_value` is the ONE shared cursor mock, matching the
convention in test_write_model.py / test_rls.py).

Covers: chain resolution (self-skip + dedup + invalid-approver1 fallback,
ADR-0006), submit branch selection (normal chain vs admin direct-approve,
ADR-0012), step-gated approve/reject, reject-then-resubmit restarts the
whole chain, concurrent-approve race protection, and append-only logging.
"""
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pyodbc
import pytest

from app.approval import (
    ACTION_ADMIN_STEP_OVERRIDE,
    ACTION_AUTO_SUBMIT,
    APPROVED,
    DRAFT,
    NIPAPORN_EMPCODE,
    PENDING_APPROVER1,
    PENDING_APPROVER2,
    PENDING_APPROVER3,
    REJECTED,
    WARAPORN_EMPCODE,
    AdminCannotSubmitInCycleError,
    ApprovalRecordNotFoundError,
    ConcurrentApprovalError,
    DepartmentEmptyError,
    InvalidApprovalStateError,
    MidChainAdminOverwriteError,
    MissingReasonError,
    NotAuthorizedToViewDepartmentError,
    NotCurrentApproverError,
    NotFillerOfDepartmentError,
    PastDeadlineError,
    StepNotOverridableError,
    YearNotOpenError,
    _active_positions,
    _bangkok_today,
    _current_step_started_at,
    _department_has_pending_rows,
    _is_post_deadline,
    admin_override_step,
    approve_department,
    authorize_status_view,
    auto_submit_department,
    cost_centers_for_departments,
    departments_pending_for_empcode,
    evaluate_submit_eligibility,
    fetch_pending_rows,
    get_approval_status,
    list_departments_pending_my_approval,
    reject_department,
    resolve_chain,
    submit_department,
)
from app.rls import Scope

DEPT = "Accounting"
FY = 2027

# 2026-08-08 3-state extension: `_submit_normal_chain` now checks
# `_fiscal_year_state` (NOT_OPEN when no dbo.submission_deadline row exists
# at all) BEFORE the pre-existing PAST_DEADLINE check — every "happy path"
# fixture below that used to mock `None` (the old "no row = OPEN" policy)
# for that position now needs a real, not-yet-passed deadline row instead,
# or it would trip the new `YearNotOpenError` refusal. Same convention as
# `test_write_model.py`'s own `_OPEN_DEADLINE`.
_OPEN_DEADLINE = (date(2099, 1, 1),)


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
        (1,),             # _department_has_pending_rows -> has rows
        _OPEN_DEADLINE,   # _fiscal_year_state -> OPEN (row exists, not yet passed)
        ("999", "200"),   # resolve_submitter
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]  # _department_cost_centers

    result = submit_department(conn, DEPT, FY, "filler@chememan.com", _scope(fill_cost_centers=["CC1"]))

    assert result.status == PENDING_APPROVER1
    assert result.submitter_empcode == "999"
    assert result.approver1_empcode == "200"
    assert result.current_position == 1
    conn.commit.assert_called_once()


# ---------------------------------------------------------------------------
# submit_department — admin-GL rows (dbo.gl_group.edit_by='admin') never
# gate the normal chain (ADR-0024). Replaces the removed
# AdminGlInNormalSubmitError guard, which forced an admin-who-Fills into
# _admin_direct_approve whenever the department held an admin-GL pending
# row — stamping the WHOLE department APPROVED and bypassing the real
# approver on the legitimate user-GL rows. Admin-GL rows are approved-on-save
# the instant the admin (Budget dept) saves them (A5's write path) and never
# enter budget.approval_status at all, so submit_department has nothing to
# check about them regardless of `Settings.gl_edit_by_enabled` — a normal
# submit governs only the department's user-GL rows, for BOTH an admin
# filler and a plain non-admin filler.
# ---------------------------------------------------------------------------

def test_submit_admin_filler_routes_normal_chain_admin_gl_rows_never_block_it():
    """An admin who also Fills the department routes through the normal
    chain exactly like any other filler, whether or not the department holds
    pending admin-GL rows — those rows are invisible to this function (it
    never queries budget.pending_budget for GL info at all)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        None,             # _fetch_row -> no existing record
        (1,),             # _department_has_pending_rows -> has rows
        _OPEN_DEADLINE,   # _fiscal_year_state -> OPEN (row exists, not yet passed)
        ("999", "200"),   # resolve_submitter
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]  # _department_cost_centers

    result = submit_department(conn, DEPT, FY, "admin@chememan.com", _admin_scope(fill_cost_centers=["CC1"]))

    assert result.status == PENDING_APPROVER1
    conn.commit.assert_called_once()


def test_submit_non_admin_filler_routes_normal_chain_unaffected():
    """A plain non-admin filler submitting a department is unaffected —
    admin-GL rows can never be theirs to begin with (rule 4: only an admin
    may write one), and submit_department treats them the same as any other
    filler submission either way."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        None,             # _fetch_row -> no existing record
        (1,),             # _department_has_pending_rows -> has rows
        _OPEN_DEADLINE,   # _fiscal_year_state -> OPEN (row exists, not yet passed)
        ("999", "200"),   # resolve_submitter
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]  # _department_cost_centers

    result = submit_department(conn, DEPT, FY, "filler@chememan.com", _scope(fill_cost_centers=["CC1"]))

    assert result.status == PENDING_APPROVER1
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
        (1,),             # _department_has_pending_rows -> has rows
        _OPEN_DEADLINE,   # _fiscal_year_state -> OPEN (row exists, not yet passed)
        ("999", "200"),   # resolve_submitter
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]  # _department_cost_centers
    # 5 dummy calls (_fetch_row, _department_cost_centers, _department_has_pending_rows,
    # _is_post_deadline, resolve_submitter) then the INSERT raises.
    cursor.execute.side_effect = [None, None, None, None, None, pyodbc.IntegrityError("23000", "duplicate key")]

    with pytest.raises(ConcurrentApprovalError):
        submit_department(conn, DEPT, FY, "filler@chememan.com", _scope(fill_cost_centers=["CC1"]))
    conn.commit.assert_not_called()


def test_submit_blocked_while_pending_no_recall():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [_status_row(status=PENDING_APPROVER2), (1,)]  # _fetch_row; _department_has_pending_rows -> has rows
    cursor.fetchall.side_effect = [[("CC1",)]]

    with pytest.raises(InvalidApprovalStateError):
        submit_department(conn, DEPT, FY, "filler@chememan.com", _scope(fill_cost_centers=["CC1"]))
    conn.commit.assert_not_called()


def test_submit_blocked_when_approved_no_reapproval_needed():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [_status_row(status=APPROVED), (1,)]  # _fetch_row; _department_has_pending_rows -> has rows
    cursor.fetchall.side_effect = [[("CC1",)]]

    with pytest.raises(InvalidApprovalStateError):
        submit_department(conn, DEPT, FY, "filler@chememan.com", _scope(fill_cost_centers=["CC1"]))


def test_submit_allowed_after_reject_resubmit_restarts_chain():
    """Also the bug-3 regression guard (2026-08-08): a REJECTED department
    that still HAS pending rows must keep resubmitting normally — the new
    emptiness guard only refuses a department with ZERO rows."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        _status_row(status=REJECTED, reject_reason="fix numbers", rejected_by_empcode="200"),
        (1,),             # _department_has_pending_rows -> still has rows
        _OPEN_DEADLINE,   # _fiscal_year_state -> OPEN
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
        (1,),             # _department_has_pending_rows -> has rows
        _OPEN_DEADLINE,   # _fiscal_year_state -> OPEN
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
        (1,),             # _department_has_pending_rows -> has rows
        _OPEN_DEADLINE,   # _fiscal_year_state -> OPEN
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
    cursor.fetchone.side_effect = [
        None,   # _fetch_row -> no existing record
        (1,),   # _department_has_pending_rows -> has rows
        (date(2020, 1, 1),),  # _is_post_deadline -> already passed
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]

    with pytest.raises(PastDeadlineError):
        submit_department(conn, DEPT, FY, "filler@chememan.com", _scope(fill_cost_centers=["CC1"]))


def test_submit_year_not_open_blocks_normal_user():
    """2026-08-08 product decision: a fiscal_year nobody may fill should not
    be submittable by a filler either — same normal-chain gate as
    PastDeadlineError above, but a DIFFERENT machine error/code (the two
    must never collapse into one, distinct from `test_submit_past_deadline_
    blocks_normal_user` above which pins a row that EXISTS and has passed)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        None,   # _fetch_row -> no existing record
        (1,),   # _department_has_pending_rows -> has rows
        None,   # _fiscal_year_state -> no dbo.submission_deadline row at all -> NOT_OPEN
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]

    with pytest.raises(YearNotOpenError):
        submit_department(conn, DEPT, FY, "filler@chememan.com", _scope(fill_cost_centers=["CC1"]))
    conn.commit.assert_not_called()


def test_submit_year_not_open_also_blocks_an_admin_who_fills_the_department():
    """Same decision, admin-filler side: an admin who ALSO Fills this
    department routes through the identical normal-chain gate (Nipaporn/
    Waraporn's own dual role, ADR-0006) — the 3 admin-ONLY doors
    (Template-2/orphan/post-deadline-override) are a separate branch, only
    reachable when the caller does NOT Fill the department at all."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        None,   # _fetch_row -> no existing record
        (1,),   # _department_has_pending_rows -> has rows
        None,   # _fiscal_year_state -> NOT_OPEN
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]

    with pytest.raises(YearNotOpenError):
        submit_department(conn, DEPT, FY, "admin@chememan.com", _admin_scope(fill_cost_centers=["CC1"]))
    conn.commit.assert_not_called()


def test_submit_forbidden_for_non_filler_non_admin():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        None,   # _fetch_row
        (1,),   # _department_has_pending_rows -> has rows, so the emptiness guard passes and the NotFiller check is reached
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]  # dept has CCs, but caller Fills none of them

    with pytest.raises(NotFillerOfDepartmentError):
        submit_department(conn, DEPT, FY, "outsider@chememan.com", _scope(fill_cost_centers=["OTHER-CC"]))
    conn.commit.assert_not_called()


def test_admin_submit_via_template_2_door_logs_admin_submit():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        None,           # _fetch_row
        (1,),           # _department_has_pending_rows -> has rows (Template-2 always does)
        (1,),           # _department_has_admin_template_rows -> found
        ("500", None),  # resolve_submitter (admin)
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]

    result = submit_department(conn, DEPT, FY, "admin@chememan.com", _admin_scope())

    assert result.status == APPROVED
    assert result.approver1_empcode is None
    insert_sql = cursor.execute.call_args_list[-1].args[0]  # log insert is the last execute before commit
    assert "budget.approval_log" in insert_sql


def test_admin_direct_approve_concurrent_insert_race_raises_conflict_not_pyodbc():
    """P2-B3 prod finding (2026-07-28): two concurrent admin submits, the
    loser's INSERT hits the PK — _admin_direct_approve must map that to
    ConcurrentApprovalError (-> 409) exactly like _insert_new_approval_row,
    never let a raw pyodbc.IntegrityError escape to the router's 502."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        None,           # _fetch_row
        (1,),           # _department_has_pending_rows -> has rows
        (1,),           # _department_has_admin_template_rows -> found
        ("500", None),  # resolve_submitter (admin)
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]
    # 5 dummy calls (_fetch_row, _department_cost_centers, _department_has_pending_rows,
    # _department_has_admin_template_rows, resolve_submitter) then the INSERT raises the PK violation.
    cursor.execute.side_effect = [None, None, None, None, None, pyodbc.IntegrityError("23000", "duplicate key")]

    with pytest.raises(ConcurrentApprovalError):
        submit_department(conn, DEPT, FY, "admin@chememan.com", _admin_scope())
    conn.commit.assert_not_called()


def test_admin_submit_orphan_department_logs_admin_override():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        None,          # _fetch_row
        (1,),          # _department_has_pending_rows -> orphan fallback finds real snapshot rows
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
        (1,),               # _department_has_pending_rows -> has rows
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
        (1,),             # _department_has_pending_rows -> has rows
        None,             # _department_has_admin_template_rows -> none
        None,             # _is_post_deadline -> not passed (admin branch, unaffected by the 2026-08-08 change)
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
        (1,),                                  # _department_has_pending_rows -> has rows
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
        (1,),           # _department_has_pending_rows -> has rows
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
        (1,),                                  # _department_has_pending_rows -> orphan fallback finds real snapshot rows
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
        (1,),           # _department_has_pending_rows -> orphan fallback finds real snapshot rows
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
        (1,),                  # _department_has_pending_rows -> has rows
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
        (1,),                              # _department_has_pending_rows -> has rows
        _OPEN_DEADLINE,                    # _fiscal_year_state -> OPEN
        (NIPAPORN_EMPCODE, WARAPORN_EMPCODE),  # resolve_submitter(nipaporn) -> her manager is Waraporn
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]
    nipaporn_scope = _admin_scope(email="nipapornt@chememan.com", fill_cost_centers=["CC1"])

    result = submit_department(conn, DEPT, FY, "nipapornt@chememan.com", nipaporn_scope)

    assert result.status == PENDING_APPROVER1  # single surviving step (Waraporn)
    assert result.approver1_empcode == WARAPORN_EMPCODE
    assert result.current_approver_empcode == WARAPORN_EMPCODE


# ---------------------------------------------------------------------------
# submit_department — DepartmentEmptyError (bug 3 of the 2026-08-07 confirmed
# wave, reproduced live: Solution Delivery/FY2026, 0 rows -> submit was
# ACCEPTED, locking the department and landing a real request on a real
# approver over an empty grid). Runs BEFORE any admin-door branch and applies
# to every caller identically (jakkaritw, 2026-08-08, option ก).
# ---------------------------------------------------------------------------

def test_submit_department_empty_as_filler_refused():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        None,   # _fetch_row -> no existing record
        None,   # _department_has_pending_rows -> zero rows for CC1
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]  # _department_cost_centers -- department IS live-mapped

    with pytest.raises(DepartmentEmptyError, match="ฝ่ายนี้ยังไม่มีข้อมูลงบประมาณ"):
        submit_department(conn, DEPT, FY, "filler@chememan.com", _scope(fill_cost_centers=["CC1"]))
    conn.commit.assert_not_called()


def test_submit_department_empty_admin_orphan_door_refused():
    """Option ก's actual new coverage: the orphan admin door normally
    reaches `_admin_direct_approve` unconditionally -- with zero cost
    centers AND zero pending_budget rows (the orphan-fallback query), it
    must now be refused instead."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        None,   # _fetch_row
        None,   # _department_has_pending_rows -> orphan fallback finds zero rows
    ]
    cursor.fetchall.side_effect = [[]]  # orphan: zero cost centers for this department

    with pytest.raises(DepartmentEmptyError):
        submit_department(conn, DEPT, FY, "admin@chememan.com", _admin_scope())
    conn.commit.assert_not_called()


def test_submit_department_empty_admin_post_deadline_door_refused():
    """Option ก's other new coverage: the post-deadline door normally
    overrides ANY existing status (ADR-0012) -- it never even gets that far
    here, proving the emptiness guard runs BEFORE the post-deadline check
    (no `_is_post_deadline` call is mocked at all -- if the guard ran later,
    this test would fail with a MagicMock StopIteration, not a clean
    DepartmentEmptyError)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        None,   # _fetch_row
        None,   # _department_has_pending_rows -> zero rows for the department's live CCs
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]  # has real CCs -- not orphan

    with pytest.raises(DepartmentEmptyError):
        submit_department(conn, DEPT, FY, "admin@chememan.com", _admin_scope())
    conn.commit.assert_not_called()


# ---------------------------------------------------------------------------
# evaluate_submit_eligibility — read-only mirror of submit_department's
# decision tree (SIT defect fix #2, 2026-08-16, sibling of the 2026-08-14
# `is_post_deadline` fix). Every submit_department test above already proves
# the WRITE path decides these branches correctly (that part was never
# broken) -- these pin the READ-ONLY `can_submit`/`reason` verdict the
# frontend button now consumes instead of re-deriving admin authorization
# client-side. Covers all 4 admin shapes from the SIT defect explicitly,
# plus the filler paths and the already-fixed mid-chain case (77308d7), so
# neither can regress alone.
# ---------------------------------------------------------------------------

def test_eligibility_admin_blocked_not_filler_not_orphan_no_template2_cycle_open():
    """Shape (a) -- THE bug: a non-filler admin, department not orphan, no
    Template-2 rows, cycle still open, DRAFT -- the old client-side
    canSubmit() always showed Submit here; the write path already refused it
    (AdminCannotSubmitInCycleError, proven by
    test_admin_cannot_submit_normal_in_cycle_department_they_do_not_fill
    above). This is the READ verdict the button now reads instead."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        None,   # _fetch_row -> DRAFT (never submitted)
        (1,),   # _department_has_pending_rows -> has rows
        None,   # _department_has_admin_template_rows -> none
        None,   # _is_post_deadline -> not passed
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]  # has real CCs -- not orphan

    result = evaluate_submit_eligibility(conn, DEPT, FY, "admin@chememan.com", _admin_scope())

    assert result.can_submit is False
    assert result.reason == "admin_cannot_submit_in_cycle"


def test_eligibility_admin_allowed_orphan_department():
    """Shape (b)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        None,   # _fetch_row
        (1,),   # _department_has_pending_rows -> orphan fallback finds real rows
        None,   # _department_has_admin_template_rows -> none
    ]
    cursor.fetchall.side_effect = [[]]  # orphan: zero cost centers for this department

    result = evaluate_submit_eligibility(conn, DEPT, FY, "admin@chememan.com", _admin_scope())

    assert result.can_submit is True
    assert result.reason is None


def test_eligibility_admin_allowed_template_2_rows_present():
    """Shape (c)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        None,   # _fetch_row
        (1,),   # _department_has_pending_rows -> has rows
        (1,),   # _department_has_admin_template_rows -> found
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]

    result = evaluate_submit_eligibility(conn, DEPT, FY, "admin@chememan.com", _admin_scope())

    assert result.can_submit is True
    assert result.reason is None


def test_eligibility_admin_allowed_post_deadline_override_any_status():
    """Shape (d) -- proven against a LOCKED existing status too (the
    post-deadline door overrides ANY status, ADR-0012)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        _status_row(status=PENDING_APPROVER2),  # _fetch_row -- locked, still overridden
        (1,),                    # _department_has_pending_rows -> has rows
        None,                    # _department_has_admin_template_rows -> none
        (date(2020, 1, 1),),      # _is_post_deadline -> already passed
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]  # has real CCs -- not orphan

    result = evaluate_submit_eligibility(conn, DEPT, FY, "admin@chememan.com", _admin_scope())

    assert result.can_submit is True
    assert result.reason is None


def test_eligibility_admin_template2_blocked_when_existing_is_mid_chain():
    """B2 guard, read side: Template-2 door blocked from overwriting a
    mid-chain/approved record -- same guard the write path enforces."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        _status_row(status=PENDING_APPROVER2),  # _fetch_row -- existing mid-chain
        (1,),   # _department_has_pending_rows -> has rows
        (1,),   # _department_has_admin_template_rows -> found
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]

    result = evaluate_submit_eligibility(conn, DEPT, FY, "admin@chememan.com", _admin_scope())

    assert result.can_submit is False
    assert result.reason == "mid_chain_admin_overwrite"


def test_eligibility_non_filler_non_admin_blocked():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [None, (1,)]  # _fetch_row; _department_has_pending_rows -> has rows
    cursor.fetchall.side_effect = [[("CC1",)]]  # dept has CCs, caller Fills none of them

    result = evaluate_submit_eligibility(conn, DEPT, FY, "outsider@chememan.com", _scope(fill_cost_centers=["OTHER-CC"]))

    assert result.can_submit is False
    assert result.reason == "not_filler_of_department"


def test_eligibility_department_empty_blocked_for_any_caller():
    """Runs BEFORE the filler/admin branch split, exactly like
    `submit_department`'s own DepartmentEmptyError guard."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [None, None]  # _fetch_row; _department_has_pending_rows -> zero rows
    cursor.fetchall.side_effect = [[("CC1",)]]

    result = evaluate_submit_eligibility(conn, DEPT, FY, "filler@chememan.com", _scope(fill_cost_centers=["CC1"]))

    assert result.can_submit is False
    assert result.reason == "department_empty"


def test_eligibility_filler_draft_allowed():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        None,             # _fetch_row
        (1,),             # _department_has_pending_rows -> has rows
        _OPEN_DEADLINE,   # _fiscal_year_state -> OPEN
    ]
    cursor.fetchall.side_effect = [[("CC1",)]]

    result = evaluate_submit_eligibility(conn, DEPT, FY, "filler@chememan.com", _scope(fill_cost_centers=["CC1"]))

    assert result.can_submit is True
    assert result.reason is None


def test_eligibility_filler_mid_chain_blocked_regression_guard_77308d7():
    """Regression guard for the 2026-08-14 fix (77308d7): a filler must never
    be told Submit is available once mid-chain -- no recall (ADR-0006)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [_status_row(status=PENDING_APPROVER1), (1,)]
    cursor.fetchall.side_effect = [[("CC1",)]]

    result = evaluate_submit_eligibility(conn, DEPT, FY, "filler@chememan.com", _scope(fill_cost_centers=["CC1"]))

    assert result.can_submit is False
    assert result.reason == "invalid_approval_state"


def test_eligibility_filler_year_not_open_blocked():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [None, (1,), None]  # _fiscal_year_state -> NOT_OPEN
    cursor.fetchall.side_effect = [[("CC1",)]]

    result = evaluate_submit_eligibility(conn, DEPT, FY, "filler@chememan.com", _scope(fill_cost_centers=["CC1"]))

    assert result.can_submit is False
    assert result.reason == "year_not_open"


def test_eligibility_filler_past_deadline_blocked():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [None, (1,), (date(2020, 1, 1),)]
    cursor.fetchall.side_effect = [[("CC1",)]]

    result = evaluate_submit_eligibility(conn, DEPT, FY, "filler@chememan.com", _scope(fill_cost_centers=["CC1"]))

    assert result.can_submit is False
    assert result.reason == "past_deadline"


def test_department_has_pending_rows_query_shape_live_cost_centers():
    """>=1 live cost center -> scoped to `cost_center IN (...)`, never to
    the `pending_budget.department` snapshot column (D2 live-first policy)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.return_value = (1,)

    result = _department_has_pending_rows(conn, DEPT, {"CC1", "CC2"}, FY)

    assert result is True
    sql, *params = cursor.execute.call_args.args
    assert "budget.pending_budget" in sql
    assert "fiscal_year = ?" in sql
    assert "cost_center IN" in sql
    assert "department" not in sql  # must NOT touch the snapshot column here
    assert sql.count("?") == 3  # fiscal_year + 2 cost centers
    assert params[0] == FY
    assert set(params[1:]) == {"CC1", "CC2"}
    cursor.close.assert_called_once()


def test_department_has_pending_rows_orphan_fallback_query_shape():
    """Zero live cost centers (orphan department) -> falls back to the
    `pending_budget.department` snapshot column -- the only way to see an
    orphan department's real, pre-existing rows (same query shape as
    `_department_has_admin_template_rows`, minus its template filter)."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.return_value = None

    result = _department_has_pending_rows(conn, DEPT, set(), FY)

    assert result is False
    sql, *params = cursor.execute.call_args.args
    assert "WHERE department = ? AND fiscal_year = ?" in sql
    assert params == [DEPT, FY]
    cursor.close.assert_called_once()


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
# ADR-0027 — admin_override_step (POST /approval/override-step)
# ---------------------------------------------------------------------------

def test_override_step_advances_one_step_stamps_and_logs_admin():
    """Override on PENDING_APPROVER1 with an active position 2 -> lands on
    PENDING_APPROVER2, stamps approver1_actioned_at, and writes exactly ONE
    ADMIN_STEP_OVERRIDE log row carrying the acting admin's real email."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        _status_row(status=PENDING_APPROVER1, approver1_empcode="200", submitter_empcode="999"),
        ("500", None),  # resolve_submitter(admin)
    ]
    cursor.rowcount = 1

    result = admin_override_step(conn, DEPT, FY, "admin@chememan.com")

    assert result.status == PENDING_APPROVER2
    assert result.approver1_actioned_at is not None
    conn.commit.assert_called_once()
    log_calls = [c for c in cursor.execute.call_args_list if "budget.approval_log" in c.args[0]]
    assert len(log_calls) == 1
    assert ACTION_ADMIN_STEP_OVERRIDE in log_calls[0].args
    assert "admin@chememan.com" in log_calls[0].args


def test_override_step_refused_when_position_1_is_the_only_active_position():
    """ADR-0027: an override may NEVER land APPROVED — a ฝ่าย whose chain
    collapsed to position 1 only (here: approver1 == Nipaporn dedups
    position 2, submitter == Waraporn self-skips position 3) is refused,
    status unchanged, no log row.

    Flagged (2026-08-02): collapsing to `active == [1]` REQUIRES approver1 to
    be Nipaporn or Waraporn, so the occupant check above always fires first —
    this test therefore pins the refusal, not which of the two guards produced
    it. The `idx == len(active) - 1` branch is unreachable defense-in-depth."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        _status_row(status=PENDING_APPROVER1, approver1_empcode=NIPAPORN_EMPCODE,
                    submitter_empcode=WARAPORN_EMPCODE),
        ("นิภาพร ทองกิ่ง",),  # lookup_employee_name for the refusal message
    ]

    with pytest.raises(StepNotOverridableError):
        admin_override_step(conn, DEPT, FY, "admin@chememan.com")
    conn.commit.assert_not_called()
    assert not [c for c in cursor.execute.call_args_list if "budget.approval_log" in c.args[0]]
    assert not [c for c in cursor.execute.call_args_list if "UPDATE budget.approval_status" in c.args[0]]


@pytest.mark.parametrize("status", [PENDING_APPROVER2, PENDING_APPROVER3])
def test_override_step_refused_on_budget_dept_positions_2_and_3(status):
    """ADR-0027 D4: positions 2/3 (Nipaporn/Waraporn = the budget-dept review
    itself) can never be overridden by anyone — an error, not a no-op."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [_status_row(status=status)]

    with pytest.raises(StepNotOverridableError):
        admin_override_step(conn, DEPT, FY, "admin@chememan.com")
    conn.commit.assert_not_called()


@pytest.mark.parametrize("status", ["DRAFT", APPROVED, REJECTED])
def test_override_step_on_non_pending_status_raises_invalid_state(status):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [_status_row(status=status)]

    with pytest.raises(InvalidApprovalStateError):
        admin_override_step(conn, DEPT, FY, "admin@chememan.com")
    conn.commit.assert_not_called()


def test_override_step_no_record_raises_not_found():
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = None
    with pytest.raises(ApprovalRecordNotFoundError):
        admin_override_step(conn, DEPT, FY, "admin@chememan.com")


def test_override_step_concurrent_race_raises_conflict_no_log_row():
    """Same conditional-UPDATE race guard as a real approve: the record's
    status moved between read and write -> ConcurrentApprovalError, and the
    log insert is never reached."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        _status_row(status=PENDING_APPROVER1, approver1_empcode="200", submitter_empcode="999"),
        ("500", None),  # resolve_submitter(admin)
    ]
    cursor.rowcount = 0  # someone else already actioned this step first

    with pytest.raises(ConcurrentApprovalError):
        admin_override_step(conn, DEPT, FY, "admin@chememan.com")
    conn.commit.assert_not_called()
    assert not [c for c in cursor.execute.call_args_list if "budget.approval_log" in c.args[0]]


def test_override_step_admin_without_employee_row_logs_none_empcode_real_email():
    """ADR-0027: an admin with no v_employee_budget_01 row (e.g. jakkaritw)
    still overrides — the log carries by_empcode=NULL and the real email,
    never a `system:` literal."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        _status_row(status=PENDING_APPROVER1, approver1_empcode="200", submitter_empcode="999"),
        None,  # resolve_submitter(admin) -> not found
    ]
    cursor.rowcount = 1

    result = admin_override_step(conn, DEPT, FY, "jakkaritw@chememan.com")

    assert result.status == PENDING_APPROVER2
    log_call = [c for c in cursor.execute.call_args_list if "budget.approval_log" in c.args[0]][0]
    # args: (sql, department, fiscal_year, action, by_empcode, by_email, now, prev, new, comment)
    assert log_call.args[3] == ACTION_ADMIN_STEP_OVERRIDE
    assert log_call.args[4] is None
    assert log_call.args[5] == "jakkaritw@chememan.com"


def test_override_step_refused_when_position_1_occupant_is_nipaporn():
    """Review hardening: dedup can place Nipaporn (budget dept) directly in
    the position-1 SLOT (her manager IS Nipaporn -> position 2 dedups away),
    status still reads PENDING_APPROVER1. The slot number alone must not be
    enough -- this is D4's protected review, just reached via position 1.
    active = [1, 3] here (verified against real _active_positions), so
    without the occupant check the override would succeed and land
    PENDING_APPROVER3, silently skipping Nipaporn's review."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        _status_row(status=PENDING_APPROVER1, approver1_empcode=NIPAPORN_EMPCODE, submitter_empcode="999"),
        ("นิภาพร ทองกิ่ง",),  # lookup_employee_name for the refusal message
    ]

    with pytest.raises(StepNotOverridableError) as exc:
        admin_override_step(conn, DEPT, FY, "admin@chememan.com")
    # The message must NAME the blocking approver, not just describe the rule.
    assert "นิภาพร ทองกิ่ง" in str(exc.value)
    conn.commit.assert_not_called()
    assert not [c for c in cursor.execute.call_args_list if "budget.approval_log" in c.args[0]]
    assert not [c for c in cursor.execute.call_args_list if "UPDATE budget.approval_status" in c.args[0]]


def test_override_step_refused_when_position_1_occupant_is_waraporn():
    """Same hardening, Waraporn: active = [1, 2] (verified against real
    _active_positions) -- without the occupant check the override would
    succeed and land PENDING_APPROVER2, silently skipping Waraporn's review."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        _status_row(status=PENDING_APPROVER1, approver1_empcode=WARAPORN_EMPCODE, submitter_empcode="999"),
        ("วราภรณ์",),  # lookup_employee_name for the refusal message
    ]

    with pytest.raises(StepNotOverridableError):
        admin_override_step(conn, DEPT, FY, "admin@chememan.com")
    conn.commit.assert_not_called()
    assert not [c for c in cursor.execute.call_args_list if "budget.approval_log" in c.args[0]]
    assert not [c for c in cursor.execute.call_args_list if "UPDATE budget.approval_status" in c.args[0]]


def test_override_step_still_allowed_for_an_ordinary_manager():
    """Guard against over-tightening: an ordinary manager (not Nipaporn/
    Waraporn) occupying position 1 must still be overridable -- the new
    occupant check must not lock out the normal, intended case."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = [
        _status_row(status=PENDING_APPROVER1, approver1_empcode="200", submitter_empcode="999"),
        ("500", None),  # resolve_submitter(admin)
    ]
    cursor.rowcount = 1

    result = admin_override_step(conn, DEPT, FY, "admin@chememan.com")

    assert result.status == PENDING_APPROVER2
    conn.commit.assert_called_once()


def test_auto_escalate_symbols_removed_from_approval_module():
    """ADR-0027 D1: the 30-day auto-escalation is DELETED outright — none of
    its symbols may remain importable from app.approval."""
    import app.approval as approval_module

    for name in (
        "auto_escalate_step", "is_step_stale", "ACTION_AUTO_ESCALATE",
        "AUTO_ESCALATE_THRESHOLD_DAYS", "AUTO_ESCALATE_ACTOR_EMAIL",
    ):
        assert not hasattr(approval_module, name), f"{name} must be deleted (ADR-0027)"


# ---------------------------------------------------------------------------
# _current_step_started_at — the derived "turn start" signal (no dedicated
# per-step timestamp column exists on budget.approval_status; flagged in the
# final report, this is the safest derivation from existing columns, never a
# schema change). The 7-day turn-reminder cadence anchors on it (ADR-0027).
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


# ---------------------------------------------------------------------------
# fetch_pending_rows — read helper for the send_reminders job's discovery pass
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


# ---------------------------------------------------------------------------
# list_departments_pending_my_approval — A10 รออนุมัติ badge data source
# ---------------------------------------------------------------------------

def test_pending_for_me_returns_departments_where_caller_is_current_approver():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    # resolve_submitter(caller) -> empcode "200" (matches approver1_empcode below)
    cursor.fetchone.return_value = ("200", None)
    cursor.fetchall.return_value = [
        _status_row(status=PENDING_APPROVER1, approver1_empcode="200"),
    ]

    result = list_departments_pending_my_approval(conn, FY, "manager@chememan.com")

    assert result == [DEPT]


def test_pending_for_me_excludes_departments_not_at_callers_step():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.return_value = ("200", None)
    cursor.fetchall.return_value = [
        _status_row(status=PENDING_APPROVER2, approver1_empcode="200"),  # caller was approver1, already passed
    ]

    result = list_departments_pending_my_approval(conn, FY, "manager@chememan.com")

    assert result == []


def test_pending_for_me_empty_when_caller_not_in_employee_view():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.return_value = None  # resolve_submitter -> (None, None)

    result = list_departments_pending_my_approval(conn, FY, "outsider@chememan.com")

    assert result == []
    cursor.fetchall.assert_not_called()  # short-circuits before fetch_pending_rows even queries


def test_pending_for_me_matches_nipaporn_on_position_2_regardless_of_approver1():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.return_value = (NIPAPORN_EMPCODE, None)
    cursor.fetchall.return_value = [
        _status_row(status=PENDING_APPROVER2, approver1_empcode="999999"),  # some other manager
    ]

    result = list_departments_pending_my_approval(conn, FY, "nipapornt@chememan.com")

    assert result == [DEPT]


def test_pending_for_me_still_scoped_to_the_given_fiscal_year_after_refactor():
    """`list_departments_pending_my_approval` now delegates to
    `departments_pending_for_empcode` (shared with `rls.resolve_scope`'s
    ADR-0029 See-overlay, which deliberately spans ANY year) — this pins that
    the A10 badge itself must stay scoped to ONE `fiscal_year` at the SQL
    layer, unaffected by that sharing."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.return_value = ("200", None)
    cursor.fetchall.return_value = []

    list_departments_pending_my_approval(conn, FY, "manager@chememan.com")

    query = cursor.execute.call_args_list[-1].args[0]
    assert "fiscal_year = ?" in query


# ---------------------------------------------------------------------------
# departments_pending_for_empcode / cost_centers_for_departments — shared
# helpers behind BOTH list_departments_pending_my_approval (A10, one year)
# and rls.resolve_scope's See-overlay (ADR-0029, any year)
# ---------------------------------------------------------------------------

def test_departments_pending_for_empcode_any_year_has_no_year_filter_in_sql():
    """`fiscal_year=None` (the overlay's call shape) must not scope the query
    to a single year -- a department pending in ANY fiscal_year is picked up."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchall.return_value = [_status_row(status=PENDING_APPROVER1, approver1_empcode="200")]

    result = departments_pending_for_empcode(conn, "200")

    assert result == [DEPT]
    query = cursor.execute.call_args.args[0]
    assert "WHERE status IN (?, ?, ?)" in query
    assert "fiscal_year = ?" not in query


def test_departments_pending_for_empcode_a_row_pending_in_a_different_year_still_matches():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    row = list(_status_row(status=PENDING_APPROVER1, approver1_empcode="200"))
    row[1] = 2099  # fiscal_year -- deliberately not FY (2027)
    cursor.fetchall.return_value = [tuple(row)]

    assert departments_pending_for_empcode(conn, "200") == [DEPT]


@pytest.mark.parametrize("status", [APPROVED, REJECTED, DRAFT])
def test_departments_pending_for_empcode_excludes_non_pending_statuses(status):
    """Belt-and-braces: even if a non-PENDING_* row somehow reached this
    function (the real SQL already filters `status IN PENDING_STATUSES`),
    `_to_state` resolves no current_position for it, so `can_act` is False."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [_status_row(status=status, approver1_empcode="200")]

    assert departments_pending_for_empcode(conn, "200") == []


def test_departments_pending_for_empcode_excludes_someone_elses_turn():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [
        _status_row(status=PENDING_APPROVER1, approver1_empcode="999999"),
    ]

    assert departments_pending_for_empcode(conn, "200") == []


def test_cost_centers_for_departments_empty_input_makes_no_query():
    conn = MagicMock()

    assert cost_centers_for_departments(conn, []) == set()
    conn.cursor.assert_not_called()


def test_cost_centers_for_departments_queries_live_cc_filler_map():
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchall.return_value = [("CC1",), ("CC2",)]

    result = cost_centers_for_departments(conn, ["Solution Delivery", "IT"])

    assert result == {"CC1", "CC2"}
    query = cursor.execute.call_args.args[0]
    assert "cc_filler_map" in query
    assert "IN (?, ?)" in query
