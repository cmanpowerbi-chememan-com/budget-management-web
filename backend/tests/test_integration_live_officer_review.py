"""Live-DB integration test — PRD #34 D15: the ONE testing property jakkaritw
scoped this task to, "data in the file = data on the web = data in Fabric".

READ-ONLY. No writes anywhere. Never calls the publisher or the notifier —
both are patched with `side_effect=AssertionError` so an accidental call
fails loudly instead of silently reaching SharePoint/Graph.

Connection-or-skip helpers are COPIED (not imported) from
`tests/tests_data_sync/test_sap_actuals_parity.py` — same defensive pattern,
kept local per that file's own convention (independent test files, no
shared fixture coupling across parallel-agent work).

Skipped by default (`pytest.ini`: `addopts = -m "not integration"`). Run:
    cd backend && python -X utf8 -m pytest -m integration tests/test_integration_live_officer_review.py -v
"""
import contextlib
import os
from io import BytesIO
from unittest.mock import patch

import pytest
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from app.budget_xlsx import FIRST_NUM_COL
from app.config import get_settings
from app.officer_reconcile import reconcile
from app.officer_workbook import build_officer_workbook

FISCAL_YEAR = int(os.environ.get("AUTOMATION_FISCAL_YEAR", "2027"))


@contextlib.contextmanager
def _fabric_connection_or_skip():
    """Yield an open TRANSACTIONAL Fabric SQL DB connection, or pytest.skip
    with the reason. Copied from tests/tests_data_sync/test_sap_actuals_parity.py."""
    try:
        from app.config import get_settings as _get_settings
        from app.db import get_fabric_conn
    except ImportError as exc:  # pragma: no cover - environment guard
        pytest.skip(f"backend app modules not importable: {exc}")

    settings = _get_settings()
    if not all([
        settings.fabric_sql_server, settings.fabric_sql_database,
        settings.entra_client_id, settings.entra_client_secret, settings.entra_tenant_id,
    ]):
        pytest.skip("backend/.env fabric-DB / Entra credentials absent — live test needs a live DB")

    ctx = get_fabric_conn(settings)
    try:
        conn = ctx.__enter__()
    except Exception as exc:  # noqa: BLE001 — skip is the correct outcome for an unreachable DB
        pytest.skip(f"fabric DB unreachable: {exc}")
    try:
        yield conn
    finally:
        ctx.__exit__(None, None, None)


@contextlib.contextmanager
def _gold_connection_or_skip():
    """Yield an open gold-DW connection, or pytest.skip with the reason.
    Copied from tests/tests_data_sync/test_sap_actuals_parity.py."""
    try:
        from app.config import get_settings as _get_settings
        from app.db import get_gold_conn
    except ImportError as exc:  # pragma: no cover - environment guard
        pytest.skip(f"backend app modules not importable: {exc}")

    settings = _get_settings()
    if not all([
        settings.gold_sql_server, settings.gold_sql_database,
        settings.entra_client_id, settings.entra_client_secret, settings.entra_tenant_id,
    ]):
        pytest.skip("backend/.env gold-DW / Entra credentials absent — live test needs a live DB")

    ctx = get_gold_conn(settings)
    try:
        conn = ctx.__enter__()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"gold DW unreachable: {exc}")
    try:
        yield conn
    finally:
        ctx.__exit__(None, None, None)


@pytest.mark.integration
def test_officer_workbook_reconciles_file_equals_web_equals_fabric():
    """D15 test 1: build the real officer workbook against live prod data and
    assert the three-way reconcile passes. Non-vacuous only when the scope
    has rows; an empty scope (0 APPROVED/ADMIN departments this FY) still
    must reconcile cleanly — the empty-workbook edge is asserted directly,
    never skipped."""
    settings = get_settings()
    with _fabric_connection_or_skip() as fabric_conn, _gold_connection_or_skip() as gold_conn:
        build = build_officer_workbook(fabric_conn, gold_conn, planning_year=FISCAL_YEAR, settings=settings)
        assert build.xlsx_bytes is not None, "builder produced no bytes"
        assert not build.failures, f"build-time controls FAILed: {build.failures[:10]}"

        with patch("app.officer_publisher.publish_officer_workbook", side_effect=AssertionError("must never publish from a test")), \
             patch("app.officer_notify.notify_officer_review", side_effect=AssertionError("must never mail from a test")):
            result = reconcile(build.xlsx_bytes, build, fabric_conn, gold_conn, planning_year=FISCAL_YEAR)

        assert result.ok, f"reconcile FAILed: {result.failures[:20]}"

        if not build.row_keys:
            # Empty-scope edge (D6): still a clean, well-formed empty workbook.
            wb = load_workbook(BytesIO(build.xlsx_bytes))
            ws1 = wb[wb.sheetnames[0]]
            assert ws1["A2"].value == "ยังไม่มีรายการ"
            assert ws1.cell(row=3, column=FIRST_NUM_COL).value == f"=SUBTOTAL(9,{get_column_letter(FIRST_NUM_COL)}5:{get_column_letter(FIRST_NUM_COL)}5)"


@pytest.mark.integration
def test_negative_control_tampered_or_missing_row_fails_reconcile():
    """D15 test 2: NEGATIVE CONTROL — a gate that can never fail is not a
    gate. Tampers one numeric data cell (+0.01) in the SAVED BYTES, and
    separately deletes one data row, then re-runs the FILE-side compare and
    asserts each tamper FAILs, naming the affected (cost_center, gl_account)
    key. Skips (not fails) when there is no in-scope row to tamper — the
    empty-scope case is a legitimate outcome, not a broken test."""
    settings = get_settings()
    with _fabric_connection_or_skip() as fabric_conn, _gold_connection_or_skip() as gold_conn:
        build = build_officer_workbook(fabric_conn, gold_conn, planning_year=FISCAL_YEAR, settings=settings)
        assert build.xlsx_bytes is not None
        if not build.row_keys:
            pytest.skip("0 in-scope rows this run — nothing to tamper (empty-scope is covered by the other test)")

        target_key = sorted(build.row_keys)[0]

        with patch("app.officer_publisher.publish_officer_workbook", side_effect=AssertionError("must never publish from a test")), \
             patch("app.officer_notify.notify_officer_review", side_effect=AssertionError("must never mail from a test")):
            # --- tamper a numeric cell (+0.01 on the FY-total column) ---
            wb = load_workbook(BytesIO(build.xlsx_bytes))
            ws1 = wb[wb.sheetnames[0]]
            total_col = FIRST_NUM_COL + 12
            found_row = None
            for r in range(5, ws1.max_row + 1):
                if (ws1.cell(row=r, column=4).value, ws1.cell(row=r, column=6).value) == target_key:
                    found_row = r
                    break
            assert found_row is not None, f"could not locate row for {target_key} to tamper"
            ws1.cell(row=found_row, column=total_col).value = float(ws1.cell(row=found_row, column=total_col).value or 0.0) + 0.01
            buf = BytesIO()
            wb.save(buf)
            tampered_bytes = buf.getvalue()

            tamper_result = reconcile(tampered_bytes, build, fabric_conn, gold_conn, planning_year=FISCAL_YEAR)
            assert not tamper_result.ok, "tampering a numeric cell by +0.01 must FAIL the reconcile"
            assert any(str(target_key) in f or (target_key[0] in f and target_key[1] in f) for f in tamper_result.failures), (
                f"tamper FAIL messages did not name the tampered key {target_key}: {tamper_result.failures[:10]}"
            )

            # --- delete the same data row entirely (row-key-set mismatch) ---
            wb2 = load_workbook(BytesIO(build.xlsx_bytes))
            ws1b = wb2[wb2.sheetnames[0]]
            ws1b.delete_rows(found_row, 1)
            buf2 = BytesIO()
            wb2.save(buf2)
            deleted_bytes = buf2.getvalue()

            delete_result = reconcile(deleted_bytes, build, fabric_conn, gold_conn, planning_year=FISCAL_YEAR)
            assert not delete_result.ok, "deleting a data row must FAIL the reconcile (row-key-set mismatch)"
