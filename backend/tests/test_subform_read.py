"""Unit tests for app.subform_read — A9 gap-fill: read-only support for the
special-GL detail subforms + Trip Manager. DB always mocked, no live
connection (same convention as test_reference_data.py)."""
from unittest.mock import MagicMock

from app.per_diem import MissingFxRateError, MissingPerDiemRateError
from app.subform_read import fetch_detail_lines, fetch_trips


# ---------------------------------------------------------------------------
# fetch_detail_lines
# ---------------------------------------------------------------------------

def test_fetch_detail_lines_maps_rows():
    conn = MagicMock()
    months = [100.0] + [0.0] * 11
    conn.cursor.return_value.fetchall.return_value = [
        (1, "CC1", "GL1", 2027, None, "Entertainment", "line label",
         *months, 100.0, '{"ประเภทการรับรอง": "Customer"}', "2026-01-01T00:00:00"),
    ]

    rows = fetch_detail_lines(conn, "CC1", "GL1", 2027)

    assert rows[0]["detail_id"] == 1
    assert rows[0]["cost_center"] == "CC1"
    assert rows[0]["gl_account"] == "GL1"
    assert rows[0]["fiscal_year"] == 2027
    assert rows[0]["trip_id"] is None
    assert rows[0]["gl_group"] == "Entertainment"
    assert rows[0]["line_label"] == "line label"
    assert rows[0]["m01"] == 100.0
    assert rows[0]["total_year"] == 100.0
    assert rows[0]["meta_json"] == {"ประเภทการรับรอง": "Customer"}
    assert rows[0]["updated_at"] == "2026-01-01T00:00:00"


def test_fetch_detail_lines_null_meta_json_becomes_none():
    conn = MagicMock()
    months = [0.0] * 12
    conn.cursor.return_value.fetchall.return_value = [
        (2, "CC1", "GL1", 2027, None, "Public Relation & Donation", None, *months, 0.0, None, "2026-01-01T00:00:00"),
    ]
    rows = fetch_detail_lines(conn, "CC1", "GL1", 2027)
    assert rows[0]["meta_json"] is None


def test_fetch_detail_lines_scopes_by_cc_gl_fiscal_year():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    fetch_detail_lines(conn, "CC1", "GL1", 2027)
    call = conn.cursor.return_value.execute.call_args
    sql_text = call.args[0]
    assert "budget.pending_budget_detail" in sql_text
    assert "cost_center = ?" in sql_text and "gl_account = ?" in sql_text and "fiscal_year = ?" in sql_text
    assert call.args[1:] == ("CC1", "GL1", 2027)


def test_fetch_detail_lines_closes_cursor():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    fetch_detail_lines(conn, "CC1", "GL1", 2027)
    conn.cursor.return_value.close.assert_called_once()


# ---------------------------------------------------------------------------
# fetch_trips — recompute-on-read (ADR-0015/0011)
# ---------------------------------------------------------------------------

def _trip_row(**overrides):
    base = dict(
        trip_id=10, cost_center="CC1", fiscal_year=2027, traveler_empcode="E1",
        traveler_name="สมชาย ใจดี", position="Supervisor", destination="Japan",
        country_group=2, days=5, travel_months="02,03", purpose="visit",
        side="COST", updated_at="2026-01-01T00:00:00",
    )
    base.update(overrides)
    return tuple(base.values())


def test_fetch_trips_recomputes_per_diem_domestic_no_fx_needed(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [
        _trip_row(country_group=1, travel_months="03"),
    ]
    monkeypatch.setattr(
        "app.subform_read._lookup_per_diem_rate",
        lambda c, position: {"rate_domestic": 300, "rate_asian": None, "rate_other": None},
    )

    rows = fetch_trips(conn, "CC1", 2027)

    assert rows[0]["trip_id"] == 10
    assert rows[0]["travel_months"] == ["03"]
    assert rows[0]["per_diem_error"] is None
    assert rows[0]["per_diem_months"]["m03"] == 1500.0  # 5 days * 300 * fx(1)


def test_fetch_trips_asian_uses_fx(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [_trip_row(country_group=2, travel_months="02,03")]
    monkeypatch.setattr(
        "app.subform_read._lookup_per_diem_rate",
        lambda c, position: {"rate_domestic": None, "rate_asian": 70, "rate_other": None},
    )
    monkeypatch.setattr("app.subform_read._lookup_fx", lambda c, fy: 35.0)

    rows = fetch_trips(conn, "CC1", 2027)

    total = 5 * 70 * 35.0
    assert sum(rows[0]["per_diem_months"].values()) == total
    assert rows[0]["per_diem_error"] is None


def test_fetch_trips_missing_fx_sets_per_diem_error_not_raise(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [_trip_row(country_group=3)]
    monkeypatch.setattr(
        "app.subform_read._lookup_per_diem_rate",
        lambda c, position: {"rate_domestic": None, "rate_asian": None, "rate_other": 90},
    )
    monkeypatch.setattr("app.subform_read._lookup_fx", lambda c, fy: None)

    rows = fetch_trips(conn, "CC1", 2027)

    assert rows[0]["per_diem_months"] is None
    assert rows[0]["per_diem_error"] is not None


def test_fetch_trips_missing_rate_row_sets_per_diem_error_not_raise(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [_trip_row(country_group=1)]
    monkeypatch.setattr("app.subform_read._lookup_per_diem_rate", lambda c, position: None)

    rows = fetch_trips(conn, "CC1", 2027)

    assert rows[0]["per_diem_months"] is None
    assert "no per_diem_rate row" in rows[0]["per_diem_error"] or rows[0]["per_diem_error"]


def test_fetch_trips_one_bad_trip_never_blocks_the_others(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [
        _trip_row(trip_id=1, country_group=3),
        _trip_row(trip_id=2, country_group=1),
    ]

    def fake_rate(c, position):
        return {"rate_domestic": 300, "rate_asian": None, "rate_other": None}

    monkeypatch.setattr("app.subform_read._lookup_per_diem_rate", fake_rate)
    monkeypatch.setattr("app.subform_read._lookup_fx", lambda c, fy: None)  # missing FX for trip 1 (other, needs FX)

    rows = fetch_trips(conn, "CC1", 2027)

    assert len(rows) == 2
    assert rows[0]["per_diem_error"] is not None  # trip 1: other, no FX -> error
    assert rows[1]["per_diem_error"] is None  # trip 2: domestic, no FX needed -> fine


def test_fetch_trips_scopes_by_cc_fiscal_year():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    fetch_trips(conn, "CC1", 2027)
    call = conn.cursor.return_value.execute.call_args
    sql_text = call.args[0]
    assert "budget.budget_trip" in sql_text
    assert "cost_center = ?" in sql_text and "fiscal_year = ?" in sql_text
    assert call.args[1:] == ("CC1", 2027)


def test_fetch_trips_closes_cursor():
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    fetch_trips(conn, "CC1", 2027)
    conn.cursor.return_value.close.assert_called_once()
