"""Unit tests for app.per_diem — pure per-diem calculation (ADR-0005/0015, A5).

No I/O at all: rate row + FX are injected. These are the NEVER-CUT financial
tests — rounding parity, missing-FX fail-loud, missing-rate fail-loud.
"""
import pytest

from app.per_diem import (
    MissingFxRateError,
    MissingPerDiemRateError,
    derive_per_diem,
)

DOMESTIC_RATE = {"rate_domestic": 500, "rate_asian": None, "rate_other": None}
ASIAN_RATE = {"rate_domestic": None, "rate_asian": 50, "rate_other": None}
OTHER_RATE = {"rate_domestic": None, "rate_asian": None, "rate_other": 70}


def test_domestic_per_diem_needs_no_fx_and_splits_across_months():
    result = derive_per_diem(
        days=10, country_group=1, rate_row=DOMESTIC_RATE, fx_rate=None, travel_months=["03", "09"],
    )
    # 10 days * 500 THB/day = 5000.00, split evenly across 2 months.
    assert result["m03"] == 2500.0
    assert result["m09"] == 2500.0
    assert sum(result.values()) == 5000.0


def test_last_selected_month_absorbs_the_rounding_remainder():
    """Never-cut #1: an amount that does NOT divide evenly across 3 months —
    the mockup's bug was rounding every month (10000/3 -> 9999 total). Here
    the last SELECTED month (by calendar order) must absorb the remainder so
    the 12-month sum equals the exact total at DECIMAL(18,2)."""
    rate_row = {"rate_domestic": None, "rate_asian": 100, "rate_other": None}
    result = derive_per_diem(
        days=10, country_group=2, rate_row=rate_row, fx_rate=10, travel_months=["01", "05", "12"],
    )
    # 10 days * 100 USD/day * FX 10 = 10000.00 THB, split across 3 months.
    assert result["m01"] == 3333.33
    assert result["m05"] == 3333.33
    assert result["m12"] == 3333.34  # last selected month (Dec) absorbs the remainder
    total = sum(result[m] for m in ("m01", "m05", "m12"))
    assert round(total, 2) == 10000.00
    # every other month stays zero
    assert result["m02"] == 0.0


def test_last_month_is_by_calendar_order_not_input_order():
    """travel_months may arrive unsorted from the client — the LAST selected
    calendar month (not the last list item) absorbs the remainder."""
    rate_row = {"rate_domestic": None, "rate_asian": 100, "rate_other": None}
    result = derive_per_diem(
        days=10, country_group=2, rate_row=rate_row, fx_rate=10, travel_months=["12", "01", "05"],
    )
    assert result["m12"] == 3333.34
    assert result["m01"] == 3333.33
    assert result["m05"] == 3333.33


def test_asian_group_uses_rate_asian_times_fx():
    result = derive_per_diem(
        days=5, country_group=2, rate_row=ASIAN_RATE, fx_rate=35, travel_months=["06"],
    )
    # 5 * 50 USD/day * 35 THB/USD = 8750.00
    assert result["m06"] == 8750.0


def test_other_group_uses_rate_other_times_fx():
    result = derive_per_diem(
        days=4, country_group=3, rate_row=OTHER_RATE, fx_rate=35, travel_months=["07"],
    )
    # 4 * 70 USD/day * 35 THB/USD = 9800.00
    assert result["m07"] == 9800.0


def test_missing_fx_for_asian_group_fails_loud_never_a_constant_fallback():
    """Never-cut #3: a missing FX year must raise, never silently use 35.00."""
    with pytest.raises(MissingFxRateError):
        derive_per_diem(days=5, country_group=2, rate_row=ASIAN_RATE, fx_rate=None, travel_months=["06"])


def test_missing_fx_for_other_group_fails_loud():
    with pytest.raises(MissingFxRateError):
        derive_per_diem(days=5, country_group=3, rate_row=OTHER_RATE, fx_rate=None, travel_months=["06"])


def test_domestic_group_never_needs_fx_even_if_not_provided():
    result = derive_per_diem(days=1, country_group=1, rate_row=DOMESTIC_RATE, fx_rate=None, travel_months=["01"])
    assert result["m01"] == 500.0


def test_missing_rate_row_fails_loud():
    with pytest.raises(MissingPerDiemRateError):
        derive_per_diem(days=5, country_group=1, rate_row=None, fx_rate=None, travel_months=["06"])


def test_rate_row_with_none_for_the_needed_column_fails_loud():
    """A traveler whose job level has no domestic rate configured (column is
    NULL in dbo.per_diem_rate) must fail loud, never silently compute 0."""
    rate_row = {"rate_domestic": None, "rate_asian": 50, "rate_other": 70}
    with pytest.raises(MissingPerDiemRateError):
        derive_per_diem(days=5, country_group=1, rate_row=rate_row, fx_rate=None, travel_months=["06"])


def test_empty_travel_months_raises_value_error():
    with pytest.raises(ValueError):
        derive_per_diem(days=5, country_group=1, rate_row=DOMESTIC_RATE, fx_rate=None, travel_months=[])


def test_invalid_country_group_raises_value_error():
    with pytest.raises(ValueError):
        derive_per_diem(days=5, country_group=4, rate_row=DOMESTIC_RATE, fx_rate=None, travel_months=["01"])


def test_zero_rate_is_valid_not_treated_as_missing():
    """A C-level rate of 0 is a legitimate configured rate (spec §4a Travelling
    Expense note) — must compute 0, not raise."""
    rate_row = {"rate_domestic": 0, "rate_asian": None, "rate_other": None}
    result = derive_per_diem(days=5, country_group=1, rate_row=rate_row, fx_rate=None, travel_months=["01", "02"])
    assert result["m01"] == 0.0
    assert result["m02"] == 0.0


def test_all_twelve_month_keys_always_present():
    result = derive_per_diem(days=1, country_group=1, rate_row=DOMESTIC_RATE, fx_rate=None, travel_months=["01"])
    assert set(result.keys()) == {f"m{m:02d}" for m in range(1, 13)}
