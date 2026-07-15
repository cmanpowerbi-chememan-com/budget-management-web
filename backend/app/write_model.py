"""Budget WRITE path (A5) — `budget.pending_budget` + `pending_budget_detail`
+ `budget_trip` upserts. Read path is A4 (`read_model.py`); approval is A6.

Design (see final report for the full rationale):
- Every public function is BATCH-shaped (`list[...] -> list[...]`) and each
  item is processed independently — one row/line/trip's failure (403/400/409)
  never blocks the others (multi-Filler concurrency, spec §4). Only a
  genuine DB/connection failure (`pyodbc.Error` not one of the known business
  exceptions below) propagates uncaught — that is the intended "fail loud".
- **Row-grain optimistic lock** (never-cut #5): every UPDATE carries
  `AND _updated_at = ?`; `cursor.rowcount == 0` means "stale or missing" ->
  `RowConflictError` (409), and nothing was written. A brand-new row
  (`expected_updated_at=None`) INSERTs; if the PK already exists (someone
  else created it first) the DB's own PK constraint raises
  `pyodbc.IntegrityError`, caught here and turned into the same conflict.
- **Editing never touches `budget.approval_status`** (never-cut #6, ADR-0013):
  not referenced anywhere in this module. **Verified live 2026-07-15:**
  `budget.pending_budget` has NO `status` column at all — the DDL
  (`db/ddl/budget_transactional_tables.sql`) says so explicitly ("NO status
  column (status lives on approval_status, spec §5 Q4)") and the live table
  matches that design. The INSERT statements here originally wrote a
  hardcoded `'DRAFT'` into that non-existent column (would have raised
  "Invalid column name 'status'" on the very first live write, hidden by
  mocks); removed — no functional loss, since `PendingRowState`/`PendingLayer`
  never modeled a `status` field either. Status lives entirely on
  `budget.approval_status`, owned by A6.
- **GL-name gap RESOLVED (2026-07-15, verified live):** `dbo.gl_group`'s real
  columns are `gl_code`, `gl_group`, `gl_name` (+ `_load_dt`/`_load_dttm`) —
  `gl_name` (the individual GL account's display name) has a home after all;
  the prior `docs/DATA_PIPELINE_PLAN.md` item 4 GAP (seed `dbo.gl_account_ref`
  vs add a SharePoint master file) is moot. `_lookup_gl_group` resolves both
  `gl_group` and `gl_name` in one query and both flow into the dimension
  snapshot. (`_lookup_gl_group` originally selected a non-existent
  `group_name` column — would have raised a live SQL error on first real
  call; fixed to select `gl_group`/`gl_name` directly.)
- **422 vs 400/403/409 is intentional, not inconsistent:** Pydantic
  request-shape violations (e.g. `TripInput.country_group` outside
  {1, 2, 3}, a negative `days`) are rejected by FastAPI's standard 422
  before any function in this module runs — the request itself is
  malformed. Everything past that point is a named business-rule error
  raised here and mapped by the router via `ERROR_HTTP_STATUS`
  (403 forbidden, 400 validation-after-parsing, 409 conflict). The two
  layers check different things: 422 = "not a well-formed request",
  4xx-from-here = "well-formed but violates a budget rule".
- **Deadline lock:** every write entry point rejects non-admin writes to a
  past-deadline `fiscal_year` via the shared check in `app/deadline.py`,
  raising `past_deadline` (403).
"""
import json
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

import pyodbc
from pydantic import BaseModel, Field, field_validator

from app.deadline import PastDeadlineError, is_post_deadline
from app.per_diem import MissingFxRateError, MissingPerDiemRateError, derive_per_diem
from app.rls import Scope
from app.special_gl import (
    MetaValidationError,
    classify_special_gl,
    validate_entertainment_meta,
    validate_lease_meta,
)

MONTH_COLUMNS: tuple[str, ...] = tuple(f"m{m:02d}" for m in range(1, 13))

# Same exclusion list as the SAP read-through (app.sap.SAP_ACTUALS_SQL) and the
# data-model DQ rule (spec §4) — kept in sync manually; 10SC012000 is NOT
# excluded (removed 2026-07-14, it is a valid CC).
EXCLUDED_COST_CENTERS: frozenset[str] = frozenset(
    {"CMRY01", "CMKK01", "CMPB01", "MNLB00", "MNLB01", "MNLB02", "MNLB03", "MNLB04"}
)

# 8 GL = 4 travel expense types x 2 accounting sides (spec §4a Travelling Expense).
TRAVEL_GL_BY_TYPE_SIDE: dict[str, dict[str, str]] = {
    "per_diem": {"COST": "5210400010", "SGA": "6210400010"},
    "transport": {"COST": "5210400020", "SGA": "6210400020"},
    "accommodation": {"COST": "5210400030", "SGA": "6210400030"},
    "other": {"COST": "5210400999", "SGA": "6210400999"},
}
PER_DIEM_GL_BY_SIDE: dict[str, str] = TRAVEL_GL_BY_TYPE_SIDE["per_diem"]
_TRAVEL_GL_SIDE: dict[str, str] = {
    gl: side for sides in TRAVEL_GL_BY_TYPE_SIDE.values() for side, gl in sides.items()
}

# D6 (never-cut): quantize every incoming month amount to DECIMAL(18,2) AT
# THE API BOUNDARY, before any sum is computed — see `_quantize_month` below.
_CENT = Decimal("0.01")

# Live NVARCHAR column widths (verified against INFORMATION_SCHEMA.COLUMNS
# on `fabric_sql_database`, 2026-07-16 — D9). Kept as named constants so a
# schema change only needs updating in one place.
_MAX_LEN_CC_OR_GL = 20      # cost_center, gl_account, traveler_empcode
_MAX_LEN_REMARK = 500       # pending_budget.remark, budget_trip.purpose
_MAX_LEN_LINE_LABEL = 300   # pending_budget_detail.line_label
_MAX_LEN_DESTINATION = 200  # budget_trip.destination
_MAX_LEN_TRAVEL_MONTHS_CSV = 40  # budget_trip.travel_months (joined CSV)
# DECIMAL(18,2) max magnitude is 9,999,999,999,999,999.99 (16 integer digits);
# 1e16 is a clean, safely-below-max bound for the Pydantic guard.
_MAX_MONTH_AMOUNT = 1e16


# ---------------------------------------------------------------------------
# Errors — one error code per class, mapped to an HTTP status by the router.
# ---------------------------------------------------------------------------

class ForbiddenScopeError(PermissionError):
    """cost_center not in caller's Fill scope and caller is not admin
    (never-cut: See-only or fully-out-of-scope writes -> 403)."""


class ExcludedCostCenterError(ValueError):
    """cost_center is on the structural exclusion list (dummy/holding CCs) —
    never valid for budget entry, even for an admin."""


class UnknownCostCenterError(ValueError):
    """cost_center not found in dbo.cc_filler_map. A non-admin's Fill scope
    is itself derived from this same master, so this can only happen via
    the admin bypass (ADR-0012) — admin must not be able to silently write
    a nonexistent cost_center."""


class UnknownGlAccountError(ValueError):
    """gl_account not found in dbo.gl_group (the only in-DB GL reference
    reachable from this connection)."""


class SpecialGlDirectEditError(ValueError):
    """A special-GL cell's months were addressed directly on /budget/rows
    instead of through its detail/trip subform (ADR-0005: the aggregate cell
    is a read-only SUM of its detail lines)."""


class NotSpecialGlError(ValueError):
    """/budget/detail was used for a GL that is not one of the 6 special
    groups — normal GLs are edited via /budget/rows."""


class PerDiemDirectEditError(ValueError):
    """The per-diem GL's detail line is system-managed via /budget/trip only
    (ADR-0005: trips are created in the per-diem subform)."""


class NegativeMonthError(ValueError):
    """A month amount was negative."""


class RowConflictError(RuntimeError):
    """Row-grain optimistic lock lost: stale `_updated_at`, or the row was
    created/deleted concurrently -> 409, no write performed."""


class TripNotFoundError(ValueError):
    """A referenced trip_id does not exist."""


class TripSideMismatchError(ValueError):
    """A detail line's gl_account belongs to the opposite side (COST/SGA) of
    its trip — never-cut: the two accounting sides must never cross."""


class TravelerNotFoundError(ValueError):
    """traveler_empcode not found in dbo.v_employee_primary."""


class InvalidRequestError(ValueError):
    """Malformed combination of fields (e.g. an existing row's lock token
    missing, or a new row supplying one)."""


class DataOverflowError(ValueError):
    """A value overflowed its column's storage limit (NVARCHAR length or
    DECIMAL(18,2) magnitude) and reached the database despite the Pydantic
    `max_length`/range guards above (D9, never-cut: one bad row must never
    surface as an uncaught 500 or block the rest of the batch)."""


# HTTP status per error code — the single source of truth the router reads
# (per_diem's fail-loud errors are 5xx: a missing FX/rate year is an app data
# problem, never the caller's fault, and must never look like a 4xx typo).
ERROR_HTTP_STATUS: dict[str, int] = {
    "forbidden": 403,
    "excluded_cost_center": 400,
    "unknown_cost_center": 400,
    "unknown_gl_account": 400,
    "special_gl_direct_edit": 400,
    "not_special_gl": 400,
    "per_diem_direct_edit": 400,
    "negative_month": 400,
    "trip_not_found": 400,
    "trip_side_mismatch": 400,
    "traveler_not_found": 400,
    "invalid_meta": 400,
    "invalid_request": 400,
    "conflict": 409,
    "data_overflow": 400,
    "past_deadline": 403,
    "missing_per_diem_rate": 500,
    "missing_fx_rate": 500,
}

_ERROR_CODE_BY_EXCEPTION: dict[type[Exception], str] = {
    ForbiddenScopeError: "forbidden",
    ExcludedCostCenterError: "excluded_cost_center",
    UnknownCostCenterError: "unknown_cost_center",
    UnknownGlAccountError: "unknown_gl_account",
    SpecialGlDirectEditError: "special_gl_direct_edit",
    NotSpecialGlError: "not_special_gl",
    PerDiemDirectEditError: "per_diem_direct_edit",
    NegativeMonthError: "negative_month",
    TripNotFoundError: "trip_not_found",
    TripSideMismatchError: "trip_side_mismatch",
    TravelerNotFoundError: "traveler_not_found",
    MetaValidationError: "invalid_meta",
    InvalidRequestError: "invalid_request",
    RowConflictError: "conflict",
    DataOverflowError: "data_overflow",
    PastDeadlineError: "past_deadline",
}
_CAUGHT_PER_ITEM = tuple(_ERROR_CODE_BY_EXCEPTION)  # never includes the per_diem fail-loud errors — those propagate


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _num(value) -> float:
    return 0.0 if value is None else float(value)


def _quantize_month(value: float) -> Decimal:
    """Quantize an incoming month amount to DECIMAL(18,2) (2dp, ROUND_HALF_UP)
    AT THE API BOUNDARY (D6, never-cut): `total_year` must equal
    `SUM(m01..m12)` exactly, which only holds if every month is rounded
    BEFORE it is summed, never after — summing the raw unrounded floats then
    rounding the total drifts from the sum of the independently-rounded
    months whenever a value sits near a cent boundary (two entries of
    100.005 must both persist as 100.00, so their total is 200.00 — not
    200.01 from rounding the unrounded sum after the fact).

    `Decimal(value)` (NOT `Decimal(str(value))`) is deliberate: it preserves
    the exact IEEE-754 double the client actually sent, which is what any
    binary-to-decimal conversion (including SQL Server's own float->DECIMAL
    cast) would also see — so Python's rounding decision matches what the
    database would otherwise have decided implicitly.
    """
    return Decimal(value).quantize(_CENT, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Shared lookups
# ---------------------------------------------------------------------------

def _ensure_write_scope(cost_center: str, scope: Scope, conn: pyodbc.Connection) -> None:
    """See-only or out-of-scope -> forbidden. Admin bypasses the Fill-scope
    gate (ADR-0012) — the ONLY gate is `scope.is_admin`, which A3 resolves
    server-side from the caller's own email; a non-admin can never set this
    themselves. The admin bypass must still not let a nonexistent
    cost_center through — a non-admin's `fill_cost_centers` is itself
    derived from `dbo.cc_filler_map`, so that check is redundant (and
    skipped) for them."""
    if scope.is_admin:
        _ensure_cost_center_exists(conn, cost_center)
        return
    if cost_center not in scope.fill_cost_centers:
        raise ForbiddenScopeError(f"{cost_center} is not in your Fill scope")


def _ensure_cost_center_exists(conn: pyodbc.Connection, cost_center: str) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT TOP 1 1 FROM dbo.cc_filler_map WHERE cost_center = ?", cost_center)
        row = cursor.fetchone()
    finally:
        cursor.close()
    if row is None:
        raise UnknownCostCenterError(f"cost_center {cost_center} not found")


def _ensure_not_excluded(cost_center: str) -> None:
    if cost_center in EXCLUDED_COST_CENTERS:
        raise ExcludedCostCenterError(f"{cost_center} is an excluded cost center — never valid for budget entry")


def _ensure_not_post_deadline(conn: pyodbc.Connection, fiscal_year: int, scope: Scope) -> None:
    """A5 gap close (flagged twice by the A6 gate, 2026-07-16): A6's Submit
    enforces the submission deadline, but editing via /budget/rows|detail|trip
    did not — a normal user could keep editing a closed fiscal_year forever.
    ADR-0012: after the deadline the cycle is closed to normal users, only
    admin may keep editing. Reuses `app.deadline.is_post_deadline` (the exact
    same Bangkok-anchored, deadline-day-inclusive, missing-row-is-OPEN check
    A6's `submit_department` already applies) so the two gates can never
    silently disagree. Called as the LAST check before the first DB write in
    each write path — reads (dims/GL/trip lookups) are unaffected."""
    if scope.is_admin:
        return
    if is_post_deadline(conn, fiscal_year):
        raise PastDeadlineError(f"the submission deadline for fiscal_year={fiscal_year} has passed")


def _ensure_no_negative_months(months: list[Decimal]) -> None:
    if any(v < 0 for v in months):
        raise NegativeMonthError("month amounts must be >= 0")


def _lookup_gl_group(conn: pyodbc.Connection, gl_account: str) -> tuple[str, str | None]:
    """Returns (gl_group, gl_name). Verified against the live table
    2026-07-15 (integration test): both the group/category value and the
    account's display name live directly on `dbo.gl_group` as `gl_group` and
    `gl_name` (not `group_name` — the old assumed column name was never
    checked against the real synced table and would have raised "Invalid
    column name 'group_name'" on first live call)."""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT gl_group, gl_name FROM dbo.gl_group WHERE gl_code = ?", gl_account)
        row = cursor.fetchone()
    finally:
        cursor.close()
    if row is None:
        # D13: never echo the internal table name to the client — this
        # message flows straight into the HTTP error body via `detail`.
        raise UnknownGlAccountError(f"gl_account {gl_account} is not a recognised GL account")
    return row[0], row[1]


def _lookup_cc_dims(conn: pyodbc.Connection, cost_center: str) -> dict[str, str | None]:
    """A cost_center can have more than one row in `dbo.cc_filler_map` (one
    per filler_email) with DIFFERING department/division/c_level (D11) — pick
    deterministically (`ORDER BY filler_email`, alphabetically first) so the
    same cost_center always resolves to the same dims snapshot, never
    flipping by whatever order the DB happens to scan rows in."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT TOP 1 department, division, c_level FROM dbo.cc_filler_map "
            "WHERE cost_center = ? ORDER BY filler_email",
            cost_center,
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
    if row is None:
        return {"department": None, "division": None, "c_level": None}
    return {"department": row[0], "division": row[1], "c_level": row[2]}


def _derive_dim_snapshot(conn: pyodbc.Connection, cost_center: str, gl_account: str) -> dict[str, str | None]:
    """Re-derive the snapshot dims stored on pending_budget (spec §4):
    `gl_name` + `gl_group` resolve from `dbo.gl_group`, `c_level`/`division`/
    `department` resolve from `dbo.cc_filler_map`."""
    gl_group, gl_name = _lookup_gl_group(conn, gl_account)
    dims = _lookup_cc_dims(conn, cost_center)
    return {"gl_name": gl_name, "gl_group": gl_group, **dims}


def _run_per_item(conn: pyodbc.Connection, items, fn, on_result) -> list:
    """Process each item of a batch independently: known business exceptions
    become a failed result (never abort the batch); anything else propagates.
    Rolls back on a caught failure so a partial transaction from one item
    never leaks into the next item's work on the same shared connection.

    D9 (never-cut): a value that slips past the Pydantic max_length/range
    guards can still overflow its NVARCHAR/DECIMAL column at the DB layer
    (`pyodbc.DataError`, e.g. SQLSTATE 22001/22003) — that must become a
    per-item 400 too, never an uncaught 500 that also aborts every OTHER
    item in the same batch. A genuine connection-level `pyodbc.Error` (not
    `DataError`) still propagates uncaught, matching this module's existing
    "fail loud on real DB/connection failures" contract.
    """
    results = []
    for item in items:
        try:
            results.append(fn(item))
        except _CAUGHT_PER_ITEM as exc:
            conn.rollback()
            results.append(on_result(item, exc))
        except pyodbc.DataError as exc:
            conn.rollback()
            results.append(on_result(item, DataOverflowError(str(exc))))
    return results


# ---------------------------------------------------------------------------
# 1. pending_budget — plain cell/row upsert
# ---------------------------------------------------------------------------

class PendingRowInput(BaseModel):
    cost_center: str = Field(max_length=_MAX_LEN_CC_OR_GL)
    gl_account: str = Field(max_length=_MAX_LEN_CC_OR_GL)
    fiscal_year: int
    m01: float = Field(default=0, lt=_MAX_MONTH_AMOUNT)
    m02: float = Field(default=0, lt=_MAX_MONTH_AMOUNT)
    m03: float = Field(default=0, lt=_MAX_MONTH_AMOUNT)
    m04: float = Field(default=0, lt=_MAX_MONTH_AMOUNT)
    m05: float = Field(default=0, lt=_MAX_MONTH_AMOUNT)
    m06: float = Field(default=0, lt=_MAX_MONTH_AMOUNT)
    m07: float = Field(default=0, lt=_MAX_MONTH_AMOUNT)
    m08: float = Field(default=0, lt=_MAX_MONTH_AMOUNT)
    m09: float = Field(default=0, lt=_MAX_MONTH_AMOUNT)
    m10: float = Field(default=0, lt=_MAX_MONTH_AMOUNT)
    m11: float = Field(default=0, lt=_MAX_MONTH_AMOUNT)
    m12: float = Field(default=0, lt=_MAX_MONTH_AMOUNT)
    remark: str | None = Field(default=None, max_length=_MAX_LEN_REMARK)
    template: Literal["USER", "ADMIN"] = "USER"
    expected_updated_at: datetime | None = None  # None = create a new row


class PendingRowState(BaseModel):
    cost_center: str
    gl_account: str
    fiscal_year: int
    m01: float = 0
    m02: float = 0
    m03: float = 0
    m04: float = 0
    m05: float = 0
    m06: float = 0
    m07: float = 0
    m08: float = 0
    m09: float = 0
    m10: float = 0
    m11: float = 0
    m12: float = 0
    total_year: float
    remark: str | None
    template: str
    gl_name: str | None
    gl_group: str | None
    c_level: str | None
    division: str | None
    department: str | None
    updated_at: datetime


class RowSaveResult(BaseModel):
    cost_center: str
    gl_account: str
    fiscal_year: int
    ok: bool
    error: str | None = None
    detail: str | None = None
    row: PendingRowState | None = None


def _save_one_pending_row(conn: pyodbc.Connection, row: PendingRowInput, user_email: str, scope: Scope) -> RowSaveResult:
    _ensure_not_excluded(row.cost_center)
    _ensure_write_scope(row.cost_center, scope, conn)
    months = [_quantize_month(getattr(row, m)) for m in MONTH_COLUMNS]
    _ensure_no_negative_months(months)

    dims = _derive_dim_snapshot(conn, row.cost_center, row.gl_account)
    if classify_special_gl(dims["gl_group"]) is not None:
        raise SpecialGlDirectEditError(
            f"{row.gl_account} ({dims['gl_group']}) is a special GL — edit via its detail subform, not /budget/rows"
        )

    # Admin overlay: a non-admin can never write template=ADMIN (the Template-2
    # / Budget-dept door, spec §1d) even if they crafted the request field.
    template = row.template if scope.is_admin else "USER"
    total_year = sum(months)  # D6: already-quantized Decimals — exact, no extra rounding needed
    now = _now()

    _ensure_not_post_deadline(conn, row.fiscal_year, scope)

    cursor = conn.cursor()
    try:
        if row.expected_updated_at is None:
            try:
                cursor.execute(
                    f"""
                    INSERT INTO budget.pending_budget
                        (cost_center, gl_account, fiscal_year, {', '.join(MONTH_COLUMNS)}, total_year,
                         template, remark, gl_name, gl_group, c_level, division, department,
                         _user, _updated_at)
                    VALUES (?, ?, ?, {', '.join(['?'] * 12)}, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    row.cost_center, row.gl_account, row.fiscal_year, *months, total_year,
                    template, row.remark,
                    dims["gl_name"], dims["gl_group"], dims["c_level"], dims["division"], dims["department"],
                    user_email, now,
                )
            except pyodbc.IntegrityError as exc:
                raise RowConflictError(
                    f"{row.cost_center}/{row.gl_account}/{row.fiscal_year} was created by someone else — reload and retry"
                ) from exc
        else:
            cursor.execute(
                f"""
                UPDATE budget.pending_budget
                SET {', '.join(f'{m} = ?' for m in MONTH_COLUMNS)}, total_year = ?,
                    template = ?, remark = ?, gl_name = ?, gl_group = ?, c_level = ?, division = ?,
                    department = ?, _user = ?, _updated_at = ?
                WHERE cost_center = ? AND gl_account = ? AND fiscal_year = ? AND _updated_at = ?
                """,
                *months, total_year, template, row.remark,
                dims["gl_name"], dims["gl_group"], dims["c_level"], dims["division"], dims["department"],
                user_email, now,
                row.cost_center, row.gl_account, row.fiscal_year, row.expected_updated_at,
            )
            if cursor.rowcount == 0:
                raise RowConflictError(
                    f"{row.cost_center}/{row.gl_account}/{row.fiscal_year} was changed by someone else — reload and retry"
                )
        conn.commit()
    finally:
        cursor.close()

    return RowSaveResult(
        cost_center=row.cost_center, gl_account=row.gl_account, fiscal_year=row.fiscal_year, ok=True,
        row=PendingRowState(
            cost_center=row.cost_center, gl_account=row.gl_account, fiscal_year=row.fiscal_year,
            **{m: v for m, v in zip(MONTH_COLUMNS, months)},
            total_year=total_year, remark=row.remark, template=template,
            gl_name=dims["gl_name"], gl_group=dims["gl_group"], c_level=dims["c_level"],
            division=dims["division"], department=dims["department"], updated_at=now,
        ),
    )


def save_pending_rows(
    conn: pyodbc.Connection, rows: list[PendingRowInput], user_email: str, scope: Scope
) -> list[RowSaveResult]:
    """Upsert each row of `rows` independently (never-cut: one row's 403/400/409
    never blocks another — multi-Filler CCs are common, spec §4)."""
    def _fail(row: PendingRowInput, exc: Exception) -> RowSaveResult:
        return RowSaveResult(
            cost_center=row.cost_center, gl_account=row.gl_account, fiscal_year=row.fiscal_year,
            ok=False, error=_ERROR_CODE_BY_EXCEPTION[type(exc)], detail=str(exc),
        )

    return _run_per_item(conn, rows, lambda r: _save_one_pending_row(conn, r, user_email, scope), _fail)


# ---------------------------------------------------------------------------
# 2. pending_budget_detail — special-GL detail lines
# ---------------------------------------------------------------------------

class DetailLineInput(BaseModel):
    detail_id: int | None = None  # None = new line
    cost_center: str = Field(max_length=_MAX_LEN_CC_OR_GL)
    gl_account: str = Field(max_length=_MAX_LEN_CC_OR_GL)
    fiscal_year: int
    trip_id: int | None = None
    line_label: str | None = Field(default=None, max_length=_MAX_LEN_LINE_LABEL)
    meta_json: dict | None = None
    m01: float = Field(default=0, lt=_MAX_MONTH_AMOUNT)
    m02: float = Field(default=0, lt=_MAX_MONTH_AMOUNT)
    m03: float = Field(default=0, lt=_MAX_MONTH_AMOUNT)
    m04: float = Field(default=0, lt=_MAX_MONTH_AMOUNT)
    m05: float = Field(default=0, lt=_MAX_MONTH_AMOUNT)
    m06: float = Field(default=0, lt=_MAX_MONTH_AMOUNT)
    m07: float = Field(default=0, lt=_MAX_MONTH_AMOUNT)
    m08: float = Field(default=0, lt=_MAX_MONTH_AMOUNT)
    m09: float = Field(default=0, lt=_MAX_MONTH_AMOUNT)
    m10: float = Field(default=0, lt=_MAX_MONTH_AMOUNT)
    m11: float = Field(default=0, lt=_MAX_MONTH_AMOUNT)
    m12: float = Field(default=0, lt=_MAX_MONTH_AMOUNT)
    expected_updated_at: datetime | None = None


class DetailLineState(BaseModel):
    detail_id: int
    cost_center: str
    gl_account: str
    fiscal_year: int
    trip_id: int | None
    gl_group: str
    line_label: str | None
    m01: float = 0
    m02: float = 0
    m03: float = 0
    m04: float = 0
    m05: float = 0
    m06: float = 0
    m07: float = 0
    m08: float = 0
    m09: float = 0
    m10: float = 0
    m11: float = 0
    m12: float = 0
    total_year: float
    meta_json: dict | None
    updated_at: datetime


class DetailLineSaveResult(BaseModel):
    cost_center: str
    gl_account: str
    fiscal_year: int
    ok: bool
    error: str | None = None
    detail: str | None = None
    line: DetailLineState | None = None


def _lookup_trip(conn: pyodbc.Connection, trip_id: int) -> tuple[str, str, int] | None:
    """Returns (cost_center, side, fiscal_year), or None if not found."""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT cost_center, side, fiscal_year FROM budget.budget_trip WHERE trip_id = ?", trip_id)
        row = cursor.fetchone()
    finally:
        cursor.close()
    return (row[0], row[1], row[2]) if row else None


def _lookup_detail_owner(conn: pyodbc.Connection, detail_id: int) -> tuple[str, str, int] | None:
    """Returns the CURRENT (cost_center, gl_account, fiscal_year) actually
    stored for `detail_id`, or None if it no longer exists. Read BEFORE any
    scope check — the payload's own cost_center/gl_account/fiscal_year must
    NEVER be trusted for authorization on an EXISTING line (IDOR fix, D3/D4):
    a caller could otherwise declare their OWN in-scope cost_center while
    `detail_id` actually belongs to someone else's, passing the scope check
    while the UPDATE and parent-cell recompute silently operated on the real
    owner's row/cell."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT cost_center, gl_account, fiscal_year FROM budget.pending_budget_detail WHERE detail_id = ?",
            detail_id,
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
    return (row[0], row[1], row[2]) if row else None


def _recompute_parent_cell(
    conn: pyodbc.Connection, cost_center: str, gl_account: str, fiscal_year: int,
    dims: dict[str, str | None], user_email: str, now: datetime,
) -> None:
    """Re-assert the never-cut DQ rule 'parent cell == SUM(detail lines)'
    after every detail-line write. This aggregate row is never addressed
    directly by a user (save_pending_rows refuses that for a special GL), so
    no optimistic lock applies here — it always reflects the current sum.

    D5 (never-cut, atomic): the SUM and the parent-cell write happen in ONE
    UPDATE statement (the month/total_year subqueries below), not a separate
    SELECT followed by a blind UPDATE. SQL Server takes a row lock on the
    target `pending_budget` row for the duration of this statement, so a 2nd
    concurrent detail save targeting the SAME parent cell blocks until the
    1st commits, then its own subquery re-reads the just-committed detail
    row — no writer can ever compute its sum from a stale read that a
    concurrent writer's commit then races past (the old bug: SELECT sum,
    then UPDATE — a 2nd writer's commit landing in between was silently
    lost)."""

    def _atomic_update(cursor: pyodbc.Cursor) -> int:
        month_set_sql = ", ".join(
            f"{m} = (SELECT COALESCE(SUM({m}), 0) FROM budget.pending_budget_detail "
            "WHERE cost_center = ? AND gl_account = ? AND fiscal_year = ?)"
            for m in MONTH_COLUMNS
        )
        total_year_sql = (
            "(SELECT COALESCE(SUM(total_year), 0) FROM budget.pending_budget_detail "
            "WHERE cost_center = ? AND gl_account = ? AND fiscal_year = ?)"
        )
        month_params: list = []
        for _ in MONTH_COLUMNS:
            month_params.extend([cost_center, gl_account, fiscal_year])
        cursor.execute(
            f"""
            UPDATE budget.pending_budget
            SET {month_set_sql}, total_year = {total_year_sql},
                gl_name = ?, gl_group = ?, c_level = ?, division = ?, department = ?,
                _user = ?, _updated_at = ?
            WHERE cost_center = ? AND gl_account = ? AND fiscal_year = ?
            """,
            *month_params, cost_center, gl_account, fiscal_year,
            dims["gl_name"], dims["gl_group"], dims["c_level"], dims["division"], dims["department"],
            user_email, now,
            cost_center, gl_account, fiscal_year,
        )
        return cursor.rowcount

    cursor = conn.cursor()
    try:
        rowcount = _atomic_update(cursor)
        if rowcount == 0:
            # No parent row exists yet — re-derive the sum fresh (D5: never a
            # stale precomputed value) to build the very first INSERT.
            cursor.execute(
                f"SELECT {', '.join(f'SUM({m})' for m in MONTH_COLUMNS)} "
                "FROM budget.pending_budget_detail WHERE cost_center = ? AND gl_account = ? AND fiscal_year = ?",
                cost_center, gl_account, fiscal_year,
            )
            sums_row = cursor.fetchone()
            months = {m: _num(v) for m, v in zip(MONTH_COLUMNS, sums_row)} if sums_row else {m: 0.0 for m in MONTH_COLUMNS}
            total_year = round(sum(months.values()), 2)
            try:
                cursor.execute(
                    f"""
                    INSERT INTO budget.pending_budget
                        (cost_center, gl_account, fiscal_year, {', '.join(MONTH_COLUMNS)}, total_year,
                         template, remark, gl_name, gl_group, c_level, division, department,
                         _user, _updated_at)
                    VALUES (?, ?, ?, {', '.join(['?'] * 12)}, ?, 'USER', NULL, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    cost_center, gl_account, fiscal_year,
                    *[months[m] for m in MONTH_COLUMNS], total_year,
                    dims["gl_name"], dims["gl_group"], dims["c_level"], dims["division"], dims["department"],
                    user_email, now,
                )
            except pyodbc.IntegrityError as exc:
                # Two concurrent FIRST-EVER writes to the same parent cell:
                # both saw rowcount==0 on the atomic UPDATE above, both tried
                # this INSERT, and the loser hits this PK violation. The row
                # exists now (the winner just created it) — retry the SAME
                # atomic UPDATE (D5: never reuse the `months`/`total_year`
                # computed above, always re-derive); if that somehow still
                # matches nothing, surface a 409 instead of letting a raw
                # pyodbc error escape as a 502.
                rowcount = _atomic_update(cursor)
                if rowcount == 0:
                    raise RowConflictError(
                        f"parent cell {cost_center}/{gl_account}/{fiscal_year} conflict while recomputing"
                    ) from exc
    finally:
        cursor.close()


def _save_one_detail_line(conn: pyodbc.Connection, line: DetailLineInput, user_email: str, scope: Scope) -> DetailLineSaveResult:
    if line.detail_id is not None:
        # IDOR fix (D3/D4): authorize an EXISTING line against its ACTUAL
        # owner, read fresh from the DB — never the payload's own
        # cost_center/gl_account/fiscal_year. A caller could otherwise
        # declare their OWN in-scope cost_center while detail_id belongs to
        # a different cost_center, passing the scope check below while the
        # UPDATE + parent-cell recompute silently operated on someone else's
        # row and cell.
        owner = _lookup_detail_owner(conn, line.detail_id)
        if owner is None:
            raise RowConflictError(f"detail line {line.detail_id} not found — reload and retry")
        actual_cc, actual_gl, actual_fy = owner
        if (actual_cc, actual_gl, actual_fy) != (line.cost_center, line.gl_account, line.fiscal_year):
            raise RowConflictError(
                f"detail line {line.detail_id} does not belong to "
                f"{line.cost_center}/{line.gl_account}/{line.fiscal_year} — reload and retry"
            )
        _ensure_not_excluded(actual_cc)
        _ensure_write_scope(actual_cc, scope, conn)
    else:
        _ensure_not_excluded(line.cost_center)
        _ensure_write_scope(line.cost_center, scope, conn)

    months = [_quantize_month(getattr(line, m)) for m in MONTH_COLUMNS]
    _ensure_no_negative_months(months)

    dims = _derive_dim_snapshot(conn, line.cost_center, line.gl_account)
    gl_group = classify_special_gl(dims["gl_group"])
    if gl_group is None:
        raise NotSpecialGlError(f"{line.gl_account} ({dims['gl_group']}) is not a special-GL detail account")

    if line.gl_account in PER_DIEM_GL_BY_SIDE.values():
        raise PerDiemDirectEditError("per-diem lines are managed via /budget/trip, not /budget/detail")

    if gl_group == "Travelling Expense":
        if line.trip_id is None:
            # The 3 non-per-diem Travelling GLs (transport/accommodation/other)
            # must attach to an existing trip (ADR-0005/spec §4a) — without
            # this, trip_id=None silently bypassed the side-check below entirely.
            raise InvalidRequestError(
                f"{line.gl_account} is a Travelling Expense detail line and must reference an existing trip_id"
            )
    elif line.trip_id is not None:
        # Defense-in-depth: only a Travelling Expense line may carry a
        # trip_id at all — otherwise an unrelated trip_id would sail through
        # with zero cross-validation (no side/CC/year check applies here).
        raise InvalidRequestError(
            f"{line.gl_account} ({gl_group}) is not a Travelling Expense detail line and must not reference a trip_id"
        )

    if line.trip_id is not None:
        trip = _lookup_trip(conn, line.trip_id)
        if trip is None:
            raise TripNotFoundError(f"trip {line.trip_id} not found")
        trip_cc, trip_side, trip_year = trip
        if trip_cc != line.cost_center or trip_year != line.fiscal_year:
            raise TripSideMismatchError(f"trip {line.trip_id} belongs to a different cost_center/fiscal_year")
        gl_side = _TRAVEL_GL_SIDE.get(line.gl_account)
        if gl_side is not None and gl_side != trip_side:
            raise TripSideMismatchError(
                f"GL {line.gl_account} ({gl_side}) does not match trip {line.trip_id}'s side ({trip_side})"
            )

    meta = line.meta_json or {}
    if gl_group == "Entertainment":
        validate_entertainment_meta(line.gl_account, meta)
        cleaned_meta = meta
    elif gl_group == "Lease & Rental":
        cleaned_meta = validate_lease_meta(line.gl_account, meta)
    else:
        cleaned_meta = meta  # not GL-conditional (spec §4a) — free-form

    total_year = sum(months)  # D6: already-quantized Decimals — exact, no extra rounding needed
    now = _now()
    meta_json_str = json.dumps(cleaned_meta, ensure_ascii=False) if cleaned_meta else None

    _ensure_not_post_deadline(conn, line.fiscal_year, scope)

    cursor = conn.cursor()
    try:
        if line.detail_id is None:
            if line.expected_updated_at is not None:
                raise InvalidRequestError("a new detail line must not carry expected_updated_at")
            cursor.execute(
                f"""
                INSERT INTO budget.pending_budget_detail
                    (cost_center, gl_account, fiscal_year, trip_id, gl_group, line_label,
                     {', '.join(MONTH_COLUMNS)}, total_year, meta_json, is_auto_calc, _user, _updated_at)
                OUTPUT INSERTED.detail_id
                VALUES (?, ?, ?, ?, ?, ?, {', '.join(['?'] * 12)}, ?, ?, 0, ?, ?)
                """,
                line.cost_center, line.gl_account, line.fiscal_year, line.trip_id, dims["gl_group"],
                line.line_label, *months, total_year, meta_json_str, user_email, now,
            )
            detail_id = cursor.fetchval()
        else:
            if line.expected_updated_at is None:
                raise InvalidRequestError("editing an existing detail line requires expected_updated_at")
            cursor.execute(
                f"""
                UPDATE budget.pending_budget_detail
                SET {', '.join(f'{m} = ?' for m in MONTH_COLUMNS)}, total_year = ?, line_label = ?,
                    meta_json = ?, trip_id = ?, _user = ?, _updated_at = ?
                WHERE detail_id = ? AND _updated_at = ?
                """,
                *months, total_year, line.line_label, meta_json_str, line.trip_id, user_email, now,
                line.detail_id, line.expected_updated_at,
            )
            if cursor.rowcount == 0:
                raise RowConflictError(f"detail line {line.detail_id} was changed by someone else — reload and retry")
            detail_id = line.detail_id
    finally:
        cursor.close()

    # Recompute BEFORE commit — one commit covers detail-write + recompute
    # atomically. Committing right after the detail write (the old bug) let
    # db.py's context-manager close() silently discard the recompute below:
    # pyodbc is manual-commit by default and an uncommitted statement is
    # lost on close(), so the parent cell stayed 0 forever.
    _recompute_parent_cell(conn, line.cost_center, line.gl_account, line.fiscal_year, dims, user_email, now)
    conn.commit()

    return DetailLineSaveResult(
        cost_center=line.cost_center, gl_account=line.gl_account, fiscal_year=line.fiscal_year, ok=True,
        line=DetailLineState(
            detail_id=detail_id, cost_center=line.cost_center, gl_account=line.gl_account,
            fiscal_year=line.fiscal_year, trip_id=line.trip_id, gl_group=dims["gl_group"],
            line_label=line.line_label, **{m: v for m, v in zip(MONTH_COLUMNS, months)},
            total_year=total_year, meta_json=cleaned_meta, updated_at=now,
        ),
    )


def save_detail_lines(
    conn: pyodbc.Connection, lines: list[DetailLineInput], user_email: str, scope: Scope
) -> list[DetailLineSaveResult]:
    """Upsert each special-GL detail line of `lines` independently."""
    def _fail(line: DetailLineInput, exc: Exception) -> DetailLineSaveResult:
        return DetailLineSaveResult(
            cost_center=line.cost_center, gl_account=line.gl_account, fiscal_year=line.fiscal_year,
            ok=False, error=_ERROR_CODE_BY_EXCEPTION[type(exc)], detail=str(exc),
        )

    return _run_per_item(conn, lines, lambda l: _save_one_detail_line(conn, l, user_email, scope), _fail)


# ---------------------------------------------------------------------------
# 3. budget_trip — trip header + its auto-calc per-diem detail line
# ---------------------------------------------------------------------------

class TripInput(BaseModel):
    trip_id: int | None = None  # None = create a new trip
    cost_center: str = Field(max_length=_MAX_LEN_CC_OR_GL)
    fiscal_year: int
    traveler_empcode: str = Field(max_length=_MAX_LEN_CC_OR_GL)
    destination: str | None = Field(default=None, max_length=_MAX_LEN_DESTINATION)
    country_group: int = Field(ge=1, le=3)  # 1 domestic / 2 asian / 3 other
    days: int = Field(ge=0)
    travel_months: list[str]
    purpose: str | None = Field(default=None, max_length=_MAX_LEN_REMARK)
    side: Literal["COST", "SGA"]
    expected_updated_at: datetime | None = None

    @field_validator("travel_months")
    @classmethod
    def _validate_travel_months(cls, value: list[str]) -> list[str]:
        """D7 fix: validate each entry is a 2-digit month '01'..'12', dedupe
        EXACT duplicates (a client accidentally submitting the same month
        twice must not halve the per-diem split — see derive_per_diem's
        even-split-by-count formula), and reject anything malformed
        (non-numeric, '', a CSV-in-one-element like '03,03', or out of
        range) as a 422 — never a silent per-diem miscalculation and never
        an uncaught 500. Also enforces the persisted CSV's NVARCHAR(40)
        limit (D9) — the CSV is built from this same deduped/sorted list at
        save time (see `_save_one_trip`)."""
        if not value:
            raise ValueError("travel_months must not be empty")
        deduped: list[str] = []
        seen: set[str] = set()
        for raw in value:
            if not isinstance(raw, str) or len(raw) != 2 or not raw.isdigit():
                raise ValueError(f"invalid travel_months entry {raw!r} — must be a 2-digit month string '01'..'12'")
            if not (1 <= int(raw) <= 12):
                raise ValueError(f"invalid travel_months entry {raw!r} — month out of range 01..12")
            if raw not in seen:
                seen.add(raw)
                deduped.append(raw)
        csv = ",".join(sorted(deduped, key=int))
        if len(csv) > _MAX_LEN_TRAVEL_MONTHS_CSV:
            raise ValueError(f"travel_months has too many distinct months for its storage column: {csv!r}")
        return deduped


class TripState(BaseModel):
    trip_id: int
    cost_center: str
    fiscal_year: int
    traveler_empcode: str
    traveler_name: str
    position: str
    destination: str | None
    country_group: int
    days: int
    travel_months: list[str]
    purpose: str | None
    side: str
    updated_at: datetime
    per_diem_months: dict[str, float]  # DERIVED, informational — never stored as authoritative (ADR-0015)


class TripSaveResult(BaseModel):
    cost_center: str
    fiscal_year: int
    traveler_empcode: str
    ok: bool
    error: str | None = None
    detail: str | None = None
    trip: TripState | None = None


def _lookup_traveler(conn: pyodbc.Connection, empcode: str) -> tuple[str, str]:
    """Full-roster lookup (dbo.v_employee_primary, not the 497-row budget
    filter) — a traveler may sit outside the budget scope (spec §3b)."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT full_name_th, job_level_name_en FROM dbo.v_employee_primary WHERE employee_code = ?", empcode
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
    if row is None:
        raise TravelerNotFoundError(f"traveler {empcode} not found")
    return row[0], row[1]


def _lookup_per_diem_rate(conn: pyodbc.Connection, position: str) -> dict[str, Decimal | None]:
    """D1 SHOWSTOPPER fix: the live `dbo.per_diem_rate` column is `job_level`,
    not `position` — the spec DBML's column name was wrong (verified live
    2026-07-15 via INFORMATION_SCHEMA.COLUMNS). The VALUE passed in here is
    still the traveler's `job_level_name_en` (the `position` parameter name
    is kept as-is; only the SQL column name was the bug) — every real
    `POST|PUT /budget/trip` raised pyodbc 42S22 ("invalid column name
    'position'") before this fix."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT rate_domestic, rate_asian, rate_other FROM dbo.per_diem_rate WHERE job_level = ?", position
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
    if row is None:
        raise MissingPerDiemRateError(f"no per_diem_rate row for position '{position}'")
    return {"rate_domestic": row[0], "rate_asian": row[1], "rate_other": row[2]}


def _lookup_fx(conn: pyodbc.Connection, fiscal_year: int) -> Decimal | None:
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT usd_thb FROM dbo.master_currency_rate WHERE fiscal_year = ?", fiscal_year)
        row = cursor.fetchone()
    finally:
        cursor.close()
    return row[0] if row else None


def _upsert_trip_detail_line(
    conn: pyodbc.Connection, trip_id: int, cost_center: str, gl_account: str, fiscal_year: int,
    months: dict[str, float], user_email: str, now: datetime,
) -> None:
    """Store the freshly-DERIVED per-diem months (never the stale prior
    value — this function never reads the existing line's amounts, only
    whether one exists, so a Master-FX edit always re-prices it, ADR-0015)."""
    total = round(sum(months.values()), 2)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT detail_id FROM budget.pending_budget_detail WHERE trip_id = ? AND gl_account = ?",
            trip_id, gl_account,
        )
        existing = cursor.fetchone()
        if existing is None:
            cursor.execute(
                f"""
                INSERT INTO budget.pending_budget_detail
                    (cost_center, gl_account, fiscal_year, trip_id, gl_group, line_label,
                     {', '.join(MONTH_COLUMNS)}, total_year, meta_json, is_auto_calc, _user, _updated_at)
                VALUES (?, ?, ?, ?, 'Travelling Expense', 'เบี้ยเลี้ยง · Per Diem',
                        {', '.join(['?'] * 12)}, ?, NULL, 1, ?, ?)
                """,
                cost_center, gl_account, fiscal_year, trip_id,
                *[months[m] for m in MONTH_COLUMNS], total, user_email, now,
            )
        else:
            cursor.execute(
                f"""
                UPDATE budget.pending_budget_detail
                SET {', '.join(f'{m} = ?' for m in MONTH_COLUMNS)}, total_year = ?, is_auto_calc = 1,
                    _user = ?, _updated_at = ?
                WHERE detail_id = ?
                """,
                *[months[m] for m in MONTH_COLUMNS], total, user_email, now, existing[0],
            )
    finally:
        cursor.close()


def _rehome_trip_detail_lines(conn: pyodbc.Connection, trip_id: int, old_gl: str, new_gl: str) -> None:
    """D8 (never-cut, COST/SGA never cross): move any manually-entered
    (non-per-diem) detail lines of `trip_id` still under the OLD side's GL
    to the NEW side's GL for the same travel type (transport/accommodation/
    other) — keeps the Filler's entered amount, just re-homes which GL it
    counts against. A trip side flip must never leave a line stranded on
    the old side. Per-diem is handled separately (deleted + freshly
    re-derived, never just moved — ADR-0015)."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE budget.pending_budget_detail SET gl_account = ? WHERE trip_id = ? AND gl_account = ?",
            new_gl, trip_id, old_gl,
        )
    finally:
        cursor.close()


def _delete_trip_detail_line(conn: pyodbc.Connection, trip_id: int, gl_account: str) -> None:
    """Remove the stale per-diem line under the OLD side's GL when a trip's
    `side` flips COST<->SGA on update. `side` determines the GL account
    (`PER_DIEM_GL_BY_SIDE`), so without this the old GL's line becomes a
    ghost amount forever — per-diem is DERIVED, never trusted as a stored
    value (ADR-0015)."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM budget.pending_budget_detail WHERE trip_id = ? AND gl_account = ?",
            trip_id, gl_account,
        )
    finally:
        cursor.close()


def _save_one_trip(conn: pyodbc.Connection, trip: TripInput, user_email: str, scope: Scope) -> TripSaveResult:
    _ensure_not_excluded(trip.cost_center)
    _ensure_write_scope(trip.cost_center, scope, conn)
    if not trip.travel_months:
        raise InvalidRequestError("travel_months must not be empty")

    traveler_name, position = _lookup_traveler(conn, trip.traveler_empcode)
    rate_row = _lookup_per_diem_rate(conn, position)  # fails loud (MissingPerDiemRateError) if no row / N/A level

    fx_rate = None
    if trip.country_group in (2, 3):
        fx_rate = _lookup_fx(conn, trip.fiscal_year)
        if fx_rate is None:
            raise MissingFxRateError(f"no master_currency_rate for fiscal_year={trip.fiscal_year}")

    per_diem_months = derive_per_diem(
        days=trip.days, country_group=trip.country_group, rate_row=rate_row,
        fx_rate=fx_rate, travel_months=trip.travel_months,
    )

    now = _now()
    travel_months_csv = ",".join(sorted(trip.travel_months, key=int))

    # Capture the OLD side BEFORE it gets overwritten below — needed to
    # detect a COST<->SGA flip (which changes the per-diem GL) and clean up
    # the old GL's line/parent cell (MUST-FIX 4).
    old_side: str | None = None
    if trip.trip_id is not None:
        existing_trip = _lookup_trip(conn, trip.trip_id)
        if existing_trip is not None:
            old_side = existing_trip[1]

    # Checked once, right before the FIRST write of this function — covers
    # create, update, AND the side-flip path below (all reached only after
    # this point), so a blocked past-deadline trip never touches the DB.
    _ensure_not_post_deadline(conn, trip.fiscal_year, scope)

    cursor = conn.cursor()
    try:
        if trip.trip_id is None:
            if trip.expected_updated_at is not None:
                raise InvalidRequestError("a new trip must not carry expected_updated_at")
            cursor.execute(
                """
                INSERT INTO budget.budget_trip
                    (cost_center, fiscal_year, traveler_empcode, traveler_name, position,
                     destination, country_group, days, travel_months, purpose, side, _user, _updated_at)
                OUTPUT INSERTED.trip_id
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                trip.cost_center, trip.fiscal_year, trip.traveler_empcode, traveler_name, position,
                trip.destination, trip.country_group, trip.days, travel_months_csv, trip.purpose,
                trip.side, user_email, now,
            )
            trip_id = cursor.fetchval()
        else:
            if trip.expected_updated_at is None:
                raise InvalidRequestError("editing an existing trip requires expected_updated_at")
            cursor.execute(
                """
                UPDATE budget.budget_trip
                SET traveler_empcode = ?, traveler_name = ?, position = ?, destination = ?,
                    country_group = ?, days = ?, travel_months = ?, purpose = ?, side = ?,
                    _user = ?, _updated_at = ?
                WHERE trip_id = ? AND cost_center = ? AND fiscal_year = ? AND _updated_at = ?
                """,
                trip.traveler_empcode, traveler_name, position, trip.destination,
                trip.country_group, trip.days, travel_months_csv, trip.purpose, trip.side,
                user_email, now,
                trip.trip_id, trip.cost_center, trip.fiscal_year, trip.expected_updated_at,
            )
            if cursor.rowcount == 0:
                raise RowConflictError(f"trip {trip.trip_id} was changed by someone else — reload and retry")
            trip_id = trip.trip_id
    finally:
        cursor.close()

    per_diem_gl = PER_DIEM_GL_BY_SIDE[trip.side]
    _upsert_trip_detail_line(
        conn, trip_id=trip_id, cost_center=trip.cost_center, gl_account=per_diem_gl,
        fiscal_year=trip.fiscal_year, months=per_diem_months, user_email=user_email, now=now,
    )
    dims = _derive_dim_snapshot(conn, trip.cost_center, per_diem_gl)
    _recompute_parent_cell(conn, trip.cost_center, per_diem_gl, trip.fiscal_year, dims, user_email, now)

    if old_side is not None and old_side != trip.side:
        # Side flipped (e.g. COST->SGA): EVERY one of this trip's detail
        # lines must move, not just per-diem (D8, never-cut: COST and SG&A
        # never cross on one trip). Per-diem is DERIVED (ADR-0015): the old
        # GL's line would otherwise survive as a ghost amount forever, so it
        # is deleted here (the new GL's line was already freshly created
        # above, never just moved). The 3 manual lines (transport/
        # accommodation/other) keep whatever amount the Filler entered and
        # are re-homed to the matching NEW-side GL.
        old_per_diem_gl = PER_DIEM_GL_BY_SIDE[old_side]
        _delete_trip_detail_line(conn, trip_id=trip_id, gl_account=old_per_diem_gl)
        old_pd_dims = _derive_dim_snapshot(conn, trip.cost_center, old_per_diem_gl)
        _recompute_parent_cell(conn, trip.cost_center, old_per_diem_gl, trip.fiscal_year, old_pd_dims, user_email, now)

        for travel_type, side_to_gl in TRAVEL_GL_BY_TYPE_SIDE.items():
            if travel_type == "per_diem":
                continue  # handled above (delete + fresh re-derive, never a plain move)
            old_type_gl, new_type_gl = side_to_gl[old_side], side_to_gl[trip.side]
            _rehome_trip_detail_lines(conn, trip_id=trip_id, old_gl=old_type_gl, new_gl=new_type_gl)
            old_type_dims = _derive_dim_snapshot(conn, trip.cost_center, old_type_gl)
            _recompute_parent_cell(conn, trip.cost_center, old_type_gl, trip.fiscal_year, old_type_dims, user_email, now)
            new_type_dims = _derive_dim_snapshot(conn, trip.cost_center, new_type_gl)
            _recompute_parent_cell(conn, trip.cost_center, new_type_gl, trip.fiscal_year, new_type_dims, user_email, now)

    conn.commit()

    return TripSaveResult(
        cost_center=trip.cost_center, fiscal_year=trip.fiscal_year, traveler_empcode=trip.traveler_empcode, ok=True,
        trip=TripState(
            trip_id=trip_id, cost_center=trip.cost_center, fiscal_year=trip.fiscal_year,
            traveler_empcode=trip.traveler_empcode, traveler_name=traveler_name, position=position,
            destination=trip.destination, country_group=trip.country_group, days=trip.days,
            travel_months=sorted(trip.travel_months, key=int), purpose=trip.purpose, side=trip.side,
            updated_at=now, per_diem_months=per_diem_months,
        ),
    )


def save_trip(
    conn: pyodbc.Connection, trips: list[TripInput], user_email: str, scope: Scope
) -> list[TripSaveResult]:
    """Upsert each trip of `trips` independently. Per-diem's missing-FX /
    missing-rate errors are NEVER caught here (they propagate as-is) — they
    are the never-cut "fail loud" case (never a per-item 4xx result); the
    router turns the propagated exception into a 5xx (see ERROR_HTTP_STATUS).
    """
    def _fail(trip: TripInput, exc: Exception) -> TripSaveResult:
        return TripSaveResult(
            cost_center=trip.cost_center, fiscal_year=trip.fiscal_year, traveler_empcode=trip.traveler_empcode,
            ok=False, error=_ERROR_CODE_BY_EXCEPTION[type(exc)], detail=str(exc),
        )

    return _run_per_item(conn, trips, lambda t: _save_one_trip(conn, t, user_email, scope), _fail)


# ---------------------------------------------------------------------------
# 4. Delete — detail line / trip (A9 backend gap close, flagged in the A9
# final report rather than invented inline: save-only endpoints shipped with
# no delete path anywhere).
#
# Neither delete function accepts cost_center/gl_account/fiscal_year (or, for
# a trip, its side) in its signature at all — authorization is resolved
# ENTIRELY from the row's actual owner, looked up fresh from the DB by its
# id. This is a stricter version of the save path's D3/D4 IDOR fix: there
# isn't just a check against a payload-declared value, there is no
# payload-declared value to spoof in the first place.
# ---------------------------------------------------------------------------

class DetailLineDeleteResult(BaseModel):
    detail_id: int
    ok: bool
    error: str | None = None
    detail: str | None = None


class TripDeleteResult(BaseModel):
    trip_id: int
    ok: bool
    error: str | None = None
    detail: str | None = None


def _delete_one_detail_line(
    conn: pyodbc.Connection, detail_id: int, expected_updated_at: datetime, user_email: str, scope: Scope
) -> DetailLineDeleteResult:
    """Delete one special-GL detail line, then re-assert parent==SUM(detail)
    (never-cut, same as every other detail-line write).

    Deleting the LAST remaining detail line for a cell is allowed by design:
    SUM(detail) becomes 0 and `_recompute_parent_cell`'s atomic UPDATE zeroes
    the EXISTING `pending_budget` row in place — the parent row is kept
    (zeroed), never deleted. This matches the "parent row always reflects
    SUM(detail)" contract every save path already relies on; deleting the
    parent row too would be a second, unrelated behavior (removing a
    cost_center/gl_account cell from the grid entirely) that nothing in this
    task asked for and that would desync the grid's zero-filled-layer
    contract (`read_model` always expects a Pending layer to exist once any
    budget activity has happened on that cell).
    """
    owner = _lookup_detail_owner(conn, detail_id)
    if owner is None:
        raise RowConflictError(f"detail line {detail_id} not found — reload and retry")
    cost_center, gl_account, fiscal_year = owner

    _ensure_not_excluded(cost_center)
    _ensure_write_scope(cost_center, scope, conn)
    _ensure_not_post_deadline(conn, fiscal_year, scope)

    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM budget.pending_budget_detail WHERE detail_id = ? AND _updated_at = ?",
            detail_id, expected_updated_at,
        )
        if cursor.rowcount == 0:
            raise RowConflictError(f"detail line {detail_id} was changed by someone else — reload and retry")
    finally:
        cursor.close()

    # Recompute BEFORE commit — same commit-order rule as every other
    # detail-line write (db.py has no implicit commit; a commit placed
    # before the recompute would silently discard it on connection close).
    now = _now()
    dims = _derive_dim_snapshot(conn, cost_center, gl_account)
    _recompute_parent_cell(conn, cost_center, gl_account, fiscal_year, dims, user_email, now)
    conn.commit()

    return DetailLineDeleteResult(detail_id=detail_id, ok=True)


def delete_detail_line(
    conn: pyodbc.Connection, detail_id: int, expected_updated_at: datetime, user_email: str, scope: Scope
) -> DetailLineDeleteResult:
    """Delete one special-GL detail line by id (see `_delete_one_detail_line`
    for the full contract). Single-item, not batch-shaped like `save_*`
    above — a delete always targets exactly one row, there is no bulk-delete
    UI — but reuses `_run_per_item` for the same rollback-on-failure and
    error-code-mapping behavior every other write path already has."""
    def _fail(_id: int, exc: Exception) -> DetailLineDeleteResult:
        return DetailLineDeleteResult(detail_id=_id, ok=False, error=_ERROR_CODE_BY_EXCEPTION[type(exc)], detail=str(exc))

    return _run_per_item(
        conn, [detail_id], lambda d: _delete_one_detail_line(conn, d, expected_updated_at, user_email, scope), _fail,
    )[0]


def _delete_one_trip(
    conn: pyodbc.Connection, trip_id: int, expected_updated_at: datetime, user_email: str, scope: Scope
) -> TripDeleteResult:
    """Delete one trip's header row AND every one of its detail lines
    (per-diem + the 3 manual travel-expense types — a single
    `WHERE trip_id = ?` DELETE removes all of them regardless of which GL
    they are under), then recompute all 4 of that side's travel-GL parent
    cells (never-cut: parent==SUM(detail)).

    Recomputing all 4 unconditionally — rather than first figuring out which
    ones actually had a line for THIS trip — is deliberately the simplest
    correct option: `_recompute_parent_cell` re-derives SUM(detail) fresh
    from whatever remains, so recomputing a cell this trip never touched
    costs nothing and cannot desync it (other trips' lines under the same
    GL are untouched by this trip's DELETE and remain fully counted)."""
    trip = _lookup_trip(conn, trip_id)
    if trip is None:
        raise RowConflictError(f"trip {trip_id} not found — reload and retry")
    cost_center, side, fiscal_year = trip

    _ensure_not_excluded(cost_center)
    _ensure_write_scope(cost_center, scope, conn)
    _ensure_not_post_deadline(conn, fiscal_year, scope)

    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM budget.budget_trip WHERE trip_id = ? AND _updated_at = ?",
            trip_id, expected_updated_at,
        )
        if cursor.rowcount == 0:
            raise RowConflictError(f"trip {trip_id} was changed by someone else — reload and retry")
    finally:
        cursor.close()

    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM budget.pending_budget_detail WHERE trip_id = ?", trip_id)
    finally:
        cursor.close()

    now = _now()
    for side_to_gl in TRAVEL_GL_BY_TYPE_SIDE.values():
        gl_account = side_to_gl[side]
        dims = _derive_dim_snapshot(conn, cost_center, gl_account)
        _recompute_parent_cell(conn, cost_center, gl_account, fiscal_year, dims, user_email, now)

    conn.commit()

    return TripDeleteResult(trip_id=trip_id, ok=True)


def delete_trip(
    conn: pyodbc.Connection, trip_id: int, expected_updated_at: datetime, user_email: str, scope: Scope
) -> TripDeleteResult:
    """Delete one trip and every one of its lines by id (see
    `_delete_one_trip`). Single-item like `delete_detail_line` above."""
    def _fail(_id: int, exc: Exception) -> TripDeleteResult:
        return TripDeleteResult(trip_id=_id, ok=False, error=_ERROR_CODE_BY_EXCEPTION[type(exc)], detail=str(exc))

    return _run_per_item(
        conn, [trip_id], lambda t: _delete_one_trip(conn, t, expected_updated_at, user_email, scope), _fail,
    )[0]
