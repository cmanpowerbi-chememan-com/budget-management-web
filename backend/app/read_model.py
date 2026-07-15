"""Main-table read path — 3-layer (SAP/Approved/Pending) budget grid, RLS
filtered (A4, ADR-0010/0020/0023).

Split by responsibility so the never-cut visibility/RLS rules are testable
without a DB at all:

- `fetch_board_pending_rows` — the ONE local cross-schema SQL: `dbo.board_budget`
  (fy=board_year) FULL OUTER JOIN `budget.pending_budget` (fy=pending_year) on
  `(cost_center, gl_account)`. Both schemas live in the SAME Fabric SQL Database
  (ADR-0023) so this is a single in-DB query, no cross-store merge.
- `merge_budget_rows` — pure function: takes the join rows + the SAP dict
  (already fetched cross-store via `app.sap.fetch_sap_actuals`) + the caller's
  RLS `Scope` (A3), and returns the final visible/editable row list. No I/O.
- `get_budget_grid` — thin orchestrator wiring the two fetches + the merge for
  the router.

Year mapping (confirmed against `docs/specs/budget-transactional-data-model.md`
§1c and ADR-0010): the endpoint's `planning_year` is the Pending year (Y+1);
board_budget and the SAP read-through both use the standing/current year
(Y = planning_year - 1). Approved-Y is a REFERENCE column beside the Pending
Y+1 the user is planning — comparing them is a Phase-2 dashboard concern, not
this table.

Row visibility (ADR-0010): the union key is `(cost_center, gl_account)` across
all three sources — SAP leads the initial set, but a row that exists ONLY in
board_budget (an Approved import with no actual yet) or ONLY in pending_budget
(added by hand via "+ เพิ่ม transaction") must persist too, so the local join
is FULL OUTER (not board-only-LEFT), and any SAP-only key not matched by the
join is appended as its own row with a blank (all-zero) Pending layer.
"""
from pydantic import BaseModel
import pyodbc

from app.rls import Scope
from app.sap import MONTH_COLUMNS, fetch_sap_actuals

_BOARD_COLUMNS = ("gl_name", "gl_group", "c_level", "division", "department")
# NOTE: no "status" here — `budget.pending_budget` has no status column
# (verified live 2026-07-15; status lives entirely on `budget.approval_status`,
# owned by A6). See app.write_model module docstring for the same finding.
_PENDING_META_COLUMNS = ("template", "remark", "gl_name", "gl_group", "c_level", "division", "department")

# Explicit column lists for the two join-side subqueries (SQL standard: no
# SELECT * — only the columns the outer SELECT / row model actually consume).
_BOARD_BUDGET_COLUMNS: tuple[str, ...] = ("cost_center", "gl_account", *MONTH_COLUMNS, "total_year", *_BOARD_COLUMNS)
_PENDING_BUDGET_COLUMNS: tuple[str, ...] = (
    "cost_center",
    "gl_account",
    *MONTH_COLUMNS,
    "total_year",
    *_PENDING_META_COLUMNS,
)

JOIN_ROW_COLUMNS: tuple[str, ...] = (
    "cost_center",
    "gl_account",
    "board_cost_center",
    "pending_cost_center",
    *(f"board_{m}" for m in MONTH_COLUMNS),
    "board_total_year",
    *(f"board_{c}" for c in _BOARD_COLUMNS),
    *(f"pending_{m}" for m in MONTH_COLUMNS),
    "pending_total_year",
    *(f"pending_{c}" for c in _PENDING_META_COLUMNS),
)


def _cc_filter_clause(cost_centers: list[str] | None) -> tuple[str, list[str]]:
    """Build the optional `AND cost_center IN (?, ?, ...)` RLS restriction,
    fully parameterized (never string-interpolated). `None` = no restriction
    (admin-wide bypass only, ADR-0012/0019). An empty list never reaches this
    helper — `fetch_board_pending_rows` short-circuits before calling it."""
    if cost_centers is None:
        return "", []
    placeholders = ", ".join(["?"] * len(cost_centers))
    return f" AND cost_center IN ({placeholders})", list(cost_centers)


def _board_pending_join_sql(cc_filter_clause: str) -> str:
    return f"""
        SELECT
            COALESCE(b.cost_center, p.cost_center) AS cost_center,
            COALESCE(b.gl_account, p.gl_account) AS gl_account,
            b.cost_center AS board_cost_center,
            p.cost_center AS pending_cost_center,
            {", ".join(f"b.{m} AS board_{m}" for m in MONTH_COLUMNS)},
            b.total_year AS board_total_year,
            {", ".join(f"b.{c} AS board_{c}" for c in _BOARD_COLUMNS)},
            {", ".join(f"p.{m} AS pending_{m}" for m in MONTH_COLUMNS)},
            p.total_year AS pending_total_year,
            {", ".join(f"p.{c} AS pending_{c}" for c in _PENDING_META_COLUMNS)}
        FROM (SELECT {", ".join(_BOARD_BUDGET_COLUMNS)} FROM dbo.board_budget WHERE fiscal_year = ?{cc_filter_clause}) b
        FULL OUTER JOIN (SELECT {", ".join(_PENDING_BUDGET_COLUMNS)} FROM budget.pending_budget WHERE fiscal_year = ?{cc_filter_clause}) p
            ON b.cost_center = p.cost_center AND b.gl_account = p.gl_account
    """


def fetch_board_pending_rows(
    conn: pyodbc.Connection,
    board_year: int,
    pending_year: int,
    cost_centers: list[str] | None = None,
) -> list[dict]:
    """Run the local board+pending cross-schema join for one (board_year,
    pending_year) pair, RLS-restricted to the caller's See-scope `cost_centers`
    on BOTH sides of the join (spec §1c: SQL-side filtering, defense-in-depth
    on top of `merge_budget_rows`'s Python-side filter — both stay active).

    `cost_centers=None` = admin-wide, no restriction (ONLY valid when the
    caller is an admin with the admin-wide toggle on — enforced by
    `get_budget_grid`, never by this function). `cost_centers=[]` (an empty
    See scope) short-circuits to an empty result with NO query executed at
    all — an empty SQL `IN ()` is invalid syntax, and there is nothing to
    fetch anyway.

    Returns a list of dicts keyed by `JOIN_ROW_COLUMNS` (fixed positional
    mapping — no reliance on `cursor.description`)."""
    if cost_centers is not None and len(cost_centers) == 0:
        return []

    cc_filter_clause, cc_params = _cc_filter_clause(cost_centers)
    sql = _board_pending_join_sql(cc_filter_clause)
    params = [board_year, *cc_params, pending_year, *cc_params]

    cursor = conn.cursor()
    try:
        cursor.execute(sql, *params)
        raw_rows = cursor.fetchall()
    finally:
        cursor.close()
    return [dict(zip(JOIN_ROW_COLUMNS, row)) for row in raw_rows]


def _num(value) -> float:
    return 0.0 if value is None else float(value)


class LayerAmounts(BaseModel):
    """12 monthly cells + the stored yearly total, common to all 3 layers."""

    m01: float = 0.0
    m02: float = 0.0
    m03: float = 0.0
    m04: float = 0.0
    m05: float = 0.0
    m06: float = 0.0
    m07: float = 0.0
    m08: float = 0.0
    m09: float = 0.0
    m10: float = 0.0
    m11: float = 0.0
    m12: float = 0.0
    total_year: float = 0.0


class SapLayer(LayerAmounts):
    """🟢 SAP · ใช้จริง — read-only, auto from the DW, never entered."""


class BoardLayer(LayerAmounts):
    """🔵 Approved · งบอนุมัติ — read-only reference, current year."""

    gl_name: str | None = None
    gl_group: str | None = None
    c_level: str | None = None
    division: str | None = None
    department: str | None = None


class PendingLayer(LayerAmounts):
    """⚫ Pending · งบรออนุมัติ — the editable planning-year layer. Starts
    blank (all defaults) when no `pending_budget` row exists yet.

    No `status` field — `budget.pending_budget` has no status column
    (status lives on `budget.approval_status`, owned by A6)."""

    template: str | None = None
    remark: str | None = None
    gl_name: str | None = None
    gl_group: str | None = None
    c_level: str | None = None
    division: str | None = None
    department: str | None = None


class BudgetRow(BaseModel):
    """One visible `(cost_center, gl_account)` row of the main grid. All 3
    layers are always present (zero-filled when absent) so the frontend never
    has to null-check a layer object — only the amounts/metadata are blank."""

    cost_center: str
    gl_account: str
    sap: SapLayer = SapLayer()
    board: BoardLayer = BoardLayer()
    pending: PendingLayer = PendingLayer()
    editable: bool = False


def _sap_layer(months: dict[str, float] | None) -> SapLayer:
    if months is None:
        return SapLayer()
    return SapLayer(**{col: months.get(col, 0.0) for col in MONTH_COLUMNS}, total_year=months.get("total_year", 0.0))


def _board_layer(jr: dict) -> BoardLayer:
    if jr.get("board_cost_center") is None:
        return BoardLayer()
    return BoardLayer(
        **{m: _num(jr.get(f"board_{m}")) for m in MONTH_COLUMNS},
        total_year=_num(jr.get("board_total_year")),
        **{c: jr.get(f"board_{c}") for c in _BOARD_COLUMNS},
    )


def _pending_layer(jr: dict) -> PendingLayer:
    if jr.get("pending_cost_center") is None:
        return PendingLayer()
    return PendingLayer(
        **{m: _num(jr.get(f"pending_{m}")) for m in MONTH_COLUMNS},
        total_year=_num(jr.get("pending_total_year")),
        **{c: jr.get(f"pending_{c}") for c in _PENDING_META_COLUMNS},
    )


def merge_budget_rows(
    join_rows: list[dict],
    sap_actuals: dict[tuple[str, str], dict[str, float]],
    scope: Scope,
    admin_view_enabled: bool = False,
    cost_center_filter: str | None = None,
    department_filter: str | None = None,
) -> list[BudgetRow]:
    """Pure merge: board+pending join rows + SAP dict + RLS scope -> the final
    visible/editable row list. No I/O — fully unit-testable.

    RLS (ADR-0019, honoring A3's `admin_view_enabled` hook): a non-admin (or
    an admin with the toggle off) only sees rows whose cost_center is in their
    `see_cost_centers`; `admin_view_enabled=True` bypasses the CC restriction
    ONLY when `scope.is_admin` is also true (a non-admin can never widen —
    A3's own scope resolution already refuses to self-elevate, and this merge
    re-checks `scope.is_admin` again as defense-in-depth). `editable` is true
    for a Fill-scope cost_center, or for every row when the admin-wide bypass
    is active (admin edits any Pending freely, ADR-0012).
    """
    admin_wide = scope.is_admin and admin_view_enabled
    visible_ccs = None if admin_wide else set(scope.see_cost_centers)
    fill_ccs = set(scope.fill_cost_centers)

    remaining_sap = dict(sap_actuals)
    merged: dict[tuple[str, str], BudgetRow] = {}

    for jr in join_rows:
        key = (jr["cost_center"], jr["gl_account"])
        sap_months = remaining_sap.pop(key, None)
        merged[key] = BudgetRow(
            cost_center=key[0],
            gl_account=key[1],
            sap=_sap_layer(sap_months),
            board=_board_layer(jr),
            pending=_pending_layer(jr),
        )

    for key, months in remaining_sap.items():
        merged[key] = BudgetRow(cost_center=key[0], gl_account=key[1], sap=_sap_layer(months))

    result: list[BudgetRow] = []
    for (cc, gl), row in merged.items():
        if visible_ccs is not None and cc not in visible_ccs:
            continue
        if cost_center_filter is not None and cc != cost_center_filter:
            continue
        if department_filter is not None:
            dept = row.pending.department or row.board.department
            if dept != department_filter:
                continue
        row.editable = admin_wide or cc in fill_ccs
        result.append(row)

    return sorted(result, key=lambda r: (r.cost_center, r.gl_account))


def get_budget_grid(
    fabric_conn: pyodbc.Connection,
    gold_conn: pyodbc.Connection,
    planning_year: int,
    scope: Scope,
    admin_view_enabled: bool = False,
    cost_center_filter: str | None = None,
    department_filter: str | None = None,
) -> list[BudgetRow]:
    """Orchestrator: board_year = planning_year - 1 (SAP + Approved both use
    the standing/current year; only Pending uses the planning year itself,
    per the data-model spec §1c). Propagates `SapActualsFetchError` as-is —
    the router turns it into a loud 5xx, never a silent-empty layer.

    Resolves the SQL-side CC filter for `fetch_board_pending_rows` here: a
    non-admin (or an admin without the toggle) ALWAYS gets their own
    `see_cost_centers` list pushed into the SQL — this function is the only
    place allowed to pass `cost_centers=None` (admin-wide bypass), and only
    when `scope.is_admin AND admin_view_enabled` are both true."""
    board_year = planning_year - 1
    admin_wide = scope.is_admin and admin_view_enabled
    see_cost_centers_filter = None if admin_wide else list(scope.see_cost_centers)

    join_rows = fetch_board_pending_rows(
        fabric_conn, board_year=board_year, pending_year=planning_year, cost_centers=see_cost_centers_filter
    )
    sap_actuals = fetch_sap_actuals(gold_conn, fiscal_year=board_year)

    return merge_budget_rows(
        join_rows,
        sap_actuals,
        scope,
        admin_view_enabled=admin_view_enabled,
        cost_center_filter=cost_center_filter,
        department_filter=department_filter,
    )
