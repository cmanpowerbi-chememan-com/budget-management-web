"""Per-diem calculation — pure, no I/O (ADR-0005 rounding, ADR-0015 recompute-on-read).

`derive_per_diem` is the ONE place the formula lives: `days * rate(position,
country_group) * FX(year)`, split across the trip's `travel_months`. The rate
row and FX rate are always INJECTED by the caller (write_model.py resolves
them from `dbo.per_diem_rate` / `dbo.master_currency_rate`) — this module never
queries a database, so it stays trivially unit-testable and is also what the
read path (A4/A8, not built here) should call to derive a per-diem detail
line's months on every read, never trusting a stored value (ADR-0015).

Never-cut rules enforced here:
- The LAST selected month (by calendar order, not input order) absorbs the
  rounding remainder so `sum(m01..m12)` equals the exact total at
  DECIMAL(18,2). The mockup's round-every-month is a bug (10000/3 -> 9999) —
  do not replicate it.
- A missing FX rate (asian/other groups) or a missing/None rate column raises
  — never a silent fallback (e.g. a constant 35.00 THB/USD).
"""
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Mapping

MONTH_COLUMNS: tuple[str, ...] = tuple(f"m{m:02d}" for m in range(1, 13))

_DOMESTIC = 1
_ASIAN = 2
_OTHER = 3
_VALID_COUNTRY_GROUPS = (_DOMESTIC, _ASIAN, _OTHER)

_CENT = Decimal("0.01")


class MissingPerDiemRateError(RuntimeError):
    """Raised when the traveler's position has no matching `per_diem_rate` row,
    or the row exists but the needed rate column (domestic/asian/other) is
    NULL. Never silently compute 0 for an unconfigured rate."""


class MissingFxRateError(RuntimeError):
    """Raised when `country_group` is asian(2)/other(3) — which need FX — but
    no `fx_rate` was supplied (i.e. no `master_currency_rate` row for the
    trip's fiscal year). Never a silent constant fallback (ADR-0015)."""


def _rate_for_group(rate_row: Mapping, country_group: int) -> Decimal | None:
    column = {
        _DOMESTIC: "rate_domestic",
        _ASIAN: "rate_asian",
        _OTHER: "rate_other",
    }[country_group]
    value = rate_row.get(column)
    return None if value is None else Decimal(str(value))


def derive_per_diem(
    days: int,
    country_group: int,
    rate_row: Mapping | None,
    fx_rate: Decimal | float | int | None,
    travel_months: list[str],
) -> dict[str, float]:
    """Compute the per-diem THB amount and split it across `travel_months`.

    Args:
        days: number of per-diem days for the trip.
        country_group: 1=domestic (THB rate, no FX), 2=asian (USD rate x FX),
            3=other (USD rate x FX).
        rate_row: mapping with `rate_domestic`/`rate_asian`/`rate_other` keys
            (a `dbo.per_diem_rate` row, injected by the caller).
        fx_rate: the fiscal year's `master_currency_rate.usd_thb`, required
            (non-None) when `country_group` is 2 or 3; ignored for 1.
        travel_months: non-empty list of 2-digit month strings, e.g. ["03","09"].

    Returns:
        A dict with all 12 `m01`..`m12` keys (float, THB, 2dp) — zero for any
        month not in `travel_months`. `sum(result.values())` equals the exact
        computed total (last selected month absorbs the rounding remainder).

    Raises:
        ValueError: empty `travel_months` or an invalid `country_group`.
        MissingPerDiemRateError: no rate row, or the needed column is NULL.
        MissingFxRateError: `country_group` in (2, 3) and `fx_rate` is None.
    """
    if not travel_months:
        raise ValueError("travel_months must be a non-empty list of month strings")
    if country_group not in _VALID_COUNTRY_GROUPS:
        raise ValueError(f"invalid country_group {country_group!r} — must be 1 (domestic), 2 (asian) or 3 (other)")
    if rate_row is None:
        raise MissingPerDiemRateError("no per_diem_rate row for this traveler's position")

    rate = _rate_for_group(rate_row, country_group)
    if rate is None:
        raise MissingPerDiemRateError(
            f"per_diem_rate row has no rate configured for country_group={country_group}"
        )

    if country_group == _DOMESTIC:
        fx = Decimal("1")
    else:
        if fx_rate is None:
            raise MissingFxRateError(
                f"no master_currency_rate FX for country_group={country_group} — fail loud, never a fallback rate"
            )
        fx = Decimal(str(fx_rate))

    total = (Decimal(str(days)) * rate * fx).quantize(_CENT, rounding=ROUND_HALF_UP)

    months_sorted = sorted(travel_months, key=int)
    n = len(months_sorted)
    # Floor (never round up) each non-last month so it can never exceed its
    # even share; the last selected month then absorbs whatever remains.
    per_month = (total / n).quantize(_CENT, rounding=ROUND_DOWN)

    result: dict[str, float] = {col: 0.0 for col in MONTH_COLUMNS}
    running = Decimal("0.00")
    for i, month in enumerate(months_sorted):
        col = f"m{int(month):02d}"
        if i < n - 1:
            result[col] = float(per_month)
            running += per_month
        else:
            result[col] = float(total - running)  # last selected month absorbs the remainder

    return result
