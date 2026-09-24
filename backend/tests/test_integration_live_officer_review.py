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
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter

from app.budget_xlsx import FIRST_NUM_COL, SummaryRow, workbook_bytes, write_summary_sheet
from app.config import get_settings
from app.officer_reconcile import _Sheet1Row, _TopicRow, _compare_sheet1, _compare_topics, _load_file_side, reconcile
from app.officer_workbook import TopicRow, _write_topic_sheets, build_officer_workbook

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
            assert any(str(target_key) in f or (target_key[0] in f and target_key[1] in f) for f in delete_result.failures), (
                f"delete FAIL messages did not name the deleted key {target_key}: {delete_result.failures[:10]}"
            )


def _topic_total_col(ws) -> int:
    headers = [ws.cell(row=4, column=c).value for c in range(1, ws.max_column + 1)]
    return next(i for i, h in enumerate(headers, start=1) if isinstance(h, str) and h.startswith("รวมปี "))


def test_negative_controls_topic_and_department_synthetic():
    """C-F6 fix round 2026-09-24: the ABOVE negative control never proves the
    gate can fail on a topic sheet, a department-label mismatch, or a
    duplicated sheet-1 row — and is vacuous whenever today's live scope
    happens to have no eligible row for those branches (F6: "vacuous for
    most scope branches on current live data"). This test builds its OWN
    tiny workbook with the REAL writer functions (`write_summary_sheet` /
    `_write_topic_sheets` — never a hand-rolled xlsx), so all four branches
    below are NEVER vacuous, whatever live data looks like this week.

    Fix round 3 (NEW-3, 2026-09-24) added branch (e): a zero-amount EXTRA
    FILE row sharing (cc, gl) with the real row but under a DIFFERENT
    department label. The (dept, cc, gl)-keyed Counter that guards branch
    (b) does not catch this — the two rows are different full keys — so it
    used to pass the gate silently (proven: placed BEFORE the real row, it
    made a live run go green with 0 failures).

    Fix round 2 (R7/C-F6/N8, 2026-09-24): NOT `@pytest.mark.integration`
    anymore — it never touched a DB or a live connection to begin with (D15
    kept the marker on it anyway, "belt and braces"), which meant it was
    silently skipped by the default `pytest tests -m "not integration"` run
    AND by CI (neither ever calls `-m integration`), so this test never
    actually ran anywhere. Kept in this SAME file (owner's "no other test
    files" instruction, D15) — self-contained (no DB, no live connection,
    nothing imported here needs env/credentials at import time), it tests
    the reconcile's own comparison functions directly against a synthetic
    baseline it builds and controls itself. Never publishes/mails (the
    publisher/notifier are never even imported here)."""
    planning_year = FISCAL_YEAR
    as_of = datetime(planning_year, 1, 15, 9, 0, tzinfo=timezone.utc)
    dept, cc, gl = "SYN01", "SYNCC01", "6210100999"
    months = (100.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    summary_row = SummaryRow(
        cost_center=cc, gl_account=gl, department=dept, division="SYN DIV", c_level="SYN CLEVEL",
        cc_name="Synthetic CC", gl_name="Synthetic GL", gl_group="Entertainment", side="SGA",
        status_label="อนุมัติแล้ว", months=months, total_year=100.0, board_total_year=90.0,
        sap_total_year=80.0, remark="", detail_lines=(),
    )
    topic_row = TopicRow(
        department=dept, division="SYN DIV", cost_center=cc, cc_name="Synthetic CC",
        gl_account=gl, gl_name="Synthetic GL", side="SGA", status_label="อนุมัติแล้ว",
        topic_vals=["ลูกค้า", "เลี้ยงรับรอง"], total_year=100.0, months=months,
        sort_key=(dept, cc, 0, gl, 1),
    )

    def _build_bytes() -> bytes:
        wb = Workbook()
        ws1 = wb.active
        write_summary_sheet(
            ws1, [summary_row], planning_year=planning_year, as_of=as_of,
            scope_label="synthetic", n_departments=1, sap_watermark=None,
        )
        _write_topic_sheets(wb, {"Entertainment": [topic_row]}, planning_year, as_of, None)
        return workbook_bytes(wb)

    baseline_bytes = _build_bytes()
    key = (dept, cc, gl)
    months_dec = tuple(Decimal(str(v)).quantize(Decimal("0.01")) for v in months)
    web_sheet1 = {
        key: _Sheet1Row(months=months_dec, total_year=Decimal("100.00"), board_total_year=Decimal("90.00"), sap_total_year=Decimal("80.00"))
    }
    fabric_sheet1 = dict(web_sheet1)
    web_topics = {"Entertainment": [_TopicRow(cost_center=cc, gl_account=gl, total_year=Decimal("100.00"), months=months_dec)]}
    fabric_topics = {"Entertainment": [_TopicRow(cost_center=cc, gl_account=gl, total_year=Decimal("100.00"), months=months_dec)]}

    # --- sanity: baseline reconciles clean at the compare-function level ---
    file_result, file_topics = _load_file_side(baseline_bytes)
    assert not file_result.failures, f"synthetic baseline FILE side unexpectedly flagged: {file_result.failures}"
    assert _compare_sheet1(file_result.rows, web_sheet1, fabric_sheet1) == []
    assert _compare_topics(file_topics, web_topics, fabric_topics, web_sheet1) == []

    # --- (a) tamper a topic-sheet month cell +0.01 (in the SAVED bytes) ---
    wb_a = load_workbook(BytesIO(baseline_bytes))
    ws_a = wb_a["Entertainment"]
    total_col_a = _topic_total_col(ws_a)
    month1_cell = ws_a.cell(row=5, column=total_col_a + 1)
    month1_cell.value = float(month1_cell.value or 0.0) + 0.01
    buf_a = BytesIO()
    wb_a.save(buf_a)
    _, file_topics_a = _load_file_side(buf_a.getvalue())
    failures_a = _compare_topics(file_topics_a, web_topics, fabric_topics, web_sheet1)
    assert failures_a, "tampering a topic-sheet month cell by +0.01 must FAIL the topic reconcile"
    assert any(cc in f and gl in f for f in failures_a), f"topic-tamper FAIL messages did not name the key ({cc}, {gl}): {failures_a}"

    # --- (b) duplicate a sheet-1 data row (same key, copied to a new row) ---
    wb_b = load_workbook(BytesIO(baseline_bytes))
    ws1_b = wb_b[wb_b.sheetnames[0]]
    for col in range(1, ws1_b.max_column + 1):
        ws1_b.cell(row=6, column=col).value = ws1_b.cell(row=5, column=col).value
    buf_b = BytesIO()
    wb_b.save(buf_b)
    file_result_b, _ = _load_file_side(buf_b.getvalue())
    assert file_result_b.failures, "duplicating a sheet-1 data row must FAIL (C-F4)"
    # R2/N4 fix round 2026-09-24: the FAIL message names (cc, gl) only — never
    # the department label — because this repo is public and its CI logs are
    # world-readable.
    assert any(cc in f and gl in f for f in file_result_b.failures), (
        f"duplicate-row FAIL messages did not name the (cc, gl) key ({cc}, {gl}): {file_result_b.failures}"
    )

    # --- (c) change one sheet-1 ฝ่าย (department) label ---
    wb_c = load_workbook(BytesIO(baseline_bytes))
    ws1_c = wb_c[wb_c.sheetnames[0]]
    ws1_c.cell(row=5, column=1).value = "OTHERDEPT"
    buf_c = BytesIO()
    wb_c.save(buf_c)
    file_result_c, _ = _load_file_side(buf_c.getvalue())
    failures_c = _compare_sheet1(file_result_c.rows, web_sheet1, fabric_sheet1)
    assert failures_c, "changing the sheet-1 ฝ่าย label must FAIL the reconcile (SPEC-2)"
    # R2/N4 fix round 2026-09-24: the row identity is now (cc, gl) — the
    # message says WHICH field differs ("department label differs") without
    # ever printing "OTHERDEPT" (a department-label VALUE) into a public log.
    assert any("department label differs" in f and cc in f and gl in f for f in failures_c), (
        f"department-tamper FAIL messages did not name the (cc, gl) key + 'department label differs': {failures_c}"
    )

    # --- (d) delete the topic-sheet line entirely ---
    wb_d = load_workbook(BytesIO(baseline_bytes))
    ws_d = wb_d["Entertainment"]
    ws_d.delete_rows(5, 1)
    buf_d = BytesIO()
    wb_d.save(buf_d)
    _, file_topics_d = _load_file_side(buf_d.getvalue())
    failures_d = _compare_topics(file_topics_d, web_topics, fabric_topics, web_sheet1)
    assert failures_d, "deleting a topic-sheet line must FAIL the reconcile"
    # R7/C-F6/N8: assert the (cc, gl) key itself is named (not just the sheet
    # name) — the line-multiset diff is the FAIL that carries it.
    assert any(cc in f and gl in f for f in failures_d), (
        f"topic-delete FAIL messages did not name the (cc, gl) key ({cc}, {gl}): {failures_d}"
    )

    # --- (e) zero-amount extra FILE row, same (cc, gl), OTHER department ---
    # (NEW-3 fix round 3): inserted BEFORE the real row, mirroring the proven
    # regression — a (dept, cc, gl)-keyed Counter alone never sees these two
    # rows as duplicates, because the department label differs.
    wb_e = load_workbook(BytesIO(baseline_bytes))
    ws1_e = wb_e[wb_e.sheetnames[0]]
    ws1_e.insert_rows(5)
    ws1_e.cell(row=5, column=1).value = "OTHERDEPT"
    ws1_e.cell(row=5, column=4).value = cc
    ws1_e.cell(row=5, column=6).value = gl
    for c in range(FIRST_NUM_COL, FIRST_NUM_COL + 15):
        ws1_e.cell(row=5, column=c).value = 0.0
    buf_e = BytesIO()
    wb_e.save(buf_e)
    file_result_e, _ = _load_file_side(buf_e.getvalue())
    assert file_result_e.failures, (
        "a zero-amount extra FILE row sharing (cc, gl) under a DIFFERENT "
        "department label must FAIL even though it is a different full key (NEW-3)"
    )
    assert any(cc in f and gl in f for f in file_result_e.failures), (
        f"duplicate-(cc, gl)-different-department FAIL messages did not name the key ({cc}, {gl}): {file_result_e.failures}"
    )
