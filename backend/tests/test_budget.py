"""Unit tests for GET /budget, GET /budget/export and GET /budget/sap-coverage
— DB always mocked, no live connection."""
import logging
from contextlib import contextmanager, ExitStack
from datetime import date
from io import BytesIO
from unittest.mock import ANY, MagicMock, patch

from openpyxl import load_workbook
import pyodbc
import pytest

from app.auth import get_current_user_email
from app.budget_xlsx import SummaryRow
from app.main import app
from app.read_model import BoardLayer, BudgetRow, PendingLayer, SapLayer
from app.rls import Scope
from app.sap import SapActualsFetchError, SapCoverage

_GENERIC_502_DETAIL = "SAP actuals unavailable, please try again later"


def _override_auth(email: str) -> None:
    app.dependency_overrides[get_current_user_email] = lambda: email


def test_budget_401_without_auth_header(client):
    response = client.get("/budget?year=2027")
    assert response.status_code == 401


def test_budget_422_when_year_missing(client):
    _override_auth("user@chememan.com")
    response = client.get("/budget")
    assert response.status_code == 422


def test_budget_returns_merged_rows_for_authenticated_user(client):
    _override_auth("filler@chememan.com")
    fake_scope = Scope(
        email="filler@chememan.com", is_admin=False, role="filler",
        fill_cost_centers=["CC1"], see_cost_centers=["CC1"],
    )
    fake_rows = [BudgetRow(cost_center="CC1", gl_account="GL1", editable=True)]
    with patch("app.routers.budget.get_fabric_conn") as mock_fabric, patch(
        "app.routers.budget.get_gold_conn"
    ) as mock_gold, patch("app.routers.budget.resolve_scope", return_value=fake_scope), patch(
        "app.routers.budget.get_budget_grid", return_value=fake_rows
    ) as mock_grid:
        mock_fabric.return_value.__enter__.return_value = MagicMock()
        mock_gold.return_value.__enter__.return_value = MagicMock()
        response = client.get("/budget?year=2027")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["cost_center"] == "CC1"
    assert body[0]["editable"] is True
    _, kwargs = mock_grid.call_args
    assert kwargs["planning_year"] == 2027


def test_budget_passes_admin_view_enabled_and_filters_through(client):
    _override_auth("admin@chememan.com")
    fake_scope = Scope(email="admin@chememan.com", is_admin=True, role="admin", fill_cost_centers=[], see_cost_centers=[])
    with patch("app.routers.budget.get_fabric_conn") as mock_fabric, patch(
        "app.routers.budget.get_gold_conn"
    ) as mock_gold, patch("app.routers.budget.resolve_scope", return_value=fake_scope), patch(
        "app.routers.budget.get_budget_grid", return_value=[]
    ) as mock_grid:
        mock_fabric.return_value.__enter__.return_value = MagicMock()
        mock_gold.return_value.__enter__.return_value = MagicMock()
        response = client.get(
            "/budget?year=2027&admin_view_enabled=true&cost_center=CC1&department=%E0%B8%9D%E0%B9%88%E0%B8%B2%E0%B8%A2A"
        )

    assert response.status_code == 200
    _, kwargs = mock_grid.call_args
    assert kwargs["admin_view_enabled"] is True
    assert kwargs["cost_center_filter"] == "CC1"
    assert kwargs["department_filter"] == "ฝ่ายA"


def test_budget_admin_view_enabled_defaults_to_false(client):
    _override_auth("user@chememan.com")
    fake_scope = Scope(email="user@chememan.com", is_admin=False, role="filler", fill_cost_centers=[], see_cost_centers=[])
    with patch("app.routers.budget.get_fabric_conn") as mock_fabric, patch(
        "app.routers.budget.get_gold_conn"
    ) as mock_gold, patch("app.routers.budget.resolve_scope", return_value=fake_scope), patch(
        "app.routers.budget.get_budget_grid", return_value=[]
    ) as mock_grid:
        mock_fabric.return_value.__enter__.return_value = MagicMock()
        mock_gold.return_value.__enter__.return_value = MagicMock()
        response = client.get("/budget?year=2027")

    assert response.status_code == 200
    _, kwargs = mock_grid.call_args
    assert kwargs["admin_view_enabled"] is False


def test_budget_sap_failure_returns_502_not_a_silent_empty_grid(client):
    """Never-cut: a failed SAP read-through must be a loud error, never a
    200 with an empty/partial grid. The raw exception message must NOT leak
    to the client (gate finding #2) — only a generic detail, matching the
    `health.py` pattern ("never leaks connection details")."""
    _override_auth("filler@chememan.com")
    fake_scope = Scope(email="filler@chememan.com", is_admin=False, role="filler", fill_cost_centers=["CC1"], see_cost_centers=["CC1"])
    with patch("app.routers.budget.get_fabric_conn") as mock_fabric, patch(
        "app.routers.budget.get_gold_conn"
    ) as mock_gold, patch("app.routers.budget.resolve_scope", return_value=fake_scope), patch(
        "app.routers.budget.get_budget_grid", side_effect=SapActualsFetchError("DW unreachable, grant revoked")
    ):
        mock_fabric.return_value.__enter__.return_value = MagicMock()
        mock_gold.return_value.__enter__.return_value = MagicMock()
        response = client.get("/budget?year=2027")

    assert response.status_code == 502
    body = response.json()
    assert body["detail"] == _GENERIC_502_DETAIL
    assert "DW unreachable" not in response.text
    assert "grant revoked" not in response.text


def test_budget_db_error_during_scope_resolution_returns_502_not_500(client):
    """`resolve_scope` used to run OUTSIDE the try/except — a pyodbc.Error
    while resolving RLS scope propagated uncaught (HTTP 500), violating the
    read-path contract that any Fabric SQL failure on this read is a 502."""
    _override_auth("filler@chememan.com")
    with patch("app.routers.budget.get_fabric_conn") as mock_fabric, patch(
        "app.routers.budget.resolve_scope",
        side_effect=pyodbc.Error("08S01", "connection reset during scope resolution"),
    ):
        mock_fabric.return_value.__enter__.return_value = MagicMock()
        response = client.get("/budget?year=2027")

    assert response.status_code == 502
    assert response.json()["detail"] == _GENERIC_502_DETAIL
    assert "connection reset" not in response.text


def test_budget_raw_pyodbc_error_also_returns_502_generic_detail(client):
    """A raw `pyodbc.Error` (not wrapped in `SapActualsFetchError`) reaching
    the handler — e.g. a connection drop inside the local board/pending
    join — must also surface as a loud 502 with the same generic detail,
    never a silent empty grid and never the raw driver message."""
    _override_auth("filler@chememan.com")
    fake_scope = Scope(email="filler@chememan.com", is_admin=False, role="filler", fill_cost_centers=["CC1"], see_cost_centers=["CC1"])
    with patch("app.routers.budget.get_fabric_conn") as mock_fabric, patch(
        "app.routers.budget.get_gold_conn"
    ) as mock_gold, patch("app.routers.budget.resolve_scope", return_value=fake_scope), patch(
        "app.routers.budget.get_budget_grid",
        side_effect=pyodbc.Error("08S01", "connection reset by peer"),
    ):
        mock_fabric.return_value.__enter__.return_value = MagicMock()
        mock_gold.return_value.__enter__.return_value = MagicMock()
        response = client.get("/budget?year=2027")

    assert response.status_code == 502
    body = response.json()
    assert body["detail"] == _GENERIC_502_DETAIL
    assert "connection reset by peer" not in response.text


# ---------------------------------------------------------------------------
# GET /budget/export — issue #35 "ดาวน์โหลด Excel". Seam A: the grid
# orchestrator, scope resolver, and enrichment reads are all replaced by
# fakes; `build_export_workbook` itself runs for real so the returned bytes
# are a genuine workbook, opened here with openpyxl.
# ---------------------------------------------------------------------------
@contextmanager
def _export_mocks():
    """Patches every seam-A fake for `GET /budget/export` at once
    (`get_fabric_conn`/`get_gold_conn`/`resolve_scope`/`get_budget_grid`/
    `build_export_summary_rows`/`resolve_sap_coverage_cached`), yielding a
    name -> Mock dict. `build_export_workbook` is deliberately left real."""
    with patch("app.routers.budget.get_fabric_conn") as get_fabric_conn, patch(
        "app.routers.budget.get_gold_conn"
    ) as get_gold_conn, patch("app.routers.budget.resolve_scope") as resolve_scope, patch(
        "app.routers.budget.get_budget_grid"
    ) as get_budget_grid, patch(
        "app.routers.budget.build_export_summary_rows"
    ) as build_export_summary_rows, patch(
        "app.routers.budget.resolve_sap_coverage_cached"
    ) as resolve_sap_coverage_cached:
        yield {
            "get_fabric_conn": get_fabric_conn,
            "get_gold_conn": get_gold_conn,
            "resolve_scope": resolve_scope,
            "get_budget_grid": get_budget_grid,
            "build_export_summary_rows": build_export_summary_rows,
            "resolve_sap_coverage_cached": resolve_sap_coverage_cached,
        }


def _fake_summary_row(**overrides) -> SummaryRow:
    base = dict(
        cost_center="10CS010000", gl_account="5211800030", department="Corporate Strategy 2",
        division="Strategy Division", c_level="CEO", cc_name="Strategy CC", gl_name="Office expenses",
        gl_group="Office", side="COST", status_label="อนุมัติแล้ว",
        months=(100.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0), total_year=100.0,
        board_total_year=50.0, sap_total_year=25.0, remark="", detail_lines=(),
    )
    base.update(overrides)
    return SummaryRow(**base)


def test_budget_export_401_without_auth_header(client):
    response = client.get("/budget/export?year=2027&department=Corporate+Strategy+2")
    assert response.status_code == 401


def test_budget_export_422_when_department_missing(client):
    _override_auth("user@chememan.com")
    response = client.get("/budget/export?year=2027")
    assert response.status_code == 422


def test_budget_export_returns_a_real_workbook_with_the_correct_headers(client):
    _override_auth("filler@chememan.com")
    fake_scope = Scope(email="filler@chememan.com", is_admin=False, role="filler", fill_cost_centers=["CC1"], see_cost_centers=["CC1"])
    fake_budget_rows = [BudgetRow(cost_center="10CS010000", gl_account="5211800030", department="Corporate Strategy 2", editable=True)]
    fake_summary_rows = [_fake_summary_row()]

    with _export_mocks() as mocks:
        mocks["get_fabric_conn"].return_value.__enter__.return_value = MagicMock()
        mocks["get_gold_conn"].return_value.__enter__.return_value = MagicMock()
        mocks["resolve_scope"].return_value = fake_scope
        mocks["get_budget_grid"].return_value = fake_budget_rows
        mocks["build_export_summary_rows"].return_value = fake_summary_rows
        mocks["resolve_sap_coverage_cached"].return_value = SapCoverage(
            fiscal_year=2026, watermark_date=date(2026, 9, 21), days_behind=1, is_stale=False,
        )
        response = client.get("/budget/export?year=2027&department=Corporate+Strategy+2")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert "filename=" in disposition and "filename*=UTF-8''" in disposition

    wb = load_workbook(BytesIO(response.content))
    ws = wb.active
    assert ws["A1"].value.startswith("งบประมาณ FY2027")
    assert "ฝ่าย: Corporate Strategy 2" in ws["A1"].value
    assert ws.cell(row=5, column=4).value == "10CS010000"  # SummaryRow parity with the fake grid row


def test_budget_export_non_ascii_department_name_reaches_filename_star(client):
    _override_auth("filler@chememan.com")
    fake_scope = Scope(email="filler@chememan.com", is_admin=False, role="filler", fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    with _export_mocks() as mocks:
        mocks["get_fabric_conn"].return_value.__enter__.return_value = MagicMock()
        mocks["get_gold_conn"].return_value.__enter__.return_value = MagicMock()
        mocks["resolve_scope"].return_value = fake_scope
        mocks["get_budget_grid"].return_value = []
        mocks["build_export_summary_rows"].return_value = []
        mocks["resolve_sap_coverage_cached"].return_value = SapCoverage(
            fiscal_year=2026, watermark_date=None, days_behind=None, is_stale=True,
        )
        response = client.get(
            "/budget/export?year=2027&department=%E0%B8%9D%E0%B9%88%E0%B8%B2%E0%B8%A2A"
        )

    assert response.status_code == 200
    assert "filename*=UTF-8''" in response.headers["content-disposition"]


def test_budget_export_passes_year_department_admin_view_and_cost_center_through(client):
    _override_auth("admin@chememan.com")
    fake_scope = Scope(email="admin@chememan.com", is_admin=True, role="admin", fill_cost_centers=[], see_cost_centers=[])

    with _export_mocks() as mocks:
        mocks["get_fabric_conn"].return_value.__enter__.return_value = MagicMock()
        mocks["get_gold_conn"].return_value.__enter__.return_value = MagicMock()
        mocks["resolve_scope"].return_value = fake_scope
        mocks["get_budget_grid"].return_value = []
        mocks["build_export_summary_rows"].return_value = []
        mocks["resolve_sap_coverage_cached"].return_value = SapCoverage(
            fiscal_year=2026, watermark_date=None, days_behind=None, is_stale=True,
        )
        response = client.get(
            "/budget/export?year=2027&admin_view_enabled=true&cost_center=CC1&department=%E0%B8%9D%E0%B9%88%E0%B8%B2%E0%B8%A2A"
        )

    assert response.status_code == 200
    _, grid_kwargs = mocks["get_budget_grid"].call_args
    assert grid_kwargs["planning_year"] == 2027
    assert grid_kwargs["admin_view_enabled"] is True
    assert grid_kwargs["cost_center_filter"] == "CC1"
    assert grid_kwargs["department_filter"] == "ฝ่ายA"
    _, scope_kwargs = mocks["resolve_scope"].call_args
    assert scope_kwargs["admin_view_enabled"] is True
    _, summary_kwargs = mocks["build_export_summary_rows"].call_args
    assert summary_kwargs["planning_year"] == 2027
    assert summary_kwargs["department"] == "ฝ่ายA"
    _, coverage_kwargs = mocks["resolve_sap_coverage_cached"].call_args
    assert coverage_kwargs["fiscal_year"] == 2026


def test_budget_export_sap_failure_returns_502(client):
    _override_auth("filler@chememan.com")
    fake_scope = Scope(email="filler@chememan.com", is_admin=False, role="filler", fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    with _export_mocks() as mocks:
        mocks["get_fabric_conn"].return_value.__enter__.return_value = MagicMock()
        mocks["get_gold_conn"].return_value.__enter__.return_value = MagicMock()
        mocks["resolve_scope"].return_value = fake_scope
        mocks["get_budget_grid"].side_effect = SapActualsFetchError("DW unreachable, grant revoked")
        response = client.get("/budget/export?year=2027&department=Corporate+Strategy+2")

    assert response.status_code == 502
    body = response.json()
    assert body["detail"] == _GENERIC_502_DETAIL
    assert "DW unreachable" not in response.text


def test_budget_export_db_error_returns_502(client):
    _override_auth("filler@chememan.com")
    with patch("app.routers.budget.get_fabric_conn") as mock_fabric, patch(
        "app.routers.budget.resolve_scope",
        side_effect=pyodbc.Error("08S01", "connection reset during scope resolution"),
    ):
        mock_fabric.return_value.__enter__.return_value = MagicMock()
        response = client.get("/budget/export?year=2027&department=Corporate+Strategy+2")

    assert response.status_code == 502
    assert response.json()["detail"] == _GENERIC_502_DETAIL
    assert "connection reset" not in response.text


def test_budget_export_empty_grid_yields_header_only_workbook_no_leaked_rows(client):
    _override_auth("filler@chememan.com")
    fake_scope = Scope(email="filler@chememan.com", is_admin=False, role="filler", fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    with _export_mocks() as mocks:
        mocks["get_fabric_conn"].return_value.__enter__.return_value = MagicMock()
        mocks["get_gold_conn"].return_value.__enter__.return_value = MagicMock()
        mocks["resolve_scope"].return_value = fake_scope
        mocks["get_budget_grid"].return_value = []
        mocks["build_export_summary_rows"].return_value = []
        mocks["resolve_sap_coverage_cached"].return_value = SapCoverage(
            fiscal_year=2026, watermark_date=None, days_behind=None, is_stale=True,
        )
        response = client.get("/budget/export?year=2027&department=Corporate+Strategy+2")

    assert response.status_code == 200
    wb = load_workbook(BytesIO(response.content))
    ws = wb.active
    assert ws.max_row == 4  # header only


# Item 2 (gate fix round, LOW): a ฝ่าย name containing an XML-illegal control
# character used to crash the endpoint with an uncaught IllegalCharacterError
# (500) rather than a clean 200 — fixed in `build_export_workbook` (see
# test_budget_export.py's dedicated unit test for the exact stripped value).
@pytest.mark.parametrize("illegal_char", ["\x0b", "￿"])
def test_budget_export_department_with_illegal_xml_chars_returns_200_not_500(client, illegal_char):
    _override_auth("filler@chememan.com")
    fake_scope = Scope(email="filler@chememan.com", is_admin=False, role="filler", fill_cost_centers=["CC1"], see_cost_centers=["CC1"])

    with _export_mocks() as mocks:
        mocks["get_fabric_conn"].return_value.__enter__.return_value = MagicMock()
        mocks["get_gold_conn"].return_value.__enter__.return_value = MagicMock()
        mocks["resolve_scope"].return_value = fake_scope
        mocks["get_budget_grid"].return_value = []
        mocks["build_export_summary_rows"].return_value = []
        mocks["resolve_sap_coverage_cached"].return_value = SapCoverage(
            fiscal_year=2026, watermark_date=None, days_behind=None, is_stale=True,
        )
        response = client.get("/budget/export", params={"year": 2027, "department": f"A{illegal_char}B"})

    assert response.status_code == 200
    wb = load_workbook(BytesIO(response.content))
    assert wb.active is not None


# Item F (gate fix round 2): `department` is caller-supplied free text — the
# 502 failure log must use %r (repr), never raw %s, so a CR/LF-bearing value
# can't forge a fake extra log line.
def test_budget_export_502_log_uses_repr_for_department_no_log_forging(client, caplog):
    _override_auth("filler@chememan.com")
    fake_scope = Scope(email="filler@chememan.com", is_admin=False, role="filler", fill_cost_centers=["CC1"], see_cost_centers=["CC1"])
    malicious_department = "Dept\r\nFAKE LOG LINE: admin login succeeded"

    with _export_mocks() as mocks:
        mocks["get_fabric_conn"].return_value.__enter__.return_value = MagicMock()
        mocks["get_gold_conn"].return_value.__enter__.return_value = MagicMock()
        mocks["resolve_scope"].return_value = fake_scope
        mocks["get_budget_grid"].side_effect = SapActualsFetchError("boom")
        with caplog.at_level(logging.ERROR):
            response = client.get("/budget/export", params={"year": 2027, "department": malicious_department})

    assert response.status_code == 502
    assert repr(malicious_department) in caplog.text  # escaped \r\n, one literal log line
    assert "\nFAKE LOG LINE" not in caplog.text  # never a raw injected newline forging a new line


# ---------------------------------------------------------------------------
# Item 1 (gate fix round, MED, financial) — a Seam-A test that really runs
# `build_export_summary_rows` + `_attach_detail_lines`: only their LEAF
# reads are faked (`fetch_cc_dims`, `_fetch_cc_names`, `_fetch_department_status`,
# `fetch_gl_accounts`, `fetch_detail_lines`, `fetch_trips`, `_fetch_is_auto_calc`
# — all named in `app.budget_export`), `build_export_summary_rows` itself is
# NOT patched. Proves the enrichment pipeline end to end: month/total
# parity, sort order, COST/SGA, Thai status label, trip numbering, PII
# exclusion, and the `filter_rows_by_department` foreign-row drop.
# ---------------------------------------------------------------------------
FIRST_NUM_COL = 11  # K = ม.ค.
TOTAL_COL = FIRST_NUM_COL + 12  # W = รวมปี
BOARD_COL = FIRST_NUM_COL + 13  # X = งบอนุมัติ
SAP_COL = FIRST_NUM_COL + 14  # Y = ใช้จริง SAP
REMARK_COL = SAP_COL + 1  # Z = Remark


@contextmanager
def _full_pipeline_mocks():
    """Same router-level fakes as `_export_mocks()` MINUS
    `build_export_summary_rows` (left real), PLUS its leaf reads patched at
    `app.budget_export.*` — the exact set the gate fix round named."""
    with ExitStack() as stack:
        names = {
            "get_fabric_conn": "app.routers.budget.get_fabric_conn",
            "get_gold_conn": "app.routers.budget.get_gold_conn",
            "resolve_scope": "app.routers.budget.resolve_scope",
            "get_budget_grid": "app.routers.budget.get_budget_grid",
            "resolve_sap_coverage_cached": "app.routers.budget.resolve_sap_coverage_cached",
            "fetch_cc_dims": "app.budget_export.fetch_cc_dims",
            "_fetch_cc_names": "app.budget_export._fetch_cc_names",
            "_fetch_department_status": "app.budget_export._fetch_department_status",
            "fetch_gl_accounts": "app.budget_export.fetch_gl_accounts",
            "fetch_detail_lines": "app.budget_export.fetch_detail_lines",
            "fetch_trips": "app.budget_export.fetch_trips",
            "_fetch_is_auto_calc": "app.budget_export._fetch_is_auto_calc",
        }
        yield {key: stack.enter_context(patch(target)) for key, target in names.items()}


def test_budget_export_seam_a_parity_full_enrichment_pipeline(client):
    _override_auth("filler@chememan.com")
    fake_scope = Scope(email="filler@chememan.com", is_admin=False, role="filler", fill_cost_centers=["CC1", "CC2"], see_cost_centers=["CC1", "CC2"])

    cost_row = BudgetRow(
        cost_center="10CS010000", gl_account="5211800030", department="Corporate Strategy 2",
        pending=PendingLayer(
            m01=10, m02=20, m03=30, m04=40, m05=50, m06=60, m07=70, m08=80, m09=90, m10=100, m11=110, m12=120,
            total_year=780, remark="Note X",
        ),
        board=BoardLayer(total_year=500), sap=SapLayer(total_year=300),
    )
    sga_row = BudgetRow(
        cost_center="10CS020000", gl_account="6210900010", department="Corporate Strategy 2",
        pending=PendingLayer(m01=5, m02=15, m03=25, m04=35, m05=45, m06=55, m07=65, m08=75, m09=85, m10=95, m11=105, m12=115, total_year=725),
        board=BoardLayer(total_year=200), sap=SapLayer(total_year=150),
    )
    special_row = BudgetRow(
        cost_center="10CS010000", gl_account="5215000010", department="Corporate Strategy 2",
        pending=PendingLayer(total_year=400), board=BoardLayer(total_year=0), sap=SapLayer(total_year=0),
    )
    foreign_row = BudgetRow(
        cost_center="10CS099999", gl_account="5299999999", department="Other Department",
        pending=PendingLayer(total_year=9999), board=BoardLayer(total_year=0), sap=SapLayer(total_year=0),
    )
    fake_budget_rows = [cost_row, sga_row, special_row, foreign_row]

    detail_lines = [
        {"detail_id": 1, "trip_id": 501, "gl_group": "Travelling Expense", "meta_json": None, "total_year": 250.0},
        {"detail_id": 2, "trip_id": 502, "gl_group": "Travelling Expense", "meta_json": None, "total_year": 150.0},
    ]
    trips = [
        {
            "trip_id": 501, "destination": "Chiang Mai", "days": 3, "travel_months": ["1"], "project": "Site visit",
            "traveler_name": "Somchai Jaidee", "traveler_empcode": "EMP001",
        },
        {
            "trip_id": 502, "destination": "Khon Kaen", "days": 2, "travel_months": ["2"], "project": "Audit",
            "traveler_name": "Malee Suwan", "traveler_empcode": "EMP002",
        },
    ]

    with _full_pipeline_mocks() as mocks:
        mocks["get_fabric_conn"].return_value.__enter__.return_value = MagicMock()
        mocks["get_gold_conn"].return_value.__enter__.return_value = MagicMock()
        mocks["resolve_scope"].return_value = fake_scope
        mocks["get_budget_grid"].return_value = fake_budget_rows
        mocks["resolve_sap_coverage_cached"].return_value = SapCoverage(
            fiscal_year=2026, watermark_date=date(2026, 9, 21), days_behind=1, is_stale=False,
        )
        mocks["fetch_cc_dims"].return_value = {
            "10CS010000": {"department": "Corporate Strategy 2", "division": "Strategy Division", "c_level": "CEO"},
            "10CS020000": {"department": "Corporate Strategy 2", "division": "Strategy Division", "c_level": "CEO"},
        }
        mocks["_fetch_cc_names"].return_value = {"10CS010000": "Strategy CC1", "10CS020000": "Strategy CC2"}
        mocks["_fetch_department_status"].return_value = "APPROVED"
        mocks["fetch_gl_accounts"].return_value = [
            {"gl_code": "5211800030", "gl_name": "Office COST", "gl_group": "Office Group"},
            {"gl_code": "6210900010", "gl_name": "Office SGA", "gl_group": "SGA Group"},
            {"gl_code": "5215000010", "gl_name": "Per Diem", "gl_group": "Travelling Expense"},
        ]
        mocks["fetch_detail_lines"].return_value = detail_lines
        mocks["fetch_trips"].return_value = trips
        mocks["_fetch_is_auto_calc"].return_value = {1: True, 2: False}

        response = client.get("/budget/export?year=2027&department=Corporate+Strategy+2")

    assert response.status_code == 200
    ws = load_workbook(BytesIO(response.content)).active

    # Sort order: (c_level, division, department, cost_center, side, gl_group,
    # gl_account) — cost_row and special_row share cost_center "10CS010000"
    # (side COST for both), so the tie-break falls to gl_group then
    # gl_account. NOTE (item B, gate fix round 2): in THIS fixture
    # gl_group ("Office Group" < "Travelling Expense") and gl_account
    # ("...5211800030" < "...5215000010") happen to AGREE, so this
    # assertion alone does not prove gl_group is consulted before
    # gl_account, or even that gl_group is consulted at all — sorting by
    # gl_account alone would produce the same order here. The dedicated
    # isolation proof (a fixture where the two DISAGREE) lives in
    # test_budget_export.py::test_build_export_summary_rows_sort_key_isolates_c_level_and_gl_group.
    data_rows = list(range(5, 8))
    assert ws.max_row == 7  # 3 admitted rows — the foreign-department row is GONE
    keys = [(ws.cell(row=r, column=4).value, ws.cell(row=r, column=6).value) for r in data_rows]
    assert keys == [("10CS010000", "5211800030"), ("10CS010000", "5215000010"), ("10CS020000", "6210900010")]

    # Foreign row absent anywhere on the sheet (not just outside data_rows).
    assert "10CS099999" not in {ws.cell(row=r, column=4).value for r in range(1, ws.max_row + 1)}

    # COST/SGA (column 9) + Thai status label (column 10).
    assert [ws.cell(row=r, column=9).value for r in data_rows] == ["COST", "COST", "SGA"]
    assert all(ws.cell(row=r, column=10).value == "อนุมัติแล้ว" for r in data_rows)

    # K..V = pending months, on the COST row (row 5 = cost_row).
    months = [ws.cell(row=5, column=FIRST_NUM_COL + i).value for i in range(12)]
    assert months == [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120]

    # W/X/Y = pending/board/SAP totals, per admitted row.
    totals_by_key = {
        (ws.cell(row=r, column=4).value, ws.cell(row=r, column=6).value): (
            ws.cell(row=r, column=TOTAL_COL).value, ws.cell(row=r, column=BOARD_COL).value, ws.cell(row=r, column=SAP_COL).value,
        )
        for r in data_rows
    }
    assert totals_by_key[("10CS010000", "5211800030")] == (780, 500, 300)
    assert totals_by_key[("10CS020000", "6210900010")] == (725, 200, 150)
    assert totals_by_key[("10CS010000", "5215000010")] == (400, 0, 0)

    # SUM(W5:Wn) == sum(pending.total_year) of the ADMITTED rows (excludes
    # the foreign row's 9999, which never reaches the sheet at all).
    w_sum = sum(ws.cell(row=r, column=TOTAL_COL).value for r in data_rows)
    assert w_sum == 780 + 725 + 400 == cost_row.pending.total_year + sga_row.pending.total_year + special_row.pending.total_year

    # Trip numbering 1..n per CC, in trip_id order — special_row is row 6.
    detail_text = ws.cell(row=6, column=SAP_COL + 2).value  # รายละเอียด column
    assert detail_text.index("ทริป 1") < detail_text.index("ทริป 2")
    assert "(เบี้ยเลี้ยงคำนวณอัตโนมัติ)" in detail_text.split("\n")[0]  # detail_id 1 -> is_auto_calc True
    assert "(เบี้ยเลี้ยงคำนวณอัตโนมัติ)" not in detail_text.split("\n")[1]  # detail_id 2 -> False

    # Item G (gate fix round 2): enriched text columns A ฝ่าย / B สายงาน /
    # C C-Level / E ชื่อ Cost Center, per row (not just spot-checked once) —
    # and the remark landing in ITS row only, never bleeding into another.
    expected_text_cols = {
        ("10CS010000", "5211800030"): ("Corporate Strategy 2", "Strategy Division", "CEO", "Strategy CC1"),
        ("10CS010000", "5215000010"): ("Corporate Strategy 2", "Strategy Division", "CEO", "Strategy CC1"),
        ("10CS020000", "6210900010"): ("Corporate Strategy 2", "Strategy Division", "CEO", "Strategy CC2"),
    }
    for r in data_rows:
        key = (ws.cell(row=r, column=4).value, ws.cell(row=r, column=6).value)
        actual = (ws.cell(row=r, column=1).value, ws.cell(row=r, column=2).value, ws.cell(row=r, column=3).value, ws.cell(row=r, column=5).value)
        assert actual == expected_text_cols[key], key
    assert ws.cell(row=5, column=REMARK_COL).value == "Note X"  # cost_row's own remark
    assert ws.cell(row=6, column=REMARK_COL).value in (None, "")  # special_row: no remark
    assert ws.cell(row=7, column=REMARK_COL).value in (None, "")  # sga_row: no remark

    # K..V (pending months) on EVERY admitted row, not just row 5.
    expected_months = {
        ("10CS010000", "5211800030"): [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120],
        ("10CS010000", "5215000010"): [0.0] * 12,
        ("10CS020000", "6210900010"): [5, 15, 25, 35, 45, 55, 65, 75, 85, 95, 105, 115],
    }
    for r in data_rows:
        key = (ws.cell(row=r, column=4).value, ws.cell(row=r, column=6).value)
        row_months = [ws.cell(row=r, column=FIRST_NUM_COL + i).value for i in range(12)]
        assert row_months == expected_months[key], key

    # Item C (gate fix round 2): the EXACT year/department/cost_center args
    # reaching the leaf reads — a `planning_year - 1` (or similarly wrong)
    # mutation on any of these must fail here, not just silently fetch the
    # wrong year's data through a mock that ignores its own arguments.
    mocks["_fetch_department_status"].assert_called_once_with(ANY, "Corporate Strategy 2", 2027)
    mocks["fetch_detail_lines"].assert_called_once_with(ANY, "10CS010000", "5215000010", 2027)
    mocks["fetch_trips"].assert_called_once_with(ANY, "10CS010000", 2027)
    mocks["_fetch_is_auto_calc"].assert_called_once_with(ANY, 2027, ["10CS010000"])

    # No traveller name/empcode anywhere on the sheet (PDPA).
    all_text = " ".join(
        str(cell.value) for row in ws.iter_rows() for cell in row if isinstance(cell.value, str)
    )
    for pii in ("Somchai Jaidee", "Malee Suwan", "EMP001", "EMP002"):
        assert pii not in all_text


# ---------------------------------------------------------------------------
# GET /budget/sap-coverage — ADR-0030 freshness metadata for the SAP layer
# ---------------------------------------------------------------------------

def _fake_coverage() -> SapCoverage:
    return SapCoverage(
        fiscal_year=2026,
        watermark_date=date(2026, 4, 29),
        days_behind=1,
        is_stale=False,
    )


def test_sap_coverage_401_without_auth_header(client):
    response = client.get("/budget/sap-coverage?year=2027")
    assert response.status_code == 401


def test_sap_coverage_422_when_year_missing(client):
    _override_auth("user@chememan.com")
    assert client.get("/budget/sap-coverage").status_code == 422


def test_sap_coverage_resolves_the_sap_layer_year_not_the_planning_year(client):
    """`year` is the PLANNING year everywhere in this API (same as
    `GET /budget`), and the SAP layer shows `year - 1` — so the endpoint must
    never be handed the planning year as the fiscal year."""
    _override_auth("filler@chememan.com")
    with patch("app.routers.budget.get_gold_conn") as mock_gold, patch(
        "app.routers.budget.resolve_sap_coverage_cached", return_value=_fake_coverage()
    ) as mock_resolve:
        mock_gold.return_value.__enter__.return_value = MagicMock()
        response = client.get("/budget/sap-coverage?year=2027")

    assert response.status_code == 200
    body = response.json()
    assert body["fiscal_year"] == 2026
    assert body["watermark_date"] == "2026-04-29"
    assert body["days_behind"] == 1
    assert body["is_stale"] is False
    _, kwargs = mock_resolve.call_args
    assert kwargs["fiscal_year"] == 2026


def test_sap_coverage_serializes_a_stale_payload(client):
    """A STALE coverage must reach the client as-is (ADR-0030): the freshness
    signal travels in the payload, so `is_stale` / `days_behind` /
    `watermark_date` must survive serialization untouched."""
    _override_auth("filler@chememan.com")
    stale = SapCoverage(
        fiscal_year=2026,
        watermark_date=date(2026, 4, 27),
        days_behind=3,
        is_stale=True,
    )
    with patch("app.routers.budget.get_gold_conn") as mock_gold, patch(
        "app.routers.budget.resolve_sap_coverage_cached", return_value=stale
    ):
        mock_gold.return_value.__enter__.return_value = MagicMock()
        response = client.get("/budget/sap-coverage?year=2027")

    assert response.status_code == 200
    body = response.json()
    assert body["is_stale"] is True
    assert body["days_behind"] == 3
    assert body["watermark_date"] == "2026-04-27"


def test_sap_coverage_failure_returns_502_with_the_same_generic_detail(client):
    """ADR-0020, never-cut: a GENUINE gold-read failure (revoked grant, dead
    connection) is still a loud 502 with no leak — ADR-0030 only removed the
    fail-closed raise for an undeterminable WATERMARK (see test_sap.py), not
    this one."""
    _override_auth("filler@chememan.com")
    with patch("app.routers.budget.get_gold_conn") as mock_gold, patch(
        "app.routers.budget.resolve_sap_coverage_cached",
        side_effect=SapActualsFetchError("grant revoked"),
    ):
        mock_gold.return_value.__enter__.return_value = MagicMock()
        response = client.get("/budget/sap-coverage?year=2027")

    assert response.status_code == 502
    assert response.json()["detail"] == _GENERIC_502_DETAIL
    assert "grant revoked" not in response.text


def test_sap_coverage_connection_failure_also_returns_502(client):
    _override_auth("filler@chememan.com")
    with patch(
        "app.routers.budget.get_gold_conn", side_effect=pyodbc.Error("HYT00", "login timeout expired")
    ):
        response = client.get("/budget/sap-coverage?year=2027")

    assert response.status_code == 502
    assert "login timeout" not in response.text
