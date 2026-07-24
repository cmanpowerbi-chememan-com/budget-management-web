"""Unit tests for jobs.repersist_perdiem_fx — FX reconciliation job (financial-
critical). DB always mocked (shared `conn.cursor.return_value` cursor, same
convention as test_jobs_auto_submit.py); `derive_per_diem` runs for REAL
(never mocked) so these tests prove the actual formula/to-the-cent/sum
invariants through the job, not just that a mock was called.

GATE decision under test (2026-07-24, jakkaritw): re-price ALL trips of the
fiscal_year regardless of approval status — no department-lock check exists
in this job at all (unlike write_model's user-facing save path).
"""
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.per_diem import MissingPerDiemRateError
from jobs.repersist_perdiem_fx import FxRateMissingError, main, run

_ASIAN_RATE_ROW = {"rate_domestic": None, "rate_asian": Decimal("100"), "rate_other": None}


def _trip_row(trip_id=1, cost_center="10CS000000", side="COST", position="Manager", country_group=2, days=5, travel_months="03"):
    return (trip_id, cost_center, side, position, country_group, days, travel_months)


def _run_with_conn(conn, fiscal_year=2027, dry_run=True):
    with patch("jobs.repersist_perdiem_fx.get_fabric_conn") as mock_conn:
        mock_conn.return_value.__enter__.return_value = conn
        return run(fiscal_year=fiscal_year, dry_run=dry_run)


# ---------------------------------------------------------------------------
# (d) missing FX for the year -> fail loud
# ---------------------------------------------------------------------------

def test_missing_fx_for_year_fails_loud_and_touches_no_trips():
    conn = MagicMock()
    with patch("jobs.repersist_perdiem_fx._lookup_fx", return_value=None):
        with pytest.raises(FxRateMissingError):
            _run_with_conn(conn, fiscal_year=2027, dry_run=True)
    # never even queried the trip table
    conn.cursor.return_value.execute.assert_not_called()


# ---------------------------------------------------------------------------
# (a) foreign trip re-priced to new FX, to the cent
# ---------------------------------------------------------------------------

def test_foreign_trip_repriced_to_new_fx_to_the_cent():
    """5 days x 100 USD/day x FX 40 = 20,000 THB, replacing an old 17,500
    (FX 35) stored value — exact cents, matches the design doc's worked
    example."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [_trip_row(days=5, travel_months="03")]
    conn.cursor.return_value.fetchone.return_value = (17500.00,)  # old stored total_year

    with patch("jobs.repersist_perdiem_fx._lookup_fx", return_value=Decimal("40")), patch(
        "jobs.repersist_perdiem_fx._lookup_per_diem_rate", return_value=_ASIAN_RATE_ROW
    ), patch("jobs.repersist_perdiem_fx._upsert_trip_detail_line") as mock_upsert, patch(
        "jobs.repersist_perdiem_fx._derive_dim_snapshot", return_value={"gl_name": None, "gl_group": None, "c_level": None, "division": None, "department": None}
    ), patch("jobs.repersist_perdiem_fx._recompute_parent_cell") as mock_recompute:
        summary = _run_with_conn(conn, fiscal_year=2027, dry_run=False)

    mock_upsert.assert_called_once()
    args = mock_upsert.call_args.args
    # (conn, trip_id, cost_center, gl_account, fiscal_year, months, user_email, now)
    months = args[5]
    assert round(sum(months.values()), 2) == 20000.00
    assert months["m03"] == 20000.00
    mock_recompute.assert_called_once()
    assert summary["repriced"] == 1
    assert summary["scanned"] == 1
    assert summary["total_delta_thb"] == pytest.approx(2500.00)


def test_run_actor_email_and_gl_account_derived_from_side():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [_trip_row(side="SGA", days=5, travel_months="03")]
    conn.cursor.return_value.fetchone.return_value = (0.0,)

    with patch("jobs.repersist_perdiem_fx._lookup_fx", return_value=Decimal("40")), patch(
        "jobs.repersist_perdiem_fx._lookup_per_diem_rate", return_value=_ASIAN_RATE_ROW
    ), patch("jobs.repersist_perdiem_fx._upsert_trip_detail_line") as mock_upsert, patch(
        "jobs.repersist_perdiem_fx._derive_dim_snapshot", return_value={"gl_name": None, "gl_group": None, "c_level": None, "division": None, "department": None}
    ), patch("jobs.repersist_perdiem_fx._recompute_parent_cell"):
        _run_with_conn(conn, fiscal_year=2027, dry_run=False)

    args = mock_upsert.call_args.args
    gl_account = args[3]
    user_email = args[6]
    assert gl_account == "6210400010"  # PER_DIEM_GL_BY_SIDE["SGA"]
    assert user_email == "system:fx_repersist"


# ---------------------------------------------------------------------------
# (b) domestic trip skipped
# ---------------------------------------------------------------------------

def test_domestic_trip_is_skipped_no_rate_lookup_no_write():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [_trip_row(country_group=1, days=3, travel_months="01")]

    with patch("jobs.repersist_perdiem_fx._lookup_fx", return_value=Decimal("40")), patch(
        "jobs.repersist_perdiem_fx._lookup_per_diem_rate"
    ) as mock_rate, patch("jobs.repersist_perdiem_fx._upsert_trip_detail_line") as mock_upsert:
        summary = _run_with_conn(conn, fiscal_year=2027, dry_run=False)

    mock_rate.assert_not_called()
    mock_upsert.assert_not_called()
    assert summary["skipped_domestic"] == 1
    assert summary["repriced"] == 0
    assert summary["scanned"] == 1


# ---------------------------------------------------------------------------
# (c) missing-rate position skipped + logged, not crashed
# ---------------------------------------------------------------------------

def test_missing_rate_position_skipped_and_logged_not_crashed(caplog):
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [
        _trip_row(trip_id=1, position="Unconfigured Level", days=5, travel_months="03"),
        _trip_row(trip_id=2, position="Manager", days=2, travel_months="05"),
    ]
    conn.cursor.return_value.fetchone.return_value = (0.0,)

    def _rate_side_effect(conn_arg, position):
        if position == "Unconfigured Level":
            raise MissingPerDiemRateError(f"no per_diem_rate row for position '{position}'")
        return _ASIAN_RATE_ROW

    with patch("jobs.repersist_perdiem_fx._lookup_fx", return_value=Decimal("40")), patch(
        "jobs.repersist_perdiem_fx._lookup_per_diem_rate", side_effect=_rate_side_effect
    ), patch("jobs.repersist_perdiem_fx._upsert_trip_detail_line") as mock_upsert, patch(
        "jobs.repersist_perdiem_fx._derive_dim_snapshot", return_value={"gl_name": None, "gl_group": None, "c_level": None, "division": None, "department": None}
    ), patch("jobs.repersist_perdiem_fx._recompute_parent_cell"), caplog.at_level("WARNING"):
        summary = _run_with_conn(conn, fiscal_year=2027, dry_run=False)

    assert summary["skipped_missing_rate"] == 1
    assert summary["repriced"] == 1  # trip 2 still processed — one bad level never blocks the rest
    assert summary["scanned"] == 2
    mock_upsert.assert_called_once()  # only for trip 2
    assert any("Unconfigured Level" in r.message or "trip_id=1" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# (f) dry-run writes nothing
# ---------------------------------------------------------------------------

def test_dry_run_writes_nothing():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [_trip_row(days=5, travel_months="03")]
    conn.cursor.return_value.fetchone.return_value = (17500.00,)

    with patch("jobs.repersist_perdiem_fx._lookup_fx", return_value=Decimal("40")), patch(
        "jobs.repersist_perdiem_fx._lookup_per_diem_rate", return_value=_ASIAN_RATE_ROW
    ), patch("jobs.repersist_perdiem_fx._upsert_trip_detail_line") as mock_upsert, patch(
        "jobs.repersist_perdiem_fx._derive_dim_snapshot"
    ) as mock_dims, patch("jobs.repersist_perdiem_fx._recompute_parent_cell") as mock_recompute:
        summary = _run_with_conn(conn, fiscal_year=2027, dry_run=True)

    mock_upsert.assert_not_called()
    mock_dims.assert_not_called()
    mock_recompute.assert_not_called()
    conn.commit.assert_not_called()
    assert summary["repriced"] == 1  # still counted as "would reprice" for the preview
    assert summary["total_delta_thb"] == pytest.approx(2500.00)
    assert summary["preview"][0]["old_total"] == 17500.00
    assert summary["preview"][0]["new_total"] == 20000.00


# ---------------------------------------------------------------------------
# (e) idempotency — second run at the same FX yields zero delta
# ---------------------------------------------------------------------------

def test_second_run_at_same_fx_yields_zero_delta():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [_trip_row(days=5, travel_months="03")]
    # 1st run: no prior line (0.0) -> new_total 20000.00.
    # 2nd run: the prior write is now reflected (20000.00) -> new_total still
    # 20000.00 at the SAME fx/inputs -> delta 0.
    conn.cursor.return_value.fetchone.side_effect = [(0.0,), (20000.00,)]

    with patch("jobs.repersist_perdiem_fx._lookup_fx", return_value=Decimal("40")), patch(
        "jobs.repersist_perdiem_fx._lookup_per_diem_rate", return_value=_ASIAN_RATE_ROW
    ), patch("jobs.repersist_perdiem_fx._upsert_trip_detail_line"), patch(
        "jobs.repersist_perdiem_fx._derive_dim_snapshot", return_value={"gl_name": None, "gl_group": None, "c_level": None, "division": None, "department": None}
    ), patch("jobs.repersist_perdiem_fx._recompute_parent_cell"):
        first = _run_with_conn(conn, fiscal_year=2027, dry_run=False)
        second = _run_with_conn(conn, fiscal_year=2027, dry_run=False)

    assert first["total_delta_thb"] == pytest.approx(20000.00)  # 0.0 -> 20000.00
    assert second["total_delta_thb"] == pytest.approx(0.00)  # re-run, same FX/inputs -> no drift
    assert second["repriced"] == 1


# ---------------------------------------------------------------------------
# (g) sum(months) == total_year (last-month-remainder rule verified end-to-end)
# ---------------------------------------------------------------------------

def test_sum_of_months_equals_total_year_with_remainder_split():
    """1 day x 100 (rate x FX=1) = 100.00 total, split across 3 months — not
    evenly divisible by 3 (33.33 + 33.33 + 33.34), so the last selected
    month must absorb the rounding remainder (per_diem.py's rule), never
    drop or duplicate a cent."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [_trip_row(days=1, travel_months="01,06,11")]
    conn.cursor.return_value.fetchone.return_value = (0.0,)

    with patch("jobs.repersist_perdiem_fx._lookup_fx", return_value=Decimal("1")), patch(
        "jobs.repersist_perdiem_fx._lookup_per_diem_rate", return_value=_ASIAN_RATE_ROW
    ), patch("jobs.repersist_perdiem_fx._upsert_trip_detail_line") as mock_upsert, patch(
        "jobs.repersist_perdiem_fx._derive_dim_snapshot", return_value={"gl_name": None, "gl_group": None, "c_level": None, "division": None, "department": None}
    ), patch("jobs.repersist_perdiem_fx._recompute_parent_cell"):
        summary = _run_with_conn(conn, fiscal_year=2027, dry_run=False)

    months = mock_upsert.call_args.args[5]
    non_zero = {k: v for k, v in months.items() if v}
    assert non_zero == {"m01": 33.33, "m06": 33.33, "m11": 33.34}
    assert round(sum(months.values()), 2) == 100.00
    assert summary["preview"][0]["new_total"] == 100.00


# ---------------------------------------------------------------------------
# multi-trip summary shape
# ---------------------------------------------------------------------------

def test_summary_counts_all_categories_across_mixed_trips():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [
        _trip_row(trip_id=1, country_group=1),  # domestic -> skipped
        _trip_row(trip_id=2, position="NoRate"),  # missing rate -> skipped
        _trip_row(trip_id=3, position="Manager"),  # repriced
    ]
    conn.cursor.return_value.fetchone.return_value = (0.0,)

    def _rate_side_effect(conn_arg, position):
        if position == "NoRate":
            raise MissingPerDiemRateError("no rate")
        return _ASIAN_RATE_ROW

    with patch("jobs.repersist_perdiem_fx._lookup_fx", return_value=Decimal("40")), patch(
        "jobs.repersist_perdiem_fx._lookup_per_diem_rate", side_effect=_rate_side_effect
    ), patch("jobs.repersist_perdiem_fx._upsert_trip_detail_line"), patch(
        "jobs.repersist_perdiem_fx._derive_dim_snapshot", return_value={"gl_name": None, "gl_group": None, "c_level": None, "division": None, "department": None}
    ), patch("jobs.repersist_perdiem_fx._recompute_parent_cell"):
        summary = _run_with_conn(conn, fiscal_year=2027, dry_run=False)

    assert summary["scanned"] == 3
    assert summary["skipped_domestic"] == 1
    assert summary["skipped_missing_rate"] == 1
    assert summary["repriced"] == 1


# ---------------------------------------------------------------------------
# F1 regression — a malformed trip must never abort the whole batch
# ---------------------------------------------------------------------------

def test_malformed_trip_between_valid_trips_is_skipped_batch_continues(caplog):
    """Regression for the gate-flagged F1 bug: `derive_per_diem` used to run
    OUTSIDE the per-trip try/except, so a malformed row (empty
    `travel_months` -> ValueError) propagated straight out of `run()` and
    aborted the whole fiscal year's re-price mid-batch — a partial run with
    no summary. Placing the bad trip BETWEEN two valid ones proves both
    valid trips still get re-priced."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [
        _trip_row(trip_id=1, days=5, travel_months="03"),
        _trip_row(trip_id=2, days=5, travel_months=""),  # malformed: empty travel_months
        _trip_row(trip_id=3, days=2, travel_months="05"),
    ]
    conn.cursor.return_value.fetchone.return_value = (0.0,)

    with patch("jobs.repersist_perdiem_fx._lookup_fx", return_value=Decimal("40")), patch(
        "jobs.repersist_perdiem_fx._lookup_per_diem_rate", return_value=_ASIAN_RATE_ROW
    ), patch("jobs.repersist_perdiem_fx._upsert_trip_detail_line") as mock_upsert, patch(
        "jobs.repersist_perdiem_fx._derive_dim_snapshot", return_value={"gl_name": None, "gl_group": None, "c_level": None, "division": None, "department": None}
    ), patch("jobs.repersist_perdiem_fx._recompute_parent_cell"), caplog.at_level("WARNING"):
        summary = _run_with_conn(conn, fiscal_year=2027, dry_run=False)

    assert summary["scanned"] == 3
    assert summary["skipped_invalid"] == 1
    assert summary["repriced"] == 2  # trip 1 AND trip 3 both still re-priced
    assert mock_upsert.call_count == 2
    assert any("trip_id=2" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# per-trip WRITE-failure isolation — one trip's write error never blocks the rest
# ---------------------------------------------------------------------------

def test_write_failure_on_one_trip_rolls_back_and_isolates_the_rest(caplog):
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [
        _trip_row(trip_id=1, days=5, travel_months="03"),
        _trip_row(trip_id=2, days=2, travel_months="05"),
    ]
    conn.cursor.return_value.fetchone.return_value = (0.0,)

    with patch("jobs.repersist_perdiem_fx._lookup_fx", return_value=Decimal("40")), patch(
        "jobs.repersist_perdiem_fx._lookup_per_diem_rate", return_value=_ASIAN_RATE_ROW
    ), patch(
        "jobs.repersist_perdiem_fx._upsert_trip_detail_line", side_effect=[RuntimeError("db boom"), None]
    ) as mock_upsert, patch(
        "jobs.repersist_perdiem_fx._derive_dim_snapshot", return_value={"gl_name": None, "gl_group": None, "c_level": None, "division": None, "department": None}
    ) as mock_dims, patch("jobs.repersist_perdiem_fx._recompute_parent_cell") as mock_recompute, caplog.at_level(
        "ERROR"
    ):
        summary = _run_with_conn(conn, fiscal_year=2027, dry_run=False)

    assert mock_upsert.call_count == 2  # both attempted
    mock_dims.assert_called_once()  # trip 1's failure happened before dims/recompute ran
    mock_recompute.assert_called_once()  # only trip 2 reached recompute
    conn.rollback.assert_called_once()  # trip 1's partial write rolled back
    assert conn.commit.call_count == 1  # only trip 2 committed
    assert summary["repriced"] == 1  # trip 1 not counted as re-priced, trip 2 is
    assert any("trip_id=1" in r.message for r in caplog.records)  # failure logged


# ---------------------------------------------------------------------------
# a PRESENT rate of 0 is a legitimate value, not a data gap
# ---------------------------------------------------------------------------

def test_present_rate_of_zero_computes_per_diem_zero_not_skipped():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [_trip_row(days=5, travel_months="03")]
    conn.cursor.return_value.fetchone.return_value = (0.0,)
    zero_rate_row = {"rate_domestic": None, "rate_asian": Decimal("0"), "rate_other": None}

    with patch("jobs.repersist_perdiem_fx._lookup_fx", return_value=Decimal("40")), patch(
        "jobs.repersist_perdiem_fx._lookup_per_diem_rate", return_value=zero_rate_row
    ), patch("jobs.repersist_perdiem_fx._upsert_trip_detail_line") as mock_upsert, patch(
        "jobs.repersist_perdiem_fx._derive_dim_snapshot", return_value={"gl_name": None, "gl_group": None, "c_level": None, "division": None, "department": None}
    ), patch("jobs.repersist_perdiem_fx._recompute_parent_cell"):
        summary = _run_with_conn(conn, fiscal_year=2027, dry_run=False)

    mock_upsert.assert_called_once()
    months = mock_upsert.call_args.args[5]
    assert round(sum(months.values()), 2) == 0.0
    assert summary["repriced"] == 1
    assert summary["skipped_missing_rate"] == 0
    assert summary["skipped_invalid"] == 0


# ---------------------------------------------------------------------------
# F3 — main() exit code reflects data-gap skips
# ---------------------------------------------------------------------------

def test_main_returns_nonzero_when_a_data_gap_skip_occurred(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["repersist_perdiem_fx", "--fiscal-year", "2027"])
    fake_summary = {
        "fiscal_year": 2027, "fx_rate": 40.0, "scanned": 2, "repriced": 1,
        "skipped_domestic": 0, "skipped_missing_rate": 1, "skipped_invalid": 0,
        "total_delta_thb": 100.0, "preview": [],
    }
    with patch("jobs.repersist_perdiem_fx.run", return_value=fake_summary):
        code = main()
    assert code == 1


def test_main_returns_nonzero_when_an_invalid_row_skip_occurred(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["repersist_perdiem_fx", "--fiscal-year", "2027"])
    fake_summary = {
        "fiscal_year": 2027, "fx_rate": 40.0, "scanned": 2, "repriced": 1,
        "skipped_domestic": 0, "skipped_missing_rate": 0, "skipped_invalid": 1,
        "total_delta_thb": 100.0, "preview": [],
    }
    with patch("jobs.repersist_perdiem_fx.run", return_value=fake_summary):
        code = main()
    assert code == 1


def test_main_returns_zero_on_a_clean_run(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["repersist_perdiem_fx", "--fiscal-year", "2027"])
    fake_summary = {
        "fiscal_year": 2027, "fx_rate": 40.0, "scanned": 2, "repriced": 2,
        "skipped_domestic": 0, "skipped_missing_rate": 0, "skipped_invalid": 0,
        "total_delta_thb": 100.0, "preview": [],
    }
    with patch("jobs.repersist_perdiem_fx.run", return_value=fake_summary):
        code = main()
    assert code == 0


def test_main_returns_one_on_fx_missing_error(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["repersist_perdiem_fx", "--fiscal-year", "2027"])
    with patch("jobs.repersist_perdiem_fx.run", side_effect=FxRateMissingError("no fx row")):
        code = main()
    assert code == 1


# ---------------------------------------------------------------------------
# R1 regression — an invalid `side` must never abort the whole batch either
# ---------------------------------------------------------------------------

def test_invalid_side_between_valid_trips_is_skipped_batch_continues_and_main_exits_nonzero(caplog, monkeypatch):
    """R1 (same bug class as F1): `PER_DIEM_GL_BY_SIDE[trip["side"]]` used to
    live OUTSIDE the per-trip guard — a corrupted/legacy `side` (not
    "COST"/"SGA") raised KeyError straight out of run(), aborting the whole
    fiscal year's re-price mid-batch. This trip sits BETWEEN two valid ones
    to prove the batch survives, and confirms main() surfaces the data gap
    as a non-zero exit code."""
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [
        _trip_row(trip_id=1, side="COST", days=5, travel_months="03"),
        _trip_row(trip_id=2, side="XXX", days=5, travel_months="03"),  # invalid side
        _trip_row(trip_id=3, side="SGA", days=2, travel_months="05"),
    ]
    conn.cursor.return_value.fetchone.return_value = (0.0,)

    with patch("jobs.repersist_perdiem_fx._lookup_fx", return_value=Decimal("40")), patch(
        "jobs.repersist_perdiem_fx._lookup_per_diem_rate", return_value=_ASIAN_RATE_ROW
    ), patch("jobs.repersist_perdiem_fx._upsert_trip_detail_line") as mock_upsert, patch(
        "jobs.repersist_perdiem_fx._derive_dim_snapshot", return_value={"gl_name": None, "gl_group": None, "c_level": None, "division": None, "department": None}
    ), patch("jobs.repersist_perdiem_fx._recompute_parent_cell"), caplog.at_level("WARNING"):
        summary = _run_with_conn(conn, fiscal_year=2027, dry_run=False)

    assert summary["scanned"] == 3
    assert summary["skipped_invalid"] == 1
    assert summary["repriced"] == 2  # trip 1 AND trip 3 both still re-priced
    assert mock_upsert.call_count == 2
    assert any("trip_id=2" in r.message and "XXX" in r.message for r in caplog.records)

    # main() must surface this data gap as a non-zero exit (reuses the real summary above)
    monkeypatch.setattr(sys, "argv", ["repersist_perdiem_fx", "--fiscal-year", "2027"])
    with patch("jobs.repersist_perdiem_fx.run", return_value=summary):
        code = main()
    assert code == 1
